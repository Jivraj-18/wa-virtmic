#!/usr/bin/env python3
"""Transcribe a WAV via the OpenAI-compatible LLM gateway (/openai/v1/audio/transcriptions).
Usage: transcribe.py file.wav [--model gpt-4o-transcribe]"""
import argparse, json, os, uuid, urllib.request
import gateway
from gateway import load_env

def utterances(path: str, thresh: float = 200.0, gap: float = 0.8, min_len: float = 0.2):
    """Energy VAD: [(start_s, end_s)] of speech regions in a 16-bit mono WAV."""
    import wave, numpy as np
    with wave.open(path) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
    hop = int(sr * 0.03)
    n = len(a) // hop
    if n == 0:
        return []
    rms = np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(axis=1))
    regs, start, last = [], None, None
    for i, on in enumerate(rms > thresh):
        t = i * hop / sr
        if on:
            if start is None:
                start = t
            last = t + hop / sr
        elif start is not None and t - last > gap:
            regs.append((start, last)); start = None
    if start is not None:
        regs.append((start, last))
    return [(max(0, s - 0.2), e + 0.2) for s, e in regs if e - s >= min_len]


def segments(path: str, language: str | None = "en") -> list[dict]:
    """Timestamped segments [{start,end,text}]: VAD-split the track, transcribe each utterance."""
    import subprocess, tempfile
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i, (s, e) in enumerate(utterances(path)):
            clip = f"{d}/u{i}.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{s:.2f}", "-to", f"{e:.2f}",
                            "-i", path, clip], check=True)
            text = transcribe(clip, language=language).strip()
            if text:
                out.append({"start": s, "end": e, "text": text})
    return out


def transcribe(path: str, model: str = "gpt-4o-transcribe", language: str | None = "en") -> str:
    return _post(path, model, {"language": language} if language else {})["text"]


def _post(path: str, model: str, extra: dict, timeout: float = 120) -> dict:
    load_env()
    b = uuid.uuid4().hex
    name, ctype = ("a.mp3", "audio/mpeg") if path.endswith(".mp3") else ("a.wav", "audio/wav")
    fields = list(extra.items()) if isinstance(extra, dict) else list(extra)
    body = b"".join([
        f"--{b}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
        *[f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in fields],
        f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: {ctype}\r\n\r\n".encode(),
        open(path, "rb").read(), f"\r\n--{b}--\r\n".encode()])
    req = urllib.request.Request(
        gateway.base() + "/openai/v1/audio/transcriptions", data=body,
        headers={**gateway.auth_header(),
                 "Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _rms_track(path: str):
    """(rms per 10 ms frame, frames per second) of a 16-bit mono WAV."""
    import wave, numpy as np
    with wave.open(path) as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32)
    hop = max(1, sr // 100)
    n = len(a) // hop
    return np.sqrt((a[: n * hop].reshape(n, hop) ** 2).mean(axis=1)), 100


def call_segments(ai_wav: str, caller_wav: str, model: str = "whisper-1") -> list[tuple]:
    """Whole-call transcript in ONE request: mix both sides into one small mp3, transcribe it with segment
    timestamps, then label each segment AI or CALLER by which recording is louder during it.
    [(start_s, end_s, who, text)]. (Per-utterance requests, one after another, took ~half the call's length;
    this takes a few seconds: 2.8 min call -> 3.5-15 s.) Language is auto-detected (Hindi callers too)."""
    import subprocess, tempfile, numpy as np
    with tempfile.TemporaryDirectory() as d:
        mix = f"{d}/call.mp3"   # mono 16 kHz 32 kbps: ~14 MB per hour, under the 25 MB upload limit
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", ai_wav, "-i", caller_wav, "-filter_complex",
                        "amix=inputs=2:normalize=0", "-ac", "1", "-ar", "16000", "-b:a", "32k", mix], check=True)
        r = _post(mix, model, [("response_format", "verbose_json"), ("timestamp_granularities[]", "segment")],
                  timeout=600)
    ai, fps = _rms_track(ai_wav)
    caller, _ = _rms_track(caller_wav)
    out = []
    for sg in r.get("segments", []):
        text = sg.get("text", "").strip()
        if not text:
            continue
        a, b = int(sg["start"] * fps), max(int(sg["end"] * fps), int(sg["start"] * fps) + 1)
        e_ai = float(np.mean(ai[a:b])) if a < len(ai) else 0.0
        e_ca = float(np.mean(caller[a:b])) if a < len(caller) else 0.0
        out.append((sg["start"], sg["end"], "AI" if e_ai >= e_ca else "CALLER", text))
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("wav"); ap.add_argument("--model", default="gpt-4o-transcribe")
    a = ap.parse_args(); print(transcribe(a.wav, a.model))
