"""Nova - the AI teammate that joins Google Meet calls as the team's meeting secretary. One command per task.

    python scripts/nova/nova.py join <meet-url>    # join now (detached); prints the phase: in_meeting / lobby / failed
    python scripts/nova/nova.py leave              # leave the current meeting (notes start in the background)
    python scripts/nova/nova.py status             # in a meeting? who's there? mic/cam? lobby? autojoin service?
    python scripts/nova/nova.py probe [--text]     # visible buttons (+ page text) of the Meet tab - when Meet's DOM changes
    python scripts/nova/nova.py login-check        # is the Google session in Nova's Chrome alive?
    python scripts/nova/nova.py upcoming [--hours 24]   # next meetings with Meet links (Calendar via gws)
    python scripts/nova/nova.py autojoin [--once]  # watch Calendar, join ~1 min before start (service: autojoin.sh)
    python scripts/nova/nova.py notes [latest|<dir>] [--send]   # meeting notes (notes.py)
    python scripts/nova/nova.py announce add "<text>" --title "<words in the title>" --wait-for "<person>"
                                                   # raises hand once that person is there, speaks when given the floor
    python scripts/nova/nova.py work list|add "<task>"|show <id>|cancel <id>   # Nova's work queue
    python scripts/nova/nova.py meetings           # past meetings (folders under ~/nova_meetings)
    python scripts/nova/nova.py chrome up|down     # start / gracefully stop Nova's Chrome (CDP 9333, display :97)

Everything is text (innerText / aria-labels); never screenshots. Nova's Chrome: CDP 9333, profile
~/.config/maya-chrome-profile, audio devices maya_*. The WhatsApp answerer (CDP 9222, virtmic*) is never touched.
"""
import argparse, asyncio, json, os, re, signal, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
os.environ.setdefault("MAYA_NAME", "Nova")

from meet import browser as B  # noqa: E402

JOIN_LOG = B.STATE_DIR / "join.log"
AUTOJOIN_HEARTBEAT = B.STATE_DIR / "autojoin.heartbeat"
MEET_URL = re.compile(r"https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}")


def ago(t):
    if not t:
        return "-"
    d = time.time() - t
    return f"{d:.0f}s ago" if d < 120 else f"{d / 60:.0f}m ago" if d < 7200 else f"{d / 3600:.1f}h ago"


def pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def busy() -> dict:
    """The running meeting session, if any (state file + live pid)."""
    st = B.read_state()
    if st.get("pid") and pid_alive(st["pid"]) and st.get("phase") not in ("left", "failed"):
        return st
    return {}


def run_async(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- join / leave
def start_join(url, until=None, event=None, title=None, wait=90, extra=()) -> int:
    m = MEET_URL.search(url or "")
    if os.environ.get("NOVA_SIM") == "1" and (url or "").startswith("http://127.0.0.1:"):
        m = re.match(r".*", url)   # local simulator page (tests/nova_sim/run_sim.py)
    if not m:
        print(f"not a Meet link: {url!r} (expected https://meet.google.com/abc-defg-hij)")
        return 2
    url = m.group(0)
    cur = busy()
    if cur:
        print(f"ALREADY in a meeting session: {cur.get('url')} phase={cur.get('phase')} (pid {cur.get('pid')}). "
              "Run `nova leave` first.")
        return 1
    B.STATE_DIR.mkdir(parents=True, exist_ok=True)
    B.write_state(phase="spawning", url=url, pid=None, error=None)
    cmd = [sys.executable, "-u", "-m", "scripts.meet.maya", "join", url]
    if until:
        cmd += ["--until", str(until)]
    if event:
        cmd += ["--event", event]
    if title:
        cmd += ["--title", title]
    cmd += list(extra)
    # cap the log: keep the previous one, start fresh
    if JOIN_LOG.exists() and JOIN_LOG.stat().st_size > 2_000_000:
        JOIN_LOG.replace(JOIN_LOG.with_suffix(".log.old"))
    with open(JOIN_LOG, "ab") as f:
        f.write(f"\n===== {time.strftime('%F %T')} join {url}\n".encode())
        p = subprocess.Popen(cmd, cwd=REPO, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             start_new_session=True, env=dict(os.environ, PYTHONUNBUFFERED="1"))
    print(f"joining {url} (pid {p.pid}, log {JOIN_LOG})")
    t0, last = time.time(), None
    while time.time() - t0 < wait:
        st = B.read_state()
        ph = st.get("phase")
        if ph != last:
            print(f"  {time.time() - t0:4.0f}s phase={ph}")
            last = ph
        if ph == "in_meeting":
            print("JOINED. Nova stays quiet unless addressed by name. `nova status` shows who is there.")
            return 0
        if ph == "lobby":
            print("IN LOBBY: the host must admit Nova (she waits up to 10 min).")
            return 0
        if ph == "failed" or p.poll() is not None:
            print(f"FAILED: {st.get('error') or 'process exited'}\n--- last log lines ---")
            print("\n".join(JOIN_LOG.read_text(errors="replace").splitlines()[-15:]))
            return 1
        time.sleep(1)
    print("still joining after %ds - check `nova status` / %s" % (wait, JOIN_LOG))
    return 0


def cmd_join(a):
    extra = ["--suggest-interval", str(a.tips)] if a.tips else []
    if a.alone_leave:
        extra += ["--alone-leave", str(a.alone_leave)]
    return start_join(a.url, until=a.until and time.time() + a.until * 60, wait=a.wait, title=a.title, extra=extra)


def cmd_leave(a):
    cur = busy()
    if cur:
        B.LEAVE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        B.LEAVE_FLAG.write_text(str(time.time()))
        print(f"asked the meeting session (pid {cur['pid']}) to leave ...")
        for _ in range(40):
            if not busy():
                st = B.read_state()
                print(f"LEFT ({st.get('left_why')}). Notes: {st.get('run_dir')}/notes.md (background, ~1-2 min)")
                return 0
            time.sleep(1)
        print("session did not exit in 40 s - sending SIGTERM")
        os.kill(int(cur["pid"]), signal.SIGTERM)
    if B.cdp_up():  # no session process (or it hung): click Leave directly
        async def go():
            pw, br, ctx = await B.connect()
            for p in ctx.pages:
                if B.is_meet_url(p.url):
                    await B.leave_meet(p)
                    await p.wait_for_timeout(1000)
                    await p.goto("about:blank")
                    print("clicked Leave on", p.url)
            await pw.stop()
        run_async(go())
    print("not in a meeting")
    return 0


# ---------------------------------------------------------------- status / probe
def cmd_status(a):
    st = B.read_state()
    cur = busy()
    print(f"Chrome (CDP {B.PORT}): {'up' if B.cdp_up() else 'DOWN'}   display {B.DISPLAY}")
    if cur:
        print(f"MEETING: phase={cur.get('phase')} url={cur.get('url')} title={cur.get('title') or '-'} "
              f"joined {ago(cur.get('joined_at'))} pid={cur.get('pid')}")
        if cur.get("until"):
            print(f"  leaves at {time.strftime('%H:%M', time.localtime(cur['until']))} at the latest")
    else:
        print(f"MEETING: none   (last: {st.get('phase', '-')} {st.get('url', '')} {st.get('left_why', '') or ''} "
              f"{ago(st.get('left_at') or st.get('updated'))})")
        if st.get("error"):
            print(f"  last error: {st['error']}")
    if B.cdp_up():
        async def go():
            pw, br, ctx = await B.connect()
            pages = [p for p in ctx.pages if B.is_meet_url(p.url)]
            for p in pages:
                s = await B.meet_state(p)
                print(f"  page {s.get('url')}: in_call={s.get('in_call')} lobby={s.get('lobby')} mic={s.get('mic')} "
                      f"cam={s.get('cam')} people={s.get('count')} tiles={s.get('tiles')} denied={s.get('denied')}")
                if s.get("names"):
                    print("  names:", ", ".join(s["names"]))
            if not pages:
                print("  no Meet tab open")
            await pw.stop()
        run_async(go())
    plan = B.STATE_DIR / "plan.txt"
    if plan.exists():
        print(plan.read_text().rstrip())
    hb = AUTOJOIN_HEARTBEAT
    if hb.exists():
        print(f"AUTOJOIN: heartbeat {ago(hb.stat().st_mtime)}  {hb.read_text().strip()[:200]}")
    else:
        print("AUTOJOIN: not running (bash scripts/nova/autojoin.sh start)")
    lt = Path.home() / "nova_live_transcript.txt"
    if cur and lt.exists():
        lines = lt.read_text(errors="replace").splitlines()[-a.lines:]
        if lines:
            print("--- last lines heard ---\n" + "\n".join(lines))
    return 0


def cmd_probe(a):
    if not B.cdp_up():
        print("Nova's Chrome is not running")
        return 1

    async def go():
        pw, br, ctx = await B.connect()
        print("tabs:", [p.url[:80] for p in ctx.pages])
        page = await B.meet_page(ctx)
        print(json.dumps(await B.meet_state(page), ensure_ascii=False))
        print("--- visible buttons/inputs: tag | aria-label | placeholder | text ---")
        for ln in await B.probe(page):
            print(ln)
        if a.text:
            print("--- page text ---")
            print(await B.page_text(page, 4000))
        await pw.stop()
    run_async(go())


def cmd_login_check(a):
    """Cookies say whether a Google session exists; --deep opens myaccount in a NEW tab to confirm (closed after)."""
    if not B.cdp_up():
        B.devices_up()
        B.launch_chrome("about:blank")

    async def go():
        pw, br, ctx = await B.connect()
        cookies = await ctx.cookies(["https://accounts.google.com", "https://meet.google.com"])
        names = {c["name"] for c in cookies}
        ok = bool(names & {"SID", "__Secure-1PSID", "__Secure-3PSID"})
        exp = [c.get("expires", -1) for c in cookies if c["name"] in ("__Secure-1PSID", "SID")]
        print(f"google session cookies: {'PRESENT' if ok else 'MISSING'}"
              + (f" (expire {time.strftime('%F', time.localtime(max(exp)))})" if exp and max(exp) > 0 else ""))
        if a.deep or not ok:
            p = await ctx.new_page()
            await p.goto("https://myaccount.google.com/", wait_until="load", timeout=30000)
            await p.wait_for_timeout(1500)
            ok = p.url.startswith("https://myaccount.google.com")
            acct = await p.evaluate("""() => { const b = [...document.querySelectorAll('[aria-label^="Google Account:"]')][0];
                return b ? b.getAttribute('aria-label') : ''; }""")
            em = re.search(r"\(([^)]+@[^)]+)\)", acct or "")
            masked = re.sub(r"^(.).*?(@.*)$", r"\1***\2", em.group(1)) if em else "?"
            print(f"myaccount: {'SIGNED IN as ' + masked if ok else 'NOT signed in -> ' + p.url[:80]}")
            await p.close()
        await pw.stop()
        print("RESULT:", "LOGGED IN" if ok else
              "LOGGED OUT - re-login: python scripts/nova/google_login.py start <email>  (password on stdin; see nova-meet skill)")
        return 0 if ok else 1
    return run_async(go())


def cmd_chrome(a):
    if a.action == "up":
        B.devices_up()
        print("Chrome:", "started" if B.launch_chrome("about:blank") else "already running", f"(CDP {B.PORT}, {B.DISPLAY})")
        return 0
    if busy():
        print("in a meeting - `nova leave` first")
        return 1
    pids = sorted(B.chrome_pids())
    roots = [p for p in pids if f"--remote-debugging-port={B.PORT}".encode() in Path(f"/proc/{p}/cmdline").read_bytes()]
    for p in roots[:1]:
        os.kill(p, signal.SIGTERM)  # graceful (never -9: it can corrupt the profile / session)
    print(f"sent SIGTERM to Nova's Chrome {roots[:1]}")
    return 0


def cmd_meetings(a):
    for d in sorted(B.MEETINGS.glob("2*"))[-a.n:]:
        meta = {}
        try:
            meta = json.loads((d / "meta.json").read_text())
        except Exception:
            pass
        lines = len((d / "who_said_what.txt").read_text(errors="replace").splitlines()) if (d / "who_said_what.txt").exists() else 0
        notes = "notes" if (d / "notes.md").exists() else "-"
        print(f"{d.name}  {meta.get('title') or meta.get('url', '?')}  lines={lines}  {notes}")


# ---------------------------------------------------------------- calendar
def cmd_upcoming(a):
    import calendar_watch as C
    try:
        evs = C.upcoming(hours=a.hours)
    except Exception as e:
        print(f"calendar error: {e}")
        return 1
    if not evs:
        print(f"no meetings with a Meet link in the next {a.hours} h")
    for e in evs:
        print(C.fmt(e))
    return 0


def cmd_autojoin(a):
    import calendar_watch as C
    return C.loop(once=a.once, start_join=start_join, busy=busy)


def render_announcement(aid):
    """Pre-record an announcement in Nova's voice so it plays instantly when she gets the floor."""
    import speak
    items = B.load_announcements()
    for x in items:
        if x.get("id") == aid:
            out = B.ANNOUNCE.parent / "announce_audio" / f"{aid}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            try:
                speak.synth_wav(x["text"], str(out), engine="gateway", voice=os.environ.get("REALTIME_VOICE", "marin"))
                x["audio"] = str(out)
                print(f"recorded {out.name} in Nova's voice")
                if x.get("if_spoken_text"):
                    out2 = out.with_name(f"{aid}_if_spoken.wav")
                    speak.synth_wav(x["if_spoken_text"], str(out2), engine="gateway",
                                    voice=os.environ.get("REALTIME_VOICE", "marin"))
                    x["if_spoken_audio"] = str(out2)
            except Exception as e:
                print(f"voice recording failed ({e}); Nova will speak it live instead")
    B.save_announcements(items)


def cmd_announce(a):
    items = B.load_announcements()
    if a.action == "add":
        aid = time.strftime("%Y%m%d%H%M%S")
        items.append({"id": aid, "title": a.title, "url": a.url, "text": a.text, "after_s": a.after,
                      "min_others": a.min_others, "quiet_s": 4, "chat": not a.no_chat, "added": time.time(),
                      "wait_for": a.wait_for, "raise_hand": not a.no_hand,
                      **({"if_spoken_text": a.if_spoken} if a.if_spoken is not None else {})})
        B.save_announcements(items)
        print(f"queued {aid}: Nova will say it in the next meeting matching title={a.title!r} url={a.url!r}")
        render_announcement(aid)
    elif a.action == "render":   # (re)record the voice of pending announcements
        for x in items:
            if not x.get("done_at"):
                render_announcement(x["id"])
    elif a.action == "rm":
        B.save_announcements([x for x in items if x.get("id") != a.id])
        print("removed", a.id)
    else:
        for x in items:
            st = f"DONE {time.strftime('%F %H:%M', time.localtime(x['done_at']))} in {x.get('done_in')}" if x.get("done_at") else "pending"
            print(f"{x['id']}  [{st}]  title={x.get('title')!r} after {x.get('after_s')}s, >= {x.get('min_others')} others, "
                  f"waits for {x.get('wait_for') or 'anyone'}{', raises hand' if x.get('raise_hand', True) else ''}\n    {x['text']}")
        if not items:
            print("no announcements")


def cmd_work(a):
    """Nova's work queue (scripts/nova/task.py)."""
    args = [sys.executable, str(HERE / "task.py"), a.action] + a.rest
    if a.action == "add":
        args = [sys.executable, str(HERE / "task.py"), "add", "--task", " ".join(a.rest), "--requester", "owner (CLI)"]
    return subprocess.call(args)


def cmd_notes(a):
    cmd = [sys.executable, str(HERE / "notes.py"), "make", a.target] + (["--send"] if a.send else [])
    return subprocess.call(cmd)


def main():
    sys.path.insert(0, str(HERE))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("join"); j.add_argument("url")
    j.add_argument("--until", type=float, help="leave after N minutes at the latest")
    j.add_argument("--wait", type=float, default=90, help="seconds to wait for joined/lobby before returning")
    j.add_argument("--tips", type=float, default=0, help="post chat tips every N s (default off)")
    j.add_argument("--title", help="meeting title for the notes")
    j.add_argument("--alone-leave", type=float, help="leave after N s alone once others were there (default 90)")
    j.set_defaults(fn=cmd_join)
    sub.add_parser("leave").set_defaults(fn=cmd_leave)
    s = sub.add_parser("status"); s.add_argument("--lines", type=int, default=5); s.set_defaults(fn=cmd_status)
    p = sub.add_parser("probe"); p.add_argument("--text", action="store_true"); p.set_defaults(fn=cmd_probe)
    lc = sub.add_parser("login-check"); lc.add_argument("--deep", action="store_true"); lc.set_defaults(fn=cmd_login_check)
    u = sub.add_parser("upcoming"); u.add_argument("--hours", type=float, default=24); u.set_defaults(fn=cmd_upcoming)
    aj = sub.add_parser("autojoin"); aj.add_argument("--once", action="store_true"); aj.set_defaults(fn=cmd_autojoin)
    n = sub.add_parser("notes"); n.add_argument("target", nargs="?", default="latest")
    n.add_argument("--send", action="store_true"); n.set_defaults(fn=cmd_notes)
    an = sub.add_parser("announce", help="queue something Nova says once in a future meeting")
    an.add_argument("action", choices=["add", "list", "rm", "render"])
    an.add_argument("text", nargs="?"); an.add_argument("--title", help="meeting title contains (case-insensitive)")
    an.add_argument("--url"); an.add_argument("--id"); an.add_argument("--after", type=float, default=120,
                                                                        help="seconds after joining (default 120)")
    an.add_argument("--min-others", type=int, default=2); an.add_argument("--no-chat", action="store_true")
    an.add_argument("--wait-for", help="only when this person is in the call, and they must give Nova the floor")
    an.add_argument("--no-hand", action="store_true", help="speak when quiet instead of raising the hand first")
    an.add_argument("--if-spoken", help="say this instead if Nova already spoke in the meeting (e.g. she introduced "
                                        "herself live); \"\" = skip it then (live engine)")
    an.set_defaults(fn=cmd_announce)
    w = sub.add_parser("work", help="Nova's work queue: list | add <task> | show <id> | cancel <id> | worker")
    w.add_argument("action", choices=["list", "add", "show", "cancel", "worker"]); w.add_argument("rest", nargs="*")
    w.set_defaults(fn=cmd_work)
    m = sub.add_parser("meetings"); m.add_argument("-n", type=int, default=10); m.set_defaults(fn=cmd_meetings)
    c = sub.add_parser("chrome"); c.add_argument("action", choices=["up", "down"]); c.set_defaults(fn=cmd_chrome)
    a = ap.parse_args()
    sys.exit(a.fn(a) or 0)


if __name__ == "__main__":
    main()
