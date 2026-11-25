"""Live, read-only observability page for the phone stack. Start it plus a Cloudflare tunnel with scripts/dashboard.sh.

    python scripts/dashboard.py [--port 8790]

What it shows (the page polls every 2 s, no refresh; big data is re-sent only when it changed):
  Phone      RAM (total/available/swap), our stack's RAM and CPU grouped by component (WhatsApp Chrome, Nova Chrome,
             Xvfb, PulseAudio, Claude Code, Python agents, proot, tunnel...), 1 h history, disk, battery (Termux:API)
  Network    TCP latency to OpenAI / WhatsApp / Meet / Cloudflare every 10 s (1 h chart); during a WhatsApp or Meet
             call: RTT, loss both ways, jitter, concealed audio, bitrate, direct/relay route (scripts/rtc_stats.py)
  Services   WhatsApp answerer, handoff, Nova autojoin, Nova meeting state, task worker
  Queue      Nova's work queue (queued / active / done) with what each task did
  Claude     every Claude Code session the agents ran (meeting desk, Nova tasks, memory updates, WhatsApp call
             helper): live or finished, model, tokens, and the steps (tools, commands, output, answers)
  Memory     Nova's long-term memory.md and the projects she built
  Logs       tails of the service logs
Android blocks /proc/stat and /proc/loadavg for apps, so CPU is our own processes' CPU (100% = one core), read from
/proc/<pid>/stat deltas.

Security: listens on 127.0.0.1 only. "/" is a static page with no data; every /api/ path needs the access token as a
Bearer header (it travels in the link's #fragment, which is never sent to the server or the tunnel). No path is ever
mapped to a file. Everything leaving the machine is redacted (keys, tokens, emails, phone numbers, meeting links); the
output of steps that touch private data (gws, mail, credentials...) is withheld.
Token: ~/.config/nova/dashboard_token (600, created on first run; delete it and restart to revoke old links).
"""
import argparse, collections, hashlib, hmac, json, os, re, secrets, shutil, subprocess, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "nova"))
import task as T  # noqa: E402

HOME = Path.home()
CONF = HOME / ".config" / "nova"
TOKEN_FILE = CONF / "dashboard_token"
MEMORY = Path(os.environ.get("NOVA_MEMORY", str(CONF / "memory.md")))
PROJECTS = CONF / "projects.json"
TRANSCRIPTS = HOME / ".claude" / "projects"
WA_RUN = Path(os.environ.get("XDG_RUNTIME_DIR", str(HOME / ".cache"))) / "wa-virtmic"
NOVA_RUN = HOME / ".cache" / "nova"
PAGE = HERE / "dashboard.html"
SAMPLE_SECS = 2.0
HISTORY = int(3600 / SAMPLE_SECS)
HIDDEN = "[hidden: this step touches private data]"
LOGS = {"WhatsApp answerer": HERE / "answer_daemon.log", "WhatsApp calls": HERE / "auto_answer.log",
        "Handoff": HERE / "handoff.log", "Nova autojoin": NOVA_RUN / "autojoin.log", "Nova join": NOVA_RUN / "join.log",
        "Nova tasks": NOVA_RUN / "tasks.log"}

# A command or tool matching this has its output withheld completely: regexes cannot recognise every private detail.
PRIVATE = re.compile(r"\b(gws|gmail|calendar|drive|contacts|printenv|environ)\b|\.config|\.ssh|\.env\b|\.claude|"
                     r"credential|secret|token|password|cookie|oauth|\bauth\b|(^|[;&|]\s*)env\b|mcp__", re.I)
RULES = [(re.compile(p, f), r) for p, r, f in [
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|\Z)", "[key]", re.S),
    (r"\b(gh[pousr]_|github_pat_|sk-|xox[abprs]-|AIza|ya29\.|GOCSPX-|AKIA|hf_|npm_)[A-Za-z0-9_\-./]{8,}", "[token]", 0),
    (r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", "[token]", 0),
    (r"\b(authorization\s*[:=]\s*)[^\r\n\"']+", r"\1[token]", re.I),
    (r"\b(bearer\s+)[A-Za-z0-9._~+/=\-]{8,}", r"\1[token]", re.I),
    (r"((?:token|secret|passw(?:or)?d|api[_-]?key|client[_-]?secret|cookie)[\w-]*[\"']?\s*[:=]\s*[\"']?)[^\s\"',;&]+",
     r"\1[secret]", re.I),
    (r"(--(?:token|password|secret|api-key)[ =])\S+", r"\1[secret]", re.I),
    (r"\b(https?://)[^/\s\"']+@", r"\1[secret]@", re.I),
    (r"\b(https?://[^\s\"'<>?#]+)[?#][^\s\"'<>)]*", r"\1", re.I),            # query strings often carry keys
    (r"(https?://)?\b(meet\.google\.com|chat\.whatsapp\.com|[\w.-]*zoom\.us|teams\.microsoft\.com)/[^\s\"'<>]*",
     "[meeting link]", re.I),
    (r"[A-Za-z0-9._%+\-]+(@|%40)[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", "[email]", 0),
    (r"\+\d[\d ()\-]{7,}\d", "[phone]", 0),
    (r"(?<![\w.\-])(?:[6-9]\d{4}[ \-]?\d{5}|\(?\d{3}\)?[ .\-]\d{3}[ .\-]\d{4})(?![\w\-])", "[phone]", 0),
    (r"\b(?!127\.0\.0\.1)(?:\d{1,3}\.){3}\d{1,3}\b", "[ip]", 0),
    (r"\b[A-Za-z0-9_\-]{40,}\b", "[long value]", 0),                          # unknown key formats, hashes
]]
_known = {"t": 0.0, "v": []}


def known_secrets() -> list:
    """Exact values to strip: everything in ~/.config/nova's secret files and secret-looking environment variables."""
    if time.time() - _known["t"] < 60:
        return _known["v"]
    vals = [v for k, v in os.environ.items() if re.search(r"TOKEN|SECRET|KEY|PASSW|COOKIE", k, re.I)]
    for f in CONF.glob("*"):
        if f.is_file() and f.name not in ("projects.json", "memory.md", "memory.md.bak", "tasks.json"):
            try:
                vals += re.findall(r"[A-Za-z0-9_\-./+=]{16,}", f.read_text())
            except Exception:
                pass
    _known.update(t=time.time(), v=sorted({v.strip() for v in vals if len(v.strip()) >= 8}, key=len, reverse=True))
    return _known["v"]


def redact(text, limit=1500) -> str:
    s = str(text or "")[:max(20000, limit * 2)]   # redact first, shorten after, so no half-secret survives the cut
    for v in known_secrets():
        s = s.replace(v, "[secret]")
    for rx, repl in RULES:
        s = rx.sub(repl, s)
    s = s.replace(str(HOME), "~")
    return s if len(s) <= limit else s[:limit] + " ...[cut]"


# ---------------------------------------------------------------- phone sampler (background thread, every 2 s)

TICK = os.sysconf("SC_CLK_TCK")
NCPU = os.cpu_count() or 1


def meminfo() -> dict:
    m = {}
    try:
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            m[k] = int(v.split()[0]) // 1024          # MB
    except Exception:
        pass
    return {"total": m.get("MemTotal", 0), "avail": m.get("MemAvailable", 0), "free": m.get("MemFree", 0),
            "cached": m.get("Cached", 0), "swap_total": m.get("SwapTotal", 0),
            "swap_used": m.get("SwapTotal", 0) - m.get("SwapFree", 0)}


def _read(p, mode="r"):
    try:
        with open(p, mode) as f:
            return f.read()
    except Exception:
        return None


def component(cmd: str, cwd: str) -> str:
    """Which part of the stack a process belongs to ('' = unknown, inherits from its parent)."""
    a0 = cmd.split(" ", 1)[0]
    base = a0.rsplit("/", 1)[-1]
    if "chrom" in a0 or base in ("exe", "chrome_crashpad_handler") and "--type=" in cmd:
        m = re.search(r"--user-data-dir=(\S+)", cmd)
        prof = m.group(1).rsplit("/", 1)[-1] if m else ""
        if "maya" in prof or "nova" in prof:
            return "Chrome: Nova (Meet)"
        if "wa-chrome" in prof:
            return "Chrome: WhatsApp"
        return "Chrome: other" if prof else ""
    if base == "Xvfb" or "xvfb" in a0.lower():
        return "Xvfb (virtual screen)"
    if base.startswith("pulseaudio"):
        return "PulseAudio"
    if "/claude/versions/" in a0 or base == "claude":
        agent = any(x in cwd for x in ("/nova_work", "/nova_meetings", "/.cache/wa-virtmic", "/scripts/calls"))
        return "Claude Code: agents" if agent else "Claude Code: interactive"
    if base == "cloudflared":
        return "Cloudflare tunnel"
    if base.startswith("python"):
        script = next((w for w in cmd.split()[1:] if w.endswith(".py")), "")
        name = script.rsplit("/", 1)[-1]
        if name in ("auto_answer.py", "wa_call.py", "live_agent.py", "realtime_agent.py", "media_agent.py"):
            return "WhatsApp agent (python)"
        if name in ("nova.py", "live_meet.py", "browser.py", "task.py", "memory.py", "calendar_watch.py"):
            return "Nova (python)"
        if name == "dashboard.py":
            return "Dashboard"
        if name == "handoff.py":
            return "Handoff"
        return "Python: " + (name or "other")
    if base in ("proot", "proot-distro", "loader") or "proot" in a0:
        return "proot"
    if base in ("gws", "gws.bin"):
        return "Google CLI (gws)"
    if base in ("node", "bun"):
        return "Node"
    return ""


class Sampler:
    def __init__(self):
        self.lock = threading.Lock()
        self.prev = {}                 # pid -> cpu ticks
        self.prev_t = None
        self.hist = collections.deque(maxlen=HISTORY)
        self.latest = {}
        self.battery = None
        self.battery_t = 0.0
        self.battery_ok = shutil.which("termux-battery-status") is not None

    def procs(self):
        now = time.monotonic()
        rows = {}
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            st = _read(f"/proc/{d}/stat")
            raw = _read(f"/proc/{d}/cmdline", "rb")
            if not st or raw is None:
                continue
            try:
                rest = st[st.rindex(")") + 2:].split()
                ppid, ticks, rss = int(rest[1]), int(rest[11]) + int(rest[12]), int(rest[21]) * 4096 // 1024
            except Exception:
                continue
            cmd = raw.replace(b"\0", b" ").decode(errors="replace").strip() or st[st.index("(") + 1:st.rindex(")")]
            try:
                cwd = os.readlink(f"/proc/{d}/cwd")
            except Exception:
                cwd = ""
            rows[int(d)] = {"ppid": ppid, "ticks": ticks, "rss": rss, "cmd": cmd, "comp": component(cmd, cwd)}
        dt = (now - self.prev_t) if self.prev_t else None
        for pid, r in rows.items():
            p = self.prev.get(pid)
            r["cpu"] = (100.0 * (r["ticks"] - p) / TICK / dt) if (dt and p is not None and r["ticks"] >= p) else 0.0
        self.prev, self.prev_t = {pid: r["ticks"] for pid, r in rows.items()}, now
        for pid, r in rows.items():                 # unknown -> parent's component (Chrome renderers, helpers)
            seen, q = 0, r
            while not r["comp"] and seen < 6:
                q = rows.get(q["ppid"])
                if not q:
                    break
                r["comp"] = q["comp"] if q["comp"] and not q["comp"].startswith("Python") else ""
                seen += 1
            r["comp"] = r["comp"] or "Shell / other"
        return rows

    def battery_read(self):
        if not self.battery_ok or time.time() - self.battery_t < 60:
            return
        self.battery_t = time.time()
        # own process group: on timeout the hung termux-api helper is killed too (it hangs forever without the
        # Termux:API app, and a plain timeout leaves it behind)
        p = subprocess.Popen(["termux-battery-status"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                             start_new_session=True)
        try:
            out, _ = p.communicate(timeout=4)
            b = json.loads(out)
            self.battery = {k: b.get(k) for k in ("percentage", "status", "temperature", "plugged")}
        except Exception:
            self.battery_ok = False       # Termux:API app missing: the command hangs; stop trying
            try:
                os.killpg(p.pid, 9)
                p.wait(1)
            except Exception:
                pass

    def sample(self):
        rows = self.procs()
        comps = {}
        for pid, r in rows.items():
            c = comps.setdefault(r["comp"], {"name": r["comp"], "rss": 0, "cpu": 0.0, "n": 0, "top": []})
            c["rss"] += r["rss"]
            c["cpu"] += r["cpu"]
            c["n"] += 1
            c["top"].append((r["rss"], pid))
        out = []
        for c in sorted(comps.values(), key=lambda c: -c["rss"]):
            top = sorted(c.pop("top"), reverse=True)[:3]
            c["procs"] = [{"pid": pid, "rss": round(rss / 1024), "cpu": round(rows[pid]["cpu"], 1),
                           "cmd": redact(rows[pid]["cmd"], 160)} for rss, pid in top]
            c["rss"] = round(c["rss"] / 1024)
            c["cpu"] = round(c["cpu"], 1)
            out.append(c)
        mem = meminfo()
        stack = sum(c["rss"] for c in out)
        cpu = round(sum(c["cpu"] for c in out), 1)
        self.battery_read()
        try:
            du = shutil.disk_usage(HOME)
            disk = {"total": du.total // 2**30, "free": round(du.free / 2**30, 1)}
        except Exception:
            disk = {}
        t = time.time()
        point = {"t": round(t), "used": mem["total"] - mem["avail"], "stack": stack, "cpu": cpu,
                 "swap": mem["swap_used"]}
        with self.lock:
            self.hist.append(point)
            self.latest = {"t": t, "mem": mem, "stack_mb": stack, "cpu": cpu, "ncpu": NCPU, "components": out,
                           "nproc": len(rows), "disk": disk, "battery": self.battery}

    def run(self):
        while True:
            t0 = time.monotonic()
            try:
                self.sample()
            except Exception as e:
                print("sample failed:", type(e).__name__, e, file=sys.stderr)
            time.sleep(max(0.2, SAMPLE_SECS - (time.monotonic() - t0)))


SAMPLER = Sampler()


# ---------------------------------------------------------------- network: internet latency + live call quality
# Android hides /proc/net and /sys/class/net from apps, so there are no byte counters. What matters for the calls is
# measured instead: TCP connect time to the services they depend on, and Chrome's own WebRTC stats during a call.
import socket  # noqa: E402
import rtc_stats  # noqa: E402

PROBES = {"OpenAI (voice)": ("api.openai.com", 443), "WhatsApp": ("web.whatsapp.com", 443),
          "Google Meet": ("meet.google.com", 443), "Cloudflare": ("1.1.1.1", 443)}
PROBE_SECS = 10


class Net:
    def __init__(self):
        self.lock = threading.Lock()
        self.probes = {}                                   # name -> {"ms": int|None, "error": str}
        self.probe_hist = collections.deque(maxlen=int(3600 / PROBE_SECS))
        self.calls = []
        self.call_hist = collections.deque(maxlen=900)    # 30 min of 2 s points while a call is live

    @staticmethod
    def connect_ms(host, port):
        t0 = time.monotonic()
        try:
            addr = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][4]
        except Exception:
            return None, "DNS failed"
        t1 = time.monotonic()
        try:
            socket.create_connection(addr[:2], timeout=3).close()
        except Exception as e:
            return None, type(e).__name__
        return round((time.monotonic() - t1) * 1000), "" if t1 - t0 < 1 else f"slow DNS {round((t1 - t0) * 1000)} ms"

    def probe_loop(self):
        while True:
            res = {n: dict(zip(("ms", "error"), self.connect_ms(*hp))) for n, hp in PROBES.items()}
            with self.lock:
                self.probes = res
                self.probe_hist.append({"t": round(time.time()), **{n: r["ms"] for n, r in res.items()}})
            time.sleep(PROBE_SECS)

    def call_loop(self):
        while True:
            calls = rtc_stats.live_calls()
            with self.lock:
                self.calls = calls
                if calls:      # the worst connection drives the chart
                    w = lambda k: max((c.get(k) or 0) for c in calls)
                    self.call_hist.append({"t": round(time.time()), "rtt": w("rtt_ms"), "in_loss": w("in_loss"),
                                           "conceal": w("in_conceal"), "far_loss": w("far_loss")})
            time.sleep(2 if calls else 5)

    def latest(self):
        with self.lock:
            return {"probes": self.probes, "calls": self.calls,
                    "probe_point": self.probe_hist[-1] if self.probe_hist else None,
                    "call_point": self.call_hist[-1] if self.call_hist else None}


NET = Net()


# ---------------------------------------------------------------- services

def _alive(pidfile: Path) -> bool:
    try:
        os.kill(int(pidfile.read_text().strip()), 0)
        return True
    except Exception:
        return False


def _age(p: Path):
    try:
        return round(time.time() - p.stat().st_mtime)
    except Exception:
        return None


def services() -> list:
    out = [{"name": "WhatsApp answerer", "ok": _alive(WA_RUN / "auto_answer.pid"),
            "detail": f"supervisor {'up' if _alive(WA_RUN / 'answer_daemon.pid') else 'DOWN'}, "
                      f"heartbeat {_age(WA_RUN / 'auto_answer.heartbeat')}s ago"},
           {"name": "Handoff page", "ok": _alive(WA_RUN / "handoff.pid"), "detail": "localhost:8787"},
           {"name": "Nova autojoin", "ok": _alive(NOVA_RUN / "autojoin_supervisor.pid"),
            "detail": f"calendar heartbeat {_age(NOVA_RUN / 'autojoin.heartbeat')}s ago"}]
    try:
        s = json.loads((NOVA_RUN / "state.json").read_text())
        phase = s.get("phase", "?")
        in_call = phase not in ("left", "idle", "error", "")
        d = f"{phase}"
        if in_call:
            d += f", {s.get('others', 0)} others, mic {s.get('mic')}, cam {s.get('cam')}"
            if s.get("joined_at"):
                d += f", for {round((time.time() - s['joined_at']) / 60)} min"
        elif s.get("left_at"):
            d += f" {round((time.time() - s['left_at']) / 60)} min ago"
        if s.get("title"):
            d += f" | {redact(s['title'], 80)}"
        if s.get("error"):
            d += f" | error: {redact(s['error'], 200)}"
        out.append({"name": "Nova in a meeting", "ok": in_call, "neutral": not in_call and not s.get("error"),
                    "detail": d})
    except Exception:
        out.append({"name": "Nova in a meeting", "ok": False, "neutral": True, "detail": "no state"})
    out.append({"name": "Nova task worker", "ok": T.worker_alive(), "neutral": not T.worker_alive(),
                "detail": "working" if T.worker_alive() else "idle (starts when a task is queued)"})
    return out


# ---------------------------------------------------------------- Claude Code sessions

def session_kind(folder: str):
    """Agent sessions only (not the developer's own Claude Code sessions). Returns (kind, label) or None."""
    h = re.sub(r"[^A-Za-z0-9]", "-", str(HOME))
    if folder == f"{h}-nova-work":
        return "desk", "Meeting desk"
    if m := re.fullmatch(re.escape(h) + r"-nova-work-([\d-]+)", folder):
        return "task", "Nova task " + m.group(1)
    if m := re.fullmatch(re.escape(h) + r"-nova-meetings-([\d-]+)", folder):
        return "memory", "Memory update " + m.group(1)
    if folder == f"{h}--cache-wa-virtmic-claude-tool":
        return "wa", "WhatsApp call helper"
    if m := re.fullmatch(re.escape(h) + r"-wa-virtmic-scripts-calls-(.+)", folder):
        return "wa", "WhatsApp call " + m.group(1)
    return None


def live_cwds() -> set:
    """Folder names (Claude's project-dir encoding) where a claude process is running right now."""
    out = set()
    for d in os.listdir("/proc"):
        if d.isdigit():
            a0 = (_read(f"/proc/{d}/cmdline", "rb") or b"").split(b"\0")[0].decode(errors="replace")
            if "/claude/versions/" in a0 or a0.endswith("/claude") or a0 == "claude":
                try:
                    out.add(re.sub(r"[^A-Za-z0-9]", "-", os.readlink(f"/proc/{d}/cwd")))
                except Exception:
                    pass
    return out


_scan_cache = {}


def scan_session(f: Path) -> dict:
    """Header of one transcript: times, model, tokens, number of tool calls, first prompt, last answer."""
    st = f.stat()
    key = (str(f), st.st_mtime, st.st_size)
    if key in _scan_cache:
        return _scan_cache[key]
    s = {"start": None, "end": None, "model": "", "tools": 0, "in": 0, "out": 0, "cache": 0, "prompt": "",
         "answer": "", "error": False}
    for line in f.read_text(errors="replace").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        ts = ev.get("timestamp")
        if ts:
            s["start"] = s["start"] or ts
            s["end"] = ts
        m = ev.get("message") or {}
        c = m.get("content")
        if ev.get("type") == "user" and not s["prompt"]:
            s["prompt"] = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or []
                                                                if isinstance(x, dict) and x.get("type") == "text")
        if ev.get("type") == "assistant":
            s["model"] = m.get("model") or s["model"]
            u = m.get("usage") or {}
            s["in"] += u.get("input_tokens", 0) or 0
            s["out"] += u.get("output_tokens", 0) or 0
            s["cache"] += (u.get("cache_read_input_tokens", 0) or 0) + (u.get("cache_creation_input_tokens", 0) or 0)
            for x in c if isinstance(c, list) else []:
                if x.get("type") == "tool_use":
                    s["tools"] += 1
                elif x.get("type") == "text" and x.get("text", "").strip():
                    s["answer"] = x["text"]
    s["prompt"], s["answer"] = redact(s["prompt"], 300), redact(s["answer"], 600)
    if len(_scan_cache) > 2000:
        _scan_cache.clear()
    _scan_cache[key] = s
    return s


def sessions(limit=150) -> list:
    if not TRANSCRIPTS.is_dir():
        return []
    live = live_cwds()
    files = []
    for d in TRANSCRIPTS.iterdir():
        k = session_kind(d.name)
        if k and d.is_dir():
            for f in d.glob("*.jsonl"):
                files.append((f.stat().st_mtime, d.name, f, k))
    files.sort(key=lambda x: -x[0])
    out, live_marked = [], set()
    for mtime, folder, f, (kind, label) in files[:limit]:
        is_live = folder in live and folder not in live_marked and time.time() - mtime < 1800
        if is_live:
            live_marked.add(folder)             # newest file in a folder with a running claude = the live one
        s = scan_session(f)
        out.append({"id": f"{folder}/{f.stem}", "kind": kind, "label": label, "live": is_live, "mtime": mtime,
                    **{k: s[k] for k in ("start", "end", "model", "tools", "in", "out", "cache", "answer")}})
    return out


def session_steps(sid: str) -> list:
    """Full step list of one agent session: answers, tool calls, command output (file contents never included)."""
    folder, _, stem = sid.partition("/")
    if not session_kind(folder) or not re.fullmatch(r"[\w\-]+", stem):
        return []
    f = TRANSCRIPTS / folder / f"{stem}.jsonl"
    if not f.is_file():
        return []
    return steps_of([f])


def steps_of(files) -> list:
    out, calls = [], {}
    for f in files:
        for line in f.read_text(errors="replace").splitlines():
            try:
                ev = json.loads(line)
                content = ev["message"]["content"]
            except Exception:
                continue
            if isinstance(content, str):
                if ev.get("type") == "user":
                    out.append({"time": ev.get("timestamp", ""), "tool": "prompt", "what": redact(content, 1200),
                                "status": "ok", "output": ""})
                continue
            for c in content if isinstance(content, list) else []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and ev.get("type") == "assistant" and c.get("text", "").strip():
                    out.append({"time": ev.get("timestamp", ""), "tool": "says", "what": redact(c["text"], 3000),
                                "status": "ok", "output": ""})
                elif c.get("type") == "tool_use":
                    name, inp = c.get("name", "?"), c.get("input") or {}
                    what = next((inp[k] for k in ("command", "file_path", "pattern", "query", "url", "path", "prompt")
                                 if inp.get(k)), "")
                    private = bool(PRIVATE.search(f"{name} {what}"))
                    step = {"time": ev.get("timestamp", ""), "tool": redact(name, 60), "what": redact(what),
                            "note": redact(inp.get("description"), 200), "status": "running", "output": ""}
                    # only command output is shown; file, search and web contents stay on the machine
                    calls[c.get("id")] = (step, private, name == "Bash")
                    out.append(step)
                elif c.get("type") == "tool_result" and c.get("tool_use_id") in calls:
                    step, private, show = calls[c["tool_use_id"]]
                    body = c.get("content")
                    if isinstance(body, list):
                        body = "\n".join(b.get("text", "") for b in body if isinstance(b, dict))
                    step["status"] = "error" if c.get("is_error") else "ok"
                    step["output"] = HIDDEN if private else (redact(body) if show else "")
    return out[-300:]


# ---------------------------------------------------------------- queue, memory, logs

def queue() -> list:
    tasks = []
    for x in T.load_queue()[::-1][:100]:
        r = x.get("result") or {}
        # meeting_url, title and context (meeting speech) are deliberately left out
        tasks.append({"id": redact(x.get("id"), 60), "state": x.get("state", ""),
                      "requester": redact(x.get("requester"), 80), "task": redact(x.get("task"), 4000),
                      "created": x.get("created"), "started": x.get("started"), "finished": x.get("finished"),
                      "session": f"{re.sub(r'[^A-Za-z0-9]', '-', str(T.WORK / str(x.get('id', ''))))}",
                      "result": {k: redact(r.get(k)) for k in ("say", "chat", "question", "repo", "url")}})
    return tasks


def memory() -> dict:
    try:
        mem = redact(MEMORY.read_text(errors="replace"), 60000)
        mem_t = MEMORY.stat().st_mtime
    except Exception:
        mem, mem_t = "", None
    try:
        projects = [{k: redact(p.get(k), 300) for k in ("repo", "url", "task", "when", "requester")}
                    for p in json.loads(PROJECTS.read_text())][-50:][::-1]
    except Exception:
        projects = []
    return {"memory": mem, "updated": mem_t, "projects": projects}


def logs() -> dict:
    out = {}
    for name, p in LOGS.items():
        try:
            with open(p, "rb") as f:
                f.seek(max(0, p.stat().st_size - 12000))
                lines = f.read().decode(errors="replace").splitlines()[-40:]
            out[name] = {"mtime": p.stat().st_mtime, "text": redact("\n".join(lines), 8000)}
        except Exception:
            pass
    return out


_work = {"t": 0.0, "json": "", "hash": ""}
_work_lock = threading.Lock()


def work_json():
    """Shared by all viewers: computed at most every 3 s, returned as (json, hash)."""
    with _work_lock:
        if time.monotonic() - _work["t"] > 3:
            j = json.dumps(work_snapshot())
            _work.update(t=time.monotonic(), json=j, hash=hashlib.sha1(j.encode()).hexdigest())
        return _work["json"], _work["hash"]


def work_snapshot() -> dict:
    """Slow-changing data; pushed only when it changed. Each part fails on its own."""
    out = {}
    for k, fn in (("queue", queue), ("sessions", sessions), ("memory", memory), ("logs", logs)):
        try:
            out[k] = fn()
        except Exception as e:
            out[k] = None
            print(f"{k} failed:", type(e).__name__, e, file=sys.stderr)
    return out


# ---------------------------------------------------------------- HTTP

def access_token() -> str:
    CONF.mkdir(parents=True, exist_ok=True)
    if not TOKEN_FILE.exists():
        with os.fdopen(os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as f:
            f.write(secrets.token_urlsafe(32))
    tok = TOKEN_FILE.read_text().strip()
    if len(tok) < 32:
        sys.exit(f"{TOKEN_FILE} is too short; delete it to create a new one")
    return tok


SECURITY = (("Cache-Control", "no-store"), ("Referrer-Policy", "no-referrer"), ("X-Content-Type-Options", "nosniff"),
            ("X-Robots-Tag", "noindex"), ("X-Frame-Options", "DENY"),
            ("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                                        "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"))


class Handler(BaseHTTPRequestHandler):
    token = ""
    protocol_version = "HTTP/1.1"

    def head(self, code, ctype, length=None, chunked=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        if chunked:            # each event its own chunk: proxies (cloudflared) forward chunks as they come
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("X-Accel-Buffering", "no")
        for k, v in SECURITY:
            self.send_header(k, v)
        self.end_headers()

    def send(self, code, body, ctype="text/plain; charset=utf-8"):
        self.head(code, ctype, len(body))
        self.wfile.write(body)

    def do_GET(self):          # GET only: every other method gets 501 from the base class
        u = urlparse(self.path)
        if u.path == "/":
            return self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        if u.path not in ("/api/system", "/api/history", "/api/work", "/api/session"):
            return self.send(404, b"not found")
        given = self.headers.get("Authorization", "").encode()
        if not hmac.compare_digest(given, f"Bearer {self.token}".encode()):
            return self.send(401, b"unauthorized")
        if u.path == "/api/session":
            sid = (parse_qs(u.query).get("id") or [""])[0]
            return self.send(200, json.dumps({"id": sid, "steps": session_steps(sid)}).encode(), "application/json")
        # Short requests, polled every 2 s by the page: a long-lived stream stalls behind Cloudflare's quick tunnel.
        if u.path == "/api/work":              # big and slow-changing: the page sends the hash it has
            w, h = work_json()
            same = (parse_qs(u.query).get("h") or [""])[0] == h
            body = f'{{"h": "{h}", "work": {"null" if same else w}}}'.encode()
            return self.send(200, body, "application/json")
        data = self.system() if u.path == "/api/system" else self.history()
        return self.send(200, json.dumps(data).encode(), "application/json")

    def system(self) -> dict:
        with SAMPLER.lock:
            d = dict(SAMPLER.latest)
            d["point"] = SAMPLER.hist[-1] if SAMPLER.hist else None
        d["services"] = services()
        d["net"] = NET.latest()
        return d

    @staticmethod
    def history() -> dict:
        with SAMPLER.lock:
            hist = list(SAMPLER.hist)
        with NET.lock:
            return {"sys": hist, "probe": list(NET.probe_hist), "call": list(NET.call_hist)}

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("DASH_PORT", "8790")))
    ap.add_argument("--once", action="store_true", help="print one snapshot as JSON and exit (for testing)")
    a = ap.parse_args()
    if a.once:
        SAMPLER.sample(); time.sleep(1); SAMPLER.sample()
        NET.probes = {n: dict(zip(("ms", "error"), NET.connect_ms(*hp))) for n, hp in PROBES.items()}
        NET.calls = rtc_stats.live_calls()
        print(json.dumps({"net": NET.latest(), "services": services()}, indent=1)[:3000])
        return
    Handler.token = access_token()
    for fn in (SAMPLER.run, NET.probe_loop, NET.call_loop):
        threading.Thread(target=fn, daemon=True).start()
    ThreadingHTTPServer.daemon_threads = True
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
