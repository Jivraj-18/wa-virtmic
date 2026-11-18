#!/usr/bin/env python3
"""Auto-answer incoming WhatsApp Web voice calls in the noVNC Chrome and greet the caller with TTS.

Run:  python3 scripts/auto_answer.py [--greeting "..."] [--once]

How it works (via CDP on :9222, Chrome started by launch_chrome.sh):
  1. Pre-grants microphone permission to https://web.whatsapp.com (no "Allow" prompt).
  2. Watches every WhatsApp page (and popups) for the incoming-call UI and clicks Accept/Answer.
     WhatsApp's call signalling is an E2E-encrypted binary WebSocket, so the DOM is the trigger, not the network.
  3. Waits for Chrome to open its mic stream (pactl source-output), forces routing virtmic / callout_sink.
  4. Records BOTH sides for the whole call (virtmic = AI, callout_sink.monitor = caller) into calls/<ts>/:
     ai.wav, caller.wav, call_stereo.wav (L=AI R=caller), call_mix.mp3, transcript.txt (timestamped, whisper-1).
     Recording stops when the call UI and Chrome's mic stream are gone for 3 s.
On first detection it dumps the call UI HTML to call_ui_<ts>.html for debugging selectors.
"""
import argparse, asyncio, json, os, re, signal, subprocess, sys, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from speak import play_wav, synth_wav  # noqa: E402
from transcribe import segments  # noqa: E402
from realtime_agent import INSTRUCTIONS, Agent  # noqa: E402

CALLS = HERE / "calls"

GREETING = "Hello! This is an AI speaking through a virtual microphone. If you can hear me, please say yes."
ORIGIN = "https://web.whatsapp.com"

# Returns {found, label, html} for an incoming-call accept control, else {found:false}.
FIND_ACCEPT_JS = r"""() => {
  const re = /^(accept|answer)(\s+(voice\s+)?call)?$/i;
  const ctrls = [...document.querySelectorAll('button, [role="button"]')];
  for (const el of ctrls) {
    const label = (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || '').trim();
    if (re.test(label) && el.offsetParent !== null) {
      el.setAttribute('data-autoanswer', '1');
      const box = el.closest('[role="dialog"], [data-animate-modal-popup], section, div[tabindex]') || el.parentElement;
      return {found: true, label, html: (box || el).outerHTML.slice(0, 20000), text: (box || el).innerText || ''};
    }
  }
  const txt = document.body ? document.body.innerText : '';
  return {found: false, ringing: /incoming (voice |video )?call/i.test(txt)};
}"""


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def pactl_short(kind):
    out = subprocess.run(["pactl", "list", "short", kind], capture_output=True, text=True).stdout
    return [l.split("\t") for l in out.splitlines() if l.strip()]


def client_streams(kind):
    """Chrome's source-outputs / sink-inputs as [index, source_or_sink_id] (ignores our parecord/paplay and module streams)."""
    out = subprocess.run(["pactl", "-f", "json", "list", kind], capture_output=True, text=True).stdout
    res = []
    for o in json.loads(out or "[]"):
        p = o.get("properties", {})
        who = f'{p.get("application.process.binary", "")} {p.get("application.name", "")}'.lower()
        if "chrome" in who:
            res.append([str(o["index"]), str(o.get("source", o.get("sink")))])
    return res


def fix_routing() -> bool:
    subprocess.run(["pactl", "set-source-mute", "virtmic", "0"])
    subprocess.run(["pactl", "set-source-volume", "virtmic", "100%"])
    vid = next(r[0] for r in pactl_short("sources") if r[1] == "virtmic")
    sid = next(r[0] for r in pactl_short("sinks") if r[1] == "callout_sink")
    outs = client_streams("source-outputs")
    for r in outs:
        if r[1] != vid:
            log(f"moving source-output {r[0]} -> virtmic"); subprocess.run(["pactl", "move-source-output", r[0], "virtmic"])
    for r in client_streams("sink-inputs"):
        if r[1] != sid:
            log(f"moving sink-input {r[0]} -> callout_sink"); subprocess.run(["pactl", "move-sink-input", r[0], "callout_sink"])
    log("chrome source-outputs:", client_streams("source-outputs"), "sink-inputs:", client_streams("sink-inputs"))
    return bool(outs)


END_CALL_JS = r"""() => {
  const re = /^(end call|end|hang up|leave call|leave)$/i;
  const ctrls = [...document.querySelectorAll('button, [role="button"]')].filter(el => el.offsetParent !== null);
  for (const el of ctrls) {
    const l = (el.getAttribute('aria-label') || el.getAttribute('title') || el.innerText || '').trim();
    if (re.test(l)) { el.click(); return 'label:' + l; }
  }
  const bar = document.querySelector('[aria-label="Call controls"]');
  if (bar) for (const el of bar.querySelectorAll('button, [role="button"]'))
    if (el.innerHTML.includes('call-end')) { el.click(); return 'icon:call-end'; }
  return null;
}"""

END_CALL_TOOL = {"type": "function", "name": "end_call",
                 "description": "Hang up the WhatsApp call. Use ONLY when the caller asks you to end/cut the call or "
                                "clearly says goodbye. Say a short goodbye first, then call this.",
                 "parameters": {"type": "object", "properties": {}}}

CALL_ACTIVE_JS = """() => !!document.querySelector('[aria-label="Call controls"], [aria-label="End call"], [aria-label="Mute microphone"]')"""


def start_rec(device: str, path: Path) -> subprocess.Popen:
    return subprocess.Popen(["parecord", f"--device={device}", "--file-format=wav", "--format=s16le",
                             "--rate=48000", "--channels=1", str(path)])


def stop_rec(p: subprocess.Popen) -> None:
    p.send_signal(signal.SIGINT)  # parecord finalizes the WAV header on SIGINT
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()


def call_active(page) -> bool:
    try:
        ui = page.evaluate(CALL_ACTIVE_JS)
    except Exception:
        ui = False
    return ui or bool(client_streams("source-outputs"))


def handle_call(page, greeting: str, max_secs: int, mode: str = "realtime"):
    """Record BOTH sides for the whole call (accept -> hang-up) and talk to the caller, then transcribe.
    mode=realtime: live two-way conversation via OpenAI Realtime (realtime_agent.py); the live
                   transcript goes to transcript_live.txt. Falls back to the greeting if it fails to start.
    mode=greeting: play the pre-synthesized greeting WAV once (the old behaviour)."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    d = CALLS / ts
    d.mkdir(parents=True, exist_ok=True)
    ai_wav, caller_wav = d / "ai.wav", d / "caller.wav"
    recs = [start_rec("virtmic", ai_wav), start_rec("callout_sink.monitor", caller_wav)]
    t0 = time.time()
    log(f"recording call -> {d}")

    for _ in range(40):  # wait up to 20 s for Chrome to open its mic (= media flowing)
        if client_streams("source-outputs"):
            break
        time.sleep(0.5)
    if not fix_routing():
        log("WARNING: Chrome has no mic stream - call may not have connected")

    time.sleep(1.0)
    agent = th = None
    hangup = threading.Event()

    async def on_tool(name, args, ag):
        if name == "end_call":
            await asyncio.sleep(2.5)  # let the goodbye finish playing
            hangup.set()
            return {"ok": True, "status": "hanging up"}
        return {"error": f"unknown tool {name}"}

    if mode == "realtime":
        agent = Agent(transcript=d / "transcript_live.txt", log=log, tools=[END_CALL_TOOL], on_tool=on_tool,
                      instructions=INSTRUCTIONS + "\nIf the caller asks you to end or cut the call, say a one-line "
                                   "goodbye and then call the end_call tool.")
        th = agent.start_thread(max_secs)
        th.join(10)  # the thread only exits early if the realtime session failed
        if not th.is_alive():
            log("realtime agent did not start - falling back to the greeting")
            agent = th = None
    if not th:
        log("speaking greeting")
        play_wav(greeting)

    gone = 0
    dumped = clicked = False
    while time.time() - t0 < max_secs:  # record until hang-up (call UI + Chrome mic both gone for 3 s)
        if not dumped:  # keep a copy of the in-call UI for selector debugging (local, git-ignored)
            try:
                (HERE / "call_ui_incall.html").write_text(page.content()); dumped = True
            except Exception:
                pass
        if hangup.is_set() and not clicked:
            try:
                how = page.evaluate(END_CALL_JS)
            except Exception as e:
                how = f"error {e}"
            log(f"end_call requested by the agent -> clicked: {how}")
            clicked = True
        gone = 0 if call_active(page) else gone + 1
        if gone >= 6:
            break
        page.wait_for_timeout(500)
    if agent:
        agent.stop.set()
        th.join(5)
    for r in recs:
        stop_rec(r)
    dur = time.time() - t0
    log(f"call ended after {dur:.0f}s")

    # stereo file: L = AI (what we sent), R = caller (what we received); plus a mono mp3 to listen to
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(ai_wav), "-i", str(caller_wav),
                    "-filter_complex", "[0:a][1:a]join=inputs=2:channel_layout=stereo[a]", "-map", "[a]",
                    str(d / "call_stereo.wav")])
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(ai_wav), "-i", str(caller_wav),
                    "-filter_complex", "amix=inputs=2:normalize=0", "-b:a", "96k", str(d / "call_mix.mp3")])
    for w in (ai_wav, caller_wav):
        subprocess.run([sys.executable, str(HERE / "rms.py"), str(w)])

    lines = []
    for who, w in (("AI", ai_wav), ("CALLER", caller_wav)):
        try:
            lines += [(s["start"], s["end"], who, s["text"]) for s in segments(str(w)) if s["text"]]
        except Exception as e:
            lines.append((0, 0, who, f"<transcription failed: {e}>"))
    lines.sort()
    tr = d / "transcript.txt"  # offline (post-call) transcript of both recordings
    tr.write_text(f"Call {ts}  duration {dur:.0f}s\n" +
                  "".join(f"[{int(a)//60:02d}:{a%60:04.1f}] {who:6s} {t}\n" for a, _, who, t in lines))
    log("transcript ->", tr)
    print(tr.read_text(), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--greeting", default=GREETING)
    ap.add_argument("--max", type=int, default=1800, help="max seconds to record a call")
    ap.add_argument("--once", action="store_true", help="exit after the first answered call")
    ap.add_argument("--mode", choices=["realtime", "greeting"], default="realtime")
    a = ap.parse_args()

    subprocess.run([str(HERE / "audio_setup.sh")], stdout=subprocess.DEVNULL, check=True)
    greeting_wav = str(HERE / "greeting.wav")
    t = time.time()
    synth_wav(a.greeting, greeting_wav)
    log(f"greeting pre-synthesized in {time.time() - t:.1f}s -> {greeting_wav}")
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp("http://localhost:9222")
        cdp = b.new_browser_cdp_session()
        cdp.send("Browser.grantPermissions", {"origin": ORIGIN, "permissions": ["audioCapture"]})
        log("mic permission granted to", ORIGIN, "- watching for incoming calls (Ctrl+C to stop)")
        warned = False
        while True:
            pages = [p for c in b.contexts for p in c.pages if "whatsapp" in p.url]
            for p in pages:
                try:
                    r = p.evaluate(FIND_ACCEPT_JS)
                except Exception:
                    continue
                if r.get("ringing") and not warned:
                    log("page says 'incoming call' but no Accept button matched - dumping UI")
                    (HERE / f"call_ui_{time.strftime('%H%M%S')}.html").write_text(p.content())
                    warned = True
                only = os.environ.get("ANSWER_ONLY", "").strip()  # optional: answer only callers whose name contains this
                if r.get("found") and only and only.lower() not in r.get("text", "").lower():
                    if not warned:
                        log("incoming call from someone not matching ANSWER_ONLY - ignoring (not answered, not recorded)")
                        warned = True
                    continue
                if r.get("found"):
                    log(f"incoming call! clicking '{r['label']}'")
                    (HERE / "call_ui_last.html").write_text(r["html"])
                    p.locator('[data-autoanswer="1"]').first.click()
                    handle_call(p, greeting_wav, a.max, a.mode)
                    warned = False
                    if a.once:
                        return
            p0 = pages[0] if pages else None
            (p0.wait_for_timeout(500) if p0 else time.sleep(0.5))


if __name__ == "__main__":
    main()
