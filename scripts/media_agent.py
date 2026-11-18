#!/usr/bin/env python3
"""E5 "Call me and I'll play it": the realtime voice agent plus a media player and a podcast maker.

  python3 scripts/media_agent.py --context experiments/E5/context --seconds 120 \
      --in-device callout_E5.monitor --out-device virtmic_E5 [--transcript run/agent_transcript.txt]

As the E0 harness agent:
  python3 scripts/sim_call.py experiments/E5/scripts/media_controls.yaml --tag E5 --agent \
    "{python} scripts/media_agent.py --context experiments/E5/context --seconds {seconds} \
     --in-device {in_device} --out-device {out_device} --transcript {transcript}"

Context folder (same format as E1): instructions.md, config.yaml, knowledge/ (.md/.txt/.pdf), media/ (audio +
optional catalog.yaml with title/description/tags per file).

Mode A  play_media(query) / pause_media / resume_media / next_track / stop_media / set_volume(up|down)
Mode B  make_podcast(topic, minutes): LLM script from knowledge/ -> two TTS voices -> played while it is still
        being synthesized (starts after the first line is ready).
The realtime agent stays live: when the caller starts talking (input_audio_buffer.speech_started) playback pauses
at once; the agent answers; "continue" resumes. Media starts only after the agent has finished its short spoken
acknowledgement, so the voice and the media don't overlap.
Media events (with timings) go to media_events.jsonl next to --transcript (or --events).
"""
import argparse, asyncio, json, re, subprocess, sys, threading, time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import realtime_agent  # noqa: E402
from realtime_agent import Agent, RATE  # noqa: E402
from media_player import AUDIO_EXT, Item, MediaPlayer, decode  # noqa: E402
import podcast  # noqa: E402

BASE_RULES = """
## How this call works (audio on demand)
- You can PLAY audio for the caller from the media library below with play_media, and control it with pause_media,
  resume_media, next_track, stop_media and set_volume. You can also MAKE a short two-host podcast from the knowledge
  files with make_podcast(topic, minutes).
- Before calling a tool, do not speak. After the tool returns, say ONE very short sentence (for play: "Here's <title>."),
  then stop talking: the audio starts right after you finish.
- For make_podcast: after it returns, tell the caller in one sentence that it will take about <eta_seconds> seconds to
  put together. Do not fill the wait with chatter.
- Playback pauses AUTOMATICALLY whenever the caller starts speaking. Then answer the caller's question briefly
  (use the knowledge below), and ask "Shall I continue?" unless they asked you to stop or change something.
  When they say continue / go on / resume / carry on, call resume_media. "Next", "skip" -> next_track.
  "Stop" -> stop_media. "Louder" / "quieter" -> set_volume. "Pause" / "hold on" -> pause_media.
- Only play items from the library; if nothing matches, say what is available.
"""


# ------------------------------------------------------------------ context
def load_context(folder: str | Path) -> dict:
    d = Path(folder)
    cfg = yaml.safe_load((d / "config.yaml").read_text()) if (d / "config.yaml").exists() else {}
    instr = (d / "instructions.md").read_text() if (d / "instructions.md").exists() else ""
    media_dir = d / "media"
    catalog = []
    cat_file = media_dir / "catalog.yaml"
    listed = set()
    if cat_file.exists():
        for e in yaml.safe_load(cat_file.read_text()) or []:
            p = media_dir / e["file"]
            listed.add(p.name)
            if p.exists():
                catalog.append({"path": str(p), "title": e.get("title") or p.stem, "description": e.get("description", ""),
                                "tags": e.get("tags", [])})
    for p in sorted(media_dir.glob("*")) if media_dir.exists() else []:
        if p.suffix.lower() in AUDIO_EXT and p.name not in listed:
            catalog.append({"path": str(p), "title": p.stem.replace("_", " "), "description": "", "tags": []})
    return {"dir": d, "config": cfg or {}, "instructions": instr, "catalog": catalog,
            "knowledge_dir": d / "knowledge", "knowledge": podcast.read_knowledge(d / "knowledge", 8000)}


def build_instructions(ctx: dict) -> str:
    lib = "\n".join(f"- {c['title']}: {c['description']}" for c in ctx["catalog"]) or "- (empty)"
    return (ctx["instructions"].strip() + "\n" + BASE_RULES + "\n## Media library\n" + lib +
            "\n\n## Knowledge (for questions and podcasts)\n" + ctx["knowledge"] +
            "\n\nAlways speak " + ("English" if ctx["config"].get("language", "en") == "en"
                                   else ctx["config"]["language"]) + ".")


def _words(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def find_media(catalog: list, query: str) -> int | None:
    q = _words(query) - {"the", "a", "play", "me", "some", "please", "of", "to"}
    best, bi = 0.0, None
    for i, c in enumerate(catalog):
        title = _words(c["title"])
        score = 2 * len(q & title) + len(q & _words(" ".join(c["tags"]))) + 0.5 * len(q & _words(c["description"]))
        if c["title"].lower() in query.lower():
            score += 5
        if score > best:
            best, bi = score, i
    return bi


TOOLS = [
    {"type": "function", "name": "play_media",
     "description": "Play an audio item from the media library (team updates, music). Queues the rest of the library after it.",
     "parameters": {"type": "object", "properties": {"query": {"type": "string", "description": "title or what the caller asked for"}},
                    "required": ["query"]}},
    {"type": "function", "name": "pause_media", "description": "Pause playback (caller said pause / hold on).",
     "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "resume_media", "description": "Resume paused playback (caller said continue / go on / resume).",
     "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "next_track", "description": "Skip to the next item in the queue.",
     "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "stop_media", "description": "Stop playback and clear the queue.",
     "parameters": {"type": "object", "properties": {}}},
    {"type": "function", "name": "set_volume", "description": "Make the playback louder or quieter (and resume it).",
     "parameters": {"type": "object", "properties": {"direction": {"type": "string", "enum": ["up", "down"]}},
                    "required": ["direction"]}},
    {"type": "function", "name": "make_podcast",
     "description": "Generate and play a short two-host podcast about a topic from the knowledge files. Returns at once; audio starts in ~10-20 s.",
     "parameters": {"type": "object", "properties": {
         "topic": {"type": "string"}, "minutes": {"type": "number", "description": "length in minutes (0.5-3), default 1"}},
         "required": ["topic"]}},
]


# ------------------------------------------------------------------ session
class MediaSession:
    def __init__(self, ctx: dict, out_device: str, events_path: Path | None, run_dir: Path | None, log=print):
        self.ctx, self.log, self.run_dir = ctx, log, run_dir
        self.events_path = events_path
        self.player = MediaPlayer(out_device, log=log, on_state=self._on_state)
        self.agent: Agent | None = None
        self.t0 = time.time()
        # agent speech tracking (to start media only after the agent stops talking)
        self.active_resp: set = set()
        self.done_seq = 0
        self.tool_resp_ids: set = set()
        self.audio_until = 0.0
        self.caller_speaking = False
        self.last_caller_start = 0.0
        self.last_caller_stop = 0.0
        self.pending: asyncio.Task | None = None
        self.cfg_media = ctx["config"].get("media", {}) or {}
        self._pcm: dict[int, bytes] = {}

    # ---- logging ---------------------------------------------------------
    def ev(self, kind: str, **kw):
        rec = {"t": round(time.time() - self.t0, 3), "event": kind, **kw}
        self.log("EVENT " + json.dumps(rec, ensure_ascii=False))
        if self.events_path:
            with open(self.events_path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _on_state(self, state, status):
        if state == "idle" and self.player.pause_reason == "finished" and self.agent and self.agent.loop:
            self.ev("media_finished")
            asyncio.get_event_loop().create_task(self.agent.respond(
                "The audio you were playing just finished. In one short sentence ask if they want anything else."))

    # ---- realtime events ---------------------------------------------------
    async def on_event(self, m: dict, agent: Agent):
        ty, now = m["type"], time.time()
        if ty == "input_audio_buffer.speech_started":
            self.caller_speaking, self.last_caller_start = True, now
            self.audio_until = now  # Agent flushes its own player on barge-in
            if self.player.state == "playing":
                await self.player.pause("caller")
                self.ev("pause_on_speech", latency_ms=round((time.time() - now) * 1000, 1),
                        at_s=self.player.status()["position_s"], title=self.player.current.title)
                await agent.send({"type": "conversation.item.create", "item": {
                    "type": "message", "role": "system", "content": [{"type": "input_text", "text":
                        f"(Playback of '{self.player.current.title}' was paused automatically because the caller started speaking.)"}]}})
        elif ty == "input_audio_buffer.speech_stopped":
            self.caller_speaking, self.last_caller_stop = False, now
        elif ty == "response.created":
            self.active_resp.add(m["response"]["id"])
        elif ty == "response.done":
            rid = m["response"]["id"]
            self.active_resp.discard(rid)
            if rid not in self.tool_resp_ids:
                self.done_seq += 1
        elif ty in ("response.output_audio.delta", "response.audio.delta"):
            dur = len(m.get("delta", "")) * 3 / 4 / 2 / RATE
            self.audio_until = max(now, self.audio_until) + dur
        elif ty == "response.function_call_arguments.done":
            self.tool_resp_ids.add(m.get("response_id"))

    async def wait_agent_quiet(self, expect_reply: bool, timeout: float = 12.0):
        """Wait for the agent's follow-up reply (after a tool) to be generated and played out, and the caller to be quiet."""
        base, end = self.done_seq, time.time() + timeout
        if expect_reply:
            while self.done_seq == base and time.time() < end:
                await asyncio.sleep(0.05)
        while time.time() < end and (self.active_resp or time.time() < self.audio_until + 0.35 or self.caller_speaking):
            await asyncio.sleep(0.05)

    def _schedule(self, coro_fn, label: str):
        """Run coro_fn() after the agent's acknowledgement; cancels a previous pending start."""
        if self.pending and not self.pending.done():
            self.pending.cancel()
        t_req, cmd_stop = time.time(), self.last_caller_stop

        async def go():
            await self.wait_agent_quiet(expect_reply=True)
            if self.last_caller_start > t_req:  # the caller spoke meanwhile: don't blast audio at them
                self.ev(f"{label}_deferred")
                return
            await coro_fn()
            t = time.time()
            self.ev(f"{label}_started", title=self.player.current.title if self.player.current else None,
                    from_tool_s=round(t - t_req, 2), from_caller_end_s=round(t - cmd_stop, 2) if cmd_stop else None)
        self.pending = asyncio.create_task(go())

    # ---- tools -------------------------------------------------------------
    def _items_from(self, i: int) -> list[Item]:
        """Queue = the chosen item, then the rest of the library. Decoded PCM is cached (decode() costs ~0.3 s/file)."""
        cat = self.ctx["catalog"]
        order = [i] + [j for j in range(len(cat)) if j != i]
        items = []
        for j in order:
            if j not in self._pcm:
                self._pcm[j] = decode(cat[j]["path"])
            items.append(Item(cat[j]["title"], cat[j]["path"], bytearray(self._pcm[j])))
        return items

    def preload(self):
        threading.Thread(target=lambda: [self._items_from(0)] if self.ctx["catalog"] else None, daemon=True).start()

    async def on_tool(self, name: str, args: dict, agent: Agent):
        self.agent = agent
        p = self.player
        self.ev("tool", name=name, args=args)
        if name == "play_media":
            i = find_media(self.ctx["catalog"], args.get("query", ""))
            if i is None:
                return {"error": "no match", "available": [c["title"] for c in self.ctx["catalog"]]}
            items = await asyncio.to_thread(self._items_from, i)
            await p.stop()
            self._schedule(lambda: p.play(items), "play")
            return {"status": "starting after your one-sentence intro", "title": items[0].title,
                    "length_s": round(items[0].seconds), "queued_after": [x.title for x in items[1:]]}
        if name == "pause_media":
            if self.pending and not self.pending.done():
                self.pending.cancel()
            was = p.state
            if p.state == "playing":
                await p.pause("request")
            elif p.state == "paused":
                p.pause_reason = "request"
            return {"status": "paused" if was != "idle" else "nothing is playing", **p.status()}
        if name == "resume_media":
            if p.state != "paused":
                return {"status": f"nothing to resume ({p.state})", **p.status()}
            self._schedule(p.resume, "resume")
            return {"status": "resuming after your one-sentence reply", **p.status()}
        if name == "next_track":
            if p.state == "idle" or p.idx + 1 >= len(p.queue):
                await p.stop()
                return {"status": "no next item; playback stopped"}
            await p.pause("next")

            async def nxt():
                await p.next()
            self._schedule(nxt, "next")
            return {"status": "next item starting after your one-sentence intro", "title": p.queue[p.idx + 1].title}
        if name == "stop_media":
            if self.pending and not self.pending.done():
                self.pending.cancel()
            await p.stop()
            return {"status": "stopped"}
        if name == "set_volume":
            v = p.set_volume(args.get("direction", "up"))
            if p.state == "paused" and p.pause_reason == "caller":
                self._schedule(p.resume, "resume")
            return {"status": "ok", "volume": round(v, 2), "resuming": p.state == "paused"}
        if name == "make_podcast":
            return await self.start_podcast(args.get("topic", "the knowledge files"), args.get("minutes", 1))
        return {"error": f"unknown tool {name}"}

    async def start_podcast(self, topic: str, minutes) -> dict:
        try:
            minutes = float(minutes)
        except (TypeError, ValueError):
            minutes = 1.0
        minutes = max(0.5, min(float(self.cfg_media.get("podcast_max_minutes", 3)), minutes))
        voices = self.cfg_media.get("podcast_voices")
        if voices and len(voices) == 2:
            podcast.VOICES["A"] = (voices[0], podcast.VOICES["A"][1])
            podcast.VOICES["B"] = (voices[1], podcast.VOICES["B"][1])
        await self.player.stop()
        item = Item.growing(f"Podcast: {topic}")
        t_req, cmd_stop = time.time(), self.last_caller_stop
        tm = {}
        first = asyncio.Event()

        async def produce():
            try:
                async for pcm in podcast.generate(topic, minutes, self.ctx["knowledge_dir"], timings=tm):
                    item.append(pcm)
                    if not first.is_set():
                        first.set()
                        self.ev("podcast_first_audio_ready", s=round(time.time() - t_req, 2), script_s=tm.get("script_s"))
                item.finish()
                self.ev("podcast_generated", from_tool_s=round(time.time() - t_req, 2), audio_s=round(item.seconds, 1),
                        **{k: v for k, v in tm.items() if k != "script"})
                if self.run_dir:
                    out = self.run_dir / "podcast.mp3"
                    await asyncio.to_thread(subprocess.run, [
                        "ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-",
                        "-b:a", "48k", str(out)], input=bytes(item.pcm))
                    (self.run_dir / "podcast_script.json").write_text(json.dumps(tm.get("script"), indent=1))
            except Exception as e:
                self.ev("podcast_failed", error=f"{type(e).__name__}: {e}")
                item.finish()
                if not first.is_set() and self.agent:
                    await self.agent.respond("Making the podcast failed. Apologise in one sentence and offer the media library instead.")
                first.set()

        async def start_when_ready():
            await first.wait()
            if not item.pcm:
                return
            await self.wait_agent_quiet(expect_reply=False)
            if self.last_caller_start > t_req and self.caller_speaking:
                await self.wait_agent_quiet(expect_reply=False, timeout=20)
            await self.player.play([item])
            t = time.time()
            self.ev("podcast_started", from_tool_s=round(t - t_req, 2),
                    from_caller_end_s=round(t - cmd_stop, 2) if cmd_stop else None)

        asyncio.create_task(produce())
        self.pending = asyncio.create_task(start_when_ready())
        eta = 10 + 5 * max(0, minutes - 1)
        return {"status": "generating", "eta_seconds": int(eta), "topic": topic, "minutes": minutes}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--context", required=True)
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--in-device", default="callout_sink.monitor")
    ap.add_argument("--out-device", default="virtmic_sink")
    ap.add_argument("--transcript")
    ap.add_argument("--events", help="media events JSONL (default: media_events.jsonl next to --transcript)")
    a = ap.parse_args()
    ctx = load_context(a.context)
    cfg = ctx["config"]
    if cfg.get("voice"):
        realtime_agent.VOICE = cfg["voice"]
    tr = Path(a.transcript) if a.transcript else None
    run_dir = tr.parent if tr else None
    events = Path(a.events) if a.events else (run_dir / "media_events.jsonl" if run_dir else None)

    def log(*x):
        print(time.strftime("%H:%M:%S"), *x, flush=True)

    ms = MediaSession(ctx, a.out_device, events, run_dir, log=log)
    greeting = cfg.get("greeting")
    greet = (f"Greet the caller with exactly: \"{greeting}\"" if greeting else realtime_agent.GREETING)
    agent = Agent(tr, log=log, instructions=build_instructions(ctx), greeting=greet,
                  in_device=a.in_device, out_device=a.out_device,
                  tools=TOOLS, on_tool=ms.on_tool, on_event=ms.on_event)
    ms.agent = agent
    ms.preload()
    log(f"media_agent: {len(ctx['catalog'])} media items: {[c['title'] for c in ctx['catalog']]}")
    seconds = min(a.seconds, float(cfg.get("max_call_seconds", a.seconds)))

    async def run():
        try:
            await agent.run(seconds)
        finally:
            await ms.player.close()
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
