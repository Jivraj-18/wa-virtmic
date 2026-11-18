#!/usr/bin/env python3
"""Transcribe a WAV with Straive LLM Foundry (/openai/v1/audio/transcriptions).
Usage: transcribe.py file.wav [--model gpt-4o-transcribe]"""
import argparse, json, os, uuid, urllib.request
from speak import load_env

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


def segments(path: str) -> list[dict]:
    """Timestamped segments [{start,end,text}]: VAD-split the track, transcribe each utterance."""
    import subprocess, tempfile
    out = []
    with tempfile.TemporaryDirectory() as d:
        for i, (s, e) in enumerate(utterances(path)):
            clip = f"{d}/u{i}.wav"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{s:.2f}", "-to", f"{e:.2f}",
                            "-i", path, clip], check=True)
            text = transcribe(clip).strip()
            if text:
                out.append({"start": s, "end": e, "text": text})
    return out


def transcribe(path: str, model: str = "gpt-4o-transcribe") -> str:
    return _post(path, model, {"language": "en"})["text"]


def _post(path: str, model: str, extra: dict) -> dict:
    load_env()
    b = uuid.uuid4().hex
    body = b"".join([
        f"--{b}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n{model}\r\n".encode(),
        *[f"--{b}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode() for k, v in extra.items()],
        f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.wav\"\r\nContent-Type: audio/wav\r\n\r\n".encode(),
        open(path, "rb").read(), f"\r\n--{b}--\r\n".encode()])
    req = urllib.request.Request(
        os.environ["LLMFOUNDRY_BASE"].rstrip("/") + "/openai/v1/audio/transcriptions", data=body,
        headers={"Authorization": f"Bearer {os.environ['LLMFOUNDRY_TOKEN']}:wa-virtmic",
                 "Content-Type": f"multipart/form-data; boundary={b}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("wav"); ap.add_argument("--model", default="gpt-4o-transcribe")
    a = ap.parse_args(); print(transcribe(a.wav, a.model))
