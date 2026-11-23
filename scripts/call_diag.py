#!/usr/bin/env python3
"""Call diagnostics: what went wrong on a call, in numbers (no listening, no screenshots).

During every call (auto_answer.handle_call, also used by wa_call.py) a Sampler writes
calls/<ts>/sysstats.jsonl every 2 s: CPU of proot / Chrome / our python / pulseaudio, free memory, swap,
and a syscall-latency probe (everything in proot-distro goes through proot's ptrace, so a slow syscall
slows every audio read/write).

After the call:
    python3 scripts/call_diag.py                 # latest call
    python3 scripts/call_diag.py 20261120_060624 # a given call (folder name or path)
    python3 scripts/call_diag.py --last 5        # one summary line per call for the last 5 calls

It reports, with a verdict for each:
  - voice cut-outs   : % of the AI's speech (ai.wav = what WhatsApp got) that is 10 ms gaps of digital silence
                       -> heard by the other side as a "cracky" voice. Good < 1 %, bad > 3 %.
  - reply latency    : caller stops talking -> AI audio starts, for each turn. Good < 2 s, bad > 4 s.
  - agent pipeline   : from the live_agent log lines (frames/5 s, longest wait for a frame, longest pacat write,
                       queued frames, RTP packets lost) -> network loss vs our loop being starved.
  - system load      : from sysstats.jsonl -> was the phone overloaded (proot CPU, swap, syscall latency)?
"""
import json, os, re, subprocess, sys, threading, time, wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
CALLS = HERE / "calls"


# ======================================================================= sampler (runs during a call)
def _ticks(pid):
    try:
        f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(f[11]) + int(f[12])  # utime + stime
    except (OSError, IndexError, ValueError):
        return None


def _groups():
    """pid -> group name for the processes that matter for call audio."""
    g = {}
    me = os.getpid()
    for p in Path("/proc").iterdir():
        if not p.name.isdigit():
            continue
        try:
            cl = (p / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        exe = cl[0].decode(errors="replace") if cl else ""
        args = b" ".join(cl).decode(errors="replace")
        pid = int(p.name)
        if exe.endswith("/proot") or exe == "proot":
            g[pid] = "proot"
        elif exe.startswith("/usr/lib/chromium/chromium"):
            g[pid] = "chrome_maya" if "maya-chrome-profile" in args else "chrome_wa"
        elif pid == me:
            g[pid] = "agent_py"
        elif "pulseaudio" in exe:
            g[pid] = "pulseaudio"
        elif exe.endswith(("parec", "pacat")):
            g[pid] = "parec_pacat"
    return g


def _meminfo():
    m = {}
    try:
        for ln in Path("/proc/meminfo").read_text().splitlines():
            k, v = ln.split(":", 1)
            m[k] = int(v.split()[0]) // 1024
    except OSError:
        pass
    return m


def _syscall_probe(n=50):
    worst, t0 = 0.0, time.perf_counter()
    for _ in range(n):
        a = time.perf_counter(); os.stat("/"); worst = max(worst, time.perf_counter() - a)
    return (time.perf_counter() - t0) / n * 1e6, worst * 1e3


def _sink_latency():
    """PulseAudio's view: each sink's actual/configured latency (ms) and each playback stream's buffer (ms).
    A null sink renders in blocks of its configured latency (up to 2 s), so a large value = audio taken in big chunks."""
    try:
        out = {}
        for sk in json.loads(subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True,
                                            text=True, timeout=3).stdout or "[]"):
            lat = sk.get("latency") or {}
            out[sk["name"]] = [round((lat.get("actual") or 0) / 1000), round((lat.get("configured") or 0) / 1000)]
        return out
    except Exception:
        return None


class Sampler:
    """Background thread: one JSON line every `every` s into `path`. Cheap (~1 % CPU)."""

    def __init__(self, path, every=2.0):
        self.path, self.every = Path(path), every
        self.stop = threading.Event()
        self.th = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.th.start()
        return self

    def close(self):
        self.stop.set()
        self.th.join(5)

    def _run(self):
        hz = os.sysconf("SC_CLK_TCK")
        prev, t_prev, groups, n = {}, time.time(), {}, 0
        with open(self.path, "a") as f:
            while not self.stop.is_set():
                if n % 5 == 0:
                    groups = _groups()  # processes come and go (parec per call, Chrome renderers)
                n += 1
                now = time.time()
                cur = {pid: _ticks(pid) for pid in groups}
                dt = max(now - t_prev, 1e-3)
                cpu = {}
                for pid, t in cur.items():
                    if t is not None and prev.get(pid) is not None:
                        cpu[groups[pid]] = cpu.get(groups[pid], 0) + (t - prev[pid]) / hz / dt * 100
                prev, t_prev = cur, now
                m = _meminfo()
                avg_us, worst_ms = _syscall_probe()
                rec = {"t": round(now, 2), "cpu": {k: round(v) for k, v in cpu.items()}, "sinks": _sink_latency(),
                       "mem_avail_mb": m.get("MemAvailable"),
                       "swap_used_mb": (m.get("SwapTotal", 0) - m.get("SwapFree", 0)) if m else None,
                       "syscall_avg_us": round(avg_us), "syscall_worst_ms": round(worst_ms, 1)}
                if n > 1:  # the first sample has no CPU deltas
                    f.write(json.dumps(rec) + "\n"); f.flush()
                self.stop.wait(self.every)


# ======================================================================= analysis
def _wav_rms(path, win_s):
    import numpy as np
    w = wave.open(str(path))
    sr, ch = w.getframerate(), w.getnchannels()
    x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
    if ch > 1:
        x = x.reshape(-1, ch).mean(1)
    n = max(1, int(sr * win_s))
    k = len(x) // n
    return np.sqrt((x[: k * n].reshape(k, n) ** 2).mean(1)) if k else np.zeros(0)


def cutouts(ai_wav):
    """% of AI speech (10 ms frames) that are digital-silence gaps with speech within 60 ms on both sides."""
    import numpy as np
    r = _wav_rms(ai_wav, 0.01)
    sp, z = r > 150, r < 1
    k = len(r)
    if k < 13:
        return 0.0, 0
    near_l = np.convolve(sp, np.ones(6), "full")[: k]          # speech in the previous 6 frames (incl. current)
    near_r = np.convolve(sp[::-1], np.ones(6), "full")[: k][::-1]
    prev_sp = np.concatenate([[0], near_l[:-1]]) > 0
    next_sp = np.concatenate([near_r[1:], [0]]) > 0
    gaps = int((z & prev_sp & next_sp).sum())
    return 100.0 * gaps / max(int(sp.sum()), 1), int(sp.sum())


def turns(ai_wav, caller_wav):
    """Reply latency per turn: caller speech ends (>= 0.7 s of quiet) -> AI speech starts. Seconds, from 100 ms RMS."""
    a, c = _wav_rms(ai_wav, 0.1), _wav_rms(caller_wav, 0.1)
    n = min(len(a), len(c))
    a_on, c_on = a[:n] > 150, c[:n] > 150
    out, i = [], 0
    while i < n:
        if c_on[i]:
            j = i
            while j < n and (c_on[j:j + 7].any()):   # caller turn continues until 0.7 s of quiet
                j += 1
            end = j  # first quiet frame
            if a_on[max(0, i):end].any():   # AI was already talking during the caller's turn (talk-over)
                i = j; continue
            k = end
            while k < n and not a_on[k] and not c_on[k]:
                k += 1
            if k < n and a_on[k]:
                out.append((round(end * 0.1, 1), round((k - end) * 0.1, 1)))
            i = k if k > j else j + 1
        else:
            i += 1
    return out


def find_log(d):
    """The log file that ran this call and its lines (from 'recording -> <dir>' to 'call ended').
    calls/<ts>/call.log (saved at the end of each call) wins: wa_call_<who>.log is overwritten by the next call."""
    if (Path(d) / "call.log").exists():
        return Path(d) / "call.log", (Path(d) / "call.log").read_text(errors="replace").splitlines()
    pat = f"-> {d}"
    for f in sorted(HERE.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            lines = f.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for i, ln in enumerate(lines):
            if ln.endswith(pat) and "recording" in ln or ln.endswith(pat) and "call (not recorded)" in ln:
                out = []
                for ln2 in lines[max(0, i - 3):]:
                    out.append(ln2)
                    if "call ended after" in ln2:
                        break
                return f, out
    return None, []


def pipeline(lines):
    """Parse live_agent diagnostics lines."""
    ai = [l for l in lines if "live: audio-in 5s:" in l][1:]  # first window = session start-up (pacat opening): ignore
    frames = [int(m.group(1)) for l in ai if (m := re.search(r"(\d+) frames", l))]
    waits = [int(m.group(1)) for l in ai if (m := re.search(r"longest wait (\d+) ms", l))]
    writes = [int(m.group(1)) for l in ai if (m := re.search(r"longest pacat write (\d+) ms", l))]
    queued = [int(m.group(1)) for l in ai if (m := re.search(r"queued (\d+)", l))]
    lag = [int(m.group(1)) for l in ai if (m := re.search(r"loop lag (\d+) ms", l))]
    outq = [int(m.group(1)) for l in ai if (m := re.search(r"out-queue max (\d+) ms", l))]
    rtp = [(int(m.group(1)), int(m.group(2))) for l in lines if (m := re.search(r"rtp-in received (\d+) lost (-?\d+)", l))]
    behind = [l for l in lines if "behind - dropping silence" in l]
    sent = [float(m.group(1)) for l in lines if (m := re.search(r"caller audio, ([+-][\d.]+)s vs real time", l))]
    first = [l.split("live: ")[1] for l in lines if "first AI audio" in l]
    errors = [l for l in lines if re.search(r"FAILED|Traceback|live error|Error", l)]
    return dict(outq=outq, lag=lag, frames=frames, waits=waits, writes=writes, queued=queued, rtp=rtp, behind=behind, sent=sent,
                first=first, errors=errors, engine=next((l.split("voice engine: ")[1] for l in lines if "voice engine:" in l), "?"))


def sysload(d):
    p = d / "sysstats.jsonl"
    if not p.exists():
        return None
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if not rows:
        return None
    def mx(key, sub=None):
        vals = [(r.get(key) or {}).get(sub) if sub else r.get(key) for r in rows]
        vals = [v for v in vals if v is not None]
        return (max(vals), sum(vals) / len(vals)) if vals else (None, None)
    groups = sorted({g for r in rows for g in r.get("cpu", {})})
    return dict(n=len(rows), cpu={g: mx("cpu", g) for g in groups}, swap=mx("swap_used_mb"),
                mem=(min(r["mem_avail_mb"] for r in rows if r.get("mem_avail_mb") is not None),) if rows else None,
                sc_worst=mx("syscall_worst_ms"), sc_avg=mx("syscall_avg_us"))


def _v(ok, bad):
    return "OK " if ok else ("BAD" if bad else "so-so")


def report(d, short=False):
    d = Path(d)
    if not d.is_absolute() and not d.exists():
        d = CALLS / d
    ai, caller = d / "ai.wav", d / "caller.wav"
    if not ai.exists():
        print(f"{d.name}: no recording"); return
    cut, speech = cutouts(ai)
    lat = turns(ai, caller)
    lats = [x[1] for x in lat]
    logf, lines = find_log(d)
    pl = pipeline(lines)
    sl = sysload(d)
    if short:
        med = sorted(lats)[len(lats) // 2] if lats else None
        cg = cutouts(caller)[0] if caller.exists() else 0
        print(f"{d.name}  engine {pl['engine']:8s} cut-outs {cut:4.1f}%  chrome-io gaps {cg:4.1f}%  reply median {med if med is not None else '-'} s "
              f"max {max(lats) if lats else '-'} s  turns {len(lats)}  "
              f"{'sysstats' if sl else 'no-sysstats'}")
        return
    print(f"== call {d.name}  (log: {logf.name if logf else 'not found'}, engine {pl['engine']})")
    print(f"[{_v(cut < 1, cut > 3)}] voice cut-outs: {cut:.1f}% of {speech / 100:.0f} s of AI speech "
          "(good < 1 %, 'cracky' > 3 %)")
    if caller.exists():   # Chrome's audio output starving: the same clock drives WhatsApp's mic path (WebAudio)
        cg, cs = cutouts(caller)
        if cs > 100:
            print(f"[{_v(cg < 2, cg > 8)}] Chrome audio I/O gaps: {cg:.1f}% of {cs / 100:.0f} s of caller speech "
                  "(caller.wav; > 8 % = Chrome's PulseAudio output starving -> WhatsApp drops our mic audio too)")
    if lats:
        print(f"[{_v(max(lats) < 2, max(lats) > 4)}] reply latency: " +
              ", ".join(f"@{t:.0f}s {l:.1f}s" for t, l in lat) + "  (good < 2 s)")
    else:
        print("[ ? ] reply latency: no caller-then-AI turns found")
    for f in pl["first"]:
        print(f"      {f}")
    try:  # PulseAudio stall: the AI-side recording (virtmic) loses wall time when the audio server freezes
        da = wave.open(str(ai)).getnframes() / wave.open(str(ai)).getframerate()
        dc = wave.open(str(caller)).getnframes() / wave.open(str(caller)).getframerate()
        print(f"[{_v(abs(dc - da) < 0.5, abs(dc - da) > 1)}] recordings: AI side {da:.1f} s vs caller side {dc:.1f} s "
              "(AI side shorter by > 1 s = PulseAudio/phone froze the AI's audio)")
    except Exception:
        da = dc = 0
    if pl["frames"]:
        lo = min(pl["frames"]); w = max(pl["waits"] or [0]); wr = max(pl["writes"] or [0]); q = max(pl["queued"] or [0])
        print(f"[{_v(lo >= 240 and w < 200, lo < 200 or w > 500)}] AI audio from OpenAI: min {lo}/250 frames per 5 s, "
              f"longest wait {w} ms, max queued {q} frames ({q * 20} ms)")
        print(f"[{_v(wr < 100, wr > 250)}] writing AI audio into the call (pacat): longest {wr} ms "
              "(blocked = the player's queue was full; older calls: up to ~0.9 s of the AI's voice queued = lag)")
        if pl["outq"]:
            oq = max(pl["outq"])
            print(f"[{_v(oq < 150, oq > 400)}] AI audio queued before the player: up to {oq} ms (= extra delay heard)")
        if pl["lag"]:
            lg = max(pl["lag"])
            print(f"[{_v(lg < 100, lg > 250)}] AI audio thread ran late by up to {lg} ms "
                  "(big while the phone is fine = another thread in the process blocked it)")
    else:
        print("[ ? ] no live_agent 5 s diagnostics in the log (older code or realtime engine)")
    if pl["rtp"]:
        rec, lost = pl["rtp"][-1]
        pct = 100 * max(lost, 0) / max(rec + max(lost, 0), 1)
        print(f"[{_v(pct < 1, pct > 3)}] network from OpenAI: {lost} of {rec + max(lost, 0)} RTP packets lost ({pct:.1f}%)")
    if pl["sent"]:
        print(f"[{_v(max(pl['sent']) < 1.5, max(pl['sent']) > 3)}] caller audio to OpenAI: up to {max(pl['sent']):+.1f} s "
              "behind real time")
    if pl["behind"]:
        print(f"      AI audio fell behind {len(pl['behind'])}x (silence skipped to catch up): {pl['behind'][0][:90]}")
    for e in pl["errors"][:5]:
        print(f"[BAD] {e[:160]}")
    if sl:
        c = sl["cpu"]
        print(f"[{_v((sl['sc_worst'][0] or 0) < 20, (sl['sc_worst'][0] or 0) > 100)}] phone load ({sl['n']} samples): "
              f"syscall worst {sl['sc_worst'][0]} ms (avg {sl['sc_avg'][1]:.0f} us); swap used max {sl['swap'][0]} MB; "
              f"min free mem {sl['mem'][0]} MB")
        print("      CPU % max/avg: " + ", ".join(f"{g} {m:.0f}/{a:.0f}" for g, (m, a) in c.items() if m is not None))
    else:
        print("[ ? ] no sysstats.jsonl (call made before the sampler existed)")
    # one-line diagnosis
    hints = []
    if cut > 3:
        if pl["rtp"] and pl["rtp"][-1][1] > 0.03 * pl["rtp"][-1][0]:
            hints.append("cut-outs + RTP loss -> network between phone and OpenAI (try Wi-Fi, or --engine realtime)")
        elif pl["writes"] and max(pl["writes"]) > 250:
            hints.append("cut-outs + slow pacat writes -> PulseAudio/proot stalls (phone overloaded)")
        elif pl["waits"] and max(pl["waits"]) > 300:
            hints.append("cut-outs + long waits for frames -> our asyncio loop starved or network jitter")
        elif pl["frames"]:
            hints.append("cut-outs but the agent pipeline looks fine -> the gap is after pacat (PulseAudio / Chrome)")
        else:
            hints.append("cut-outs, cause unknown: this call has no agent diagnostics (older code)")
    if pl["lag"] and max(pl["lag"]) > 500:
        hints.append(f"AI audio thread blocked up to {max(pl['lag']) / 1000:.1f} s by other work in the same process")
    if pl["writes"] and max(pl["writes"]) > 1000:
        hints.append(f"AI audio froze up to {max(pl['writes']) / 1000:.1f} s in pacat (heard as lag) - a phone-wide stall "
                     "if CPU of ALL processes dropped at that moment in sysstats.jsonl (Android power saving/thermal)")
    if lats and max(lats) > 4:
        hints.append("slow replies -> check 'first AI audio' and 'behind' lines")
    if sl and (sl["sc_worst"][0] or 0) > 100:
        hints.append("syscall stalls > 100 ms -> proot overloaded; close other Chrome (Maya) / reduce load")
    print("diagnosis: " + ("; ".join(hints) if hints else "nothing obviously wrong"))


def main():
    a = sys.argv[1:]
    if a[:1] == ["--last"]:
        n = int(a[1]) if len(a) > 1 else 5
        for d in sorted(p for p in CALLS.iterdir() if p.is_dir())[-n:]:
            report(d, short=True)
        return
    d = Path(a[0]) if a else max((p for p in CALLS.iterdir() if p.is_dir()), key=lambda p: p.name)
    report(d)


if __name__ == "__main__":
    main()
