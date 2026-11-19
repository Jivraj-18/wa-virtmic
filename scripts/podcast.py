#!/usr/bin/env python3
"""E5 Mode B: a short two-host podcast generated from a knowledge/ folder.

  1. LLM (gateway chat completions) writes a two-host script as JSON from the knowledge files.
  2. Each line is synthesized with one of two TTS voices (gateway gpt-4o-mini-tts, edge-tts as fallback).
  3. Lines are concatenated with short gaps. `generate()` yields PCM line by line, so a player can start
     after the FIRST line is ready instead of waiting for the whole episode.

  python3 scripts/podcast.py --knowledge experiments/E5/context/knowledge --topic "Project Nimbus" --minutes 1 \
      --out /tmp/pod.mp3                     # writes the episode + prints timings
"""
import argparse, asyncio, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.request, uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402
from media_player import RATE, decode  # noqa: E402

CHAT_MODEL = os.environ.get("PODCAST_MODEL", gateway.CHAT_MODEL)
WPM = 110  # target words per minute: the LLM overshoots the word budget by ~10-25 %, TTS hosts speak ~120-125 wpm
GAP_S = 0.25
VOICES = {  # host -> (gateway voice, edge-tts voice)
    "A": ("coral", "en-US-AvaNeural"),
    "B": ("ash", "en-US-AndrewNeural"),
}
HOSTS = {"A": "Maya", "B": "Arjun"}


def read_knowledge(folder: str | Path, max_chars: int = 12000) -> str:
    out = []
    for p in sorted(Path(folder).glob("**/*")):
        if p.suffix.lower() in (".md", ".txt"):
            out.append(f"## {p.name}\n{p.read_text(errors='ignore')}")
        elif p.suffix.lower() == ".pdf":
            try:
                txt = subprocess.run(["pdftotext", str(p), "-"], capture_output=True, text=True).stdout
                out.append(f"## {p.name}\n{txt}")
            except FileNotFoundError:
                pass
    return "\n\n".join(out)[:max_chars]


def _post(path: str, body: dict, timeout=90) -> bytes:
    """POST to the gateway with backoff on 429/5xx."""
    for attempt in range(5):
        req = urllib.request.Request(gateway.base() + path, data=json.dumps(gateway.adapt_chat(body)).encode(),
                                     headers={**gateway.auth_header(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(1.5 * 2 ** attempt)
                continue
            raise


def write_script(topic: str, minutes: float, knowledge: str) -> dict:
    words = int(max(0.5, min(5, minutes)) * WPM)
    prompt = f"""Write a short, lively two-host audio podcast episode about: {topic}
Hosts: {HOSTS['A']} (host A) and {HOSTS['B']} (host B). Total length about {words} words (strict), so it lasts about {minutes} minute(s).
Use ONLY facts from the knowledge below; do not invent numbers, names or dates. If the topic is not covered, say so briefly
and talk about the closest thing that is. Open with a one-line welcome naming the topic; close with a one-line sign-off.
Alternate hosts, 1-3 sentences per turn, natural spoken English, no stage directions, no markdown, no sound effects.
Return JSON: {{"title": "...", "lines": [{{"host": "A"|"B", "text": "..."}}]}}

KNOWLEDGE:
{knowledge}

(request {uuid.uuid4().hex[:8]})"""
    body = {"model": CHAT_MODEL, "response_format": {"type": "json_object"}, "temperature": 0.8,
            "messages": [{"role": "user", "content": prompt}]}
    data = json.loads(_post("/openai/v1/chat/completions", body))
    js = json.loads(data["choices"][0]["message"]["content"])
    lines = [{"host": "B" if str(x.get("host", "A")).upper().startswith("B") else "A", "text": x["text"].strip()}
             for x in js.get("lines", []) if x.get("text", "").strip()]
    return {"title": js.get("title") or topic, "lines": lines}


def tts_line(text: str, host: str, engine: str = "gateway") -> bytes:
    """One line -> 24 kHz mono PCM. gateway first (unless engine='edge'), edge-tts as fallback."""
    gw_voice, edge_voice = VOICES[host]
    with tempfile.TemporaryDirectory() as d:
        mp3 = os.path.join(d, "l.mp3")
        if engine == "gateway" and gateway.has_gateway():
            try:
                body = {"model": gateway.TTS_MODEL, "voice": gw_voice,
                        "input": text, "response_format": "mp3",
                        "instructions": "You are a warm, upbeat podcast host. Conversational pace."}
                Path(mp3).write_bytes(_post("/openai/v1/audio/speech", body, timeout=60))
                return decode(mp3)
            except Exception as e:
                print(f"podcast: gateway TTS failed ({e}); falling back to edge-tts", file=sys.stderr)
        import edge_tts
        for attempt in range(3):
            try:
                asyncio.run(edge_tts.Communicate(text, edge_voice).save(mp3))
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)
        return decode(mp3)


async def generate(topic: str, minutes: float, knowledge_dir, engine="gateway", parallel=2, timings=None):
    """Async generator of PCM chunks (one per line, with a trailing gap), in order.
    `timings` (dict) gets: script_s, first_audio_s, total_s, lines, words, title."""
    timings = timings if timings is not None else {}
    t0 = time.time()
    script = await asyncio.to_thread(write_script, topic, minutes, read_knowledge(knowledge_dir))
    timings.update(script_s=round(time.time() - t0, 2), lines=len(script["lines"]), title=script["title"],
                   words=sum(len(x["text"].split()) for x in script["lines"]), script=script)
    sem = asyncio.Semaphore(parallel)

    async def one(ln):
        async with sem:
            return await asyncio.to_thread(tts_line, ln["text"], ln["host"], engine)

    tasks = [asyncio.create_task(one(ln)) for ln in script["lines"]]
    gap = b"\x00\x00" * int(GAP_S * RATE)
    for i, tk in enumerate(tasks):
        pcm = await tk
        if i == 0:
            timings["first_audio_s"] = round(time.time() - t0, 2)
        yield pcm + gap
    timings["total_s"] = round(time.time() - t0, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--knowledge", required=True)
    ap.add_argument("--topic", required=True)
    ap.add_argument("--minutes", type=float, default=1)
    ap.add_argument("--engine", choices=["gateway", "edge"], default="gateway")
    ap.add_argument("--out", required=True, help="output audio file (.mp3/.wav)")
    a = ap.parse_args()
    tm = {}

    async def run():
        pcm = bytearray()
        async for c in generate(a.topic, a.minutes, a.knowledge, a.engine, timings=tm):
            pcm += c
        return bytes(pcm)
    pcm = asyncio.run(run())
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-",
                    a.out], input=pcm, check=True)
    tm["audio_s"] = round(len(pcm) / 2 / RATE, 1)
    script = tm.pop("script")
    for ln in script["lines"]:
        print(f"{HOSTS[ln['host']]}: {ln['text']}")
    print(json.dumps(tm))


if __name__ == "__main__":
    main()
