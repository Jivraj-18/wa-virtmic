#!/usr/bin/env python3
"""Health check for the WhatsApp AI-voice demo. READ-ONLY: it never clicks, navigates, starts or kills anything.

  python3 scripts/doctor.py              # all checks, PASS/WARN/FAIL + the exact fix for each failure
  python3 scripts/doctor.py --offline    # skip the network checks (gateway, realtime key, api.openai.com)
  python3 scripts/doctor.py --redact     # hide the codespace name and hosts (for sharing the output)
  python3 scripts/doctor.py --url        # just print the noVNC URL
  python3 scripts/doctor.py --wait-login 600   # poll WhatsApp Web until logged in (used by demo.sh)

Exit code: 0 if nothing FAILed, 1 otherwise.
"""
import argparse, asyncio, json, os, re, shutil, socket, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
CDP = os.environ.get("WA_CDP", "http://localhost:9222")
REDACT = False

# Same probe as cdp_eval.py status (pure DOM reads, no side effects).
STATUS_JS = """(() => ({
  url: location.href,
  qr: !!document.querySelector('canvas[aria-label*="QR" i], [aria-label*="QR code" i], [data-ref]'),
  loading: !!document.body && /Loading your chats|Loading chats/i.test(document.body.innerText),
  chatList: !!document.querySelector('#pane-side, [aria-label="Chat list"], div[role="grid"]'),
}))()"""


def novnc_url() -> str:
    name, dom = os.environ.get("CODESPACE_NAME"), os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")
    if REDACT and name:
        name = "<codespace-name>"
    if name and dom:
        return f"https://{name}-6080.{dom}/vnc.html?autoconnect=true&resize=scale"
    return "http://localhost:6080/vnc.html?autoconnect=true&resize=scale"


# ---------------------------------------------------------------- reporting
results = []
C = {"PASS": "\033[32m", "WARN": "\033[33m", "FAIL": "\033[31m", "": "\033[0m"} if sys.stdout.isatty() else \
    {"PASS": "", "WARN": "", "FAIL": "", "": ""}


def report(status: str, name: str, detail: str = "", fix: str = ""):
    results.append((status, name))
    print(f"{C[status]}{status:4s}{C['']}  {name:24s} {detail}")
    if fix and status != "PASS":
        for i, line in enumerate(fix.splitlines()):
            print(f"      {'fix: ' if i == 0 else '     '}{line}")


def run(cmd, timeout=5):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(cmd, 127, "", str(e))


def port_open(port, host="127.0.0.1", timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------- checks
def check_binaries():
    need = ["google-chrome", "pulseaudio", "pactl", "parec", "pacat", "paplay", "parecord", "ffmpeg", "curl"]
    miss = [b for b in need if not shutil.which(b)]
    mods = [m for m in ("edge_tts", "numpy", "playwright", "websockets", "yaml")
            if run([sys.executable, "-c", f"import {m}"]).returncode != 0]
    if miss or mods:
        report("FAIL", "binaries + modules", f"missing: {' '.join(miss + mods)}", "bash scripts/install.sh")
    else:
        report("PASS", "binaries + modules", "chrome, pulseaudio-utils, ffmpeg, python modules")
    if shutil.which("claude") or (Path.home() / ".local/bin/claude").exists():
        report("PASS", "claude code", "installed")
    else:
        report("WARN", "claude code", "not installed (optional)", "bash scripts/install.sh")


def check_pulse() -> bool:
    r = run(["pactl", "info"])
    if r.returncode != 0:
        report("FAIL", "pulseaudio daemon", "not running", "bash scripts/audio_setup.sh")
        return False
    info = dict(l.split(": ", 1) for l in r.stdout.splitlines() if ": " in l)
    report("PASS", "pulseaudio daemon", f"server {info.get('Server Version', '?')}")
    sinks = [l.split("\t")[1] for l in run(["pactl", "list", "short", "sinks"]).stdout.splitlines() if "\t" in l]
    srcs = [l.split("\t")[1] for l in run(["pactl", "list", "short", "sources"]).stdout.splitlines() if "\t" in l]
    miss = [n for n, ok in (("virtmic_sink", "virtmic_sink" in sinks), ("virtmic", "virtmic" in srcs),
                            ("callout_sink", "callout_sink" in sinks)) if not ok]
    if miss:
        report("FAIL", "virtual audio devices", f"missing: {', '.join(miss)}", "bash scripts/audio_setup.sh")
    else:
        report("PASS", "virtual audio devices", "virtmic_sink, virtmic, callout_sink")
    ds, dk = info.get("Default Source"), info.get("Default Sink")
    if ds == "virtmic" and dk == "callout_sink":
        report("PASS", "default devices", "source=virtmic sink=callout_sink")
    else:
        report("FAIL", "default devices", f"source={ds} sink={dk} (want virtmic / callout_sink)",
               "bash scripts/audio_setup.sh")
    if "virtmic" in srcs:
        mute = run(["pactl", "get-source-mute", "virtmic"]).stdout.strip()
        if "yes" in mute:
            report("FAIL", "virtmic unmuted", mute, "pactl set-source-mute virtmic 0")
    mods = run(["pactl", "list", "short", "modules"]).stdout
    if "module-suspend-on-idle" in mods:
        report("WARN", "suspend-on-idle", "loaded: recordings can drift", "bash scripts/audio_setup.sh")
    return True


def check_desktop():
    if port_open(6080):
        report("PASS", "noVNC (port 6080)", f"listening -> {novnc_url()}")
    else:
        report("FAIL", "noVNC (port 6080)", "nothing listening",
               "the desktop-lite feature isn't running: /usr/local/share/desktop-init.sh true\n"
               "(or Codespaces: Command Palette > Rebuild Container)")
    disp = os.environ.get("DISPLAY", ":1")
    sock = Path(f"/tmp/.X11-unix/X{disp.lstrip(':').split('.')[0]}")
    if sock.exists():
        report("PASS", "X display", f"{disp} present")
    else:
        report("FAIL", "X display", f"{sock} missing", "/usr/local/share/desktop-init.sh true  (or rebuild the container)")
    try:
        shm = shutil.disk_usage("/dev/shm").total
        st = "PASS" if shm >= 512 << 20 else "WARN"
        report(st, "/dev/shm", f"{shm >> 20} MB", 'devcontainer.json "runArgs": ["--shm-size=1g"], then rebuild')
    except OSError:
        pass


def cdp_get(path):
    with urllib.request.urlopen(CDP + path, timeout=3) as r:
        return json.load(r)


async def _eval(ws_url, expr):
    import websockets
    async with websockets.connect(ws_url, max_size=None, open_timeout=5) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True}}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 5))
            if m.get("id") == 1:
                return m.get("result", {}).get("result", {}).get("value")


def wa_status():
    """Read-only DOM probe of the WhatsApp tab -> dict, or None if there is no WhatsApp tab."""
    tabs = [t for t in cdp_get("/json/list") if t.get("type") == "page" and "web.whatsapp.com" in t.get("url", "")]
    if not tabs:
        return None
    return asyncio.run(_eval(tabs[0]["webSocketDebuggerUrl"], STATUS_JS)) or {}


def login_state(st) -> str:
    if st is None:
        return "no-tab"
    if st.get("chatList"):
        return "logged-in"
    if st.get("qr"):
        return "qr"
    if st.get("loading"):
        return "loading"
    return "unknown"


def check_chrome():
    try:
        v = cdp_get("/json/version")
        report("PASS", "chrome CDP (:9222)", v.get("Browser", "?"))
    except Exception as e:
        report("FAIL", "chrome CDP (:9222)", f"not reachable ({type(e).__name__})", "bash scripts/launch_chrome.sh")
        return
    try:
        state = login_state(wa_status())
    except Exception as e:
        report("FAIL", "whatsapp login", f"DOM probe failed: {type(e).__name__}: {e}", "python3 scripts/cdp_eval.py status")
        return
    fixes = {
        "no-tab": ("FAIL", "no web.whatsapp.com tab open", "open https://web.whatsapp.com in the noVNC Chrome"),
        "qr": ("FAIL", "QR code shown: not linked yet",
               f"open {novnc_url()} (password vscode), then on your phone:\n"
               "WhatsApp > Settings > Linked devices > Link a device, and scan the QR"),
        "loading": ("WARN", "loading chats...", "wait a minute, then re-run make doctor"),
        "unknown": ("WARN", "page loaded but no chat list / QR found", f"look at the noVNC desktop: {novnc_url()}"),
        "logged-in": ("PASS", "chat list visible", ""),
    }
    s, d, f = fixes[state]
    report(s, "whatsapp login", d, f)


def check_auto_answer():
    r = run(["pgrep", "-af", r"scripts/auto_answer\.py"])
    procs = [l for l in r.stdout.splitlines() if len(l.split()) > 1 and "python" in l.split()[1]]
    if len(procs) == 1:
        report("PASS", "auto_answer.py", f"running (pid {procs[0].split()[0]})")
    elif len(procs) > 1:
        report("WARN", "auto_answer.py", f"{len(procs)} copies running: they would race to answer",
               "make stop, then make demo")
    else:
        report("WARN", "auto_answer.py", "not running: calls won't be answered", "make demo")


def check_gateway(offline: bool):
    import gateway
    env = HERE / ".env"
    if not env.exists():
        report("FAIL", "scripts/.env", "missing", "cp scripts/.env.example scripts/.env   # then fill in the gateway URL + token")
        return
    if not gateway.has_gateway():
        report("FAIL", "scripts/.env", "LLM_GATEWAY_BASE or LLM_GATEWAY_TOKEN empty",
               "edit scripts/.env: set LLM_GATEWAY_BASE and LLM_GATEWAY_TOKEN")
        return
    report("PASS", "scripts/.env", "LLM_GATEWAY_BASE + LLM_GATEWAY_TOKEN set")
    if offline:
        return
    # 1) reachability: any HTTP answer from the base URL counts (no auth, no POST)
    # (TCP + TLS handshake only: the gateway's own pages can be slow, and every HTTP request counts against its rate limit)
    import ssl
    from urllib.parse import urlsplit
    u = urlsplit(gateway.base())
    port = u.port or (443 if u.scheme == "https" else 80)
    t = time.time()
    try:
        with socket.create_connection((u.hostname, port), timeout=10) as s:
            if u.scheme == "https":
                ssl.create_default_context().wrap_socket(s, server_hostname=u.hostname).close()
    except Exception as e:
        report("FAIL", "gateway reachable", f"{type(e).__name__}: {str(e)[:80]}",
               "check LLM_GATEWAY_BASE in scripts/.env and your network/VPN")
        return
    report("PASS", "gateway reachable", f"{u.scheme} connect in {time.time() - t:.2f}s")
    # 2) one realtime client-secret request (unique nonce inside, so the gateway cache can't answer it)
    from realtime_agent import client_secret
    t = time.time()
    try:
        key = client_secret("doctor check")
        ok = isinstance(key, str) and key.startswith("ek_")
        report("PASS" if ok else "FAIL", "realtime client secret",
               f"obtained in {time.time() - t:.1f}s" if ok else "unexpected response",
               "check that the gateway exposes /openai/v1/realtime/client_secrets")
    except urllib.error.HTTPError as e:
        fix = {401: "token rejected: update LLM_GATEWAY_TOKEN in scripts/.env",
               403: "token not allowed to use realtime: ask the gateway admin",
               429: "rate limited: wait a minute and re-run make doctor"}.get(e.code, "see scripts/README.md (gateway notes)")
        report("FAIL", "realtime client secret", f"HTTP {e.code}", fix)
    except Exception as e:
        report("FAIL", "realtime client secret", f"{type(e).__name__}: {str(e)[:80]}", "re-run make doctor; check the network")
    # 3) the realtime WebSocket goes straight to OpenAI: is it reachable (TCP only, no request)?
    host = "api.openai.com"
    if port_open(443, host, 5):
        report("PASS", "realtime host reachable", f"{host}:443")
    else:
        report("FAIL", "realtime host reachable", f"cannot connect to {host}:443", "check firewall/proxy rules")


def wait_login(secs: float) -> int:
    """Poll the login state read-only and print the next step whenever it changes. 0 = logged in."""
    end, last = time.time() + secs, None
    steps = {
        "no-tab": "Chrome has no WhatsApp tab yet (still starting?).",
        "qr": "QR code is showing. On your phone: WhatsApp > Settings > Linked devices > Link a device, "
              "then point the camera at the QR in the noVNC window.",
        "loading": "Linked! WhatsApp is loading your chats (can take a minute)...",
        "unknown": "WhatsApp is still loading...",
        "logged-in": "WhatsApp Web is logged in.",
        "no-cdp": f"Waiting for Chrome's debugging port ({CDP})...",
    }
    while True:
        try:
            state = login_state(wa_status())
        except Exception:
            state = "no-cdp"
        if state != last:
            print(time.strftime("%H:%M:%S"), steps[state], flush=True)
            last = state
        if state == "logged-in":
            return 0
        if time.time() > end:
            print(f"Still not logged in after {secs:.0f}s. Re-run: make doctor", flush=True)
            return 1
        time.sleep(3)


def main():
    global REDACT
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="skip network checks")
    ap.add_argument("--redact", action="store_true", help="hide codespace name in the output")
    ap.add_argument("--url", action="store_true", help="print the noVNC URL and exit")
    ap.add_argument("--wait-login", type=float, metavar="SECS", help="poll until WhatsApp Web is logged in")
    a = ap.parse_args()
    REDACT = a.redact
    if a.url:
        print(novnc_url())
        return 0
    if a.wait_login is not None:
        return wait_login(a.wait_login)
    print("wa-virtmic doctor (read-only)\n")
    check_binaries()
    if shutil.which("pactl"):
        check_pulse()
    check_desktop()
    check_chrome()
    check_auto_answer()
    check_gateway(a.offline)
    fails = sum(1 for s, _ in results if s == "FAIL")
    warns = sum(1 for s, _ in results if s == "WARN")
    print(f"\n{len(results)} checks: {len(results) - fails - warns} pass, {warns} warn, {fails} fail")
    if not fails:
        print("Ready. Have someone WhatsApp voice-call this account; the AI answers. Logs: scripts/auto_answer.log")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
