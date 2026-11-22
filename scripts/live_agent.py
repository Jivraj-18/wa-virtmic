#!/usr/bin/env python3
"""Full-duplex voice agent on OpenAI GPT-Live (gpt-live-1) over WebRTC, as a drop-in for realtime_agent.Agent.

Why: gpt-realtime-2.1 is turn-based (it answers only after ~500 ms of caller silence), so it can't jump in while
the caller is still talking (a tester's "say every multiple of three while I count" test failed). GPT-Live is
full-duplex: it listens and speaks at the same time and decides itself when to talk, backchannel or yield.

How it connects without a raw API key: the LLM gateway can't proxy WebSockets, but WebRTC only needs one plain
HTTPS POST (our SDP offer -> /v1/live/sessions -> SDP answer), which the gateway forwards. Media then flows
directly between this process and OpenAI. aiortc does the WebRTC part.

Audio: callout_sink.monitor (what the WhatsApp caller says) -> WebRTC mic track -> GPT-Live -> remote track ->
virtmic_sink (what WhatsApp sends to the caller). Same devices as realtime_agent.Agent.

Interface (same as Agent): LiveAgent(transcript, log, instructions, greeting, on_line, ...).start_thread(max_s),
.stop (threading.Event). greeting=None -> it is told to wait for the other person to speak first.
Try it alone:  python3 scripts/live_agent.py 60     (talk into callout_sink, hear it on virtmic)
"""
import asyncio, fractions, json, os, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gateway  # noqa: E402

MODEL = os.environ.get("LIVE_MODEL", "gpt-live-1")
VOICE = os.environ.get("LIVE_VOICE", "marin")
RATE = 48000                  # WebRTC/Opus native rate; avoids resampling on the way in
FRAME = RATE // 50            # 20 ms
# Playback buffer. 60 ms was too small on the phone: every hiccup of this Python loop (busy CPU, swap) became a
# gap in the AI's voice - callers said it was "very cracky" (10-18 % of speech was cut-outs on GPT-Live calls).
PLAY_LATENCY_MS = int(os.environ.get("LIVE_PLAY_LATENCY_MS", "250"))
OUT_QUEUE_BYTES = int(os.environ.get("LIVE_OUT_QUEUE_BYTES", "8192"))   # ~85 ms at 48 kHz mono s16


class LiveAgent:
    def __init__(self, transcript: Path | None = None, log=print, instructions: str = "", greeting: str | None = "",
                 in_device="callout_sink.monitor", out_device="virtmic_sink", on_line=None, **_ignored):
        self.transcript, self.log, self.on_line = transcript, log, on_line
        self.instructions = instructions
        if greeting is None:
            self.instructions += "\nWait for the other person to speak first; don't talk while the phone is ringing."
        elif greeting:
            self.instructions += f"\nWhen the call connects: {greeting}"
        self.in_device, self.out_device = in_device, out_device
        self.stop = threading.Event()
        self.t0 = time.time()
        self._buf = {"CALLER": "", "AI": ""}
        self._last = {"CALLER": 0.0, "AI": 0.0}
        self._seen = set()

    # ---- transcript (same line format as realtime_agent.Agent.say) ------------------------------------
    def say(self, who: str, text: str):
        if not text.strip():
            return
        t = time.time() - self.t0
        line = f"[{int(t) // 60:02d}:{t % 60:04.1f}] {who:6s} {text.strip()}"
        self.log(line)
        if self.transcript:
            with open(self.transcript, "a") as f:
                f.write(line + "\n")
        if self.on_line:
            try:
                self.on_line(who, text.strip())
            except Exception as e:
                self.log(f"on_line hook failed: {type(e).__name__}: {e}")

    def _flush(self, who: str):
        text, self._buf[who] = self._buf[who], ""
        self.say(who, text)

    def _on_event(self, ev: dict):
        ty = ev.get("type", "")
        if ty not in self._seen:          # log each new event type once: GPT-Live is new, names may change
            self._seen.add(ty)
            self.log(f"live: event {ty}")
        # full duplex: both sides can talk at once, so each side keeps its own line (flushed after 1.2 s quiet)
        if ty == "session.input_transcript.delta":
            self._buf["CALLER"] += ev.get("delta", ""); self._last["CALLER"] = time.time()
        elif ty == "session.output_transcript.delta":
            self._buf["AI"] += ev.get("delta", ""); self._last["AI"] = time.time()
        elif ty.endswith("transcript.done") or ty.endswith("transcript.completed"):
            self._flush("CALLER" if "input" in ty else "AI")
        elif ty == "error":
            self.log(f"live error: {json.dumps(ev)[:300]}")

    # ---- main --------------------------------------------------------------------------------------
    async def run(self, max_seconds: float = 3600):
        import urllib.request
        import av
        import numpy as np
        from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription

        agent = self

        class CallerTrack(MediaStreamTrack):
            """20 ms s16 mono 48 kHz frames read from PulseAudio (the WhatsApp caller)."""
            kind = "audio"

            def __init__(self, proc):
                super().__init__()
                self.proc, self.pts = proc, 0

            async def recv(self):
                data = await self.proc.stdout.readexactly(FRAME * 2)  # parec paces this in real time
                fr = av.AudioFrame(format="s16", layout="mono", samples=FRAME)
                fr.planes[0].update(data)
                fr.sample_rate, fr.pts, fr.time_base = RATE, self.pts, fractions.Fraction(1, RATE)
                self.pts += FRAME
                n = self.pts // FRAME
                if n % 250 == 0:  # every 5 s of audio: how far behind real time are we?
                    agent.log(f"live: sent {n * 0.02:.0f}s of caller audio, {time.time() - agent.t_track0 - n * 0.02:+.2f}s"
                              " vs real time")
                return fr

        gateway.load_env()
        parec = await asyncio.create_subprocess_exec(
            "parec", f"--device={self.in_device}", "--raw", "--format=s16le", f"--rate={RATE}", "--channels=1",
            "--latency-msec=20", stdout=asyncio.subprocess.PIPE)
        pacat = await asyncio.create_subprocess_exec(
            "pacat", "--playback", f"--device={self.out_device}", "--raw", "--format=s16le", f"--rate={RATE}",
            "--channels=1", f"--latency-msec={PLAY_LATENCY_MS}", stdin=asyncio.subprocess.PIPE)
        # Keep audio waiting for pacat SMALL. asyncio's write buffer (64 KB) + the pipe (64 KB) could hold ~1.4 s of
        # the AI's voice: bench runs showed writes blocking 0.65-0.85 s = the pipe full = the caller hears the AI
        # that much late ("you are lagging"), and skip-silence can't trim audio that already left aiortc's queue.
        out_fd = None
        try:
            pacat.stdin.transport.set_write_buffer_limits(high=OUT_QUEUE_BYTES)
            out_fd = pacat.stdin.transport.get_extra_info("pipe").fileno()
            import fcntl
            fcntl.fcntl(out_fd, 1031, OUT_QUEUE_BYTES)  # F_SETPIPE_SZ (rounded up to a page)
        except Exception as e:
            self.log(f"live: could not shrink the playback queue: {type(e).__name__}: {e}")

        def out_queued_ms():
            """Audio written but not yet taken by pacat (asyncio buffer + pipe), in ms."""
            try:
                import fcntl, termios, struct
                n = pacat.stdin.transport.get_write_buffer_size()
                if out_fd is not None:
                    n += struct.unpack("i", fcntl.ioctl(out_fd, termios.FIONREAD, b"\0\0\0\0"))[0]
                return n / (2 * RATE) * 1000
            except Exception:
                return -1
        pc = RTCPeerConnection()
        self.t_track0 = time.time()
        pc.addTrack(CallerTrack(parec))
        dc = pc.createDataChannel("oai-events")
        started = asyncio.get_running_loop().create_future()
        tasks = []

        @dc.on("message")
        def on_message(msg):
            ev = json.loads(msg)
            if ev.get("type") == "session.started" and not started.done():
                started.set_result(ev)
            self._on_event(ev)

        async def play(track):
            rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
            first, nfr, last_warn = True, 0, -500
            # per-5 s diagnostics (crackle hunt): frames in, longest wait for a frame, longest write into pacat
            w = {"n": 0, "rgap": 0.0, "wmax": 0.0, "drop": 0, "t": time.time(), "last": time.time(), "outq": 0.0}
            while not self.stop.is_set():
                try:
                    fr = await track.recv()
                except Exception:
                    break
                nfr += 1
                now = time.time()
                w["n"] += 1; w["rgap"] = max(w["rgap"], now - w["last"]); w["last"] = now
                if now - w["t"] >= 5:
                    self.log(f"live: audio-in 5s: {w['n']} frames (250 = real time), longest wait {w['rgap']*1e3:.0f} ms, "
                              f"longest pacat write {w['wmax']*1e3:.0f} ms, out-queue max {w['outq']:.0f} ms, silence skipped {w['drop']}, "
                              f"queued {getattr(track, '_queue', None).qsize() if hasattr(track, '_queue') else '?'}, "
                              f"loop lag {self._lag * 1e3:.0f} ms")
                    w.update(n=0, rgap=0.0, wmax=0.0, drop=0, t=now, outq=0.0); self._lag = 0.0
                if nfr == 1:
                    self.log(f"live: first remote frame {time.time() - t_post:.2f}s after connect")
                # GPT-Live streams 20 ms frames (silence too) from session start, into aiortc's UNBOUNDED queue, and
                # pacat only takes them in real time. Any stall here (busy phone while WhatsApp dials) left a backlog
                # that was never caught up: on a call to Sujal the AI's voice came 10 s after its text and he hung
                # up. So skip queued SILENT frames while behind; speech is never dropped.
                q = getattr(track, "_queue", None)
                backlog = q.qsize() if q is not None else 0
                if backlog >= 50 and nfr - last_warn > 500:
                    last_warn = nfr
                    self.log(f"live: AI audio {backlog * 0.02:.1f}s behind - dropping silence to catch up")
                for out in rs.resample(fr):
                    pcm = bytes(out.planes[0])[: out.samples * 2]
                    if backlog > 5 and int(np.abs(np.frombuffer(pcm, np.int16)).max(initial=0)) < 64:  # silent
                        w["drop"] += 1
                        continue
                    if first and any(pcm):
                        first = False
                        self.log(f"live: first AI audio {time.time() - t_post:.2f}s after connect")
                    try:
                        t_w = time.time()
                        pacat.stdin.write(pcm)
                        await pacat.stdin.drain()
                        w["wmax"] = max(w["wmax"], time.time() - t_w)
                        w["outq"] = max(w["outq"], out_queued_ms())
                    except (BrokenPipeError, ConnectionResetError):
                        return

        # How late this thread's event loop runs (max oversleep of a 20 ms timer per 5 s window). Large lag while the
        # phone is NOT stalled = another thread of this process held Python's GIL (e.g. Playwright in handle_call).
        self._lag = 0.0

        async def lag_monitor():
            while True:
                t = time.time()
                await asyncio.sleep(0.02)
                self._lag = max(self._lag, time.time() - t - 0.02)
        tasks.append(asyncio.ensure_future(lag_monitor()))

        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                tasks.append(asyncio.ensure_future(play(track)))

        # ICE gathering waits for a STUN reply on every local interface; on the phone one never answers and aioice
        # retried for ~5 s (RTO 0.5 s x 6) - heard by callers as silence after we picked up. Short retries ONLY while
        # gathering (1.5 s, same candidates incl. server-reflexive), then the normal values for connectivity checks.
        import aioice.stun as aistun
        saved = aistun.RETRY_MAX, aistun.RETRY_RTO
        aistun.RETRY_MAX, aistun.RETRY_RTO = 2, 0.2
        try:
            t_ice = time.time()
            await pc.setLocalDescription(await pc.createOffer())
        finally:
            aistun.RETRY_MAX, aistun.RETRY_RTO = saved
        self.log(f"live: ICE gathered in {time.time() - t_ice:.1f}s")
        body = {"session": {"model": MODEL, "instructions": self.instructions, "audio": {"output": {"voice": VOICE}}},
                "transport": {"type": "webrtc", "sdp": pc.localDescription.sdp}}
        t_post = time.time()
        req = urllib.request.Request(gateway.base() + "/openai/v1/live/sessions", data=json.dumps(body).encode(),
                                     headers={**gateway.auth_header(), "Content-Type": "application/json"})
        res = await asyncio.to_thread(lambda: json.load(urllib.request.urlopen(req, timeout=30)))
        self.log(f"live: session {res['session']['id'][:16]}… created in {time.time() - t_post:.1f}s ({MODEL})")
        await pc.setRemoteDescription(RTCSessionDescription(res["transport"]["sdp"], "answer"))
        await asyncio.wait_for(started, 20)
        self.log(f"live: ready {time.time() - t_post:.1f}s after POST")

        end = time.time() + max_seconds
        t_stats = time.time()
        while not self.stop.is_set() and time.time() < end and pc.connectionState not in ("failed", "closed"):
            await asyncio.sleep(0.25)
            if time.time() - t_stats >= 10:  # network side of the crackle hunt: packets lost / jitter from OpenAI
                t_stats = time.time()
                try:
                    for st in (await pc.getStats()).values():
                        if st.type == "inbound-rtp":
                            self.log(f"live: rtp-in received {st.packetsReceived} lost {st.packetsLost} "
                                     f"jitter {st.jitter}")
                except Exception as e:
                    self.log(f"live: getStats failed: {type(e).__name__}: {e}")
            for who in ("CALLER", "AI"):  # no explicit done event seen yet: flush a line after 1.2 s of quiet
                if self._buf[who] and time.time() - self._last[who] > 1.2:
                    self._flush(who)
        self.log(f"live: stopping @{time.time() - self.t0:.1f}s ({pc.connectionState})")
        for who in ("CALLER", "AI"):
            self._flush(who)
        if dc.readyState == "open":
            dc.send(json.dumps({"type": "session.close"}))
            await asyncio.sleep(1.5)  # let session.closed (final usage) arrive
        for t in tasks:
            t.cancel()
        await pc.close()
        for p in (parec, pacat):
            if p.returncode is None:
                p.kill()
        self.log("live: session closed")

    def start_thread(self, max_seconds: float = 3600) -> threading.Thread:
        def target():
            try:
                asyncio.run(self.run(max_seconds))
            except Exception as e:
                self.log(f"live: FAILED {type(e).__name__}: {e}")
        th = threading.Thread(target=target, daemon=True)
        th.start()
        return th


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 30
    a = LiveAgent(instructions="You are a friendly AI on a test call. Keep replies short.", greeting="Say hello.")
    a.start_thread(secs).join()
