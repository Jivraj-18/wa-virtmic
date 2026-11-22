#!/usr/bin/env python3
"""Reproducible call bench: a WhatsApp-like call with NO WhatsApp and NO person, measured like a real call.

    python3 scripts/bench_call.py                 # one run (~70 s), then the call_diag report
    python3 scripts/bench_call.py --no-chrome     # without the Chrome mic consumer (isolates Chrome's effect)
    python3 scripts/bench_call.py --runs 3        # repeat, one summary line per run at the end

It mirrors a real call exactly, on its OWN PulseAudio devices (the WhatsApp answerer is never touched):
    bench_in        null sink 48 kHz 2ch      = callout_sink  (what the "caller" says; the AI listens to its monitor)
    bench_mic_sink  null sink 44.1 kHz 2ch    = virtmic_sink  (the AI plays here)
    bench_mic       remap of bench_mic_sink   = virtmic       (Chrome's microphone; ai.wav is recorded from it)
    bench_spk       null sink                 = Chrome's speaker
  - the same LiveAgent (GPT-Live over WebRTC) as real calls, same recorders (parecord 48 kHz mono)
  - a headless Chromium (CDP :9335, temp profile) that, like WhatsApp when a call CONNECTS, starts capturing
    bench_mic a few seconds after the AI session is up and sends it through a WebRTC loopback (encode + decode)
  - a scripted caller: TTS lines played into bench_in, each after the AI has had time to answer
  - the call_diag Sampler (phone load) during the run
Output: scripts/bench/<ts>/ with ai.wav, caller.wav, call.log, sysstats.jsonl -> call_diag.report().
Cost: OpenAI live session ~70 s + Chrome ~250 MB RAM while running.
"""
import argparse, http.server, json, os, shutil, signal, subprocess, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
BENCH = HERE / "bench"
VOICES = BENCH / "voices"
PORT = 9335
LINES = ["Hello?",
         "Hi, can you hear me okay?",
         "Can you count from one to ten for me, slowly?",
         "Okay. What is the capital of France?",
         "Great, thanks. Bye!"]

PAGE = """<!doctype html><meta charset=utf-8><title>bench</title><audio id=a autoplay></audio><script>
window.startCall = async () => {
  const s = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true,
                                                                autoGainControl: true}});
  const p1 = new RTCPeerConnection(), p2 = new RTCPeerConnection();
  p1.onicecandidate = e => e.candidate && p2.addIceCandidate(e.candidate);
  p2.onicecandidate = e => e.candidate && p1.addIceCandidate(e.candidate);
  p2.ontrack = e => { document.getElementById('a').srcObject = e.streams[0]; };
  s.getTracks().forEach(t => p1.addTrack(t, s));
  await p1.setLocalDescription(await p1.createOffer()); await p2.setRemoteDescription(p1.localDescription);
  await p2.setLocalDescription(await p2.createAnswer()); await p1.setRemoteDescription(p2.localDescription);
  window.pcs = [p1, p2, s];
  return 'call up';
};
</script>"""


def pa(*a):
    return subprocess.run(["pactl", *a], capture_output=True, text=True).stdout.strip()


def devices_up():
    pa("unload-module", "module-suspend-on-idle")
    mods = [pa("load-module", "module-null-sink", "sink_name=bench_in", "rate=48000", "channels=2"),
            pa("load-module", "module-null-sink", "sink_name=bench_mic_sink", "rate=44100", "channels=2"),
            pa("load-module", "module-null-sink", "sink_name=bench_spk", "rate=48000", "channels=2")]
    mods.append(pa("load-module", "module-remap-source", "master=bench_mic_sink.monitor", "source_name=bench_mic"))
    return [m for m in mods if m.isdigit()]


def devices_down(mods=None):
    if mods is None:  # clean up leftovers of a crashed run (only bench_* devices)
        mods = [ln.split("\t")[0] for ln in pa("list", "short", "modules").splitlines()
                if "bench_" in ln and ("sink_name=bench_" in ln or "source_name=bench_" in ln)]
    for m in reversed(mods):
        pa("unload-module", m)


def voices():
    """Caller lines as WAVs (TTS once, cached)."""
    from speak import synth_wav
    VOICES.mkdir(parents=True, exist_ok=True)
    out = []
    for i, text in enumerate(LINES):
        p = VOICES / f"line{i}.wav"
        if not p.exists():
            synth_wav(text, str(p))
        out.append((text, p))
    return out


def serve_page(d):
    (d / "index.html").write_text(PAGE)
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(d), **k)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/index.html"


def chrome_start(url, log):
    prof = Path(tempfile.mkdtemp(prefix="bench_chrome_"))
    env = dict(os.environ, PULSE_SOURCE="bench_mic", PULSE_SINK="bench_spk")
    cmd = [shutil.which("chromium") or "chromium", f"--user-data-dir={prof}", f"--remote-debugging-port={PORT}",
           "--headless=new", "--no-first-run", "--use-fake-ui-for-media-stream",
           "--autoplay-policy=no-user-gesture-required", "--log-level=3"]
    if "proot" in os.uname().release.lower():
        cmd.append("--no-sandbox")
    proc = subprocess.Popen(cmd + [url], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1).read()
            break
        except Exception:
            time.sleep(0.5)
    else:
        log("bench: Chrome did not start")
    return proc, prof


def chrome_eval(expr):
    """Evaluate JS in the bench page over CDP (Playwright, already installed); awaits promises."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        br = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        page = next(p for c in br.contexts for p in c.pages if p.url.startswith("http://127.0.0.1"))
        return page.evaluate(expr)


def chrome_stop(proc, prof):
    if proc and proc.poll() is None:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    shutil.rmtree(prof, ignore_errors=True)


def wa_load(stop, connected, log):
    """What handle_call's main thread does during a real call, against the REAL WhatsApp page, READ-ONLY:
    one page.content() when the call connects (call_ui_incall.html dump), then CALL_ACTIVE_JS + a pactl stream
    listing every 0.5 s, plus a CallerSilence parec reader. Nothing is clicked or changed."""
    import auto_answer as aa
    from playwright.sync_api import sync_playwright
    parts = os.environ.get("WL_PARTS", "sil,cdp,pactl").split(",")   # bisect which part hurts
    log(f"bench: wa-load parts {parts}")
    sil = aa.CallerSilence("bench_in.monitor") if "sil" in parts else None
    with sync_playwright() as pw:
        br = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = next(p for c in br.contexts for p in c.pages if "web.whatsapp.com" in p.url)
        connected.wait()
        if "cdp" in parts:
            t = time.time(); n = len(page.content())
            log(f"bench: wa-load page.content() {n} chars in {time.time() - t:.2f}s")
        worst = 0.0
        while not stop.is_set():
            t = time.time()
            if "cdp" in parts:
                page.evaluate(aa.CALL_ACTIVE_JS)
            if "pactl" in parts:
                aa.client_streams("source-outputs")
            worst = max(worst, time.time() - t)
            page.wait_for_timeout(500)
        log(f"bench: wa-load poll worst {worst:.2f}s")
    if sil:
        sil.stop()


def run(a):
    import call_diag
    from live_agent import LiveAgent
    d = BENCH / time.strftime("%Y%m%d_%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    logf = open(d / "call.log", "w")

    def log(*m):
        line = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in m)
        print(line, flush=True); logf.write(line + "\n"); logf.flush()

    lines = voices()
    devices_down()
    mods = devices_up()
    chrome = prof = srv = None
    recs = []
    sampler = call_diag.Sampler(d / "sysstats.jsonl").start()
    try:
        recs = [subprocess.Popen(["parecord", "--device=bench_mic", "--file-format=wav", "--format=s16le",
                                  "--rate=48000", "--channels=1", str(d / "ai.wav")]),
                subprocess.Popen(["parecord", "--device=bench_in.monitor", "--file-format=wav", "--format=s16le",
                                  "--rate=48000", "--channels=1", str(d / "caller.wav")])]
        log(f"recording -> {d}")
        log(f"bench: chrome={'off' if a.no_chrome else 'on'} wa_load={a.wa_load} connect_after={a.connect_after}s")
        if not a.no_chrome:
            srv, url = serve_page(d)
            chrome, prof = chrome_start(url, log)
        agent = LiveAgent(d / "transcript_live.txt", log=log,
                          instructions="You are a friendly AI assistant on a phone call. Keep answers short.",
                          greeting=None, in_device="bench_in.monitor", out_device="bench_mic_sink")
        log("voice engine: live")
        th = agent.start_thread(a.seconds)
        wl_stop, wl_conn = threading.Event(), threading.Event()
        wl = threading.Thread(target=wa_load, args=(wl_stop, wl_conn, log), daemon=True) if a.wa_load else None
        if wl:
            wl.start()
        t0 = time.time()
        while not getattr(agent, "t_track0", None) and time.time() - t0 < 20:
            time.sleep(0.2)
        time.sleep(a.connect_after)          # the "call connects" after the AI session is up, like WhatsApp
        if chrome:
            log(f"bench: call connected (Chrome mic capture): {chrome_eval('startCall()')}")
        wl_conn.set()
        time.sleep(2)
        for text, wav in lines:
            if not th.is_alive():
                break
            log(f"bench: caller says: {text}")
            subprocess.run(["paplay", "--device=bench_in", str(wav)])
            time.sleep(a.gap)
        wl_stop.set()
        if wl:
            wl.join(10)
        agent.stop.set()
        th.join(15)
        log(f"call ended after {time.time() - t0:.0f}s")
    finally:
        for r in recs:
            r.send_signal(signal.SIGINT)
            try:
                r.wait(5)
            except subprocess.TimeoutExpired:
                r.kill()
        sampler.close()
        chrome_stop(chrome, prof) if chrome else None
        if srv:
            srv.shutdown()
        devices_down(mods)
        logf.close()
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--no-chrome", action="store_true", help="no Chrome mic consumer")
    ap.add_argument("--wa-load", action="store_true",
                    help="also do handle_call's in-process work against the real WhatsApp page (read-only)")
    ap.add_argument("--connect-after", type=float, default=5, help="s after the AI session is up when the call connects")
    ap.add_argument("--gap", type=float, default=9, help="s after each caller line for the AI to answer")
    ap.add_argument("--seconds", type=float, default=120, help="max AI session length")
    a = ap.parse_args()
    import call_diag
    dirs = []
    for i in range(a.runs):
        d = run(a)
        dirs.append(d)
        print(); call_diag.report(d); print()
    if a.runs > 1:
        for d in dirs:
            call_diag.report(d, short=True)


if __name__ == "__main__":
    main()
