#!/usr/bin/env python3
"""E0 - simulated caller + test harness for voice agents (no human, no WhatsApp needed).

  python3 scripts/sim_call.py experiments/E0/scripts/basic_qa.yaml --tag E0

What it does
  1. Creates two private PulseAudio null sinks, suffixed with --tag:
       virtmic_<tag>  : the agent PLAYS its voice here  (agent --out-device)
       callout_<tag>  : the simulated caller's voice    (agent --in-device = callout_<tag>.monitor)
  2. Starts the agent command (default: scripts/realtime_agent.py) pointed at those devices.
  3. "Speaks" each caller line (edge-tts) into callout_<tag>, waiting for the agent's reply first
     (energy VAD on the agent's output). A line marked `interrupt: true` starts while the agent is still talking.
  4. Records both sides on one clock and writes experiments/runs/<tag>_<ts>/:
       agent.wav, caller.wav, call_stereo.wav (L = agent, R = caller), call.mp3 (small mono mix),
       transcript.txt / transcript.json (both sides, transcribe.py), agent_transcript.txt (agent's own live log),
       metrics.csv (per turn), summary.json, agent.log

Script format (YAML)
  name: basic_qa
  voice: en-IN-PrabhatNeural          # edge-tts voice for the caller (optional)
  transcribe_language: en             # STT language hint for transcript.txt (e.g. hi; null = auto)
  lines:
    - text: "Yes, I can hear you."
      pause: 0.5                      # seconds to wait after the agent finished (default 0.6)
    - text: "Stop, stop. What's two plus two?"
      interrupt: true                 # start while the agent is talking...
      after: 2.0                      # ...this many seconds after it started its reply (default 2.0)
    - text: "What's the total cost?"
      reply_timeout: 40               # optional: max wait for the agent's reply to this line (default --reply-timeout)
      until_quiet: 20                 # optional: after the reply, keep following further agent speech (e.g. a filler
                                      # "let me check" and then the real answer) until it is quiet for this many s

Agent command template placeholders: {in_device} {out_device} {transcript} {seconds} {python} {tag}
"""
import argparse, asyncio, csv, json, os, shlex, signal, statistics, subprocess, sys, tempfile, threading, time, wave
from pathlib import Path

import numpy as np
import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

RATE = 16000
FRAME = 320  # 20 ms
VAD_RMS = 200.0  # int16 RMS threshold for "someone is talking"
DEFAULT_AGENT = ("{python} scripts/realtime_agent.py --seconds {seconds} "
                 "--in-device {in_device} --out-device {out_device} --transcript {transcript}")


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- PulseAudio
class Sinks:
    def __init__(self, tag: str):
        self.agent_sink, self.caller_sink = f"virtmic_{tag}", f"callout_{tag}"
        self.modules = []

    def __enter__(self):
        subprocess.run(["pactl", "unload-module", "module-suspend-on-idle"], capture_output=True)
        existing = subprocess.run(["pactl", "list", "short", "sinks"], capture_output=True, text=True).stdout
        for name in (self.agent_sink, self.caller_sink):
            if f"\t{name}\t" in existing:
                raise SystemExit(f"sink {name} already exists - another run with this --tag is active?")
            mid = subprocess.run(["pactl", "load-module", "module-null-sink", f"sink_name={name}",
                                  f"sink_properties=device.description={name}"],
                                 capture_output=True, text=True, check=True).stdout.strip()
            self.modules.append(mid)
        return self

    def __exit__(self, *exc):
        for mid in self.modules:
            subprocess.run(["pactl", "unload-module", mid], capture_output=True)


# ---------------------------------------------------------------- recorder
class Track:
    """Raw 16 kHz mono capture of a PulseAudio source, with per-20ms RMS on a shared wall clock."""

    def __init__(self, source: str):
        self.source = source
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.proc = None
        self.t_start = None

    def start(self):
        self.proc = subprocess.Popen(["parec", f"--device={self.source}", "--raw", "--format=s16le",
                                      f"--rate={RATE}", "--channels=1", "--latency-msec=20"],
                                     stdout=subprocess.PIPE)
        self.t_start = time.time()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        while True:
            d = self.proc.stdout.read(FRAME * 2)
            if not d:
                return
            with self.lock:
                self.buf += d

    def stop(self):
        self.proc.terminate()
        self.proc.wait(5)

    def samples(self) -> np.ndarray:
        with self.lock:
            return np.frombuffer(bytes(self.buf), np.int16)

    def now(self) -> float:
        """Current position of this track in seconds of captured audio (the track's own clock).
        We never compare against the wall clock: parec can drop/delay samples, so wall time drifts."""
        with self.lock:
            return len(self.buf) / 2 / RATE

    def frames(self):
        """(times[], rms[]) per 20 ms frame, times in track seconds."""
        a = self.samples().astype(np.float64)
        n = len(a) // FRAME
        rms = np.sqrt((a[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1)) if n else np.zeros(0)
        t = np.arange(n) * FRAME / RATE
        return t, rms

    def voice_span(self, t0: float, t1: float):
        """(first, last) speech frame times within [t0, t1], else None."""
        t, r = self.frames()
        idx = np.where((t >= t0) & (t <= t1) & (r > VAD_RMS))[0]
        return (float(t[idx[0]]), float(t[idx[-1]] + FRAME / RATE)) if len(idx) else None

    def active_after(self, t0: float):
        """First frame time >= t0 with speech, else None."""
        t, r = self.frames()
        idx = np.where((t >= t0) & (r > VAD_RMS))[0]
        return float(t[idx[0]]) if len(idx) else None

    def silent_for(self, secs: float) -> bool:
        t, r = self.frames()
        k = int(secs * RATE / FRAME)
        return len(r) >= k and not (r[-k:] > VAD_RMS).any()

    def talking_now(self, window: float = 0.3) -> bool:
        return not self.silent_for(window)

    def save(self, path: Path, pad_front: float = 0.0):
        a = self.samples()
        if pad_front > 0:
            a = np.concatenate([np.zeros(int(pad_front * RATE), np.int16), a])
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(a.tobytes())


# ---------------------------------------------------------------- caller voice
def synth_lines(lines, default_voice: str, d: Path):
    import edge_tts

    async def one(text, voice, out):
        mp3 = out.with_suffix(".mp3")
        for attempt in range(4):
            try:
                await edge_tts.Communicate(text, voice).save(str(mp3))
                break
            except Exception:
                if attempt == 3:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mp3), "-ac", "1", "-ar", str(RATE), str(out)],
                       check=True)
        mp3.unlink()

    outs = []
    for i, ln in enumerate(lines):
        out = d / f"caller_line_{i:02d}.wav"
        asyncio.run(one(ln["text"], ln.get("voice", default_voice), out))
        with wave.open(str(out)) as w:
            outs.append((out, w.getnframes() / w.getframerate()))
    return outs


# ---------------------------------------------------------------- harness
def wait_until(cond, timeout: float, step: float = 0.05) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(step)
    return False


def wait_reply(agent: Track, since: float, timeout: float, silence: float) -> tuple:
    """Wait for the agent to start talking after `since`, then to stop (silence for `silence` s)."""
    first = None
    if wait_until(lambda: agent.active_after(since) is not None, timeout):
        first = agent.active_after(since)
        wait_until(lambda: agent.silent_for(silence), 60)
    return first


def wait_turn(agent: Track, since: float, ln: dict, timeout: float, silence: float):
    """wait_reply for one caller line, honouring its optional reply_timeout / until_quiet keys."""
    first = wait_reply(agent, since, float(ln.get("reply_timeout", timeout)), silence)
    if ln.get("until_quiet"):
        while wait_reply(agent, agent.now(), float(ln["until_quiet"]), silence) is not None:
            pass
    return first


def turn_metrics(agent: Track, turns, silence: float, shift: float = 0.0):
    t, r = agent.frames()
    on = r > VAD_RMS
    rows = []
    for i, tn in enumerate(turns):
        cs, ce = tn["caller_start"], tn["caller_end"]
        nxt = turns[i + 1]["caller_start"] if i + 1 < len(turns) else t[-1] + 1 if len(t) else ce + 60
        # was the agent talking when the caller started? (interruption / barge-in)
        before = on[(t >= cs - 0.3) & (t < cs)]
        talking_at_start = bool(before.any())
        stop_latency = None
        if talking_at_start:
            k = int(0.3 * RATE / FRAME)
            seg_idx = np.where(t >= cs)[0]
            for j in seg_idx:
                if j + k <= len(on) and not on[j:j + k].any():
                    stop_latency = float(t[j] - cs)
                    break
        # first agent audio after the caller finished, within this turn
        win = np.where((t > ce) & (t < nxt) & on)[0]
        first = float(t[win[0]]) if len(win) else None
        dur = None
        if first is not None:
            k = int(silence * RATE / FRAME)
            last = first
            for j in range(win[0], len(on)):
                if t[j] >= nxt:
                    break
                if on[j]:
                    last = t[j]
                elif t[j] - last >= silence:
                    break
            dur = float(last - first + FRAME / RATE)
        rows.append({
            "turn": i + 1, "caller_text": tn["text"], "interrupt": tn["interrupt"],
            "caller_start_s": round(cs + shift, 2), "caller_end_s": round(ce + shift, 2),
            "agent_talking_at_caller_start": talking_at_start,
            "agent_stop_latency_s": None if stop_latency is None else round(stop_latency, 3),
            "first_audio_latency_s": None if first is None else round(first - ce, 3),
            "reply_duration_s": None if dur is None else round(dur, 2),
        })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("script")
    ap.add_argument("--tag", default="sim", help="suffix for sink names and the run folder (e.g. E3)")
    ap.add_argument("--agent", default=DEFAULT_AGENT, help="agent command template")
    ap.add_argument("--out-root", default=str(ROOT / "experiments" / "runs"))
    ap.add_argument("--greeting-timeout", type=float, default=20)
    ap.add_argument("--reply-timeout", type=float, default=20)
    ap.add_argument("--silence", type=float, default=1.2, help="agent silence (s) that ends a reply")
    ap.add_argument("--max-seconds", type=int, default=300)
    ap.add_argument("--no-transcribe", action="store_true")
    a = ap.parse_args()

    spec = yaml.safe_load(Path(a.script).read_text())
    lines = spec["lines"]
    name = spec.get("name", Path(a.script).stem)
    run = Path(a.out_root) / f"{a.tag}_{name}_{time.strftime('%Y%m%d_%H%M%S')}"
    run.mkdir(parents=True, exist_ok=True)
    log(f"run -> {run}")

    with tempfile.TemporaryDirectory() as tmp:
        clips = synth_lines(lines, spec.get("voice", "en-IN-PrabhatNeural"), Path(tmp))
        log(f"synthesized {len(clips)} caller lines")
        with Sinks(a.tag) as sk:
            agent_tr = Track(f"{sk.agent_sink}.monitor")
            caller_tr = Track(f"{sk.caller_sink}.monitor")
            agent_tr.start(); caller_tr.start()
            cmd = a.agent.format(python=shlex.quote(sys.executable), in_device=f"{sk.caller_sink}.monitor",
                                 out_device=sk.agent_sink, transcript=shlex.quote(str(run / "agent_transcript.txt")),
                                 seconds=a.max_seconds, tag=a.tag)
            log("agent:", cmd)
            agent_log = open(run / "agent.log", "w")
            agent = subprocess.Popen(cmd, shell=True, cwd=ROOT, stdout=agent_log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            turns = []
            try:
                g0 = agent_tr.now()
                first = wait_reply(agent_tr, g0, a.greeting_timeout, a.silence)
                log("greeting:", "none" if first is None else f"started {first - g0:.2f}s after launch")
                for i, (ln, (clip, dur)) in enumerate(zip(lines, clips)):
                    if agent.poll() is not None:
                        log("agent exited early"); break
                    interrupt = bool(ln.get("interrupt"))
                    if interrupt:
                        since = turns[-1]["caller_end"] if turns else g0
                        if not wait_until(lambda: agent_tr.active_after(since) is not None, a.reply_timeout):
                            log(f"turn {i + 1}: agent never started talking - playing anyway")
                        else:
                            time.sleep(float(ln.get("after", 2.0)))
                    else:
                        if turns:
                            wait_turn(agent_tr, turns[-1]["caller_end"], lines[i - 1], a.reply_timeout, a.silence)
                        time.sleep(float(ln.get("pause", 0.6)))
                    a_cs, c_cs = agent_tr.now(), caller_tr.now()
                    subprocess.run(["paplay", f"--device={sk.caller_sink}", str(clip)], check=True)
                    time.sleep(0.15)  # let the last caller samples arrive
                    a_ce, c_ce = agent_tr.now(), caller_tr.now()
                    # the clip has leading/trailing silence: find the real speech in the caller track,
                    # then map it onto the agent track via the offsets measured at the same instants
                    span = caller_tr.voice_span(c_cs, c_ce)
                    vs, ve = span if span else (c_cs, c_ce)
                    cs = a_cs + (vs - c_cs)
                    ce = a_ce - (c_ce - ve)
                    turns.append({"text": ln["text"], "interrupt": interrupt, "caller_start": cs, "caller_end": ce,
                                  "t0": g0})
                    log(f"turn {i + 1}{' (interrupt)' if interrupt else ''}: caller spoke {ve - vs:.1f}s: {ln['text']}")
                if turns:
                    wait_turn(agent_tr, turns[-1]["caller_end"], lines[len(turns) - 1], a.reply_timeout, a.silence)
                time.sleep(1.0)
            finally:
                try:
                    os.killpg(agent.pid, signal.SIGINT)
                    agent.wait(8)
                except Exception:
                    try:
                        os.killpg(agent.pid, signal.SIGKILL)
                    except Exception:
                        pass
                agent_log.close()
                agent_tr.stop(); caller_tr.stop()

    # ---- outputs -------------------------------------------------------
    # align: both recorders stopped at the same instant, so pad the shorter track at the front.
    # The agent track's clock is the reference for metrics; caller events were mapped onto it.
    la, lc = len(agent_tr.samples()) / RATE, len(caller_tr.samples()) / RATE
    agent_tr.save(run / "agent.wav", max(0.0, lc - la))
    caller_tr.save(run / "caller.wav", max(0.0, la - lc))
    shift = max(0.0, lc - la)  # agent-track time + shift = time in the saved files
    ff = ["ffmpeg", "-loglevel", "error", "-y", "-i", str(run / "agent.wav"), "-i", str(run / "caller.wav")]
    subprocess.run(ff + ["-filter_complex", "[0:a][1:a]join=inputs=2:channel_layout=stereo[a]", "-map", "[a]",
                         str(run / "call_stereo.wav")], check=True)
    subprocess.run(ff + ["-filter_complex", "amix=inputs=2:normalize=0:duration=longest", "-ac", "1",
                         "-b:a", "32k", str(run / "call.mp3")], check=True)

    rows = turn_metrics(agent_tr, turns, a.silence, shift) if turns else []
    with open(run / "metrics.csv", "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)

    lat = [r["first_audio_latency_s"] for r in rows if r["first_audio_latency_s"] is not None and not
           (r["agent_talking_at_caller_start"] and r["agent_stop_latency_s"] is None)]
    stops = [r["agent_stop_latency_s"] for r in rows if r["agent_stop_latency_s"] is not None]

    def pct(v, p):
        return None if not v else round(float(np.percentile(v, p)), 3)

    summary = {
        "script": name, "tag": a.tag, "turns": len(rows), "agent_cmd": a.agent,
        "replied_turns": sum(r["first_audio_latency_s"] is not None for r in rows),
        "latency_median_s": pct(lat, 50), "latency_p90_s": pct(lat, 90),
        "interruptions": sum(r["interrupt"] for r in rows),
        "barge_in_stop_median_s": pct(stops, 50),
        "barge_ins_handled": sum(1 for r in rows if r["interrupt"] and r["agent_stop_latency_s"] is not None
                                 and r["agent_stop_latency_s"] < 1.5),
    }

    if not a.no_transcribe:
        from transcribe import segments
        items = []
        for who, f in (("AGENT", "agent.wav"), ("CALLER", "caller.wav")):
            try:
                items += [{"t": round(s["start"], 2), "end": round(s["end"], 2), "who": who, "text": s["text"]}
                          for s in segments(str(run / f), spec.get("transcribe_language", "en"))]
            except Exception as e:
                items.append({"t": 0, "end": 0, "who": who, "text": f"<transcription failed: {e}>"})
        items.sort(key=lambda x: x["t"])
        (run / "transcript.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
        (run / "transcript.txt").write_text("".join(
            f"[{int(x['t']) // 60:02d}:{x['t'] % 60:04.1f}] {x['who']:6s} {x['text']}\n" for x in items))

    (run / "summary.json").write_text(json.dumps(summary, indent=1))
    log("summary:", json.dumps(summary))
    for r in rows:
        log(f"  turn {r['turn']}: latency={r['first_audio_latency_s']}s reply={r['reply_duration_s']}s "
            f"talking_at_start={r['agent_talking_at_caller_start']} stop={r['agent_stop_latency_s']}s")
    if (run / "transcript.txt").exists():
        print((run / "transcript.txt").read_text())
    print(run)


if __name__ == "__main__":
    main()
