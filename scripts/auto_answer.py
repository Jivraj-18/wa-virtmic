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
On first detection it dumps the call UI HTML to call_ui_ringing.html for debugging selectors (overwritten each time).
Storage (diskguard.py): calls/ is pruned oldest-first to CALLS_MAX_MB before each call; below DISK_MIN_FREE_GB free,
recordings and debug dumps are skipped (or stopped mid-call) - the call is still answered.
"""
import argparse, asyncio, json, os, re, signal, subprocess, sys, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from speak import play_wav, synth_wav  # noqa: E402
from transcribe import segments  # noqa: E402
from realtime_agent import INSTRUCTIONS, Agent  # noqa: E402
import diskguard  # noqa: E402

CALLS = HERE / "calls"

GREETING = "Hello! You've reached an AI assistant. How can I help you?"
GREETING_SAID = GREETING  # what greeting.wav says (set from --greeting in main)
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
      return {found: true, label, html: (box || el).outerHTML.slice(0, 20000), text: (box || el).innerText.slice(0, 500)};
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
        if "chrom" in who:  # Google Chrome ("chrome") and Debian/Termux Chromium ("chromium")
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

CALL_ACTIVE_JS = """() => !!document.querySelector('[aria-label="Call controls"], [aria-label="End call"], [aria-label="End icon button"], [aria-label="Mute microphone"], [aria-label="Unmute microphone"]')"""
# WhatsApp Web muted our mic by itself mid-call (2026-11-23: "Mute microphone" when answered, "Unmute microphone"
# 18 s later; the other phone showed "muted" and heard nothing). Nothing of ours clicks it, so on every poll: if the
# call shows "Unmute microphone", click it (and log when, to learn what triggers it).
UNMUTE_JS = r"""() => {
  const b = [...document.querySelectorAll('[aria-label="Unmute microphone"]')].find(el => el.offsetParent !== null);
  if (!b) return false;
  b.click(); return true;
}"""


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


DEAD_AIR_SECS = float(os.environ.get("DEAD_AIR_SECS", "30"))


class CallerSilence:
    """Seconds since the caller side last carried ANY signal. A live WhatsApp call always has some noise; exact
    digital zero means the remote side is gone. Real calls showed up to 12 s of zeros mid-call (silence
    suppression), so the default limit is 30 s. Backstop for when WhatsApp Web's call UI / mic stream lingers after
    the other side hangs up (happened: a 27 s call was held "active" for 6 min, blocking new calls)."""

    def __init__(self, device="callout_sink.monitor"):
        self.last = time.time()
        self.p = subprocess.Popen(["parec", f"--device={device}", "--raw", "--format=s16le", "--rate=8000",
                                  "--channels=1", "--latency-msec=100"], stdout=subprocess.PIPE)
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        import array
        while True:
            b = self.p.stdout.read(800)  # 50 ms
            if not b:
                return
            if any(array.array("h", b[: len(b) // 2 * 2])):
                self.last = time.time()

    def silent_for(self) -> float:
        return time.time() - self.last

    def stop(self):
        self.p.kill()


def route_when_ready():
    for _ in range(40):  # wait up to 20 s for Chrome to open its mic (= media flowing)
        if client_streams("source-outputs"):
            break
        time.sleep(0.5)
    if not fix_routing():
        log("WARNING: Chrome has no mic stream - call may not have connected")


def handle_call(page, greeting: str, max_secs: int, mode: str = "realtime", context: str | None = None,
                caller: str | None = None, speak_first: bool = True, extra_instructions: str = "",
                engine: str | None = None):
    """Record BOTH sides for the whole call (accept -> hang-up) and talk to the caller, then transcribe.
    speak_first=False: the live agent stays silent until the other person speaks (outgoing calls: wa_call.py),
                       so it doesn't greet a phone that is still ringing.
    mode=realtime: live two-way conversation via OpenAI Realtime (realtime_agent.py); the live
                   transcript goes to transcript_live.txt. Falls back to the greeting if it fails to start.
    mode=greeting: play the pre-synthesized greeting WAV once (the old behaviour).
    context      : E1 call-center folder (context.py). Re-read on every call; the agent is built from it and
                   summary.md is written after the call."""
    ctx = None
    if context:
        from context import load_context
        ctx = load_context(context)
        max_secs = int(ctx["config"].get("max_call_seconds") or max_secs)
    ts = time.strftime("%Y%m%d_%H%M%S")
    for old in diskguard.prune_dirs(CALLS):
        log(f"disk: removed old call {old.name} (calls/ over {diskguard.CALLS_MAX_MB:g} MB)")
    d = CALLS / ts
    d.mkdir(parents=True, exist_ok=True)
    ai_wav, caller_wav = d / "ai.wav", d / "caller.wav"
    if diskguard.low(CALLS):
        log(f"WARNING disk: only {diskguard.free_gb(CALLS):.1f} GB free (< {diskguard.MIN_FREE_GB:g} GB) - "
            "answering WITHOUT recording")
        recs = []
    else:
        recs = [start_rec("virtmic", ai_wav), start_rec("callout_sink.monitor", caller_wav)]
    t0 = time.time()
    log(f"{'recording' if recs else 'call (not recorded)'} -> {d}")
    try:  # phone load during the call (CPU, swap, syscall latency) -> sysstats.jsonl, read by call_diag.py
        from call_diag import Sampler
        sampler = Sampler(d / "sysstats.jsonl").start()
    except Exception as e:
        sampler = None
        log(f"sysstats sampler not started: {type(e).__name__}: {e}")
    if ctx:
        (d / "call_meta.json").write_text(json.dumps({"caller": caller, "context": ctx["path"]}))

    agent = th = None
    hangup = threading.Event()
    # The SCRIPT decides when to hang up (hangup.py watches the transcript); the AI only has to say goodbye.
    # It used to rely on the model calling an end_call tool, which it often "promised" but never did.
    from hangup import HangupWatcher
    watcher = HangupWatcher(lambda reason: hangup.set(), log=log)

    async def on_tool(name, args, ag):
        if name == "end_call":
            await asyncio.sleep(2.5)  # let the goodbye finish playing
            hangup.set()
            return {"ok": True, "status": "hanging up"}
        return {"error": f"unknown tool {name}"}

    instant_greeting = False
    if mode == "realtime":
        hang = ("\nIf the caller asks you to end or cut the call, say ONE short goodbye line and stop talking - "
                "the call is hung up automatically after your goodbye. Never say goodbye otherwise.")
        if ctx:
            from context import make_agent, build_instructions
            import tools  # E2: search_knowledge / read_file / ask_agent over the context folder, with holding lines
            e2 = tools.agent_kwargs(ctx["path"], d, log=log)
            agent = make_agent(ctx, caller, extra={
                "tools": e2["tools"],
                "on_line": watcher.feed,
                "on_tool": tools.chain_on_tool(e2["on_tool"], on_tool),  # E2 returns None for end_call
                "on_event": e2["on_event"],  # needed for the holding-line logic
                "instructions": build_instructions(ctx, caller) + hang + e2["instructions_suffix"]},
                transcript=d / "transcript_live.txt", log=log)
        else:
            kw = {} if speak_first else {"greeting": None}
            engine = engine or os.environ.get("VOICE_ENGINE", "realtime")
            AgentCls = Agent
            if engine == "live":  # full-duplex GPT-Live over WebRTC (live_agent.py)
                from live_agent import LiveAgent as AgentCls
                if speak_first:
                    # GPT-Live decides itself when to talk and has waited up to ~20 s before greeting (plus a slow
                    # session start) - callers hung up in the silence. So the recorded greeting plays the moment
                    # Chrome's mic is up, and the model is told it has already been said.
                    kw["greeting"] = (f'You have ALREADY greeted the caller with this recorded line: "{GREETING_SAID}". '
                                      "Don't greet again; wait for their reply and continue from there.")
                    instant_greeting = True
            log(f"voice engine: {engine}")
            agent = AgentCls(transcript=d / "transcript_live.txt", log=log, on_line=watcher.feed,
                          instructions=INSTRUCTIONS + hang + extra_instructions, **kw)
        th = agent.start_thread(max_secs)
        # Mic wait + stream routing now run WHILE the agent connects (ICE + session setup take seconds); before,
        # they ran first and the caller heard ~15 s of silence after we picked up.
        route_when_ready()
        if instant_greeting:
            log("playing the recorded greeting now (the live model was told it has been said)")
            threading.Thread(target=play_wav, args=(greeting,), daemon=True).start()
        th.join(10)  # the thread only exits early if the realtime session failed
        if not th.is_alive():
            log("realtime agent did not start - falling back to the greeting")
            agent = th = None
    if not th:
        route_when_ready()
        if not instant_greeting:  # already played when the live agent started
            log("speaking greeting")
            play_wav(greeting)

    gone = n = unmutes = 0
    dumped = clicked = False
    silence = CallerSilence()
    recorded = bool(recs)
    while time.time() - t0 < max_secs:  # record until hang-up (call UI + Chrome mic both gone for 3 s)
        n += 1
        beat()
        if recs and n % 20 == 0 and diskguard.low(CALLS):  # ~every 10 s
            log(f"WARNING disk: free space fell to {diskguard.free_gb(CALLS):.1f} GB - stopping the recording "
                "(call continues)")
            for r in recs:
                stop_rec(r)
            recs = []
        if not dumped and not diskguard.low(HERE):  # in-call UI copy for selector debugging (local, git-ignored)
            try:
                (HERE / "call_ui_incall.html").write_text(page.content()); dumped = True
            except Exception:
                pass
        if hangup.is_set() and not clicked:
            try:
                how = page.evaluate(END_CALL_JS)
            except Exception as e:
                how = f"error {e}"
            log(f"hang-up requested -> clicked: {how}")
            clicked = True
        try:
            if page.evaluate(UNMUTE_JS):
                unmutes += 1
                log(f"WhatsApp had MUTED our mic ({time.time() - t0:.1f}s into the call) - clicked Unmute (#{unmutes})")
        except Exception:
            pass
        gone = 0 if call_active(page) else gone + 1
        if gone >= 6:
            break
        if silence.silent_for() > DEAD_AIR_SECS:
            try:
                how = page.evaluate(END_CALL_JS)
            except Exception as e:
                how = f"error {e}"
            log(f"caller audio has been digital silence for {DEAD_AIR_SECS:g}s - treating the call as over "
                f"(end call: {how})")
            break
        page.wait_for_timeout(500)
    else:  # max_secs reached: hang up, or the caller is left on a live call with nobody talking (2026-11-23)
        try:
            how = page.evaluate(END_CALL_JS)
        except Exception as e:
            how = f"error {e}"
        log(f"max call length {max_secs}s reached - ending the call (end call: {how})")
    silence.stop()
    if agent:
        agent.stop.set()
        th.join(5)
    for r in recs:
        stop_rec(r)
    if sampler:
        sampler.close()
    dur = time.time() - t0
    log(f"call ended after {dur:.0f}s")
    try:  # keep this call's log lines next to its recording (wa_call_<who>.log is overwritten by the next call)
        import call_diag
        _, lines = call_diag.find_log(d)
        if lines:
            (d / "call.log").write_text("\n".join(lines) + "\n")
    except Exception as e:
        log(f"call.log not saved: {type(e).__name__}: {e}")
    if not recorded or diskguard.low(CALLS):
        log("disk: skipping stereo/mp3/offline transcript (no recording or low space); live transcript: "
            f"{d / 'transcript_live.txt'}")
        return

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
    if ctx:
        try:
            from call_summary import summarize
            log("summary ->", summarize(d, ctx, caller))
        except Exception as e:
            log(f"summary failed: {type(e).__name__}: {e}")


HEARTBEAT = os.environ.get("AA_HEARTBEAT")  # answer_daemon.sh: file touched while we're alive and not stuck


def beat():
    if HEARTBEAT:
        try:
            Path(HEARTBEAT).touch()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--greeting", default=GREETING)
    ap.add_argument("--max", type=int, default=1800, help="max seconds to record a call")
    ap.add_argument("--once", action="store_true", help="exit after the first answered call")
    ap.add_argument("--mode", choices=["realtime", "greeting"], default="realtime")
    ap.add_argument("--context", help="E1 call-center folder (see context.py); reloaded on every call")
    a = ap.parse_args()

    # One answerer per machine: two would both click Accept and run two AIs talking over each other on one call
    # (happened once when a supervisor lost track of an orphaned copy). The lock dies with the process.
    import fcntl
    lock_path = Path(os.environ.get("AA_LOCK", Path.home() / ".cache/wa-virtmic/auto_answer.lock"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    global _lock_fd
    _lock_fd = open(lock_path, "w")
    try:
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log(f"another auto_answer.py already holds {lock_path} - exiting")
        sys.exit(4)

    subprocess.run([str(HERE / "audio_setup.sh")], stdout=subprocess.DEVNULL, check=True)
    if os.environ.get("VOICE_ENGINE", "realtime") == "live":
        t = time.time()
        import live_agent, aiortc, av  # noqa: F401  ~8 s on the phone: do it now, not after accepting a call
        log(f"live engine libraries preloaded in {time.time() - t:.1f}s")
    greeting_wav = str(HERE / "greeting.wav")
    t = time.time()
    global GREETING_SAID
    GREETING_SAID = a.greeting
    synth_wav(a.greeting, greeting_wav)
    log(f"greeting pre-synthesized in {time.time() - t:.1f}s -> {greeting_wav}")
    with sync_playwright() as pw:
        b = pw.chromium.connect_over_cdp("http://localhost:9222")
        cdp = b.new_browser_cdp_session()
        cdp.send("Browser.grantPermissions", {"origin": ORIGIN, "permissions": ["audioCapture"]})
        log("mic permission granted to", ORIGIN, "- watching for incoming calls (Ctrl+C to stop)")
        import mic_apm
        apm_ctx = set()   # browser contexts that already have the getUserMedia hook (see mic_apm.py)
        warned = False
        while True:
            beat()
            if not b.is_connected():  # Chrome died/restarted: exit so the supervisor restarts us cleanly
                log("lost the CDP connection to Chrome - exiting")
                sys.exit(3)
            pages = [p for c in b.contexts for p in c.pages if "whatsapp" in p.url]
            for p in pages:
                if id(p.context) not in apm_ctx:   # once per context, even if it failed (no log spam)
                    mic_apm.install(p, log)
                    apm_ctx.add(id(p.context))
            for p in pages:
                try:
                    r = p.evaluate(FIND_ACCEPT_JS)
                except Exception:
                    continue
                if r.get("ringing") and not warned:
                    log("page says 'incoming call' but no Accept button matched - dumping UI")
                    if not diskguard.low(HERE):  # one file, overwritten (was call_ui_<time>.html, ~2 MB each)
                        (HERE / "call_ui_ringing.html").write_text(p.content())
                    warned = True
                only = os.environ.get("ANSWER_ONLY", "").strip()  # optional: answer only callers whose name contains this
                if r.get("found") and only and only.lower() not in r.get("text", "").lower():
                    if not warned:
                        log("incoming call from someone not matching ANSWER_ONLY - ignoring (not answered, not recorded)")
                        warned = True
                    continue
                caller = None
                if r.get("found") and a.context:
                    from context import caller_allowed, caller_from_text, load_context
                    caller = caller_from_text(r.get("text"))
                    if not caller_allowed(load_context(a.context), caller):
                        if not warned:
                            log(f"incoming call from {caller!r} not in answer_only - leaving it ringing")
                            warned = True
                        continue
                if r.get("found"):
                    log(f"incoming call! clicking '{r['label']}'" + (f" (caller {caller!r})" if caller else ""))
                    (HERE / "call_ui_last.html").write_text(r["html"])
                    p.locator('[data-autoanswer="1"]').first.click()
                    handle_call(p, greeting_wav, a.max, a.mode, a.context, caller)
                    warned = False
                    if a.once:
                        return
            p0 = pages[0] if pages else None
            (p0.wait_for_timeout(500) if p0 else time.sleep(0.5))


if __name__ == "__main__":
    main()
