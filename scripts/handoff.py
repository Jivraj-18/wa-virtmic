#!/usr/bin/env python3
"""Escalation to a human: rings THIS phone and lets a person take over a live WhatsApp AI call with the phone's
own mic and speaker.

Why a browser page: Termux has no RECORD_AUDIO permission (PulseAudio's module-sles-source fails to load) and the
Termux:API app isn't installed. Android Chrome DOES have the mic, and with getUserMedia it uses the phone's
hardware echo canceller, so speakerphone doesn't echo back to the caller. The page (http://localhost:8787, local
only) streams PCM over a WebSocket (:8788) to this server, which bridges it into the call's PulseAudio
devices:

  WhatsApp caller -> callout_sink.monitor -> [this server] -> WebSocket -> Chrome page -> phone speaker/earpiece
  phone mic -> Chrome page (AEC) -> WebSocket -> [this server] -> virtmic_sink -> virtmic -> WhatsApp -> caller

Ringing: a ringtone + a spoken announcement ("<caller> needs a person: <reason>") on the phone speaker
(OpenSL_ES_sink, works without any extra app), and the page is brought to the front with `am start`.

Flow (auto_answer.py drives it through Client):
  call starts  -> POST /call      state "live"      (page shows "Take over" for a manual takeover any time)
  AI says "...connect you to a person..." (EscalationWatcher) -> POST /ring -> state "ringing" for RING_SECS
  human taps Answer -> POST /accept + WebSocket audio -> state "connected"; auto_answer.py stops the AI at once
  human taps Decline / nobody answers -> state "declined" / "missed"; auto_answer.py tells the caller
  human taps Hang up -> state "hangup"; auto_answer.py ends the WhatsApp call
  call ends    -> POST /end       state "idle", bridge closed

  python3 scripts/handoff.py serve         # the server (answer_daemon.sh keeps it running)
  python3 scripts/handoff.py ring "Test caller" "testing the ringer"   # ring now (no call needed)
  python3 scripts/handoff.py status
Env: HANDOFF_PORT (8787), HANDOFF_RING_SECS (45), HANDOFF_SPEAKER (OpenSL_ES_sink), HANDOFF=0 disables it in calls.
"""
import asyncio, json, os, re, subprocess, sys, threading, time, urllib.request, wave
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
RUN = Path(os.environ.get("XDG_RUNTIME_DIR") or Path.home() / ".cache") / "wa-virtmic"


def log(*a):
    print(time.strftime("%H:%M:%S"), "handoff:", *a, flush=True)


# ---------------------------------------------------------------------------------------------- transcript trigger
OWNER = os.environ.get("OWNER_NAME", "Jivraj")   # the person who takes over (named in the greeting too)
# The AI is told to say this exact kind of line when the caller needs a person (handoff instructions below); the
# SCRIPT then rings - same idea as hangup.py: don't trust the model to call a tool.
# The caller may ask in ANY words/language - GPT-Live understands that and answers with the fixed line in INSTRUCTIONS;
# we only have to recognise the AI's own line (plus close paraphrases, Hinglish and Devanagari) here.
_WHO = (r"(person|human|someone|somebody|team ?member|owner|boss|manager|representative|agent|"
        + re.escape(OWNER) + r"|जीवराज|जिवराज)")
AI_ESCALATE = re.compile(
    r"\b(connect|connecting|transfer|transferring|put|putting|pass|passing|get|getting)\b.{0,25}"
    r"\b(you\b.{0,15})?(to|with|through to)\b.{0,12}\b(a |an |the |my |real )?" + _WHO + r"\b"
    r"|\b(ringing|calling|get|getting|bringing)\s+" + re.escape(OWNER) + r"\b(?!'s)"
    r"|\b" + re.escape(OWNER) + r"\b.{0,25}\b(se|ko)\b.{0,20}\b(connect|bula|jod|transfer)"
    r"|(जीवराज|जिवराज).{0,30}(कनेक्ट|जोड़|बुला|ट्रांसफर)", re.I)

INSTRUCTIONS = f"""
HANDING OVER TO {OWNER.upper()}: {OWNER} (a real person) can join this call - your greeting tells the caller they can
ask for {OWNER} at any time. Treat ANY way of asking as a request to escalate, in any language or wording, e.g.
"I want to talk to {OWNER}", "is {OWNER} there?", "put me through", "can I speak to a real person / human?",
"{OWNER} se baat karao", "{OWNER} ko bulao", or just "yes" / "haan" right after you offered {OWNER}. Also escalate if
the caller is upset or needs something you can't do (a decision, money, a promise, anything you're unsure about).
Don't ask "are you sure?" and don't try to handle it yourself first. Escalate at once by saying, in English, exactly:
"Sure, connecting you to {OWNER} now, please hold on." (that sentence is what rings {OWNER}'s phone - say it even if
you are speaking Hindi, then you may continue in Hindi). Then keep the caller company briefly while it rings.
If {OWNER} joins, you will be cut off - that's expected. Never say that sentence unless you really are connecting."""

# When the handoff server is down the greeting still offers {OWNER}: don't pretend to connect, take a message.
INSTRUCTIONS_OFF = f"""
If the caller asks for {OWNER} or a human (in any words): {OWNER} can't join this call right now - apologise, take
their message (name, what it's about, how to reach them) and say {OWNER} will get back to them."""


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
        elif who == "AI" and not self.fired and self.caller_lines and AI_ESCALATE.search(text):
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

    @staticmethod
    def has_api() -> bool:
        """Termux:API app installed? Without it every termux-* command hangs, so check the package first."""
        try:
            out = subprocess.run(["cmd", "package", "list", "packages", "com.termux.api"],
                                 capture_output=True, text=True, timeout=10).stdout
            return "package:com.termux.api" in out
        except Exception:
            return False

    def notify(self, who: str, reason: str):
        """Tappable high-priority notification (needs Termux:API): tap it or 'Answer' -> the takeover page."""
        if not self.has_api():
            log("no Termux:API app - no notification (install it for a tappable 'Answer' notification)")
            return
        opener = f"termux-open-url {URL}?ring"
        cmd = ["termux-notification", "--id", "wa-handoff", "--priority", "max", "--ongoing", "--vibrate", "500,300,500",
               "--title", f"\U0001F4DE {who} needs you", "--content", (reason or "Tap to take over the call")[:200],
               "--action", opener, "--button1", "Answer", "--button1-action", opener]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            log(f"notification posted{'' if r.returncode == 0 else f' (rc {r.returncode}: {r.stderr.strip()[:200]})'}")
        except Exception as e:
            log(f"notification failed: {type(e).__name__}: {e}")
        self.notified = True

    def unnotify(self):
        if getattr(self, "notified", False):
            self.notified = False
            threading.Thread(target=lambda: subprocess.run(["termux-notification-remove", "wa-handoff"],
                                                           capture_output=True, timeout=15), daemon=True).start()

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
        self.unnotify()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()


class Bridge:
    """The takeover page's audio, as raw 16 kHz mono s16 PCM over a localhost WebSocket (port PORT+1).

    Was WebRTC (aiortc): on the phone ICE never connected - Android Chrome hides its host addresses behind mDNS
    names (*.local) that aiortc can't use, and the link went "failed" after 30 s. The page already reaches localhost
    over HTTP, so a WebSocket needs no ICE at all. Chrome's getUserMedia still applies the phone's echo canceller."""

    RATE, CHUNK = 16000, 640          # 20 ms of s16 mono
    MAX_BACKLOG = 16000               # 0.5 s queued for the caller -> drop, stay live

    def __init__(self, loop):
        self.loop, self.ws, self.procs = loop, None, []
        asyncio.run_coroutine_threadsafe(self._serve(), loop).result(10)

    async def _serve(self):
        import websockets
        self.server = await websockets.serve(self._client, "127.0.0.1", PORT + 1, max_size=2 ** 16,
                                             compression=None, ping_interval=5, ping_timeout=10)

    async def _client(self, ws):
        if not self.allowed():
            await ws.close(4001, "no call taken over")
            return
        await self.close()            # one human at a time: a rejoin replaces the old link
        self.ws = ws
        parec = await asyncio.create_subprocess_exec(
            "parec", f"--device={CALL_IN}", "--raw", "--format=s16le", f"--rate={self.RATE}", "--channels=1",
            "--latency-msec=20", stdout=asyncio.subprocess.PIPE)
        pacat = await asyncio.create_subprocess_exec(
            "pacat", "--playback", f"--device={CALL_OUT}", "--raw", "--format=s16le", f"--rate={self.RATE}",
            "--channels=1", "--latency-msec=60", stdin=asyncio.subprocess.PIPE)
        self.procs = [parec, pacat]
        log("page audio connected: caller <-> human")

        async def to_page():          # what the caller says -> the human's speaker
            while True:
                data = await parec.stdout.readexactly(self.CHUNK)
                await ws.send(data)

        async def from_page():        # the human's mic -> the caller
            n = 0
            async for msg in ws:
                if isinstance(msg, bytes) and msg:
                    if pacat.stdin.transport.get_write_buffer_size() > self.MAX_BACKLOG:
                        continue
                    pacat.stdin.write(msg)
                    n += 1
                    if n == 1:
                        log("human's mic is live -> caller")
        tasks = [asyncio.ensure_future(to_page()), asyncio.ensure_future(from_page())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except Exception:
            pass
        finally:
            for t in tasks:
                t.cancel()
            for pr in (parec, pacat):
                if pr.returncode is None:
                    pr.kill()
            if self.ws is ws:
                self.ws = None
            log("page audio disconnected")

    allowed = staticmethod(lambda: False)   # set by Desk: only while state == connected

    async def close(self):
        if self.ws:
            ws, self.ws = self.ws, None
            await ws.close()
        for pr in self.procs:
            if pr.returncode is None:
                pr.kill()
        self.procs = []


class Desk:
    def __init__(self):
        self.lock = threading.Lock()
        self.s = {"state": "idle", "caller": None, "num": None, "reason": None, "since": time.time()}
        self.ringer = Ringer()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.bridge = Bridge(self.loop)
        self.bridge.allowed = lambda: self.s["state"] == "connected"
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
        self.ringer.start(f"Call for you. {who} needs a person. {reason}. Tap the notification to answer.")
        threading.Thread(target=self.ringer.notify, args=(who, reason), daemon=True).start()
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

    def accept(self):
        """The page then opens ws://localhost:PORT+1 for the audio."""
        if self.s["state"] not in ("live", "ringing", "connected"):
            raise ValueError(f"no call to take over (state {self.s['state']})")
        self.ringer.stop()
        self.set("connected")
        return {"ok": True, "ws": f"ws://localhost:{PORT + 1}/"}

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
                    return self._send(200, desk.accept())
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
