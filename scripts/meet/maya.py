#!/usr/bin/env python3
"""E4: "Maya", a Google Meet participant that listens silently, speaks only when addressed, and posts rare chat tips.

  # listen/speak logic only, against any PulseAudio devices (used by the E0 harness, no Meet needed)
  python3 -m scripts.meet.maya agent --in-device callout_E4.monitor --out-device virtmic_E4 --transcript run/t.txt

  # real Meet (needs the user): one-time Google login in Maya's own Chrome, then join a meeting
  python3 -m scripts.meet.maya devices up
  python3 -m scripts.meet.maya login
  python3 -m scripts.meet.maya join https://meet.google.com/abc-defg-hij
  python3 -m scripts.meet.maya leave

How it decides to talk
  gpt-realtime hears the whole meeting (server VAD + gpt-4o-transcribe) but with turn_detection.create_response=false,
  so it never answers by itself. Each utterance's transcript (streamed deltas, then the final text) goes through
  addressing.py; only "Maya, ..." style utterances trigger agent.respond(). While Maya talks, a local energy VAD on
  the meeting audio stops her within ~0.1-0.3 s if anyone talks over her (plus the server's own interrupt).
"""
import argparse, asyncio, base64, json, os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))

import numpy as np  # noqa: E402

import realtime_agent  # noqa: E402
from realtime_agent import Agent, RATE  # noqa: E402
from meet.addressing import early_address, is_addressed  # noqa: E402
from meet.suggester import Suggester  # noqa: E402

INSTRUCTIONS = """You are Maya, an AI participant in a video meeting with several people. You hear everything that is said.
You only speak when the system asks you to, which happens when someone addresses you by name.
Then answer that person directly, using what was said in the meeting so far. Keep it to one to three short spoken
sentences, natural and to the point. Do not greet, do not recap the meeting unless asked, do not say you are an AI
unless asked. Always speak English unless the person addressing you spoke another language."""

RESPOND = ("Someone in the meeting just addressed you by name. Answer them now, briefly (1-3 short sentences). "
           "Their words, from speech-to-text (may be cut off or slightly wrong): \"{text}\"")

BARGE_RMS = 400.0      # int16 RMS at 16 kHz that counts as someone talking
BARGE_MS = 120         # ...for this long while Maya is speaking -> stop her


class Maya:
    def __init__(self, in_device, out_device, transcript=None, events=None, chat_post=None,
                 suggest_interval=180.0, suggest_first=60.0, suggest_check=20.0, silence_ms=500, log=print):
        self.log = log
        self.events_path = Path(events) if events else None
        self.t0 = time.time()
        self.partial = {}          # item_id -> partial transcript
        self.triggered = set()     # item_ids we answered
        self.cancelled = set()     # response ids we stopped (drop their late audio)
        self.response_id = None
        self.audio_item = None     # (item_id, wall time of its first audio delta) of Maya's current spoken answer
        self.stats_written = False
        self.response_active = False
        self.play_until = 0.0      # wall time when queued Maya audio ends (pacat plays in real time)
        self.stats = {"utterances": 0, "triggers": 0, "early_triggers": 0, "barge_ins": 0, "suggestions": 0}
        self.suggester = Suggester(chat_post or self._log_suggestion, min_interval=suggest_interval,
                                   first_after=suggest_first, check_every=suggest_check, log=log)
        audio = {
            "input": {"format": {"type": "audio/pcm", "rate": RATE},
                      "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300,
                                         "silence_duration_ms": silence_ms,
                                         "create_response": False,      # never answer on its own
                                         "interrupt_response": True},   # server also cancels on talk-over
                      "transcription": {"model": "gpt-4o-transcribe", "language": "en"}},
            "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": realtime_agent.VOICE}}
        self.agent = Agent(Path(transcript) if transcript else None, log=log, instructions=INSTRUCTIONS,
                           greeting=None, in_device=in_device, out_device=out_device,
                           on_event=self.on_event, session_extra={"audio": audio})

    # ---------------------------------------------------------------- bookkeeping
    def event(self, kind, **kw):
        rec = {"t": round(time.time() - self.t0, 2), "kind": kind, **kw}
        self.log(f"maya: {kind} {json.dumps(kw, ensure_ascii=False)[:200]}")
        if self.events_path:
            with open(self.events_path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _log_suggestion(self, text):
        self.stats["suggestions"] += 1
        self.event("chat_suggestion", text=text)

    def write_stats(self):
        if not self.stats_written:
            self.stats_written = True
            self.event("stats", **self.stats)

    def speaking(self) -> bool:
        return time.time() < self.play_until

    # ---------------------------------------------------------------- realtime events
    async def trigger(self, item_id, text, early):
        self.triggered.add(item_id)
        self.stats["triggers"] += 1
        self.stats["early_triggers"] += early
        self.event("addressed", item=item_id, early=early, text=text)
        await self.agent.respond(RESPOND.format(text=text.replace('"', "'")))

    async def on_event(self, m, agent):
        ty = m["type"]
        if ty == "conversation.item.input_audio_transcription.delta":
            iid = m.get("item_id")
            self.partial[iid] = self.partial.get(iid, "") + m.get("delta", "")
            if iid not in self.triggered and early_address(self.partial[iid]):
                await self.trigger(iid, self.partial[iid], early=True)
        elif ty == "conversation.item.input_audio_transcription.completed":
            iid, text = m.get("item_id"), (m.get("transcript") or "").strip()
            self.partial.pop(iid, None)
            if not text:
                return
            self.stats["utterances"] += 1
            self.suggester.add("Participant", text)
            if iid not in self.triggered and is_addressed(text):
                await self.trigger(iid, text, early=False)
        elif ty == "response.created":
            self.response_id = m.get("response", {}).get("id")
            self.response_active = True
        elif ty == "response.done":
            self.response_active = False
        elif ty in ("response.output_audio.delta", "response.audio.delta"):
            if m.get("response_id") in self.cancelled:
                m["delta"] = ""          # late audio of a response we stopped: Agent writes 0 bytes
                return
            if not self.audio_item or self.audio_item[0] != m.get("item_id"):
                self.audio_item = (m.get("item_id"), time.time())
            n = len(m.get("delta", "")) * 3 // 4
            self.play_until = max(time.time(), self.play_until) + n / (2 * RATE)
        elif ty in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
            self.suggester.add("Maya", m.get("transcript", ""))
        elif ty == "input_audio_buffer.speech_started" and self.speaking():
            await self.barge_in("server_vad")

    async def barge_in(self, source):
        if not self.speaking():
            return
        self.play_until = 0.0
        if self.response_id:
            self.cancelled.add(self.response_id)
        self.stats["barge_ins"] += 1
        self.event("barge_in", source=source)
        await self.agent.flush_player()
        try:
            if self.response_active:  # generation usually finished long before playback did
                await self.agent.send({"type": "response.cancel"})
            if self.audio_item:  # tell the model how much of its answer was actually heard
                iid, t_first = self.audio_item
                await self.agent.send({"type": "conversation.item.truncate", "item_id": iid, "content_index": 0,
                                       "audio_end_ms": max(0, int((time.time() - t_first) * 1000) - 100)})
        except Exception:
            pass

    # ---------------------------------------------------------------- local barge-in VAD
    async def local_vad(self):
        """Energy VAD on the meeting audio. The server VAD needs ~0.3 s of speech + network; this stops Maya faster."""
        while self.agent.ws is None:
            await asyncio.sleep(0.1)
        proc = await asyncio.create_subprocess_exec(
            "parec", f"--device={self.agent.in_device}", "--raw", "--format=s16le", "--rate=16000", "--channels=1",
            "--latency-msec=20", stdout=asyncio.subprocess.PIPE)
        need, run = BARGE_MS // 20, 0
        try:
            while True:
                data = await proc.stdout.readexactly(640)
                rms = float(np.sqrt(np.mean(np.frombuffer(data, np.int16).astype(np.float64) ** 2)))
                run = run + 1 if rms > BARGE_RMS else 0
                if run >= need and self.speaking():
                    await self.barge_in("local_vad")
                    run = 0
        except (asyncio.IncompleteReadError, asyncio.CancelledError):
            pass
        finally:
            if proc.returncode is None:
                proc.kill()

    # ---------------------------------------------------------------- run
    async def run(self, max_seconds=3600, extra=()):
        self.suggester.start()
        tasks = [asyncio.create_task(self.local_vad())] + [asyncio.create_task(c) for c in extra]
        try:
            await self.agent.run(max_seconds)
        finally:
            self.suggester.stop.set()
            for t in tasks:
                t.cancel()
            self.write_stats()


# ==================================================================== CLI
def cmd_agent(a):
    run_dir = Path(a.transcript).parent if a.transcript else None
    events = a.events or (run_dir / "maya_events.jsonl" if run_dir else None)
    maya = Maya(a.in_device, a.out_device, a.transcript, events, suggest_interval=a.suggest_interval,
                suggest_first=a.suggest_first, suggest_check=a.suggest_check, silence_ms=a.silence_ms)
    try:
        asyncio.run(maya.run(a.seconds))
    except KeyboardInterrupt:
        maya.write_stats()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ag = sub.add_parser("agent", help="listen/speak logic on given PulseAudio devices (no Meet)")
    ag.add_argument("--in-device", required=True, help="source carrying the meeting audio (e.g. maya_out.monitor)")
    ag.add_argument("--out-device", required=True, help="sink feeding Maya's microphone (e.g. maya_mic_sink)")
    ag.add_argument("--transcript")
    ag.add_argument("--events", help="jsonl of triggers / barge-ins / chat suggestions (default: next to transcript)")
    ag.add_argument("--seconds", type=float, default=600)
    ag.add_argument("--suggest-interval", type=float, default=180, help="min seconds between chat suggestions")
    ag.add_argument("--suggest-first", type=float, default=60, help="no suggestion during the first N seconds")
    ag.add_argument("--suggest-check", type=float, default=20)
    ag.add_argument("--silence-ms", type=int, default=500, help="server VAD end-of-utterance silence")
    ag.set_defaults(fn=cmd_agent)
    from meet import browser  # Meet/Chrome commands live there
    browser.add_commands(sub)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
