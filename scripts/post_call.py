#!/usr/bin/env python
"""Everything after a call ends, in its OWN process, so the answerer is watching for the next call at once.

auto_answer.handle_call() starts this detached (own session, low priority) and returns right after hang-up. Rule:
nothing slow (transcription, Claude wrap-up, mp3s) ever runs in the answerer: a caller who rang back 40 s after
hanging up (2026-11-24) was never answered while the answerer was busy transcribing. A crash or hang here can't
touch the answerer, and this keeps going if the answerer restarts.

    python scripts/post_call.py calls/20261124_114100 [--wrapup] [--context PATH --caller NAME] [--dur 167]

  --wrapup  Claude's after-call turn (notes, anything promised, escalation, summary) - claude_tool.finish()
  then      stereo wav + mp3, RMS check, English transcript (transcribe.call_segments), context summary.
Output goes to the caller's stdout (the answerer's log).
"""
import argparse, subprocess, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def log(*a):
    print(time.strftime("%H:%M:%S"), "post-call:", *a, flush=True)


def media(d: Path, ai_wav: Path, caller_wav: Path):
    # stereo file: L = AI (what we sent), R = caller (what we received); plus a mono mp3 to listen to
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(ai_wav), "-i", str(caller_wav),
                    "-filter_complex", "[0:a][1:a]join=inputs=2:channel_layout=stereo[a]", "-map", "[a]",
                    str(d / "call_stereo.wav")])
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(ai_wav), "-i", str(caller_wav),
                    "-filter_complex", "amix=inputs=2:normalize=0", "-b:a", "96k", str(d / "call_mix.mp3")])
    for w in (ai_wav, caller_wav):
        subprocess.run([sys.executable, str(HERE / "rms.py"), str(w)])


def transcript(d: Path, ai_wav: Path, caller_wav: Path, dur: float):
    from transcribe import call_segments, segments
    t = time.time()
    try:   # one request for the whole call, English
        lines = call_segments(str(ai_wav), str(caller_wav), log)
    except Exception as e:
        log(f"one-shot transcript failed ({type(e).__name__}: {e}) - falling back to per-utterance")
        lines = []
        for who, w in (("AI", ai_wav), ("CALLER", caller_wav)):
            try:
                lines += [(s["start"], s["end"], who, s["text"]) for s in segments(str(w)) if s["text"]]
            except Exception as e2:
                lines.append((0, 0, who, f"<transcription failed: {e2}>"))
    lines.sort()
    tr = d / "transcript.txt"  # offline (post-call) transcript of both recordings
    tr.write_text(f"Call {d.name}  duration {dur:.0f}s\n" +
                  "".join(f"[{int(a)//60:02d}:{a % 60:04.1f}] {who:6s} {x}\n" for a, _, who, x in lines))
    log(f"transcript in {time.time() - t:.1f}s -> {tr}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("call_dir")
    ap.add_argument("--wrapup", action="store_true")
    ap.add_argument("--context")
    ap.add_argument("--caller")
    ap.add_argument("--dur", type=float, default=0)
    ap.add_argument("--no-media", action="store_true", help="no recording / low disk: wrap-up only")
    a = ap.parse_args()
    d = Path(a.call_dir).resolve()
    ai_wav, caller_wav = d / "ai.wav", d / "caller.wav"
    wrap = None
    if a.wrapup:   # Claude wrap-up alongside the transcript (it reads the live transcript, not this one)
        import claude_tool
        wrap = threading.Thread(target=claude_tool.finish, args=(d, log), name="claude-wrapup")
        wrap.start()
    if not a.no_media:
        try:
            media(d, ai_wav, caller_wav)
            transcript(d, ai_wav, caller_wav, a.dur)
        except Exception as e:
            log(f"failed: {type(e).__name__}: {e}")
        if a.context:
            try:
                from context import load_context
                from call_summary import summarize
                log("summary ->", summarize(d, load_context(a.context), a.caller))
            except Exception as e:
                log(f"summary failed: {type(e).__name__}: {e}")
    if wrap:
        wrap.join()
    log("done")


if __name__ == "__main__":
    main()
