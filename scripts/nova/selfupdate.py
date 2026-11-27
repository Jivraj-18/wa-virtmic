#!/usr/bin/env python3
"""Nova changes her own code (this repo) when a teammate asks for it in a meeting - safely.

The work worker (task.py) decides a task is about Nova herself, then follows .claude/skills/nova-self-update/SKILL.md:

    python scripts/nova/selfupdate.py start <task-id>          # git worktree ~/nova_work/<id>/wa-virtmic, branch nova-self/<id>
    python scripts/nova/selfupdate.py check <worktree>         # compile + test suite; must PASS before ship
    python scripts/nova/selfupdate.py ship <worktree> "<what changed, one line>"
                                                               # commit, push the branch, open a PR, queue the deploy
    python scripts/nova/selfupdate.py deploy [--wait]          # put pending changes live (ship starts this detached)
    python scripts/nova/selfupdate.py status                   # recent self-updates and their state
    python scripts/nova/selfupdate.py rollback                 # undo the last deploy (live checkout back to before it)

Never edits the live checkout directly: work happens in a worktree. Deploy waits until Nova is in no meeting and no
WhatsApp call is running, then merges into the live branch, re-runs the checks there, restarts only the services
whose files changed, health-checks them and rolls back on any failure. Changes to PROTECTED files (this script, the
skill, task.py with the requester allow-list and the worker's rules) are pushed as a PR for a human and never
auto-deployed. Log: ~/nova_work/selfupdate.log; state: ~/nova_work/selfupdate.json.
"""
import json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent                       # the LIVE checkout (services run from here)
WORK = Path(os.environ.get("NOVA_WORK", str(Path.home() / "nova_work")))
STATE = WORK / "selfupdate.json"
LOG = WORK / "selfupdate.log"
TOKEN = Path.home() / ".config" / "nova" / "github_token"
NOVA_STATE = Path.home() / ".cache" / "nova" / "state.json"
PY = sys.executable
GIT_ID = ["-c", "user.name=Nova (AI teammate)", "-c", "user.email=noreply@anthropic.com"]

PROTECTED = ("scripts/nova/selfupdate.py", ".claude/skills/nova-self-update/", "scripts/nova/task.py")
# Fast tests that need no live call/meeting (test_meet_browser needs the live audio devices + a Chrome: run by hand).
TESTS = ["tests/test_meet_addressing.py", "tests/test_handoff.py", "tests/test_hangup.py", "tests/test_diskguard.py",
         "tests/test_meet_suggester.py", "tests/test_nova_voice.py"]
# which service to restart when files under a prefix change (meeting code is loaded fresh for every meeting)
WA_FILES = ("scripts/auto_answer.py", "scripts/live_agent.py", "scripts/realtime_agent.py", "scripts/hangup.py",
            "scripts/claude_tool.py", "scripts/cc.py", "scripts/speak.py", "scripts/context.py", "scripts/gateway.py",
            "scripts/mic_apm.py", "scripts/post_call.py", "scripts/answer_daemon.sh", "scripts/audio_setup.sh")
NOVA_FILES = ("scripts/nova/calendar_watch.py", "scripts/nova/nova.py", "scripts/nova/autojoin.sh")


def log(*a):
    line = time.strftime("%F %T ") + " ".join(str(x) for x in a)
    print(line, flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")


def git(*args, cwd=REPO, check=True, env=None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, timeout=300)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {(r.stderr or r.stdout).strip()[:400]}")
    return r.stdout.strip()


def load() -> list:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return []


def save(items):
    WORK.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items[-50:], indent=1))
    tmp.replace(STATE)


def set_item(tid, **kw):
    items = load()
    for x in items:
        if x["id"] == tid:
            x.update(kw)
            break
    else:
        items.append(dict(id=tid, **kw))
    save(items)


def live_branch() -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD")


def gh_env() -> dict:
    env = dict(os.environ)
    if TOKEN.exists():
        env["GH_TOKEN"] = TOKEN.read_text().strip()
    return env


# ---------------------------------------------------------------- start
def cmd_start(tid: str):
    wt = WORK / tid / "wa-virtmic"
    br = f"nova-self/{tid}"
    if not wt.exists():
        wt.parent.mkdir(parents=True, exist_ok=True)
        git("worktree", "add", "-b", br, str(wt), "HEAD")
        log(f"start {tid}: worktree {wt} on {br} from {live_branch()}@{git('rev-parse', '--short', 'HEAD')}")
    set_item(tid, branch=br, path=str(wt), state="working", base=live_branch(), started=time.time())
    print(wt)


# ---------------------------------------------------------------- check
def changed_files(path: Path, base: str) -> list[str]:
    committed = git("diff", "--name-only", f"{base}...HEAD", cwd=path, check=False).splitlines()
    dirty = [l.split(maxsplit=1)[1] for l in git("status", "--porcelain", cwd=path).splitlines() if l.strip()]
    return sorted({f.split(" -> ")[-1] for f in committed + dirty if f})


def run_checks(path: Path, files: list[str] | None = None) -> tuple[bool, str]:
    out = []
    files = files if files is not None else [str(p.relative_to(path)) for p in path.rglob("*.py")
                                             if ".git" not in p.parts and "experiments" not in p.parts]
    for f in files:
        p = path / f
        if not p.exists():
            continue
        try:
            if f.endswith(".py"):
                compile(p.read_text(), str(p), "exec")
            elif f.endswith(".sh"):
                r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
                if r.returncode:
                    raise RuntimeError(r.stderr.strip())
        except Exception as e:
            out.append(f"FAIL compile {f}: {str(e)[:300]}")
    for t in TESTS:
        if not (path / t).exists():
            continue
        try:
            r = subprocess.run([PY, t], cwd=path, capture_output=True, text=True, timeout=300)
            ok = r.returncode == 0
            out.append(f"{'ok  ' if ok else 'FAIL'} {t}" + ("" if ok else ": " + (r.stdout + r.stderr)[-600:]))
        except subprocess.TimeoutExpired:
            out.append(f"FAIL {t}: timeout")
    # new tests the change added (tests/test_*.py not in the fixed list) run too
    for p in sorted((path / "tests").glob("test_*.py")):
        rel = str(p.relative_to(path))
        if rel not in TESTS and rel != "tests/test_meet_browser.py" and files and rel in files:
            r = subprocess.run([PY, rel], cwd=path, capture_output=True, text=True, timeout=300)
            out.append(f"{'ok  ' if r.returncode == 0 else 'FAIL'} {rel}" +
                       ("" if r.returncode == 0 else ": " + (r.stdout + r.stderr)[-600:]))
    ok = not any(l.startswith("FAIL") for l in out)
    return ok, "\n".join(out)


def cmd_check(path: str):
    p = Path(path).resolve()
    base = next((x.get("base") for x in load() if x.get("path") == str(p)), live_branch())
    files = changed_files(p, base)
    ok, report = run_checks(p, None)
    print(f"changed: {', '.join(files) or '(nothing)'}")
    print(report)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


# ---------------------------------------------------------------- ship
def cmd_ship(path: str, summary: str):
    p = Path(path).resolve()
    item = next((x for x in load() if x.get("path") == str(p)), None)
    if not item:
        print("not a self-update worktree (run `start` first)"); return 2
    tid, base = item["id"], item["base"]
    files = changed_files(p, base)
    if not files:
        print("nothing changed - nothing to ship"); return 2
    ok, report = run_checks(p, None)
    if not ok:
        print(report + "\nFAIL - fix the failures before shipping"); return 1
    if git("status", "--porcelain", cwd=p):
        git("add", "-A", cwd=p)
        git(*GIT_ID, "commit", "-m", f"Nova self-update: {summary}\n\nRequested in a meeting; task {tid}.", cwd=p)
    protected = [f for f in files if f.startswith(PROTECTED)]
    env = gh_env()
    pushed, pr = False, ""
    try:   # gh as the git credential helper (token from ~/.config/nova/github_token, never printed)
        git("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential", "push", "-u", "origin",
            item["branch"], cwd=p, env=env)
        pushed = True
        body = (f"{summary}\n\nNova changed her own code (task {tid}).\nFiles: {', '.join(files)}\n\nChecks:\n{report}\n\n"
                + ("PROTECTED files changed - needs a human review; NOT auto-deployed."
                   if protected else "Auto-deploys when Nova is idle (no meeting, no WhatsApp call)."))
        r = subprocess.run(["gh", "pr", "create", "--base", base, "--head", item["branch"], "--title",
                            f"Nova self-update: {summary}"[:120], "--body", body],
                           cwd=p, capture_output=True, text=True, env=env, timeout=120)
        pr = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ""
    except Exception as e:
        log(f"ship {tid}: push/PR failed: {e}")
    state = "needs_review" if protected else "pending"
    set_item(tid, state=state, summary=summary, files=files, pr=pr, pushed=pushed, shipped=time.time())
    log(f"ship {tid}: {state} files={files} pr={pr or '-'}")
    if not protected:
        subprocess.Popen([PY, str(Path(__file__).resolve()), "deploy", "--wait"], cwd=REPO, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    print(json.dumps({"state": state, "pr": pr, "files": files, "protected": protected,
                      "deploy": "waits until Nova is idle, then goes live (auto rollback on failure)"
                      if not protected else "a human must review and merge the PR"}))
    return 0


# ---------------------------------------------------------------- deploy
def busy() -> str:
    """Why now is a bad time to restart things ('' = idle)."""
    try:
        st = json.loads(NOVA_STATE.read_text())
        if st.get("phase") in ("spawning", "joining", "lobby", "in_meeting"):
            pid = st.get("pid")
            if pid and Path(f"/proc/{pid}").exists():
                return "Nova is in a meeting"
    except Exception:
        pass
    r = subprocess.run(["pgrep", "-f", "parecord --device=virtmic"], capture_output=True, text=True)
    if r.stdout.strip():
        return "a WhatsApp call is running"
    return ""


def restart_services(files: list[str]) -> list[str]:
    done = []
    if any(f.startswith(WA_FILES) for f in files):
        pidf = Path.home() / ".cache/wa-virtmic/auto_answer.pid"
        if pidf.exists():
            subprocess.run(["kill", pidf.read_text().strip()], capture_output=True)
            done.append("WhatsApp answerer")
    if "scripts/handoff.py" in files or "scripts/handoff.html" in files:
        pidf = Path.home() / ".cache/wa-virtmic/handoff.pid"
        if pidf.exists():
            subprocess.run(["kill", pidf.read_text().strip()], capture_output=True)
            done.append("handoff server")
    if any(f.startswith(NOVA_FILES) for f in files):
        subprocess.run(["bash", "scripts/nova/autojoin.sh", "stop"], cwd=REPO, capture_output=True, timeout=60)
        subprocess.Popen(["bash", "scripts/nova/autojoin.sh", "start"], cwd=REPO, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        done.append("autojoin")
    return done


def healthy(restarted: list[str]) -> tuple[bool, str]:
    if not restarted:
        return True, "nothing restarted"
    deadline = time.time() + 120
    msg = ""
    while time.time() < deadline:
        time.sleep(10)
        msg = ""
        if "WhatsApp answerer" in restarted or "handoff server" in restarted:
            s = subprocess.run(["bash", "scripts/answer_daemon.sh", "status"], cwd=REPO, capture_output=True,
                               text=True, timeout=60).stdout
            if "auto_answer: running" not in s or "handoff: running" not in s:
                msg += "answerer/handoff not running; "
        if "autojoin" in restarted:
            s = subprocess.run(["bash", "scripts/nova/autojoin.sh", "status"], cwd=REPO, capture_output=True,
                               text=True, timeout=60).stdout
            if "watcher: running" not in s:
                msg += "autojoin watcher not running; "
        if not msg:
            return True, "services up"
    return False, msg


def deploy_one(x) -> bool:
    tid, br = x["id"], x["branch"]
    if git("status", "--porcelain", "--untracked-files=no"):
        set_item(tid, state="blocked", why="the live checkout has uncommitted changes (a human is editing it)")
        log(f"deploy {tid}: blocked - live checkout has uncommitted changes")
        return False
    old = git("rev-parse", "HEAD")
    r = subprocess.run(["git", *GIT_ID, "merge", "--no-edit", br], cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        git("merge", "--abort", check=False)
        set_item(tid, state="blocked", why=f"merge conflict with the live branch: {r.stdout[-300:]}")
        log(f"deploy {tid}: merge conflict - left as PR")
        return False
    files = git("diff", "--name-only", old, "HEAD").splitlines()
    ok, report = run_checks(REPO, None)
    if ok:
        restarted = restart_services(files)
        ok, report = healthy(restarted)
    if not ok:
        git("reset", "--hard", old)
        restart_services(files)
        set_item(tid, state="rolled_back", why=report[-600:], deployed_at=time.time())
        log(f"deploy {tid}: FAILED, rolled back to {old[:8]}: {report[-300:]}")
        return False
    set_item(tid, state="deployed", deployed_at=time.time(), prev=old, head=git("rev-parse", "HEAD"))
    log(f"deploy {tid}: live ({x.get('summary')}); restarted: {', '.join(restarted) or 'nothing'}")
    try:   # keep GitHub's live branch in step (best effort)
        git("-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential", "push", "origin",
            live_branch(), env=gh_env())
    except Exception as e:
        log(f"deploy {tid}: push of {live_branch()} failed: {e}")
    return True


def cmd_deploy(wait: bool):
    lock = WORK / "selfupdate.deploy.pid"
    if lock.exists() and Path(f"/proc/{lock.read_text().strip()}").exists():
        print("a deploy is already running"); return 0
    lock.write_text(str(os.getpid()))
    try:
        t0 = time.time()
        while True:
            pending = [x for x in load() if x.get("state") == "pending"]
            if not pending:
                return 0
            why = busy()
            if not why:
                for x in pending:
                    deploy_one(x)
                return 0
            if not wait or time.time() - t0 > 24 * 3600:
                print(f"not now: {why}"); return 0
            time.sleep(60)
    finally:
        lock.unlink(missing_ok=True)


def cmd_rollback():
    done = [x for x in load() if x.get("state") == "deployed"]
    if not done:
        print("nothing deployed to roll back"); return 1
    x = done[-1]
    if git("rev-parse", "HEAD") != x.get("head"):
        print(f"live HEAD moved since {x['id']} was deployed - revert by hand (git revert)"); return 1
    files = git("diff", "--name-only", x["prev"], "HEAD").splitlines()
    git("reset", "--hard", x["prev"])
    restart_services(files)
    set_item(x["id"], state="rolled_back", why="rolled back on request")
    log(f"rollback {x['id']}: live back at {x['prev'][:8]}")
    print(f"rolled back {x['id']} ({x.get('summary')})")
    return 0


def cmd_status(n=10):
    for x in load()[-n:]:
        print(f"{x['id']}  {x.get('state', '?'):12s} {x.get('summary', '')[:70]}  {x.get('pr', '')}"
              + (f"  ({x['why'][:120]})" if x.get("why") else ""))
    return 0


def recent_text(n=5) -> str:
    """For the worker's prompt: Nova's latest changes to herself."""
    rows = load()[-n:]
    return "\n".join(f"- {x['id'][:13]} [{x.get('state')}] {x.get('summary', '')[:120]}" for x in rows) or "(none yet)"


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__); return 2
    c = a[0]
    if c == "start" and len(a) == 2:
        return cmd_start(a[1])
    if c == "check" and len(a) == 2:
        return cmd_check(a[1])
    if c == "ship" and len(a) == 3:
        return cmd_ship(a[1], a[2])
    if c == "deploy":
        return cmd_deploy("--wait" in a)
    if c == "rollback":
        return cmd_rollback()
    if c == "status":
        return cmd_status()
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
