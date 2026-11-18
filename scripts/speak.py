#!/usr/bin/env python3
"""Speak text into the virtual mic.

Usage: python scripts/speak.py "text" [--engine gateway|edge] [--voice V] [--device virtmic_sink]

Engines:
  gateway    : OpenAI-compatible LLM gateway (/openai/v1/audio/speech, gpt-4o-mini-tts).
               Needs LLM_GATEWAY_BASE / LLM_GATEWAY_TOKEN in scripts/.env (see gateway.py). Default when set.
  edge       : edge-tts, voice en-IN-NeerjaNeural.
Pipeline: TTS -> MP3 -> ffmpeg decode -> paplay --device=virtmic_sink
"""
import argparse, asyncio, json, os, subprocess, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402
from gateway import load_env  # noqa: E402,F401  (re-exported)


def tts_edge(text: str, voice: str, path: str) -> None:
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, voice).save(path))


def tts_gateway(text: str, voice: str, path: str) -> None:
    body = {"model": os.environ.get("LLM_GATEWAY_TTS_MODEL", "gpt-4o-mini-tts"),
            "voice": voice, "input": text, "response_format": "mp3",
            "instructions": "Speak clearly and warmly, like a friendly phone agent."}
    req = urllib.request.Request(
        f"{gateway.base()}/openai/v1/audio/speech", data=json.dumps(body).encode(),
        headers={**gateway.auth_header(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())


def synth_wav(text: str, out_wav: str, engine: str | None = None, voice: str | None = None) -> str:
    """Synthesize text to a 48 kHz mono WAV file (so it can be pre-generated and played instantly)."""
    load_env()
    engine = engine or ("gateway" if gateway.has_gateway() else "edge")
    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "tts.mp3")
        if engine == "gateway":
            tts_gateway(text, voice or "alloy", mp3)
        else:
            tts_edge(text, voice or "en-IN-NeerjaNeural", mp3)
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ac", "1", "-ar", "48000", out_wav],
                       check=True)
    return out_wav


def play_wav(path: str, device: str = "virtmic_sink") -> int:
    return subprocess.run(["paplay", f"--device={device}", path]).returncode


def speak(text: str, engine: str | None = None, voice: str | None = None, device: str = "virtmic_sink") -> int:
    with tempfile.TemporaryDirectory() as d:
        return play_wav(synth_wav(text, os.path.join(d, "tts.wav"), engine, voice), device)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("text")
    p.add_argument("--engine", choices=["gateway", "edge"])
    p.add_argument("--voice")
    p.add_argument("--device", default="virtmic_sink")
    a = p.parse_args()
    return speak(a.text, a.engine, a.voice, a.device)


if __name__ == "__main__":
    sys.exit(main())
