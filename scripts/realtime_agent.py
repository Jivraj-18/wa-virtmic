#!/usr/bin/env python3
"""Live two-way voice agent for a WhatsApp Web call, using OpenAI Realtime (gpt-realtime).

Audio path (all 24 kHz mono s16le):
  caller  -> Chrome -> callout_sink.monitor -> parec  -> WebSocket input_audio_buffer.append
  model   -> response.output_audio.delta     -> pacat -> virtmic_sink -> virtmic -> Chrome mic -> caller

Auth: our OpenAI-compatible LLM gateway cannot proxy WebSockets, so we ask it (plain HTTP) for a short-lived
OpenAI Realtime client secret (ek_...) and connect directly to wss://api.openai.com with that.

Standalone test (talks through the virtual mic; no call needed):
  python3 scripts/realtime_agent.py --seconds 30
"""
import argparse, asyncio, base64, json, os, threading, time, urllib.request, uuid
from pathlib import Path

import gateway
from gateway import load_env

RATE = 24000
CHUNK = RATE * 2 // 50  # 20 ms of s16le mono
MODEL = os.environ.get("REALTIME_MODEL", "gpt-realtime")
VOICE = os.environ.get("REALTIME_VOICE", "marin")

INSTRUCTIONS = """You are a friendly AI voice assistant answering a WhatsApp voice call.
This is a test of an AI voice running on a virtual microphone; the caller knows that.
Speak naturally and keep every reply short: one or two sentences, then let the caller talk.
Always speak English. Only switch to Hindi if the caller clearly speaks Hindi to you first.
If the caller is silent or says 'hello?' repeatedly, ask whether they can hear you clearly.
If asked, explain you are an AI speaking through a virtual microphone inside a cloud dev container."""

GREETING = ("In English, greet the caller warmly in one short sentence, say you are an AI assistant on a test call, "
            "and ask if they can hear you clearly.")


def client_secret(instructions: str) -> str:
    """Short-lived OpenAI Realtime key via the LLM gateway. A unique nonce defeats the gateway's response cache."""
    load_env()
    body = {"session": {"type": "realtime", "model": MODEL,
                        "instructions": f"{instructions}\n(session {uuid.uuid4().hex[:10]})"}}
    req = urllib.request.Request(
        gateway.base() + "/openai/v1/realtime/client_secrets",
        data=json.dumps(body).encode(),
        headers={**gateway.auth_header(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["value"]


class Agent:
    def __init__(self, transcript: Path | None = None, log=print, instructions=INSTRUCTIONS, greeting=GREETING,
                 in_device="callout_sink.monitor", out_device="virtmic_sink",
                 tools: list | None = None, on_tool=None, on_event=None, session_extra: dict | None = None):
        """Extension hooks (shared by experiments, keep them backward compatible):
        tools         : list of Realtime function tools [{"type":"function","name":..,"description":..,"parameters":{..}}]
        on_tool       : async (name, args: dict, agent) -> result (any JSON-able). May be slow; the result is sent back
                        as function_call_output and a new response is requested automatically.
        on_event      : (event: dict, agent) -> None, sync or async; called for every server event.
        session_extra : dict merged into the session.update "session" object (e.g. turn_detection tweaks).
        While running, agent.respond(instructions) makes the model speak (e.g. a filler line), agent.ws is the socket."""
        self.tools, self.on_tool, self.on_event = tools or [], on_tool, on_event
        self.session_extra = session_extra or {}
        self.ws = None
        self.loop = None
        self.transcript, self.log = transcript, log
        self.instructions, self.greeting = instructions, greeting
        self.in_device, self.out_device = in_device, out_device
        self.stop = threading.Event()
        self.t0 = time.time()
        self.player = None

    # ---- transcript -------------------------------------------------------
    def say(self, who: str, text: str):
        t = time.time() - self.t0
        line = f"[{int(t) // 60:02d}:{t % 60:04.1f}] {who:6s} {text.strip()}"
        self.log(line)
        if self.transcript:
            with open(self.transcript, "a") as f:
                f.write(line + "\n")

    # ---- audio out --------------------------------------------------------
    async def start_player(self):
        self.player = await asyncio.create_subprocess_exec(
            "pacat", "--playback", f"--device={self.out_device}", "--raw", "--format=s16le",
            f"--rate={RATE}", "--channels=1", "--latency-msec=60", stdin=asyncio.subprocess.PIPE)

    async def flush_player(self):
        """Barge-in: drop whatever audio is still queued for the caller."""
        if self.player and self.player.returncode is None:
            self.player.kill()
            await self.player.wait()
        await self.start_player()

    # ---- hooks ------------------------------------------------------------
    async def send(self, msg: dict):
        await self.ws.send(json.dumps(msg))

    async def respond(self, instructions: str | None = None):
        """Ask the model to speak now (optionally with one-off instructions)."""
        await self.send({"type": "response.create", "response": {"instructions": instructions} if instructions else {}})

    def respond_threadsafe(self, instructions: str | None = None):
        if self.loop:
            asyncio.run_coroutine_threadsafe(self.respond(instructions), self.loop)

    async def _run_tool(self, m: dict):
        name, call_id = m.get("name"), m.get("call_id")
        try:
            args = json.loads(m.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        t = time.time()
        self.log(f"tool call: {name}({json.dumps(args, ensure_ascii=False)[:200]})")
        try:
            result = await self.on_tool(name, args, self) if self.on_tool else {"error": "no tool handler"}
        except Exception as e:
            result = {"error": f"{type(e).__name__}: {e}"}
        self.log(f"tool done: {name} in {time.time() - t:.1f}s -> {json.dumps(result, ensure_ascii=False)[:200]}")
        await self.send({"type": "conversation.item.create", "item": {
            "type": "function_call_output", "call_id": call_id, "output": json.dumps(result, ensure_ascii=False)}})
        await self.respond()

    # ---- main -------------------------------------------------------------
    async def run(self, max_seconds: float = 3600):
        import websockets
        t = time.time()
        key = await asyncio.to_thread(client_secret, self.instructions)
        self.log(f"realtime: key in {time.time() - t:.1f}s, connecting to {MODEL}")
        async with websockets.connect(f"wss://api.openai.com/v1/realtime?model={MODEL}",
                                      additional_headers={"Authorization": f"Bearer {key}"},
                                      max_size=None, open_timeout=15) as ws:
            self.ws, self.loop = ws, asyncio.get_running_loop()
            sess = {
                "type": "realtime", "instructions": self.instructions,
                "audio": {
                    "input": {"format": {"type": "audio/pcm", "rate": RATE},
                              # near-field noise reduction + a slightly higher VAD threshold: on a real call,
                              # line noise was being transcribed as speech and triggered replies / cut-offs
                              "noise_reduction": {"type": os.environ.get("REALTIME_NOISE_REDUCTION", "near_field")},
                              "turn_detection": {"type": "server_vad",
                                                 "threshold": float(os.environ.get("REALTIME_VAD_THRESHOLD", "0.6")),
                                                 "prefix_padding_ms": 300, "silence_duration_ms": 500},
                              "transcription": {"model": "gpt-4o-transcribe"}},
                    "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": VOICE}}}
            if self.tools:
                sess["tools"], sess["tool_choice"] = self.tools, "auto"
            sess.update(self.session_extra)
            await ws.send(json.dumps({"type": "session.update", "session": sess}))
            await self.start_player()
            mic = await asyncio.create_subprocess_exec(
                "parec", f"--device={self.in_device}", "--raw", "--format=s16le", f"--rate={RATE}",
                "--channels=1", "--latency-msec=20", stdout=asyncio.subprocess.PIPE)
            await ws.send(json.dumps({"type": "response.create", "response": {"instructions": self.greeting}}))
            self.t_first_req = time.time()

            async def pump_mic():
                while not self.stop.is_set():
                    data = await mic.stdout.read(CHUNK)
                    if not data:
                        break
                    await ws.send(json.dumps({"type": "input_audio_buffer.append",
                                              "audio": base64.b64encode(data).decode()}))

            async def pump_events():
                first_audio = False
                async for raw in ws:
                    m = json.loads(raw)
                    ty = m["type"]
                    if self.on_event:
                        r = self.on_event(m, self)
                        if asyncio.iscoroutine(r):
                            await r
                    if ty == "response.function_call_arguments.done":
                        asyncio.create_task(self._run_tool(m))
                    if ty in ("response.output_audio.delta", "response.audio.delta"):
                        if not first_audio:
                            first_audio = True
                            self.log(f"realtime: first audio {time.time() - self.t_first_req:.2f}s after request")
                        try:
                            self.player.stdin.write(base64.b64decode(m["delta"]))
                            await self.player.stdin.drain()
                        except (BrokenPipeError, ConnectionResetError):
                            pass
                    elif ty == "input_audio_buffer.speech_started":
                        self.log(f"realtime: caller speech started @{time.time() - self.t0:.1f}s")
                        await self.flush_player()  # caller started talking: stop our audio now
                    elif ty == "input_audio_buffer.speech_stopped":
                        self.t_first_req = time.time()
                        first_audio = False
                    elif ty == "conversation.item.input_audio_transcription.completed":
                        if m.get("transcript", "").strip():
                            self.say("CALLER", m["transcript"])
                    elif ty in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
                        self.say("AI", m.get("transcript", ""))
                    elif ty == "error":
                        self.log(f"realtime error: {m.get('error')}")

            async def watch_stop():
                end = time.time() + max_seconds
                while not self.stop.is_set() and time.time() < end:
                    await asyncio.sleep(0.2)

            tasks = [asyncio.create_task(c) for c in (pump_mic(), pump_events(), watch_stop())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for tk in done:
                if tk.exception():
                    self.log(f"realtime: task ended with {type(tk.exception()).__name__}: {tk.exception()}")
            self.log(f"realtime: stopping @{time.time() - self.t0:.1f}s")
            for tk in tasks:
                tk.cancel()
            for p in (mic, self.player):
                if p and p.returncode is None:
                    p.kill()
        self.log("realtime: session closed")

    # ---- thread helpers (used by auto_answer.py) ---------------------------
    def start_thread(self, max_seconds: float = 3600) -> threading.Thread:
        def target():
            try:
                asyncio.run(self.run(max_seconds))
            except Exception as e:  # never kill the watcher
                self.log(f"realtime: FAILED {type(e).__name__}: {e}")
        th = threading.Thread(target=target, daemon=True)
        th.start()
        return th


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--transcript")
    ap.add_argument("--in-device", default="callout_sink.monitor", help="PulseAudio source carrying the caller's voice")
    ap.add_argument("--out-device", default="virtmic_sink", help="PulseAudio sink feeding the call's microphone")
    ap.add_argument("--instructions-file", help="system instructions (default: built-in test-call persona)")
    ap.add_argument("--demo-tool", action="store_true", help="add a get_secret_code tool (smoke test for tool calling)")
    a = ap.parse_args()
    kw = {"instructions": Path(a.instructions_file).read_text()} if a.instructions_file else {}
    if a.demo_tool:
        async def demo(name, args, agent):
            await asyncio.sleep(1.0)
            return {"code": "BLUE-42"}
        kw.update(tools=[{"type": "function", "name": "get_secret_code",
                          "description": "Returns today's secret code. Call it when the caller asks for the code.",
                          "parameters": {"type": "object", "properties": {}}}], on_tool=demo)
    ag = Agent(Path(a.transcript) if a.transcript else None, in_device=a.in_device, out_device=a.out_device, **kw)
    asyncio.run(ag.run(a.seconds))
