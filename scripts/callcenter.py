#!/usr/bin/env python3
"""E1: "call center" mode. Edit plain files in a folder; WhatsApp answers calls as your call center.

  python3 scripts/callcenter.py start  --context callcenter     # background auto_answer.py --context callcenter
  python3 scripts/callcenter.py start  --context callcenter --dry-run   # validate + print instructions, no Chrome
  python3 scripts/callcenter.py status
  python3 scripts/callcenter.py stop
  python3 scripts/callcenter.py agent  --context callcenter.example --in-device X.monitor --out-device Y \\
                                       --transcript t.txt --seconds 120    # standalone agent (E0 harness)
  python3 scripts/callcenter.py summarize <call folder> --context callcenter

Context folder: see context.py (instructions.md, config.yaml, knowledge/). It is re-read on every call, so edits
take effect on the next call. After each call auto_answer writes scripts/calls/<ts>/summary.md.
"""
import argparse, asyncio, json, os, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from context import build_instructions, load_context, make_agent  # noqa: E402

STATE = HERE / "callcenter_state.json"   # git-ignored
LOG = HERE / "callcenter.log"            # git-ignored (*.log)
CALLS = HERE / "calls"


def alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def read_state() -> dict:
    return json.loads(STATE.read_text()) if STATE.exists() else {}


def other_watchers(exclude=None) -> list[str]:
    """auto_answer.py processes we did not start (e.g. the live one). Read-only check, never touched."""
    out = subprocess.run(["pgrep", "-af", "auto_answer.py"], capture_output=True, text=True).stdout
    return [l for l in out.splitlines() if l.split()[0] != str(exclude) and "pgrep" not in l]


def show_context(ctx: dict, verbose: bool):
    c = ctx["config"]
    print(f"context  : {ctx['path']}")
    print(f"owner    : {c['owner_name']} · voice {c['voice']} · language {c['language']} · "
          f"max {c['max_call_seconds']} s · answer_only {c['answer_only'] or 'everyone'}")
    print(f"knowledge: {len(ctx['knowledge'])} file(s): " +
          ", ".join(f"{k['name']} ({len(k['text'])} chars)" for k in ctx["knowledge"]))
    ins = build_instructions(ctx)
    for w in ctx["warnings"]:
        print(f"WARNING  : {w}")
    print(f"instructions: {len(ins)} chars")
    if verbose:
        print("-" * 70 + "\n" + ins + "\n" + "-" * 70)


def cmd_start(a):
    ctx = load_context(a.context)  # fail fast on a bad folder
    show_context(ctx, a.dry_run or a.check)
    st = read_state()
    if alive(st.get("pid")):
        raise SystemExit(f"already running (pid {st['pid']}, context {st['context']}); run stop first")
    if a.check:
        print("check: context OK")
        return
    others = other_watchers()
    if a.dry_run:  # stand-in watcher: no Chrome, no audio; reloads the context like a call would
        cmd = [sys.executable, "-u", str(HERE / "callcenter.py"), "_standin", "--context", ctx["path"]]
    elif others and not a.force:
        raise SystemExit("another auto_answer.py is already watching WhatsApp (two watchers would both click Accept):\n  "
                         + "\n  ".join(others) + "\nstop it yourself first, or pass --force")
    else:
        cmd = [sys.executable, "-u", str(HERE / "auto_answer.py"), "--context", ctx["path"]]
    if not a.dry_run and ctx["config"].get("greeting"):
        cmd += ["--greeting", ctx["config"]["greeting"]]  # fallback WAV if the realtime agent fails to start
    if a.once and not a.dry_run:
        cmd.append("--once")
    with open(LOG, "a") as lf:
        lf.write(f"\n=== callcenter start {time.strftime('%F %T')} {' '.join(cmd)}\n")
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, cwd=HERE.parent)
    STATE.write_text(json.dumps({"pid": p.pid, "context": ctx["path"], "started": time.time(), "cmd": cmd,
                                 "dry_run": a.dry_run}))
    time.sleep(3)
    if p.poll() is not None:
        STATE.unlink(missing_ok=True)
        raise SystemExit(f"auto_answer exited with {p.returncode}; see {LOG}")
    print(f"started pid {p.pid}; log {LOG}")


def cmd_stop(a):
    st = read_state()
    pid = st.get("pid")
    if not alive(pid):
        print("not running")
        STATE.unlink(missing_ok=True)
        return
    os.killpg(pid, signal.SIGINT)  # only the process group we started
    for _ in range(50):
        if not alive(pid):
            break
        time.sleep(0.2)
    else:
        os.killpg(pid, signal.SIGKILL)
    STATE.unlink(missing_ok=True)
    print(f"stopped pid {pid}")


def cmd_status(a):
    st = read_state()
    if alive(st.get("pid")):
        print(("DRY-RUN " if st.get("dry_run") else "RUNNING ") + f" pid {st['pid']} since {time.strftime('%F %T', time.localtime(st['started']))} "
              f"({(time.time() - st['started']) / 60:.0f} min)")
        try:
            show_context(load_context(st["context"]), False)
        except Exception as e:
            print(f"context  : {st['context']} - ERROR {e}")
    else:
        print("STOPPED" + (" (stale state file removed)" if st else ""))
        STATE.unlink(missing_ok=True)
    others = other_watchers(st.get("pid"))
    if others:
        print("other auto_answer.py processes (not managed by callcenter):\n  " + "\n  ".join(others))
    calls = sorted(CALLS.glob("*/")) if CALLS.exists() else []
    summ = [c for c in calls if (c / "summary.md").exists()]
    print(f"calls    : {len(calls)} in {CALLS} ({len(summ)} with summary.md)")
    if summ:
        print(f"last summary: {summ[-1] / 'summary.md'}")
    if LOG.exists():
        tail = LOG.read_text(errors="replace").splitlines()[-5:]
        print("log tail :\n  " + "\n  ".join(tail))


def cmd_agent(a):
    ctx = load_context(a.context)
    ag = make_agent(ctx, a.caller, transcript=Path(a.transcript) if a.transcript else None,
                    in_device=a.in_device, out_device=a.out_device)
    print(f"agent from {ctx['path']}: {len(ag.instructions)} chars of instructions, voice {ctx['config']['voice']}",
          flush=True)
    secs = min(a.seconds, float(ctx["config"].get("max_call_seconds") or a.seconds))
    asyncio.run(ag.run(secs))


def cmd_standin(a):
    """Dry-run stand-in for auto_answer.py: every 5 s reload the context as if a call came in, log what changed."""
    last = None
    while True:
        ctx = load_context(a.context)
        ins = build_instructions(ctx)
        sig = ("\n".join(l for l in ins.splitlines() if not l.startswith("Current local date")),
               json.dumps(ctx["config"], sort_keys=True))
        if sig != last:
            print(time.strftime("%H:%M:%S"), f"standin: context (re)loaded, {len(ins)} chars, "
                  f"{len(ctx['knowledge'])} knowledge file(s)", flush=True)
            last = sig
        time.sleep(5)


def cmd_summarize(a):
    from call_summary import summarize
    out = summarize(a.folder, load_context(a.context) if a.context else None, a.caller)
    print(out.read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start")
    s.add_argument("--context", required=True)
    s.add_argument("--check", action="store_true", help="validate the context and print the instructions, then exit")
    s.add_argument("--dry-run", action="store_true",
                   help="print the instructions and run a stand-in watcher (no Chrome) so status/stop can be tested")
    s.add_argument("--once", action="store_true", help="stop after the first answered call")
    s.add_argument("--force", action="store_true", help="start even if another auto_answer.py is running")
    sub.add_parser("stop")
    sub.add_parser("status")
    g = sub.add_parser("agent", help="run the context-built agent standalone (for sim_call.py)")
    g.add_argument("--context", required=True)
    g.add_argument("--in-device", default="callout_sink.monitor")
    g.add_argument("--out-device", default="virtmic_sink")
    g.add_argument("--transcript")
    g.add_argument("--seconds", type=float, default=300)
    g.add_argument("--caller", help="pretend WhatsApp shows this caller name")
    t = sub.add_parser("_standin")
    t.add_argument("--context", required=True)
    m = sub.add_parser("summarize")
    m.add_argument("folder")
    m.add_argument("--context")
    m.add_argument("--caller")
    a = ap.parse_args()
    {"start": cmd_start, "stop": cmd_stop, "status": cmd_status, "agent": cmd_agent, "summarize": cmd_summarize,
     "_standin": cmd_standin}[a.cmd](a)


if __name__ == "__main__":
    main()
