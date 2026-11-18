#!/usr/bin/env python3
"""Speak text into the virtual mic.

Usage: python scripts/speak.py "text" [--engine llmfoundry|edge] [--voice V] [--device virtmic_sink]

Engines:
  llmfoundry : Straive LLM Foundry (OpenAI-compatible /openai/v1/audio/speech, gpt-4o-mini-tts).
               Needs LLMFOUNDRY_BASE / LLMFOUNDRY_TOKEN (read from scripts/.env). Default when the token exists.
  edge       : edge-tts, voice en-IN-NeerjaNeural.
Pipeline: TTS -> MP3 -> ffmpeg decode -> paplay --device=virtmic_sink
"""
import argparse, asyncio, json, os, subprocess, sys, tempfile, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_env() -> None:
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def tts_edge(text: str, voice: str, path: str) -> None:
    import edge_tts
    asyncio.run(edge_tts.Communicate(text, voice).save(path))


def tts_llmfoundry(text: str, voice: str, path: str) -> None:
    base = os.environ["LLMFOUNDRY_BASE"].rstrip("/")
    token = os.environ["LLMFOUNDRY_TOKEN"]
    body = {"model": os.environ.get("LLMFOUNDRY_TTS_MODEL", "gpt-4o-mini-tts"),
            "voice": voice, "input": text, "response_format": "mp3",
            "instructions": "Speak clearly and warmly, like a friendly phone agent."}
    req = urllib.request.Request(
        f"{base}/openai/v1/audio/speech", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}:wa-virtmic", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r, open(path, "wb") as f:
        f.write(r.read())


def synth_wav(text: str, out_wav: str, engine: str | None = None, voice: str | None = None) -> str:
    """Synthesize text to a 48 kHz mono WAV file (so it can be pre-generated and played instantly)."""
    load_env()
    engine = engine or ("llmfoundry" if os.environ.get("LLMFOUNDRY_TOKEN") else "edge")
    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "tts.mp3")
        if engine == "llmfoundry":
            tts_llmfoundry(text, voice or "alloy", mp3)
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
    p.add_argument("--engine", choices=["llmfoundry", "edge"])
    p.add_argument("--voice")
    p.add_argument("--device", default="virtmic_sink")
    a = p.parse_args()
    return speak(a.text, a.engine, a.voice, a.device)


if __name__ == "__main__":
    sys.exit(main())
