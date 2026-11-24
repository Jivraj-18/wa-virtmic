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


def _post(path: str, model: str, extra: dict, timeout: float = 120, endpoint: str = "transcriptions") -> dict:
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
        gateway.base() + f"/openai/v1/audio/{endpoint}", data=body,
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


GEMINI_MODEL = os.environ.get("TRANSCRIBE_MODEL", "gemini-3.8-flash")
_GEMINI_PROMPT = ("Two audio tracks of one phone call with the same start time: track 1 is the AI assistant, track 2 is "
    "the CALLER. Transcribe both and write every line in ENGLISH: translate Hindi, Bhojpuri or any other language "
    "into natural English; keep English as spoken. Return ONLY JSON: a list of {\"t\": start time in SECONDS from "
    "the start as a number (75.5, not 1:15), \"who\": \"AI\" or \"CALLER\", \"text\": \"...\"}, one item per "
    "sentence, sorted by t.")


def _mp3(wav: str, out: str) -> bytes:
    """Mono 16 kHz 32 kbps mp3 (~0.24 MB/min)."""
    import subprocess
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-ac", "1", "-ar", "16000", "-b:a", "32k", out],
                   check=True)
    return open(out, "rb").read()


def gemini_call_segments(ai_wav: str, caller_wav: str, model: str = GEMINI_MODEL) -> list[tuple]:
    """Both sides in ONE Gemini request, each track its own audio part (so who said what is certain), English out.
    On the 8.5 min Hindi test call: gemini-3.8-flash 155 s and the most accurate; whisper-1 36 s but missed and
    repeated lines. Runs after the call in the background, so its speed never delays answering."""
    import base64, tempfile
    with tempfile.TemporaryDirectory() as d:
        audio = [_mp3(ai_wav, f"{d}/ai.mp3"), _mp3(caller_wav, f"{d}/caller.mp3")]
    if sum(map(len, audio)) > 18_000_000:   # inline request limit ~20 MB (~35 min per side)
        raise ValueError("call too long for an inline Gemini request")
    body = {"contents": [{"role": "user", "parts": [{"text": _GEMINI_PROMPT}] + [
                {"inline_data": {"mime_type": "audio/mp3", "data": base64.b64encode(x).decode()}} for x in audio]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    load_env()
    req = urllib.request.Request(f"{gateway.base()}/gemini/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(),
                                 headers={**gateway.auth_header(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        res = json.load(r)
    items = json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
    out = [(float(x["t"]), float(x["t"]), "AI" if str(x["who"]).upper() == "AI" else "CALLER", str(x["text"]).strip())
           for x in items if str(x.get("text", "")).strip()]
    if not out:
        raise ValueError("Gemini returned no lines")
    return sorted(out)


def whisper_call_segments(ai_wav: str, caller_wav: str) -> list[tuple]:
    """Fallback, ONE request: mix both sides, whisper-1 /audio/translations (always English) with segment times,
    label each segment AI or CALLER by which recording is louder during it."""
    import subprocess, tempfile, numpy as np
    with tempfile.TemporaryDirectory() as d:
        mix = f"{d}/call.mp3"   # ~14 MB per hour, under the 25 MB upload limit
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", ai_wav, "-i", caller_wav, "-filter_complex",
                        "amix=inputs=2:normalize=0", "-ac", "1", "-ar", "16000", "-b:a", "32k", mix], check=True)
        r = _post(mix, "whisper-1", [("response_format", "verbose_json")], timeout=600,
                  endpoint="translations")
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


def call_segments(ai_wav: str, caller_wav: str, log=print) -> list[tuple]:
    """Whole-call English transcript [(start_s, end_s, who, text)]: Gemini, else whisper-1 (one request each)."""
    try:
        return gemini_call_segments(ai_wav, caller_wav)
    except Exception as e:
        log(f"Gemini transcript failed ({type(e).__name__}: {e}) - using whisper-1")
        return whisper_call_segments(ai_wav, caller_wav)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("wav"); ap.add_argument("--model", default="gpt-4o-transcribe")
    a = ap.parse_args(); print(transcribe(a.wav, a.model))
