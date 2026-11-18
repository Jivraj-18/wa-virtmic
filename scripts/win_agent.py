#!/usr/bin/env python3
"""Run the SAME realtime voice agent (realtime_agent.Agent) with sounddevice audio instead of PulseAudio.
Meant for Windows + WhatsApp Desktop + two VB-Cables (see WINDOWS.md). UNTESTED ON WINDOWS.

  pip install sounddevice numpy websockets
  python scripts/win_agent.py --list                                   # show audio device names
  python scripts/win_agent.py --in "CABLE-A Output" --out "CABLE Input" --wait

  --in   the device that CAPTURES WhatsApp's speaker (WhatsApp speaker = "CABLE-A Input" -> record "CABLE-A Output")
  --out  the device the AI PLAYS into (AI plays "CABLE Input" -> WhatsApp microphone = "CABLE Output")
  --wait don't open a (paid) realtime session until the caller's audio is heard; answer the call yourself first.

How: realtime_agent.Agent starts `parec` (caller audio) and `pacat` (AI voice) as subprocesses and only uses
proc.stdout.read(), proc.stdin.write()/drain(), proc.kill(), proc.wait() and proc.returncode. This adapter
replaces asyncio.create_subprocess_exec inside this process so those two commands become sounddevice streams;
every other part of the agent (session, VAD, barge-in, transcript, tools hooks) is the unchanged shared code.
Device names: any unique substring of a name from --list, or a device index.
"""
import argparse, asyncio, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

RATE = 24000          # realtime_agent.RATE (s16le mono)
BLOCK = RATE // 50    # 20 ms


def _dev(spec):
    """'12' -> 12, names stay names (sounddevice matches substrings)."""
    return int(spec) if spec is not None and str(spec).isdigit() else spec


class _Reader:
    """stdout of the fake `parec`: bytes from a RawInputStream callback."""

    def __init__(self, proc):
        self.proc, self.buf, self.cv = proc, bytearray(), asyncio.Condition()

    def feed(self, data: bytes):  # called on the event loop
        self.buf += data
        asyncio.ensure_future(self._notify())

    async def _notify(self):
        async with self.cv:
            self.cv.notify_all()

    async def read(self, n: int) -> bytes:
        async with self.cv:
            while len(self.buf) < n and self.proc.returncode is None:
                await self.cv.wait()
            if not self.buf:
                return b""
            out = bytes(self.buf[:n])
            del self.buf[:n]
            return out


class _Writer:
    """stdin of the fake `pacat`: queued bytes, consumed by a RawOutputStream callback."""

    def __init__(self):
        self.buf, self.lock = bytearray(), threading.Lock()

    def write(self, data: bytes):
        with self.lock:
            self.buf += data

    async def drain(self):
        # keep at most ~2 s queued so barge-in (kill) drops little and memory stays flat
        while len(self.buf) > RATE * 2 * 2:
            await asyncio.sleep(0.05)

    def pull(self, n: int) -> bytes:
        with self.lock:
            out = bytes(self.buf[:n])
            del self.buf[:n]
        return out + b"\0" * (n - len(out))


class FakeProc:
    """Looks enough like asyncio.subprocess.Process for realtime_agent.Agent."""

    def __init__(self, sd, kind: str, device):
        self.returncode = None
        self.kind = kind
        self.stdout = self.stdin = None
        loop = asyncio.get_running_loop()
        if kind == "rec":
            self.stdout = _Reader(self)

            def cb(indata, frames, t, status):
                loop.call_soon_threadsafe(self.stdout.feed, bytes(indata))
            self.stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                            device=_dev(device), callback=cb)
        else:
            self.stdin = _Writer()

            def cb(outdata, frames, t, status):
                outdata[:] = self.stdin.pull(len(outdata))
            self.stream = sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                                             device=_dev(device), callback=cb)
        self.stream.start()

    def kill(self):
        if self.returncode is None:
            self.returncode = -9
            try:
                self.stream.abort()
                self.stream.close()
            except Exception:
                pass
            if self.stdout:
                asyncio.ensure_future(self.stdout._notify())

    async def wait(self):
        return self.returncode


def install_adapter(sd):
    """Route the agent's `parec`/`pacat` subprocesses to sounddevice; anything else runs normally."""
    real = asyncio.create_subprocess_exec

    async def fake_exec(prog, *args, **kw):
        dev = next((a.split("=", 1)[1] for a in args if a.startswith("--device=")), None)
        if prog == "parec":
            return FakeProc(sd, "rec", dev)
        if prog == "pacat":
            return FakeProc(sd, "play", dev)
        return await real(prog, *args, **kw)

    asyncio.create_subprocess_exec = fake_exec


def wait_for_caller(sd, device, threshold: float, timeout: float) -> bool:
    """Block until the capture device carries sound (the call is up), so no realtime session is wasted."""
    import numpy as np
    hit = threading.Event()

    def cb(indata, frames, t, status):
        x = np.frombuffer(bytes(indata), dtype=np.int16).astype(np.float32)
        if x.size and float(np.sqrt(np.mean(x * x))) > threshold:
            hit.set()
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=BLOCK,
                           device=_dev(device), callback=cb):
        return hit.wait(timeout)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="list audio devices and exit")
    ap.add_argument("--in", dest="in_dev", default="CABLE-A Output", help="capture device carrying the caller's voice")
    ap.add_argument("--out", dest="out_dev", default="CABLE Input", help="playback device feeding WhatsApp's mic")
    ap.add_argument("--seconds", type=float, default=1800, help="max session length")
    ap.add_argument("--wait", action="store_true", help="start only once the caller's audio is heard")
    ap.add_argument("--threshold", type=float, default=150, help="int16 RMS that counts as 'caller audio' for --wait")
    ap.add_argument("--transcript", default=None, help="append the live transcript here")
    ap.add_argument("--instructions-file", help="system instructions (default: built-in test-call persona)")
    a = ap.parse_args()

    import sounddevice as sd
    if a.list:
        print(sd.query_devices())
        return
    install_adapter(sd)
    from realtime_agent import Agent  # imported after the adapter, but it looks the function up at call time anyway

    if a.wait:
        print(f"waiting for caller audio on '{a.in_dev}' (answer the call in WhatsApp)...", flush=True)
        if not wait_for_caller(sd, a.in_dev, a.threshold, 3600):
            print("no caller audio within an hour, giving up")
            return
    kw = {"instructions": Path(a.instructions_file).read_text()} if a.instructions_file else {}
    tr = Path(a.transcript) if a.transcript else Path(f"transcript_{time.strftime('%Y%m%d_%H%M%S')}.txt")
    agent = Agent(tr, in_device=a.in_dev, out_device=a.out_dev, **kw)
    print(f"AI on the line: caller <- '{a.out_dev}', caller -> '{a.in_dev}'. Ctrl+C to hang up the agent.", flush=True)
    try:
        asyncio.run(agent.run(a.seconds))
    except KeyboardInterrupt:
        pass
    print(f"transcript: {tr}")


if __name__ == "__main__":
    main()
