"""E4: Maya's own Chrome + PulseAudio devices + Google Meet page control (Playwright over CDP).

Isolation from the WhatsApp setup (never touched): its own profile dir (~/.config/maya-chrome-profile), its own CDP
port (9333, never 9222), and its own PulseAudio devices:
    maya_out       null sink    - Chrome's speaker (PULSE_SINK). Maya listens on maya_out.monitor
    maya_mic_sink  null sink    - Maya's voice is played here
    maya_mic       remap source of maya_mic_sink.monitor - Chrome's microphone (PULSE_SOURCE)
The default sink/source are never changed.

Meet DOM selectors (best effort, Nov 2026; several fallbacks each, borrowed in spirit from joinly's Meet controller).
Meet changes its DOM often; when something breaks, `python3 -m scripts.meet.maya probe` prints the visible buttons.
    guest name field   : input placeholder ~ /name/i  (only when not logged in)
    camera off         : button aria-label ~ /^turn off camera/i
    mic on             : button aria-label ~ /^turn on (microphone|mic)/i   (mic off: /^turn off (microphone|mic)/i)
    join               : button name ~ /^(join now|ask to join|join)$/i  (not "other ways to join")
    joined             : button aria-label ~ /^leave call/i ; lobby: text /asking to be let in|someone .* let you in/i
    chat open          : button aria-label ~ /^chat with everyone|^chat/i   (toggle; only clicked if the box is hidden)
    chat box           : textarea[aria-label*="Send a message" i], textarea[placeholder*="Send a message" i]
    chat send          : Enter key (fallback: button aria-label ~ /^send a message/i)
    dialogs            : div[role=dialog] button ~ /got it|dismiss|close|ok/i
"""
import asyncio, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

PORT = int(os.environ.get("MAYA_CDP_PORT", "9333"))
PROFILE = Path(os.environ.get("MAYA_PROFILE", str(Path.home() / ".config" / "maya-chrome-profile")))
OUT_SINK, MIC_SINK, MIC_SOURCE = "maya_out", "maya_mic_sink", "maya_mic"
FORBIDDEN = {"virtmic", "virtmic_sink", "callout_sink"}
NAME = os.environ.get("MAYA_NAME", "Maya")


def _check_port(port):
    if port == 9222:
        raise SystemExit("port 9222 belongs to the WhatsApp Chrome - Maya must use her own port (default 9333)")


# ---------------------------------------------------------------- PulseAudio
def _pactl(*args) -> str:
    return subprocess.run(["pactl", *args], capture_output=True, text=True).stdout


def _names(kind):
    return {ln.split("\t")[1] for ln in _pactl("list", "short", kind).splitlines() if "\t" in ln}


def devices_up(prefix="maya"):
    out, mic_sink, mic = f"{prefix}_out", f"{prefix}_mic_sink", f"{prefix}_mic"
    assert not ({out, mic_sink, mic} & FORBIDDEN)
    _pactl("unload-module", "module-suspend-on-idle")  # same as audio_setup.sh: keeps silent sinks clocked
    sinks = _names("sinks")
    for s in (out, mic_sink):
        if s not in sinks:
            _pactl("load-module", "module-null-sink", f"sink_name={s}", f"sink_properties=device.description={s}")
    if mic not in _names("sources"):
        _pactl("load-module", "module-remap-source", f"master={mic_sink}.monitor", f"source_name={mic}",
               f"source_properties=device.description={mic}")
    return out, mic_sink, mic


def devices_down(prefix="maya"):
    names = {f"{prefix}_out", f"{prefix}_mic_sink", f"{prefix}_mic"}
    for ln in _pactl("list", "short", "modules").splitlines():
        parts = ln.split("\t")
        if len(parts) >= 3 and any(re.search(rf"(sink_name|source_name)={n}(\s|$)", parts[2]) for n in names):
            _pactl("unload-module", parts[0])


def _pulse_server():
    for ln in _pactl("info").splitlines():
        if ln.startswith("Server String:"):
            return "unix:" + ln.split(":", 1)[1].strip()
    return None


# ---------------------------------------------------------------- Chrome
def cdp_up(port=PORT) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1).read()
        return True
    except Exception:
        return False


def launch_chrome(url="about:blank", port=PORT, profile=PROFILE, headless=False, display=":1", prefix="maya"):
    """Start Maya's Chrome (or reuse it if already on `port`). Returns the Popen or None if it was running."""
    _check_port(port)
    if cdp_up(port):
        return None
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PULSE_SINK=f"{prefix}_out", PULSE_SOURCE=f"{prefix}_mic")
    ps = _pulse_server()
    if ps:
        env["PULSE_SERVER"] = ps
    if not headless:
        env["DISPLAY"] = display
    cmd = [shutil.which("google-chrome") or "google-chrome", f"--user-data-dir={profile}",
           f"--remote-debugging-port={port}", "--no-first-run", "--no-default-browser-check",
           "--disable-dev-shm-usage", "--window-size=1280,860", "--autoplay-policy=no-user-gesture-required"]
    if headless:
        cmd += ["--headless=new", "--use-fake-ui-for-media-stream"]
    proc = subprocess.Popen(cmd + [url], env=env, stdout=open(profile / "chrome.log", "a"),
                            stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(60):
        if cdp_up(port):
            return proc
        time.sleep(0.5)
    raise RuntimeError(f"Maya Chrome did not open CDP on :{port} (see {profile}/chrome.log)")


def chrome_pids(port=PORT):
    """PIDs of the Chrome process tree whose command line has OUR --remote-debugging-port (never the 9222 one)."""
    roots = set()
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            try:
                cl = (p / "cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if f"--remote-debugging-port={port}".encode() in cl:
                roots.add(int(p.name))
    tree, changed = set(roots), True
    while changed:
        changed = False
        for p in Path("/proc").iterdir():
            if p.name.isdigit() and int(p.name) not in tree:
                try:
                    ppid = int((p / "stat").read_text().rsplit(")", 1)[1].split()[1])
                except (OSError, IndexError, ValueError):
                    continue
                if ppid in tree:
                    tree.add(int(p.name)); changed = True
    return tree


def route_streams(port=PORT, prefix="maya", log=print):
    """Fallback if Chrome ignored PULSE_SINK/PULSE_SOURCE: move ONLY streams of Maya's Chrome tree to Maya's devices."""
    pids = chrome_pids(port)
    moved = 0
    for kind, target in (("sink-inputs", f"{prefix}_out"), ("source-outputs", f"{prefix}_mic")):
        cur = None
        for ln in _pactl("list", kind).splitlines() + [""]:
            m = re.match(r"^(Sink Input|Source Output) #(\d+)", ln)
            if m:
                cur = {"id": m.group(2)}
            elif cur is not None and "application.process.id" in ln:
                cur["pid"] = int(re.findall(r"\d+", ln)[0])
            elif cur is not None and re.match(r"^\s*(Sink|Source): ", ln):
                cur["dev"] = ln.split(":", 1)[1].strip()
            elif cur is not None and ln == "":
                if cur.get("pid") in pids:
                    verb = "move-sink-input" if kind == "sink-inputs" else "move-source-output"
                    subprocess.run(["pactl", verb, cur["id"], target], capture_output=True)
                    moved += 1
                cur = None
    if moved:
        log(f"maya: routed {moved} Chrome stream(s) to {prefix}_out / {prefix}_mic")
    return moved


# ---------------------------------------------------------------- Meet page control
RX = {
    "name": re.compile(r"name", re.I),
    "cam_off": re.compile(r"^turn off camera", re.I),
    "mic_on": re.compile(r"^turn on (microphone|mic)", re.I),
    # real Meet labels the button "Join now without camera" / "Ask to join without camera" when no camera exists
    "join": re.compile(r"^(join now|ask to join|join)( without (camera|microphone|camera and microphone))?$", re.I),
    "leave": re.compile(r"^leave call", re.I),
    "lobby": re.compile(r"asking to be let in|someone .{0,30}let you in|wait for the host", re.I),
    "chat": re.compile(r"^chat with everyone|^chat\b", re.I),
    "send": re.compile(r"^send a message", re.I),
    "dialog_ok": re.compile(r"^(got it|dismiss|close|ok)$", re.I),
}
CHAT_BOX = 'textarea[aria-label*="Send a message" i], textarea[placeholder*="Send a message" i]'


async def _click(loc, timeout=1500) -> bool:
    try:
        if await loc.count() and await loc.first.is_visible():
            await loc.first.click(timeout=timeout)
            return True
    except Exception:
        pass
    return False


async def dismiss_dialogs(page):
    await _click(page.locator("div[role=dialog]").get_by_role("button", name=RX["dialog_ok"]))


async def join_meet(page, url, name=NAME, lobby_timeout=180, log=print) -> str:
    """Open the Meet URL, camera off, mic on, click Join/Ask to join. Returns 'joined' or raises."""
    await page.goto(url, wait_until="load", timeout=30000)
    await page.wait_for_timeout(2500)
    await dismiss_dialogs(page)
    name_box = page.get_by_placeholder(RX["name"])
    if await name_box.count() and await name_box.first.is_visible():  # not logged in -> guest join
        await name_box.first.fill(name)
        log("maya: not logged in - joining as guest (host must admit)")
    if await _click(page.get_by_role("button", name=RX["cam_off"])):
        log("maya: camera off")
    if await _click(page.get_by_role("button", name=RX["mic_on"])):
        log("maya: mic on")
    joined = False
    for _ in range(20):
        if await _click(page.get_by_role("button", name=RX["join"])):
            joined = True
            break
        await page.wait_for_timeout(500)
    if not joined:
        raise RuntimeError("join button not found (run `maya probe` and update RX['join'])")
    log("maya: clicked join")
    end = time.time() + lobby_timeout
    while time.time() < end:
        if await page.get_by_role("button", name=RX["leave"]).count():
            await dismiss_dialogs(page)
            return "joined"
        await page.wait_for_timeout(1000)
    raise RuntimeError("not admitted within the lobby timeout")


async def in_meeting(page) -> bool:
    try:
        return await page.get_by_role("button", name=RX["leave"]).count() > 0
    except Exception:
        return False


async def send_chat(page, text, log=print) -> bool:
    text = text.strip()[:450]
    box = page.locator(CHAT_BOX)
    if not (await box.count() and await box.first.is_visible()):
        await _click(page.get_by_role("button", name=RX["chat"]))
        await page.wait_for_timeout(800)
    if not await box.count():
        log("maya: chat box not found")
        return False
    await box.first.fill(text)
    await page.wait_for_timeout(200)
    await box.first.press("Enter")
    log(f"maya: chat sent: {text}")
    return True


async def leave_meet(page):
    await dismiss_dialogs(page)
    await _click(page.get_by_role("button", name=RX["leave"]))


async def probe(page):
    """List visible buttons/inputs with their accessible names (to fix selectors when Meet changes)."""
    return await page.evaluate("""() => [...document.querySelectorAll('button,[role=button],input,textarea')]
        .filter(e => e.offsetParent !== null)
        .map(e => `${e.tagName.toLowerCase()} | ${e.getAttribute('aria-label') || ''} | ${e.getAttribute('placeholder') || ''} | ${(e.innerText || '').trim().slice(0, 40)}`)""")


async def connect(port=PORT):
    from playwright.async_api import async_playwright
    _check_port(port)
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
    try:  # mic + speaker access for Meet without a permission prompt (Maya's own Chrome only)
        cdp = await browser.new_browser_cdp_session()
        await cdp.send("Browser.grantPermissions", {"origin": "https://meet.google.com",
                                                    "permissions": ["audioCapture", "speakerSelection"]})
    except Exception:
        try:
            await cdp.send("Browser.grantPermissions", {"origin": "https://meet.google.com", "permissions": ["audioCapture"]})
        except Exception:
            pass
    return pw, browser, ctx


async def meet_page(ctx):
    for p in ctx.pages:
        if "meet.google.com" in p.url:
            return p
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


# ---------------------------------------------------------------- CLI commands
def _cmd_devices(a):
    if a.action == "up":
        print("devices:", devices_up())
    else:
        devices_down(); print("maya devices removed")


def _cmd_login(a):
    devices_up()
    launch_chrome("https://accounts.google.com/", port=a.port)
    print(f"Maya's Chrome is open on the noVNC desktop (profile {PROFILE}, CDP :{a.port}).\n"
          "Log in with Maya's SEPARATE Google account there. The login is kept in that profile.")


def load_previous_history(url, root, max_dirs=6):
    """Context from earlier sessions of the SAME meeting (meta.json url match), oldest first."""
    lines = []
    dirs = sorted([d for d in Path(root).glob("*") if (d / "meta.json").exists()])[-max_dirs:]
    for d in dirs:
        try:
            if json.loads((d / "meta.json").read_text()).get("url") != url:
                continue
        except Exception:
            continue
        for fname in ("who_said_what.txt", "transcript.txt"):
            f = d / fname
            if f.exists():
                lines += [l.split(" ", 1)[1] if fname == "who_said_what.txt" and " " in l else l
                          for l in f.read_text().splitlines() if l.strip()]
                break
    return lines[-300:]


def _cmd_join(a):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from meet.maya import Maya
    from meet import meet_reader as R

    async def go():
        devices_up()
        launch_chrome("about:blank", port=a.port)
        pw, browser, ctx = await connect(a.port)
        try:
            await ctx.grant_permissions(["microphone", "camera"], origin="https://meet.google.com")
        except Exception as e:
            print("maya: grant_permissions failed:", e)
        page = await meet_page(ctx)
        await join_meet(page, a.url, name=a.name)
        loop = asyncio.get_running_loop()
        root = Path.home() / "maya_meetings"
        history = load_previous_history(a.url, root) if not a.fresh else []
        run_dir = Path(a.out or root / time.strftime("%Y%m%d_%H%M%S"))
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "meta.json").write_text(json.dumps({"url": a.url, "started": time.time()}))
        live = Path.home() / "maya_live_transcript.txt"  # stable path to the current meeting's who-said-what log
        (run_dir / "who_said_what.txt").touch()
        try:
            live.unlink(missing_ok=True)
            live.symlink_to(run_dir / "who_said_what.txt")
        except Exception:
            pass
        print(f"maya: {len(history)} lines of earlier context from previous sessions of this meeting")
        await page.wait_for_timeout(2500)
        await R.enable_captions(page)
        await R.open_chat(page)
        state = {"maya": None}
        cap, chat = R.CaptionTracker(), R.ChatTracker()

        def post(text):  # called from the suggester thread
            m = state["maya"]
            m.stats["suggestions"] += 1
            m.event("chat_suggestion", text=text)
            asyncio.run_coroutine_threadsafe(send_chat(page, text), loop)

        async def reader():
            """Poll Meet's captions (who said what) and chat; feed new lines to the current Maya session."""
            warned = {"cap": False, "chat": False}
            n = 0
            while True:
                n += 1
                m = state["maya"]
                blocks = await R.read_captions(page)
                if blocks is None:
                    if n % 20 == 1:
                        await R.enable_captions(page, log=lambda *_: None)
                    if not warned["cap"] and n > 10:
                        print("maya: captions region not found (yet)"); warned["cap"] = True
                elif m:
                    if blocks:
                        own = [b for b in blocks if b["speaker"].strip().lower() not in ("you", "maya")]
                        if own:
                            m.live_caption = (time.time(), own[-1]["speaker"], own[-1]["text"])
                    for sp, tx in cap.update(blocks):
                        await m.on_caption(sp, tx)
                msgs = await R.read_chat(page)
                if msgs is None:
                    if n % 10 == 1:
                        await R.open_chat(page)
                elif m:
                    for msg in chat.update(msgs, include_existing=True):
                        await m.on_chat(msg["sender"], msg["text"])
                await asyncio.sleep(1.5)

        async def watch():
            while True:
                route_streams(a.port)
                if not await in_meeting(page):
                    state["maya"].event("meeting_ended")
                    state["ended"] = True
                    state["maya"].agent.stop.set()
                    return
                await asyncio.sleep(10)

        reader_task = asyncio.create_task(reader())
        t_end = time.time() + a.seconds
        try:
            while time.time() < t_end:
                maya = Maya(f"{OUT_SINK}.monitor", MIC_SINK, run_dir / "transcript.txt", run_dir / "maya_events.jsonl",
                            chat_post=post, suggest_interval=a.suggest_interval, history=history)
                state["maya"] = maya
                await maya.run(t_end - time.time(), extra=[watch()])
                history = maya.history
                if maya.leave_requested or state.get("ended") or time.time() >= t_end:
                    break
                print("maya: realtime session ended unexpectedly - reconnecting with the meeting context")
                await asyncio.sleep(2)
        finally:
            reader_task.cancel()
            await leave_meet(page)
            await pw.stop()

    asyncio.run(go())


def _cmd_leave(a):
    async def go():
        pw, browser, ctx = await connect(a.port)
        await leave_meet(await meet_page(ctx)); await pw.stop()
    asyncio.run(go())


def _cmd_probe(a):
    async def go():
        pw, browser, ctx = await connect(a.port)
        for ln in await probe(await meet_page(ctx)):
            print(ln)
        await pw.stop()
    asyncio.run(go())


def add_commands(sub):
    d = sub.add_parser("devices", help="create/remove Maya's PulseAudio devices")
    d.add_argument("action", choices=["up", "down"]); d.set_defaults(fn=_cmd_devices)
    for name, fn, hlp in (("login", _cmd_login, "open Maya's Chrome at accounts.google.com for a manual login"),
                          ("join", _cmd_join, "join a Meet URL and run Maya there"),
                          ("leave", _cmd_leave, "leave the current meeting"),
                          ("probe", _cmd_probe, "print visible buttons on the Meet page (fix selectors)")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("--port", type=int, default=PORT)
        if name == "join":
            p.add_argument("url")
            p.add_argument("--name", default=NAME, help="guest display name if not logged in")
            p.add_argument("--seconds", type=float, default=3600)
            p.add_argument("--suggest-interval", type=float, default=180)
            p.add_argument("--out", help="folder for transcript + events (default ~/maya_meetings/<ts>, outside the repo)")
            p.add_argument("--fresh", action="store_true", help="don't load context from earlier sessions of this meeting")
        p.set_defaults(fn=fn)
