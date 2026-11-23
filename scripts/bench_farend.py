#!/usr/bin/env python3
"""The bench call's far end (the "other phone"), started by bench_call.py:  bench_farend.py <dir>
Serves <dir>/index.html (the bench page) on a free localhost port, prints its URL, answers the page's WebRTC offer
(POST /offer) with aiortc and writes what it receives to <dir>/heard.wav on the RTP timeline (gaps = silence) and
per-frame arrival times to <dir>/arrival.jsonl. No playout device or time-stretching in between, so heard.wav shows
what Chrome SENT (capture + APM + Opus). SIGTERM closes the files cleanly."""
import asyncio, http.server, json, signal, sys, threading, time, wave
from pathlib import Path


class FarEnd:
    """The other phone: an aiortc peer (its own asyncio thread) that answers the bench page's offer and writes what it
    receives to heard.wav on the RTP timeline (gaps = silence), plus per-packet arrival lateness to arrival.jsonl.
    No time-stretching/playout device in between, so heard.wav shows what Chrome SENT (capture + APM + Opus)."""

    def __init__(self, d):
        self.d, self.loop = d, asyncio.new_event_loop()
        self.pcs, self.tasks, self.closers = [], [], []
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

    def answer(self, sdp):
        return asyncio.run_coroutine_threadsafe(self._answer(sdp), self.loop).result(20)

    async def _answer(self, sdp):
        from aiortc import RTCPeerConnection, RTCSessionDescription
        pc = RTCPeerConnection()
        self.pcs.append(pc)

        @pc.on("datachannel")
        def on_dc(ch):
            st = {"w": None, "next": 0, "t0": None, "arr": open(self.d / "arrival.jsonl", "w")}

            @ch.on("message")
            def on_msg(m):
                now = time.monotonic()
                if isinstance(m, str):
                    rate = json.loads(m)["rate"]
                    st["rate"] = rate
                    st["w"] = w = wave.open(str(self.d / "heard.wav"), "wb")
                    w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(rate))
                    self.closers.append(lambda: (w.close(), st["arr"].close()))
                    return
                seq = int.from_bytes(m[:4], "little")
                if st["t0"] is None:
                    st["t0"] = now
                if seq > st["next"]:
                    st["w"].writeframes(b"\0\0" * ((len(m) - 4) // 2) * (seq - st["next"]))
                st["w"].writeframes(m[4:])
                st["next"] = seq + 1
                st["arr"].write(json.dumps([round(seq * 0.02, 3), round(now - st["t0"], 4)]) + "\n")

        @pc.on("track")
        def on_track(track):
            self.tasks.append(asyncio.ensure_future(self._record(track)))
        await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="offer"))
        await pc.setLocalDescription(await pc.createAnswer())
        return pc.localDescription.sdp

    async def _record(self, track):
        import numpy as np
        w = wave.open(str(self.d / "heard.wav"), "wb")
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000)
        arr = open(self.d / "arrival.jsonl", "w")
        pos = p0 = t0 = None
        try:
            while True:
                fr = await track.recv()
                now = time.monotonic()
                pts = int(fr.pts * fr.time_base * 48000)
                if p0 is None:
                    p0, t0, pos = pts, now, pts
                x = fr.to_ndarray().reshape(-1, fr.layout.nb_channels if hasattr(fr.layout, "nb_channels")
                                            else len(fr.layout.channels))
                if fr.sample_rate != 48000:
                    continue
                x = x.mean(axis=1).astype("<i2") if x.ndim == 2 and x.shape[1] > 1 else x.reshape(-1).astype("<i2")
                if pts > pos:
                    w.writeframes(b"\0\0" * (pts - pos))      # missing RTP time = silence
                    pos = pts
                if pts == pos:
                    w.writeframes(x.tobytes())
                    pos += len(x)
                arr.write(json.dumps([round((pts - p0) / 48000, 3), round(now - t0, 4)]) + "\n")
        except Exception:  # noqa: BLE001 - track ended
            pass
        finally:
            w.close(); arr.close()

    def close(self):

        async def _c():
            for pc in self.pcs:
                await pc.close()
            for c in self.closers:
                c()
            await asyncio.sleep(0.5)
        try:
            asyncio.run_coroutine_threadsafe(_c(), self.loop).result(10)
        except Exception:  # noqa: BLE001
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


def main():
    d = Path(sys.argv[1])
    far = FarEnd(d)

    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(d), **k)

        def do_POST(self):
            sdp = self.rfile.read(int(self.headers["Content-Length"])).decode()
            body = far.answer(sdp).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *a: stop.set())
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"http://127.0.0.1:{srv.server_address[1]}/index.html", flush=True)
    stop.wait()
    far.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
