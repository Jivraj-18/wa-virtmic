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
NAME = os.environ.get("MAYA_NAME", "Nova")
NATIVE = sys.platform == "android" or os.path.exists("/data/data/com.termux/files/usr/bin/termux-info")
XTMP = (os.environ.get("PREFIX", "/data/data/com.termux/files/usr") + "/tmp") if NATIVE else "/tmp"
# Native Termux: Nova gets her OWN Xvfb (:97), so the WhatsApp supervisor restarting its Xvfb :99 never kills her
# Chrome. Elsewhere (proot / Codespace) the old behaviour: :99 if it exists, else noVNC :1.
DISPLAY = os.environ.get("MAYA_DISPLAY") or (":97" if NATIVE else
                                             (":99" if Path(f"{XTMP}/.X11-unix/X99").exists() else ":1"))
IN_PROOT = "proot" in os.uname().release.lower()   # Chrome's sandbox crashes under proot's ptrace


def ensure_display(display=DISPLAY):
    """Start a private Xvfb for Nova if her display isn't up (never touches :99, the WhatsApp display)."""
    n = display.lstrip(":")
    if n == "99":
        return
    sock, lock = Path(f"{XTMP}/.X11-unix/X{n}"), Path(f"{XTMP}/.X{n}-lock")
    if sock.exists():
        try:  # a phone reboot leaves the socket/lock behind with no Xvfb: check the lock's pid is alive
            os.kill(int(lock.read_text().strip()), 0)
            return
        except Exception:
            sock.unlink(missing_ok=True)
            lock.unlink(missing_ok=True)
    xvfb = shutil.which("Xvfb")
    if not xvfb:
        raise SystemExit("Xvfb not found (pkg install xorg-server-xvfb)")
    subprocess.Popen([xvfb, display, "-screen", "0", "1280x860x24", "-nolisten", "tcp"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(40):
        if Path(f"{XTMP}/.X11-unix/X{n}").exists():
            return
        time.sleep(0.25)
    raise RuntimeError(f"Xvfb {display} did not start")


def _check_port(port):
    if port == 9222:
        raise SystemExit("port 9222 belongs to the WhatsApp Chrome - Nova must use her own port (default 9333)")


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


def allow_meet_media(profile=PROFILE):
    """Persist 'allow microphone + camera on meet.google.com' in the profile (Chrome must be stopped).
    CDP permission overrides vanish when the CDP connection that set them closes - every `nova status` / probe
    used to reset Meet to "Microphone problem" mid-meeting (2026-11-24). A real site setting doesn't."""
    prefs = Path(profile) / "Default" / "Preferences"
    if not prefs.exists():
        return False
    p = json.loads(prefs.read_text())
    ex = p.setdefault("profile", {}).setdefault("content_settings", {}).setdefault("exceptions", {})
    changed = False
    for kind in ("media_stream_mic", "media_stream_camera"):
        d = ex.setdefault(kind, {})
        key = "https://meet.google.com:443,*"
        if d.get(key, {}).get("setting") != 1:
            d[key] = {"last_modified": str(int(time.time() * 1e6)), "setting": 1}
            changed = True
    if changed:
        prefs.write_text(json.dumps(p))
    return changed


def launch_chrome(url="about:blank", port=PORT, profile=PROFILE, headless=False, display=DISPLAY, prefix="maya"):
    """Start Maya's Chrome (or reuse it if already on `port`). Returns the Popen or None if it was running."""
    _check_port(port)
    if cdp_up(port):
        return None
    profile = Path(profile)
    profile.mkdir(parents=True, exist_ok=True)
    allow_meet_media(profile)
    env = dict(os.environ, PULSE_SINK=f"{prefix}_out", PULSE_SOURCE=f"{prefix}_mic")
    env.pop("PULSE_LATENCY_MSEC", None)   # WhatsApp finding: the big-buffer flags drop mic frames natively
    ps = _pulse_server()
    if ps:
        env["PULSE_SERVER"] = ps
    if not headless:
        ensure_display(display)
        env["DISPLAY"] = display
    chrome = shutil.which("chromium-browser") if NATIVE else None
    cmd = [chrome or shutil.which("google-chrome") or "google-chrome", f"--user-data-dir={profile}",
           f"--remote-debugging-port={port}", "--no-first-run", "--no-default-browser-check",
           "--disable-dev-shm-usage", "--window-size=1280,860", "--autoplay-policy=no-user-gesture-required"]
    if headless:
        cmd += ["--headless=new", "--use-fake-ui-for-media-stream"]
    # e.g. CHROME_EXTRA_ARGS="--no-sandbox" under proot-distro on Termux (see launch_chrome.sh); no-op elsewhere.
    cmd += os.environ.get("CHROME_EXTRA_ARGS", "--no-sandbox" if IN_PROOT else "").split()
    # Chrome's stderr is discarded: nothing reads it, and an unbounded chrome.log once filled a phone (50 GB).
    # To debug a Chrome that won't start, run the printed command by hand.
    cmd.append("--log-level=3")
    (profile / "chrome.log").unlink(missing_ok=True)  # old unbounded log location
    proc = subprocess.Popen(cmd + [url], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            stdin=subprocess.DEVNULL, start_new_session=True)
    for _ in range(60):
        if cdp_up(port):
            return proc
        time.sleep(0.5)
    raise RuntimeError(f"Maya Chrome did not open CDP on :{port}; run it by hand to see why: {' '.join(cmd + [url])}")


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
    "raise": re.compile(r"^raise hand", re.I),
    "lower": re.compile(r"^lower hand", re.I),
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


async def join_meet(page, url, name=NAME, lobby_timeout=600, log=print, on_phase=lambda p: None) -> str:
    """Open the Meet URL, camera off, mic on, click Join/Ask to join. Returns 'joined' or raises."""
    on_phase("joining")
    # Meet keeps loading for a long time on the phone; "load" can take > 30 s. Continue as soon as the DOM is there
    # and the pre-join controls (or a name field / lobby / error text) appear.
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        log(f"maya: goto slow ({type(e).__name__}) - continuing if the page is usable")
    for _ in range(60):
        try:
            if await page.get_by_role("button", name=RX["join"]).count() or \
                    await page.get_by_placeholder(RX["name"]).count() or (await meet_state(page)).get("denied"):
                break
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    await page.wait_for_timeout(1500)
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
    for _ in range(30):
        # a click can land but report a timeout on a slow phone: judge by the page, not by the click's result
        st = await meet_state(page)
        if st.get("lobby") or st.get("in_call"):
            joined = True
            break
        if await _click(page.get_by_role("button", name=RX["join"]), timeout=5000):
            joined = True
            break
        await page.wait_for_timeout(700)
    if not joined:
        raise RuntimeError("join button not found (run `maya probe` and update RX['join'])")
    log("maya: clicked join")
    end = time.time() + lobby_timeout
    in_lobby = False
    while time.time() < end:
        if await page.get_by_role("button", name=RX["leave"]).count():
            await dismiss_dialogs(page)
            return "joined"
        st = await meet_state(page)
        if st.get("denied"):
            raise RuntimeError("Meet refused the join: " + (await page_text(page, 300)).replace("\n", " | "))
        if st.get("lobby") and not in_lobby:
            in_lobby = True
            on_phase("lobby")
            log("maya: waiting in the lobby for the host to admit us")
        await page.wait_for_timeout(1000)
    raise RuntimeError("not admitted within the lobby timeout")


async def in_meeting(page) -> bool:
    try:
        return await page.get_by_role("button", name=RX["leave"]).count() > 0
    except Exception:
        return False


def chat_chunks(text, limit=450):
    """Meet chat messages are capped (~500 chars): split long text at sentence ends."""
    parts, cur = [], ""
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        if cur and len(cur) + 1 + len(sent) > limit:
            parts.append(cur); cur = sent
        else:
            cur = f"{cur} {sent}".strip()
    if cur:
        parts.append(cur)
    return [p[:limit] for p in parts]


async def send_chat(page, text, log=print) -> bool:
    chunks = chat_chunks(text)
    if len(chunks) > 1:
        ok = True
        for c in chunks:
            ok = await send_chat(page, c, log) and ok
            await page.wait_for_timeout(600)
        return ok
    text = chunks[0] if chunks else ""
    box = page.locator(CHAT_BOX)
    if not (await box.count() and await box.first.is_visible()):
        await _click(page.get_by_role("button", name=RX["chat"]))
        await page.wait_for_timeout(800)
    if not await box.count():
        log("maya: chat box not found")
        return False
    before = await _undelivered_count(page)
    await box.first.fill(text)
    await page.wait_for_timeout(200)
    await box.first.press("Enter")
    # Meet accepts the text but may refuse delivery: outside accounts can't post in an organization's meeting chat
    # ("Your message wasn't delivered" + "In-call messages are available ... in the host's organization", 2026-11-24)
    for _ in range(8):
        await page.wait_for_timeout(500)
        if await _undelivered_count(page) > before:
            log(f"maya: chat NOT delivered (Meet refused it - outside account?): {text}")
            CHAT_BLOCKED[page.url.split("?")[0]] = True
            return False
    log(f"maya: chat sent: {text}")
    return True


CHAT_BLOCKED = {}   # meeting url -> True once Meet refused one of our chat messages


async def _undelivered_count(page) -> int:
    try:
        return await page.evaluate("() => (document.body.innerText.match(/message wasn.t delivered|not delivered|couldn.t send/gi) || []).length")
    except Exception:
        return 0


def speakable_url(url: str) -> str:
    """'https://jivraj-18.github.io/innovation-lab/' -> 'jivraj-18 dot github dot io slash innovation-lab'."""
    u = re.sub(r"^https?://(www\.)?", "", url.strip()).rstrip("/")
    return u.replace(".", " dot ").replace("/", " slash ").replace("-", " dash ").replace("_", " underscore ")


async def raise_hand(page, up=True) -> bool:
    """Raise (up=True) or lower Nova's hand in Meet. True if the hand is now in the wanted state."""
    want, other = (RX["lower"], RX["raise"]) if up else (RX["raise"], RX["lower"])
    if await page.get_by_role("button", name=want).count():
        return True            # already in that state
    await _click(page.get_by_role("button", name=other), timeout=5000)
    await page.wait_for_timeout(800)
    if await page.get_by_role("button", name=want).count():
        return True
    # Playwright clicks often time out on the heavy Meet page on the phone: click in the page instead
    await js_click(page, other.pattern)
    await page.wait_for_timeout(1200)
    return await page.get_by_role("button", name=want).count() > 0


async def unmute(page) -> bool:
    """Turn Nova's mic back on (e.g. the host muted her). True if it is on now."""
    on = re.compile(r"^turn off (microphone|mic)", re.I)
    if await page.get_by_role("button", name=on).count():
        return True
    await _click(page.get_by_role("button", name=RX["mic_on"]), timeout=4000)
    await page.wait_for_timeout(700)
    if not await page.get_by_role("button", name=on).count():
        await js_click(page, RX["mic_on"].pattern)
        await page.wait_for_timeout(1000)
    return await page.get_by_role("button", name=on).count() > 0


async def js_click(page, pattern: str) -> bool:
    """Click the first visible button whose aria-label matches `pattern` (case-insensitive) from inside the page."""
    try:
        return await page.evaluate("""(p) => { const rx = new RegExp(p, 'i');
            const b = [...document.querySelectorAll('button')].find(b => b.getBoundingClientRect().width > 0 &&
                                                                     rx.test(b.getAttribute('aria-label') || ''));
            if (b) { b.click(); return true; } return false; }""", pattern)
    except Exception:
        return False


async def leave_meet(page):
    await dismiss_dialogs(page)
    if not await _click(page.get_by_role("button", name=RX["leave"])):
        await js_click(page, RX["leave"].pattern)


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
    # Meet's mic/camera permission is a persistent site setting (allow_meet_media at launch). No CDP permission
    # overrides here: they are dropped when this connection closes, which broke Meet's mic mid-meeting.
    return pw, browser, ctx


def is_meet_url(url: str) -> bool:
    """meet.google.com, or the local simulator page when NOVA_SIM=1 (tests/nova_sim)."""
    return "meet.google.com" in url or (os.environ.get("NOVA_SIM") == "1" and url.startswith("http://127.0.0.1:"))


async def meet_page(ctx):
    for p in ctx.pages:
        if is_meet_url(p.url):
            return p
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


# ---------------------------------------------------------------- meeting state (text only, no screenshots)
STATE_DIR = Path(os.environ.get("NOVA_STATE_DIR", str(Path.home() / ".cache" / "nova")))
STATE_FILE = STATE_DIR / "state.json"
LEAVE_FLAG = STATE_DIR / "leave.request"
MEETINGS = Path(os.environ.get("NOVA_MEETINGS", str(Path.home() / "nova_meetings")))


def write_state(**kw):
    """Merge kw into ~/.cache/nova/state.json (read by `nova status`, the autojoin service and the supervisor)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        cur = json.loads(STATE_FILE.read_text())
    except Exception:
        cur = {}
    cur.update(kw, updated=time.time())
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cur, ensure_ascii=False, indent=1))
    tmp.replace(STATE_FILE)
    return cur


def read_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


# Everything Meet shows, as text: in call? lobby? mic/cam (from the toggle buttons' labels), participant count/names.
# Participant count: the People button carries a number badge; tiles carry data-participant-id. Both are heuristics,
# `nova probe` shows the raw buttons/text when they break.
MEET_STATE_JS = r"""() => {
  const vis = e => e && e.offsetParent !== null;
  const btns = [...document.querySelectorAll('button,[role=button]')].filter(vis);
  const lab = e => (e.getAttribute('aria-label') || e.innerText || '').trim();
  const has = rx => btns.some(b => rx.test(lab(b)));
  const text = document.body ? document.body.innerText : '';
  let count = null;
  for (const b of btns) {
    const l = lab(b);
    if (/^(people|show everyone|participants|view everyone)/i.test(l) || /people/i.test(b.getAttribute('aria-label') || '')) {
      const m = (b.innerText || '').match(/\d+/) || l.match(/\((\d+)\)/) || l.match(/\b(\d+)\b/);
      if (m) { count = parseInt(m[1] || m[0]); break; }
    }
  }
  const tiles = new Map();
  document.querySelectorAll('[data-participant-id]').forEach(t => {
    const id = t.getAttribute('data-participant-id');
    const nameEl = t.querySelector('[data-self-name]') || t.querySelector('.notranslate');
    const nm = (nameEl && (nameEl.getAttribute('data-self-name') || nameEl.innerText) || '').split('\n')[0].trim();
    if (!tiles.has(id) || (!tiles.get(id) && nm)) tiles.set(id, nm);
  });
  return {
    url: location.href.split('?')[0], title: document.title,
    in_call: has(/^leave call/i),
    lobby: /asking to be let in|someone .{0,30}let you in|wait for the host|you'll join the call when someone lets you in/i.test(text),
    denied: /you can't join this video call|denied your request|you've been removed|no one responded to your request/i.test(text),
    ended: /you left the meeting|the call has ended|you've left the call|returning to home screen/i.test(text),
    mic: has(/^turn off (microphone|mic)/i) ? 'on' : has(/^turn on (microphone|mic)/i) ? 'off' : '?',
    cam: has(/^turn off camera/i) ? 'on' : has(/^turn on camera/i) ? 'off' : '?',
    count, tiles: tiles.size, names: [...new Set([...tiles.values()].filter(Boolean))].slice(0, 30),
  };
}"""


async def meet_state(page) -> dict:
    try:
        return await page.evaluate(MEET_STATE_JS)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def others_count(st: dict):
    """People in the call other than us, or None if unknown."""
    if st.get("count") is not None:
        return max(0, st["count"] - 1)
    if st.get("tiles"):
        return max(0, st["tiles"] - 1)
    return None


async def page_text(page, limit=3000) -> str:
    try:
        return (await page.evaluate("() => document.body.innerText"))[:limit]
    except Exception as e:
        return f"(no text: {e})"


ANNOUNCE = Path(os.environ.get("NOVA_ANNOUNCE", str(Path.home() / ".config" / "nova" / "announce.json")))


def load_announcements() -> list:
    try:
        return json.loads(ANNOUNCE.read_text())
    except Exception:
        return []


def save_announcements(items: list):
    ANNOUNCE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ANNOUNCE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=1, ensure_ascii=False))
    tmp.replace(ANNOUNCE)


def due_announcements(title: str, url: str) -> list:
    """Pending one-off things Nova should SAY in this meeting (queued by the owner with `nova announce add`)."""
    t, u = (title or "").lower(), (url or "").lower()
    return [x for x in load_announcements() if not x.get("done_at") and
            (not x.get("title") or x["title"].lower() in t) and (not x.get("url") or x["url"].lower() in u)]


def mark_announced(aid: str, meeting: str):
    items = load_announcements()
    for x in items:
        if x.get("id") == aid:
            x["done_at"], x["done_in"] = time.time(), meeting
    save_announcements(items)


ANNOUNCE_PROMPT = ("You raised your hand and {who} just gave you the floor ({cue}). Now say the following, once, "
                   "naturally and politely, close to this wording, in English, without adding anything else: \"{text}\"")


def spawn_notes(run_dir, log=print):
    """Post-meeting notes in a separate, detached process (never in the meeting loop)."""
    notes = Path(__file__).resolve().parents[1] / "nova" / "notes.py"
    if not notes.exists():
        return
    with open(Path(run_dir) / "notes.log", "ab") as f:
        subprocess.Popen([sys.executable, str(notes), "make", str(run_dir), "--send"], stdout=f, stderr=f,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    log(f"nova: notes are being written in the background -> {run_dir}/notes.md")


# ---------------------------------------------------------------- CLI commands
def _cmd_devices(a):
    if a.action == "up":
        print("devices:", devices_up())
    else:
        devices_down(); print("maya devices removed")


def _cmd_login(a):
    devices_up()
    launch_chrome("https://accounts.google.com/", port=a.port)
    print(f"Maya's Chrome is open on display {DISPLAY} (profile {PROFILE}, CDP :{a.port}).\n"
          "Log in with Maya's SEPARATE Google account there. The login is kept in that profile.\n"
          "On the phone :99 is invisible (Xvfb): skip this and join as a guest (the host admits Maya).")


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
    import mic_apm

    run_dir = Path(a.out or MEETINGS / time.strftime("%Y%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)
    LEAVE_FLAG.unlink(missing_ok=True)
    write_state(phase="starting", url=a.url, pid=os.getpid(), run_dir=str(run_dir), event=a.event, title=a.title,
                until=a.until, joined_at=None, error=None, others=None, names=[])

    def phase(p, **kw):
        write_state(phase=p, **kw)
        print(f"nova: phase={p}", flush=True)

    async def go():
        devices_up()
        launch_chrome("about:blank", port=a.port)
        pw, browser, ctx = await connect(a.port)
        if "meet.google.com" not in a.url:   # simulator page; real Meet is granted in connect() (Playwright's
            try:                              # grant_permissions here overrode that and broke Meet's mic)
                await ctx.grant_permissions(["microphone", "camera"], origin="/".join(a.url.split("/")[:3]))
            except Exception as e:
                print("maya: grant_permissions failed:", e)
        if mic_apm.enabled():  # Chrome's echo cancel / noise suppression / AGC damage a clean digital voice
            await ctx.add_init_script(mic_apm.JS)
        page = await meet_page(ctx)
        try:
            await join_meet(page, a.url, name=a.name, lobby_timeout=a.lobby_timeout, on_phase=phase)
        except Exception as e:
            phase("failed", error=str(e)[:300])
            await pw.stop()
            raise SystemExit(f"nova: join failed: {e}")
        phase("in_meeting", joined_at=time.time())
        loop = asyncio.get_running_loop()
        history = load_previous_history(a.url, MEETINGS) if not a.fresh else []
        (run_dir / "meta.json").write_text(json.dumps({"url": a.url, "started": time.time(), "event": a.event,
                                                        "title": a.title, "name": NAME}))
        live = Path.home() / "nova_live_transcript.txt"  # stable path to the current meeting's who-said-what log
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
            """Poll Meet's captions (who said what) and chat; feed new lines to the current session."""
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
                        own = [b for b in blocks if b["speaker"].strip().lower() not in ("you", NAME.lower())]
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

        def stop(why):
            state["ended"] = why
            if state["maya"]:
                state["maya"].event("leaving", why=why)
                state["maya"].agent.stop.set()

        async def watch():
            """Every 5 s: still in the call? leave requested? alone? past the scheduled end?"""
            seen_others, alone_since, t_join = False, None, time.time()
            pending = due_announcements(a.title or "", a.url)
            if pending:
                print(f"nova: {len(pending)} announcement(s) queued for this meeting")
            while True:
                route_streams(a.port)
                st = await meet_state(page)
                others = others_count(st)
                write_state(others=others, names=st.get("names", []), mic=st.get("mic"), cam=st.get("cam"))
                if not st.get("in_call") and not st.get("error"):
                    return stop("meeting_ended")
                if LEAVE_FLAG.exists():
                    return stop("leave_requested")
                if others is not None:
                    if others > 0:
                        seen_others, alone_since = True, None
                    elif alone_since is None:
                        alone_since = time.time()
                    limit = a.alone_leave if seen_others else a.nobody_leave
                    if alone_since and time.time() - alone_since > limit:
                        return stop("everyone_left" if seen_others else "nobody_came")
                if a.until and time.time() > a.until:
                    return stop("scheduled_end")
                m = state["maya"]
                fl = state.get("floor")
                if fl and m and m.floor is None and not fl.get("spoken"):
                    m.floor = fl          # carry a raised hand over a realtime reconnect
                if not fl:   # re-read: announcements can be queued while Nova is already in the meeting
                    pending = due_announcements(a.title or "", a.url)
                if pending and not fl and m and m.agent.ws and not m.speaking():
                    x = pending[0]
                    quiet = time.time() - max(m.last_caption, m.last_trigger) > x.get("quiet_s", 4)
                    who = (x.get("wait_for") or "").lower()
                    heard = {sp.lower() for _, sp in m.recent_speakers} | {n.lower() for n in st.get("names", [])}
                    present = (not who) or any(who in n for n in heard)
                    enough = (others or 0) >= x.get("min_others", 1) or (others is None and time.time() - t_join > 300)
                    if time.time() - t_join >= x.get("after_s", 60) and enough and present and quiet:
                        pending.pop(0)
                        if x.get("raise_hand", True):
                            ok = await raise_hand(page, True)
                            m.event("hand_raised", id=x.get("id"), ok=ok, waiting_for=who or "anyone")
                            fl = {"x": x, "who": (x.get("floor_from") or who).lower(), "since": time.time(), "spoken": False}
                            state["floor"] = fl
                            m.floor = fl
                        else:
                            state["floor"] = fl = {"x": x, "who": (x.get("floor_from") or who).lower(), "since": time.time(), "spoken": False}
                            await m.say_floor()
                if fl and fl.get("spoken") and not fl.get("finished"):
                    fl["finished"] = True
                    x = fl["x"]
                    await raise_hand(page, False)
                    if x.get("chat", True) and (x.get("chat_text") or x["text"]):
                        ok = await send_chat(page, x.get("chat_text") or x["text"])
                        urls = re.findall(r"https?://\S+[\w/]", x.get("chat_text") or "")
                        if not ok and urls and m:
                            spoken = "; ".join(speakable_url(u) for u in urls[:2])
                            m.event("links_spoken", urls=urls[:2])
                            await m.agent.respond("The meeting chat refused your message (you joined from an outside "
                                                  "account). Say in one short sentence that you can't post in this "
                                                  f"meeting's chat, then read this link out slowly and clearly: {spoken}")
                    mark_announced(x.get("id"), a.title or a.url)
                    state["floor"] = None     # done: the next queued announcement (if any) can start
                    if m:
                        m.floor = None
                await asyncio.sleep(5)

        reader_task = asyncio.create_task(reader())
        watch_task = None
        t_end = time.time() + a.seconds
        try:
            while time.time() < t_end:
                maya = Maya(f"{OUT_SINK}.monitor", MIC_SINK, run_dir / "transcript.txt", run_dir / "maya_events.jsonl",
                            chat_post=post, suggest_interval=a.suggest_interval, history=history)
                maya.meeting_url, maya.meeting_title = a.url, a.title or ""
                maya.chat_send = lambda text: send_chat(page, text)
                maya.unmute = lambda: unmute(page)
                state["maya"] = maya
                if watch_task is None or watch_task.done():
                    watch_task = asyncio.create_task(watch())
                await maya.run(t_end - time.time())
                history = maya.history
                if maya.leave_requested or state.get("ended") or time.time() >= t_end:
                    break
                print("maya: realtime session ended unexpectedly - reconnecting with the meeting context")
                await asyncio.sleep(2)
        finally:
            reader_task.cancel()
            if watch_task:
                watch_task.cancel()
            try:
                await leave_meet(page)
                await page.wait_for_timeout(1500)
                await page.goto("about:blank")
            except Exception:
                pass
            await pw.stop()
            why = state.get("ended") or ("asked_by_voice" if state["maya"] and state["maya"].leave_requested else "timeout")
            phase("left", left_at=time.time(), left_why=why)
            LEAVE_FLAG.unlink(missing_ok=True)
            # Meeting notes / action items come from Meet itself ("Notes by Gemini" on the Calendar event); Nova's own
            # notes only with NOVA_NOTES=1 (scripts/nova/notes.py can also be run by hand).
            if os.environ.get("NOVA_NOTES") == "1" and (run_dir / "who_said_what.txt").stat().st_size:
                spawn_notes(run_dir)

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
            p.add_argument("--suggest-interval", type=float, default=float(os.environ.get("MAYA_SUGGEST_INTERVAL", "0")),
                           help="seconds between chat tips; 0 (default) = never post tips")
            p.add_argument("--out", help="folder for transcript + events (default ~/nova_meetings/<ts>, outside the repo)")
            p.add_argument("--until", type=float, help="unix time to leave at (autojoin: the event's end + grace)")
            p.add_argument("--event", help="calendar event id (autojoin bookkeeping)")
            p.add_argument("--title", help="meeting title (for the notes)")
            p.add_argument("--lobby-timeout", type=float, default=600)
            p.add_argument("--alone-leave", type=float, default=90, help="leave after this long alone once others were there")
            p.add_argument("--nobody-leave", type=float, default=900, help="leave if nobody else shows up for this long")
            p.add_argument("--fresh", action="store_true", help="don't load context from earlier sessions of this meeting")
        p.set_defaults(fn=fn)
