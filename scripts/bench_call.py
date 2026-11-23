#!/usr/bin/env python3
"""Reproducible call bench: a WhatsApp-like call with NO WhatsApp and NO person, measured like a real call.

    python3 scripts/bench_call.py                 # one run (~70 s), then the call_diag report
    python3 scripts/bench_call.py --no-chrome     # without the Chrome mic consumer (isolates Chrome's effect)
    python3 scripts/bench_call.py --runs 3        # repeat, one summary line per run at the end
    python3 scripts/bench_call.py --burn 3 --gemini   # load Chrome like WhatsApp; rate the far end with Gemini
  Fix switches (one at a time): --dither -60, --no-apm, --pulse-latency 60, --mic-rate 48000

It mirrors a real call exactly, on its OWN PulseAudio devices (the WhatsApp answerer is never touched):
    bench_in        null sink 48 kHz 2ch      = callout_sink  (what the "caller" says; the AI listens to its monitor)
    bench_mic_sink  null sink 44.1 kHz 2ch    = virtmic_sink  (the AI plays here)
    bench_mic       remap of bench_mic_sink   = virtmic       (Chrome's microphone; ai.wav is recorded from it)
    bench_spk       null sink                 = Chrome's speaker
  - the same LiveAgent (GPT-Live over WebRTC) as real calls, same recorders (parecord 48 kHz mono)
  - a headless Chromium (CDP :9335, temp profile) that, like WhatsApp when a call CONNECTS, starts capturing
    bench_mic a few seconds after the AI session is up (getUserMedia with EC/NS/AGC like WhatsApp) and sends it
    over WebRTC (Opus) to a "far end": an aiortc peer in this process that writes heard.wav on the RTP timeline
    and logs packet arrival times (arrival.jsonl). Chrome getStats every 1 s -> webrtc_stats.json.
  - a scripted caller: TTS lines played into bench_in, each after the AI has had time to answer
  - the call_diag Sampler (phone load) during the run
Output: scripts/bench/<ts>/ with ai.wav, caller.wav, call.log, sysstats.jsonl -> call_diag.report(), and
heard.wav (what the loopback receiver plays = what the far end would hear) -> audio_score (score.json).
Cost: OpenAI live session ~70 s + Chrome ~250 MB RAM while running.
"""
import argparse, json, os, shutil, signal, subprocess, sys, tempfile, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
BENCH = HERE / "bench"
VOICES = BENCH / "voices"
PORT = 9335
MIC_RATE = 44100      # virtmic_sink's rate (--mic-rate)
CHROME_EXTRA = ""     # extra Chrome flags (--chrome-args)
LINES = ["Hello?",
         "Hi, can you hear me okay?",
         "Can you count from one to ten for me, slowly?",
         "Okay. What is the capital of France?",
         "Great, thanks. Bye!"]

PAGE = """<!doctype html><meta charset=utf-8><title>bench</title><script>
// opts: apm (EC/NS/AGC), burn (busy workers), mainBusy (ms busy per 100 ms on the main thread),
//       worklet (null = Chrome's native WebRTC audio; else {rate, latencyHint}: WhatsApp-like WebAudio capture:
//       mic -> AudioContext -> AudioWorklet -> main thread -> data channel, raw 16-bit PCM)
const PROC = `class Cap extends AudioWorkletProcessor {
  constructor(o) { super(); this.n = o.processorOptions.frame; this.buf = new Float32Array(this.n); this.i = 0; }
  process(inp, out) { const x = inp[0] && inp[0][0]; if (!x) return true;
    out[0].forEach(ch => ch.set(x));   // play the mic out, like WhatsApp plays the caller (-> spk.wav gaps)
    for (let k = 0; k < x.length; k++) { this.buf[this.i++] = x[k];
      if (this.i === this.n) { this.port.postMessage(this.buf); this.buf = new Float32Array(this.n); this.i = 0; } }
    return true; } }
registerProcessor('cap', Cap);`;
window.startCall = async (o) => {
  for (let i = 0; i < (o.burn || 0); i++)
    new Worker(URL.createObjectURL(new Blob(['for(;;){let x=0;for(let i=0;i<1e7;i++)x+=Math.sqrt(i);}'])));
  if (o.mainBusy) setInterval(() => { const e = performance.now() + o.mainBusy; while (performance.now() < e); }, 100);
  const apm = o.apm !== false;
  const s = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: apm, noiseSuppression: apm,
                                                                autoGainControl: apm}});
  const track = s.getAudioTracks()[0];
  const p1 = new RTCPeerConnection();
  let ctx = null;
  if (o.worklet) {
    const dc = p1.createDataChannel('pcm');
    ctx = new AudioContext({sampleRate: o.worklet.rate || undefined, latencyHint: o.worklet.latencyHint || 'interactive'});
    await ctx.audioWorklet.addModule(URL.createObjectURL(new Blob([PROC], {type: 'text/javascript'})));
    const frame = Math.round(ctx.sampleRate / 50);
    const node = new AudioWorkletNode(ctx, 'cap', {processorOptions: {frame}});
    ctx.createMediaStreamSource(s).connect(node); node.connect(ctx.destination);
    let seq = 0;
    dc.onopen = () => dc.send(JSON.stringify({rate: ctx.sampleRate}));
    node.port.onmessage = e => { if (dc.readyState !== 'open') return;
      const f = e.data, b = new ArrayBuffer(4 + 2 * f.length), v = new DataView(b);
      v.setUint32(0, seq++, true);
      for (let k = 0; k < f.length; k++) v.setInt16(4 + 2 * k, Math.max(-32768, Math.min(32767, f[k] * 32768)), true);
      dc.send(b); };
  } else {
    s.getTracks().forEach(t => p1.addTrack(t, s));
  }
  await p1.setLocalDescription(await p1.createOffer());
  await new Promise(r => { if (p1.iceGatheringState === 'complete') r();
                           else p1.onicegatheringstatechange = () => p1.iceGatheringState === 'complete' && r(); });
  const ans = await (await fetch('/offer', {method: 'POST', body: p1.localDescription.sdp})).text();
  await p1.setRemoteDescription({type: 'answer', sdp: ans});
  window.pcs = [p1, s, ctx];
  window.statsLog = [];
  const t0 = performance.now();
  setInterval(async () => {   // every second: WebRTC sender stats, mic track stats, AudioContext playback stats
    const row = {t: (performance.now() - t0) / 1000};
    (await p1.getStats()).forEach(r => {
      if (['media-source', 'outbound-rtp'].includes(r.type) && r.kind !== 'video') row['tx:' + r.type] = r;
    });
    if (track.stats) row.track = track.stats.toJSON();
    if (ctx) row.ctx = {rate: ctx.sampleRate, base: ctx.baseLatency, out: ctx.outputLatency,
                        ps: ctx.playbackStats && ctx.playbackStats.toJSON ? ctx.playbackStats.toJSON() : null};
    window.statsLog.push(row);
  }, 1000);
  return 'call up' + (ctx ? ` (worklet ${ctx.sampleRate} Hz, base latency ${ctx.baseLatency})` : '');
};
</script>"""


def pa(*a):
    return subprocess.run(["pactl", *a], capture_output=True, text=True).stdout.strip()


def devices_up():
    pa("unload-module", "module-suspend-on-idle")
    mods = [pa("load-module", "module-null-sink", "sink_name=bench_in", "rate=48000", "channels=2"),
            pa("load-module", "module-null-sink", "sink_name=bench_mic_sink", f"rate={MIC_RATE}", "channels=2"),
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


def farend_start(d, log):
    """Serve the bench page + the far end (bench_farend.py) in their own process (not to compete with the agent)."""
    (d / "index.html").write_text(PAGE)
    p = subprocess.Popen([sys.executable, str(HERE / "bench_farend.py"), str(d)], stdout=subprocess.PIPE, text=True)
    url = p.stdout.readline().strip()
    log(f"bench: far end {url}")
    return p, url


def chrome_start(url, log, pulse_latency=None):
    prof = Path(tempfile.mkdtemp(prefix="bench_chrome_"))
    env = dict(os.environ, PULSE_SOURCE="bench_mic", PULSE_SINK="bench_spk")
    if CHROME_EXTRA:
        cmd_extra = CHROME_EXTRA.split()
    else:
        cmd_extra = []
    if pulse_latency:
        env["PULSE_LATENCY_MSEC"] = str(pulse_latency)
    cmd = [shutil.which("chromium") or "chromium", f"--user-data-dir={prof}", f"--remote-debugging-port={PORT}",
           "--headless=new", "--no-first-run", "--use-fake-ui-for-media-stream",
           "--autoplay-policy=no-user-gesture-required", "--log-level=3"]
    if "proot" in os.uname().release.lower():
        cmd.append("--no-sandbox")
    cmd += cmd_extra
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


def dither_start(sink, dbfs):
    """Constant white noise at `dbfs` RMS into `sink` (mixed under the AI's voice), so the mic never
    carries pure digital silence."""
    amp = 10 ** (dbfs / 20) * 3 ** 0.5       # uniform noise: RMS = amp / sqrt(3)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                           f"anoisesrc=r=48000:a={amp:.6f}:c=white", "-ac", "2", "-f", "s16le", "-"],
                          stdout=subprocess.PIPE)
    return subprocess.Popen(["pacat", "--playback", f"--device={sink}", "--rate=48000", "--channels=2",
                             "--format=s16le", "--latency-msec=100", "--client-name=dither"], stdin=ff.stdout)


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
    chrome = prof = far = None
    recs = []
    sampler = call_diag.Sampler(d / "sysstats.jsonl").start()
    try:
        recs = [subprocess.Popen(["parecord", "--device=bench_mic", "--file-format=wav", "--format=s16le",
                                  "--rate=48000", "--channels=1", str(d / "ai.wav")]),
                subprocess.Popen(["parecord", "--device=bench_in.monitor", "--file-format=wav", "--format=s16le",
                                  "--rate=48000", "--channels=1", str(d / "caller.wav")])]
        log(f"recording -> {d}")
        log(f"bench: chrome={'off' if a.no_chrome else 'on'} wa_load={a.wa_load} connect_after={a.connect_after}s "
            f"apm={not a.no_apm} burn={a.burn} main_busy={a.main_busy} worklet={a.worklet} ctx_rate={a.ctx_rate} "
            f"latency_hint={a.latency_hint} chrome_args={a.chrome_args!r} dither={a.dither} pulse_latency={a.pulse_latency} mic_rate={MIC_RATE}")
        if not a.no_chrome:
            far, url = farend_start(d, log)
            chrome, prof = chrome_start(url, log, a.pulse_latency)
        if a.dither is not None:
            recs.append(dither_start("bench_mic_sink", a.dither))
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
        opts = {"apm": not a.no_apm, "burn": a.burn, "mainBusy": a.main_busy,
                "worklet": {"rate": a.ctx_rate, "latencyHint": a.latency_hint} if a.worklet else None}
        if chrome:
            if a.worklet:
                recs.append(subprocess.Popen(["parecord", "--device=bench_spk.monitor", "--file-format=wav",
                                              "--format=s16le", "--rate=48000", "--channels=1", str(d / "spk.wav")]))
            log(f"bench: call connected (Chrome mic capture): "
                f"{chrome_eval('startCall(' + json.dumps(opts) + ')')}")
        wl_conn.set()
        time.sleep(2)
        for text, wav in lines:
            if not th.is_alive():
                break
            log(f"bench: caller says: {text}")
            subprocess.run(["paplay", "--device=bench_in", str(wav)])
            time.sleep(a.gap)
        if chrome:
            (d / "webrtc_stats.json").write_text(json.dumps(chrome_eval("window.statsLog")))
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
        if far:
            far.send_signal(signal.SIGTERM)
            try:
                far.wait(10)
            except subprocess.TimeoutExpired:
                far.kill()
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
    ap.add_argument("--no-apm", action="store_true", help="getUserMedia without echoCancellation/NS/AGC")
    ap.add_argument("--burn", type=int, default=0, help="busy JS workers in the bench page (CPU load like WhatsApp)")
    ap.add_argument("--dither", type=float, help="constant noise floor (dBFS) played into bench_mic_sink")
    ap.add_argument("--pulse-latency", type=int, help="PULSE_LATENCY_MSEC for the bench Chrome")
    ap.add_argument("--mic-rate", type=int, default=44100, help="bench_mic_sink rate (virtmic_sink: 44100)")
    ap.add_argument("--main-busy", type=int, default=0, help="ms of busy main thread per 100 ms (WhatsApp's main thread)")
    ap.add_argument("--worklet", action="store_true",
                    help="WhatsApp-like capture: AudioContext + AudioWorklet + data channel instead of native WebRTC")
    ap.add_argument("--ctx-rate", type=int, help="AudioContext sampleRate for --worklet (default: the device's)")
    ap.add_argument("--latency-hint", default="interactive", help="AudioContext latencyHint for --worklet "
                    "(interactive|balanced|playback or seconds)")
    ap.add_argument("--chrome-args", default="", help="extra Chrome flags, e.g. '--audio-buffer-size=2048'")
    ap.add_argument("--gemini", action="store_true", help="also rate heard.wav vs ai.wav with Gemini")
    a = ap.parse_args()
    global MIC_RATE, CHROME_EXTRA
    MIC_RATE, CHROME_EXTRA = a.mic_rate, a.chrome_args
    import audio_score
    import call_diag
    dirs = []
    for i in range(a.runs):
        d = run(a)
        dirs.append(d)
        print(); call_diag.report(d)
        if (d / "heard.wav").exists():
            r = audio_score.score(d / "ai.wav", d / "heard.wav")
            if a.gemini:
                r["gemini"] = audio_score.gemini(d / "ai.wav", d / "heard.wav")
            (d / "score.json").write_text(json.dumps(r))
            print("far end:", audio_score.line(r))
        if (d / "spk.wav").exists():   # same metric as caller.wav gaps on real calls (Chrome's output starving)
            r = json.loads((d / "score.json").read_text()) if (d / "score.json").exists() else {}
            r["spk_gaps_pct"] = round(call_diag.cutouts(d / "spk.wav")[0], 1)
            (d / "score.json").write_text(json.dumps(r))
            print(f"Chrome output gaps (like caller.wav): {r['spk_gaps_pct']}%")
        if (d / "webrtc_stats.json").exists():
            import bench_webrtc
            print(bench_webrtc.summary(d))
        print()
    if a.runs > 1:
        for d in dirs:
            call_diag.report(d, short=True)
            if (d / "score.json").exists():
                print("   far end:", audio_score.line(json.loads((d / "score.json").read_text())))


if __name__ == "__main__":
    main()
