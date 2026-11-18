#!/usr/bin/env python3
"""E5: a tiny pausable media player that plays into a PulseAudio sink (the call's microphone sink).

PulseAudio mixes every stream that plays into a sink, so this player can run next to the realtime agent's own voice
(both go into --out-device and the caller hears the mix).

Design: each item is decoded once to 24 kHz mono s16le PCM in memory (ffmpeg). An asyncio task writes 20 ms chunks to
`pacat` paced at real time, keeping only LEAD seconds queued, so pause/stop take effect within ~LEAD seconds without
killing the stream. Volume is applied per chunk. A podcast that is still being synthesized is an item whose PCM grows
(`Item.append()` / `Item.finish()`); playback waits for more audio instead of ending.

  python3 scripts/media_player.py file.mp3 --device virtmic_E5     # quick manual test (plays to the end)
"""
import argparse, asyncio, subprocess, time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RATE = 24000
CHUNK_S = 0.02
CHUNK = int(RATE * CHUNK_S) * 2  # bytes
LEAD = 0.12  # seconds of audio queued in pacat ahead of real time
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".opus"}


def decode(path: str | Path) -> bytes:
    """Any audio file -> 24 kHz mono s16le PCM."""
    return subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-ac", "1", "-ar", str(RATE),
                           "-f", "s16le", "-"], capture_output=True, check=True).stdout


@dataclass
class Item:
    title: str
    path: str | None = None
    pcm: bytearray = field(default_factory=bytearray)
    complete: bool = True
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, path, title=None, **meta):
        return cls(title or Path(path).stem, str(path), bytearray(decode(path)), True, meta)

    @classmethod
    def growing(cls, title, **meta):
        return cls(title, None, bytearray(), False, meta)

    def append(self, pcm: bytes):
        self.pcm += pcm

    def finish(self):
        self.complete = True

    @property
    def seconds(self) -> float:
        return len(self.pcm) / 2 / RATE


class MediaPlayer:
    """state: idle | playing | paused. Methods are coroutine-safe within one event loop."""

    def __init__(self, device: str, log=print, on_state=None):
        self.device, self.log, self.on_state = device, log, on_state
        self.queue: list[Item] = []
        self.idx = -1
        self.pos = 0  # byte offset in current item
        self.state = "idle"
        self.volume = 1.0
        self.pause_reason = None
        self._task = None
        self._proc = None
        self._wake = asyncio.Event()

    # ---- info ------------------------------------------------------------
    @property
    def current(self) -> Item | None:
        return self.queue[self.idx] if 0 <= self.idx < len(self.queue) else None

    def status(self) -> dict:
        it = self.current
        return {"state": self.state, "title": it.title if it else None,
                "position_s": round(self.pos / 2 / RATE, 1), "length_s": round(it.seconds, 1) if it else None,
                "still_generating": bool(it and not it.complete), "volume": round(self.volume, 2),
                "queue": [i.title for i in self.queue[self.idx + 1:]] if it else []}

    def _set(self, state, reason=None):
        self.state, self.pause_reason = state, reason
        self._wake.set()
        if self.on_state:
            self.on_state(state, self.status())

    # ---- controls --------------------------------------------------------
    async def play(self, items: list[Item]):
        """Replace the queue and start playing items[0]."""
        self.queue, self.idx, self.pos = list(items), 0, 0
        self._ensure_task()
        self._set("playing")
        self.log(f"media: play '{self.current.title}' ({self.current.seconds:.1f}s{'' if self.current.complete else '+'})")

    async def pause(self, reason="request"):
        if self.state == "playing":
            self._set("paused", reason)
            self.log(f"media: paused ({reason}) at {self.pos / 2 / RATE:.1f}s")
            return True
        return False

    async def resume(self):
        if self.state == "paused" and self.current:
            self._set("playing")
            self.log(f"media: resume '{self.current.title}' at {self.pos / 2 / RATE:.1f}s")
            return True
        return False

    async def next(self):
        if self.idx + 1 < len(self.queue):
            self.idx, self.pos = self.idx + 1, 0
            self._set("playing")
            self.log(f"media: next -> '{self.current.title}'")
            return True
        await self.stop()
        return False

    async def stop(self):
        if self.state != "idle":
            self.log("media: stop")
        self.queue, self.idx, self.pos = [], -1, 0
        self._set("idle")

    def set_volume(self, direction: str):
        f = {"up": 1.6, "louder": 1.6, "down": 1 / 1.6, "quieter": 1 / 1.6}.get(direction, 1.0)
        self.volume = float(min(3.0, max(0.15, self.volume * f)))
        self.log(f"media: volume {direction} -> {self.volume:.2f}")
        return self.volume

    async def close(self):
        await self.stop()
        if self._task:
            self._task.cancel()
        if self._proc and self._proc.returncode is None:
            self._proc.kill()

    # ---- engine ----------------------------------------------------------
    def _ensure_task(self):
        if not self._task or self._task.done():
            self._task = asyncio.create_task(self._run())

    async def _pacat(self):
        if not self._proc or self._proc.returncode is not None:
            self._proc = await asyncio.create_subprocess_exec(
                "pacat", "--playback", f"--device={self.device}", "--raw", "--format=s16le", f"--rate={RATE}",
                "--channels=1", "--latency-msec=60", "--client-name=e5-media", "--stream-name=media",
                stdin=asyncio.subprocess.PIPE)
        return self._proc

    async def _run(self):
        t0 = None  # wall time at which `sent` seconds of audio == 0
        sent = 0.0
        while True:
            if self.state != "playing":
                t0 = None
                self._wake.clear()
                await self._wake.wait()
                continue
            it = self.current
            if it is None:
                self._set("idle")
                continue
            if self.pos >= len(it.pcm):
                if not it.complete:  # podcast still being synthesized: wait for more audio
                    t0 = None
                    await asyncio.sleep(0.1)
                    continue
                self.log(f"media: finished '{it.title}'")
                if self.idx + 1 < len(self.queue):
                    self.idx, self.pos = self.idx + 1, 0
                    self.log(f"media: auto-next -> '{self.current.title}'")
                else:
                    self.queue, self.idx, self.pos = [], -1, 0
                    self._set("idle", "finished")
                continue
            now = time.monotonic()
            if t0 is None:
                t0, sent = now, 0.0
            ahead = sent - (now - t0)
            if ahead > LEAD:
                await asyncio.sleep(min(ahead - LEAD, CHUNK_S))
                continue
            if ahead < -0.5:  # we fell behind (CPU hiccup): resync instead of bursting
                t0, sent = now, 0.0
            chunk = bytes(it.pcm[self.pos:self.pos + CHUNK])
            self.pos += len(chunk)
            if abs(self.volume - 1.0) > 1e-3:
                a = np.frombuffer(chunk, np.int16).astype(np.float32) * self.volume
                chunk = np.clip(a, -32768, 32767).astype(np.int16).tobytes()
            p = await self._pacat()
            try:
                p.stdin.write(chunk)
                await p.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                self._proc = None
            sent += len(chunk) / 2 / RATE


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--device", required=True)
    a = ap.parse_args()

    async def main():
        mp = MediaPlayer(a.device)
        await mp.play([Item.from_file(f) for f in a.files])
        while mp.state != "idle":
            await asyncio.sleep(0.2)
        await mp.close()
    asyncio.run(main())
