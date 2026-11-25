#!/usr/bin/env python3
"""Escalation to a human: rings THIS phone and lets a person take over a live WhatsApp AI call with the phone's
own mic and speaker.

Why a browser page: Termux has no RECORD_AUDIO permission (PulseAudio's module-sles-source fails to load) and the
Termux:API app isn't installed. Android Chrome DOES have the mic, and with getUserMedia it uses the phone's
hardware echo canceller, so speakerphone doesn't echo back to the caller. The page (http://localhost:8787, local
only) talks WebRTC to this server (aiortc, like live_agent.py) and the server bridges it into the call's PulseAudio
devices:

  WhatsApp caller -> callout_sink.monitor -> [this server] -> WebRTC -> Chrome page -> phone speaker/earpiece
  phone mic -> Chrome page (AEC) -> WebRTC -> [this server] -> virtmic_sink -> virtmic -> WhatsApp -> caller

Ringing: a ringtone + a spoken announcement ("<caller> needs a person: <reason>") on the phone speaker
(OpenSL_ES_sink, works without any extra app), and the page is brought to the front with `am start`.

Flow (auto_answer.py drives it through Client):
  call starts  -> POST /call      state "live"      (page shows "Take over" for a manual takeover any time)
  AI says "...connect you to a person..." (EscalationWatcher) -> POST /ring -> state "ringing" for RING_SECS
  human taps Answer -> POST /accept (SDP offer) -> state "connected"; auto_answer.py stops the AI at once
  human taps Decline / nobody answers -> state "declined" / "missed"; auto_answer.py tells the caller
  human taps Hang up -> state "hangup"; auto_answer.py ends the WhatsApp call
  call ends    -> POST /end       state "idle", bridge closed

  python3 scripts/handoff.py serve         # the server (answer_daemon.sh keeps it running)
  python3 scripts/handoff.py ring "Test caller" "testing the ringer"   # ring now (no call needed)
  python3 scripts/handoff.py status
Env: HANDOFF_PORT (8787), HANDOFF_RING_SECS (45), HANDOFF_SPEAKER (OpenSL_ES_sink), HANDOFF=0 disables it in calls.
"""
import asyncio, fractions, json, os, re, subprocess, sys, threading, time, urllib.request, wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PORT = int(os.environ.get("HANDOFF_PORT", "8787"))
URL = f"http://localhost:{PORT}/"
RING_SECS = float(os.environ.get("HANDOFF_RING_SECS", "45"))
SPEAKER = os.environ.get("HANDOFF_SPEAKER", "OpenSL_ES_sink")
CALL_IN = os.environ.get("HANDOFF_CALL_IN", "callout_sink.monitor")   # what the caller says
CALL_OUT = os.environ.get("HANDOFF_CALL_OUT", "virtmic_sink")          # what WhatsApp sends to the caller
RATE, FRAME = 48000, 960                                      # 20 ms, Opus native rate
RUN = Path(os.environ.get("XDG_RUNTIME_DIR") or Path.home() / ".cache") / "wa-virtmic"


def log(*a):
    print(time.strftime("%H:%M:%S"), "handoff:", *a, flush=True)


# ---------------------------------------------------------------------------------------------- transcript trigger
# The AI is told to say this exact kind of line when the caller needs a person (handoff instructions below); the
# SCRIPT then rings - same idea as hangup.py: don't trust the model to call a tool.
AI_ESCALATE = re.compile(
    r"\b(connect|connecting|transfer|transferring|put|putting|pass|passing|get|getting)\b.{0,25}"
    r"\b(you\b.{0,15})?(to|with|through to)\b.{0,12}\b(a |an |the |my |real )?"
    r"(person|human|someone|somebody|team ?member|owner|boss|manager|representative|agent)\b", re.I)

INSTRUCTIONS = """
HANDING OVER TO A PERSON: a real person can join this call. If the caller asks for a human / real person / the owner,
or is upset, or needs something you can't do (a decision, money, a promise, anything you're unsure about), say:
"Let me connect you to a person, please hold on." Then keep the caller company briefly while their phone rings.
If a person joins, you will be cut off - that's expected. Don't offer a person for things you can handle yourself."""


class EscalationWatcher:
    """feed(who, text) gets every transcript line. Fires on_escalate(reason) once per call when the AI says it is
    connecting the caller to a person. reason = the caller's last few lines (what they need)."""

    def __init__(self, on_escalate, log=print):
        self.on_escalate, self.log = on_escalate, log
        self.caller_lines: list[str] = []
        self.fired = False

    def feed(self, who: str, text: str):
        if who == "CALLER":
            self.caller_lines = (self.caller_lines + [text])[-3:]
        elif who == "AI" and not self.fired and AI_ESCALATE.search(text):
            self.fired = True
            reason = " ".join(self.caller_lines)[-240:] or "the caller asked for a person"
            self.log(f"handoff: AI is escalating ({text[:80]!r}) - ringing the phone")
            threading.Thread(target=self.on_escalate, args=(reason,), daemon=True).start()


# ---------------------------------------------------------------------------------------------- client (auto_answer)
class Client:
    """Used by auto_answer.py. All calls are best-effort: a dead handoff server never disturbs a call.
    .state is refreshed every 0.5 s by a background thread (never blocks the Playwright loop)."""

    def __init__(self):
        self.state, self._stop = "idle", threading.Event()

    def _req(self, path, body=None, timeout=1.5):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(URL.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=timeout))

    def available(self) -> bool:
        if os.environ.get("HANDOFF", "1") == "0":
            return False
        try:
            return bool(self._req("/state"))
        except Exception:
            return False

    def call_started(self, caller, num=None):
        try:
            self._req("/call", {"caller": caller, "num": num})
        except Exception as e:
            log(f"server not reachable ({type(e).__name__})")
        threading.Thread(target=self._poll, daemon=True).start()

    def _poll(self):
        while not self._stop.is_set():
            try:
                self.state = self._req("/state", timeout=1)["state"]
            except Exception:
                pass
            self._stop.wait(0.5)

    def ring(self, reason):
        try:
            self._req("/ring", {"reason": reason}, timeout=5)
        except Exception as e:
            log(f"ring failed: {type(e).__name__}: {e}")

    def call_ended(self):
        self._stop.set()
        try:
            self._req("/end", {})
        except Exception:
            pass


# ---------------------------------------------------------------------------------------------- server
class Ringer:
    """Ringtone + spoken announcement on the phone speaker until stop()."""

    def __init__(self):
        self.stop_ev, self.proc, self.th = threading.Event(), None, None

    @staticmethod
    def ringtone() -> Path:
        p = RUN / "handoff_ring.wav"
        if not p.exists():
            import numpy as np
            r = 44100
            t = np.arange(int(r * 0.4)) / r
            burst = 0.45 * (np.sin(2 * np.pi * 400 * t) + np.sin(2 * np.pi * 450 * t)) / 2
            env = np.minimum(1, np.minimum(t, t[::-1]) / 0.01)            # 10 ms fades: no clicks
            gap = np.zeros(int(r * 0.2))
            x = np.concatenate([burst * env, gap, burst * env, np.zeros(int(r * 1.2))])
            RUN.mkdir(parents=True, exist_ok=True)
            with wave.open(str(p), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(r)
                w.writeframes((x * 32767).astype("<i2").tobytes())
        return p

    def start(self, announcement: str):
        self.stop_ev.clear()
        self.th = threading.Thread(target=self._run, args=(announcement,), daemon=True)
        self.th.start()

    def _play(self, path):
        if self.stop_ev.is_set():
            return
        self.proc = subprocess.Popen(["paplay", f"--device={SPEAKER}", str(path)])
        self.proc.wait()

    def _run(self, announcement):
        subprocess.run(["pactl", "set-sink-volume", SPEAKER, "100%"], capture_output=True)
        ann = RUN / "handoff_announce.wav"
        ann.unlink(missing_ok=True)

        def synth():   # gateway TTS takes ~4 s: ring meanwhile
            try:
                from speak import synth_wav
                synth_wav(announcement, str(ann))
            except Exception as e:
                log(f"announcement TTS failed: {type(e).__name__}: {e}")
        threading.Thread(target=synth, daemon=True).start()
        ring, n = self.ringtone(), 0
        while not self.stop_ev.is_set():
            self._play(ring)
            n += 1
            if n % 3 == 1 and ann.exists():    # ring, announce, ring, ring, announce, ...
                self._play(ann)

    def stop(self):
        self.stop_ev.set()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()


class Bridge:
    """One WebRTC connection to the takeover page, bridged into the call's PulseAudio devices."""

    def __init__(self, loop):
        self.loop, self.pc, self.procs, self.tasks = loop, None, [], []

    async def answer(self, sdp: str, typ: str) -> dict:
        import av
        from aiortc import MediaStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
        await self.close()
        parec = await asyncio.create_subprocess_exec(
            "parec", f"--device={CALL_IN}", "--raw", "--format=s16le", f"--rate={RATE}", "--channels=1",
            "--latency-msec=20", stdout=asyncio.subprocess.PIPE)
        pacat = await asyncio.create_subprocess_exec(
            "pacat", "--playback", f"--device={CALL_OUT}", "--raw", "--format=s16le", f"--rate={RATE}",
            "--channels=1", "--latency-msec=100", stdin=asyncio.subprocess.PIPE)
        self.procs = [parec, pacat]

        class CallerTrack(MediaStreamTrack):
            kind = "audio"

            def __init__(self):
                super().__init__()
                self.pts = 0

            async def recv(self):
                data = await parec.stdout.readexactly(FRAME * 2)   # parec paces this in real time
                fr = av.AudioFrame(format="s16", layout="mono", samples=FRAME)
                fr.planes[0].update(data)
                fr.sample_rate, fr.pts, fr.time_base = RATE, self.pts, fractions.Fraction(1, RATE)
                self.pts += FRAME
                return fr

        pc = self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))   # same phone: no STUN needed
        pc.addTrack(CallerTrack())

        async def play(track):
            rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
            while True:
                try:
                    fr = await track.recv()
                except Exception:
                    return
                q = getattr(track, "_queue", None)
                if q is not None and q.qsize() > 10:   # fell behind (busy phone): drop backlog, keep it live
                    continue
                for out in rs.resample(fr):
                    try:
                        pacat.stdin.write(bytes(out.planes[0])[: out.samples * 2])
                        await pacat.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        return

        @pc.on("track")
        def on_track(track):
            if track.kind == "audio":
                log("human's mic is live -> caller")
                self.tasks.append(asyncio.ensure_future(play(track)))

        @pc.on("connectionstatechange")
        async def on_state():
            log(f"page connection: {pc.connectionState}")

        await pc.setRemoteDescription(RTCSessionDescription(sdp, typ))
        await pc.setLocalDescription(await pc.createAnswer())
        return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}

    async def close(self):
        for t in self.tasks:
            t.cancel()
        self.tasks = []
        if self.pc:
            await self.pc.close()
            self.pc = None
        for p in self.procs:
            if p.returncode is None:
                p.kill()
        self.procs = []


class Desk:
    def __init__(self):
        self.lock = threading.Lock()
        self.s = {"state": "idle", "caller": None, "num": None, "reason": None, "since": time.time()}
        self.ringer = Ringer()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.bridge = Bridge(self.loop)
        self.ring_id = 0

    def set(self, state, **kw):
        with self.lock:
            self.s.update(kw, state=state, since=time.time())
        log(f"state -> {state}" + (f" {kw}" if kw else ""))

    def run(self, coro, timeout=20):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    # -- actions
    def call(self, caller, num):
        self.ringer.stop()
        self.run(self.bridge.close())
        self.set("live", caller=caller, num=num, reason=None)

    def ring(self, reason):
        if self.s["state"] in ("ringing", "connected"):
            return
        self.ring_id += 1
        rid, who = self.ring_id, self.s["caller"] or "A caller"
        self.set("ringing", reason=reason)
        self.ringer.start(f"Call for you. {who} needs a person. {reason}. Open the takeover page and tap Answer.")
        try:   # bring the page to the front (Termux needs "Display over other apps" for this from the background)
            subprocess.run(["am", "start", "--user", "0", "-a", "android.intent.action.VIEW", "-d", URL + "?ring",
                            "-e", "com.android.browser.application_id", "wa-handoff", "com.android.chrome"],
                           capture_output=True, timeout=15)
        except Exception as e:
            log(f"could not open the page: {type(e).__name__}: {e}")

        def timeout():
            time.sleep(RING_SECS)
            if self.ring_id == rid and self.s["state"] == "ringing":
                self.ringer.stop()
                self.set("missed")
        threading.Thread(target=timeout, daemon=True).start()

    def accept(self, sdp, typ):
        if self.s["state"] not in ("live", "ringing", "connected"):
            raise ValueError(f"no call to take over (state {self.s['state']})")
        self.ringer.stop()
        ans = self.run(self.bridge.answer(sdp, typ))
        self.set("connected")
        return ans

    def decline(self):
        if self.s["state"] == "ringing":
            self.ringer.stop()
            self.set("declined")

    def hangup(self):
        if self.s["state"] != "idle":
            self.set("hangup")

    def end(self):
        self.ringer.stop()
        self.run(self.bridge.close())
        self.set("idle", caller=None, num=None, reason=None)


def serve():
    desk = Desk()
    page = (HERE / "handoff.html").read_bytes()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            b = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path.split("?")[0] == "/":
                return self._send(200, page, "text/html; charset=utf-8")
            if self.path == "/state":
                with desk.lock:
                    return self._send(200, dict(desk.s, ring_secs=RING_SECS, now=time.time()))
            self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            try:
                if self.path == "/call":
                    desk.call(body.get("caller"), body.get("num"))
                elif self.path == "/ring":
                    desk.ring(body.get("reason") or "")
                elif self.path == "/accept":
                    return self._send(200, desk.accept(body["sdp"], body.get("type", "offer")))
                elif self.path == "/decline":
                    desk.decline()
                elif self.path == "/hangup":
                    desk.hangup()
                elif self.path == "/end":
                    desk.end()
                else:
                    return self._send(404, {"error": "not found"})
                self._send(200, {"ok": True, "state": desk.s["state"]})
            except Exception as e:
                log(f"{self.path} failed: {type(e).__name__}: {e}")
                self._send(409, {"error": str(e)})

    # localhost only: the page runs in this phone's Chrome; nobody on the Wi-Fi can take over a call
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    log(f"takeover page on {URL} (ring {RING_SECS:g}s on {SPEAKER})")
    srv.serve_forever()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    c = Client()
    if cmd == "serve":
        serve()
    elif cmd == "ring":   # test: ring without a call
        caller = sys.argv[2] if len(sys.argv) > 2 else "Test caller"
        c._req("/call", {"caller": caller})
        c.ring(sys.argv[3] if len(sys.argv) > 3 else "This is a test of the ringer.")
        print(f"ringing; answer on {URL} - stop with: python3 {sys.argv[0]} end")
    elif cmd == "end":
        c.call_ended(); print("ended")
    else:
        try:
            print(json.dumps(c._req("/state"), indent=1))
        except Exception as e:
            print(f"handoff server not running ({type(e).__name__}) - start: python3 {sys.argv[0]} serve")
