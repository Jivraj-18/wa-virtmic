#!/usr/bin/env python3
"""Summarise a bench run's sender stats (webrtc_stats.json, Chrome getStats every 1 s) and the far end's packet
arrival times (arrival.jsonl: [rtp_time_s, arrival_s] per 20 ms frame).
    python3 scripts/bench_webrtc.py scripts/bench/<ts> [-v]
capture  seconds of mic audio Chrome captured per wall second (1.00 = real time)
pkts/s   Opus packets Chrome sent per second (50 = real time at 20 ms)
late     frames arriving > 60 ms / > 120 ms after their ideal time (a real far end's jitter buffer would stretch or
         conceal those: stutter / metallic sound)
gaps     RTP time missing at the far end (never sent or lost)"""
import json, sys
from pathlib import Path


def g(row, key, field, default=0):
    return (row.get(key) or {}).get(field, default)


def summary(d, verbose=False):
    d = Path(d)
    parts = []
    f = d / "webrtc_stats.json"
    if f.exists():
        R = json.loads(f.read_text())
        caps = []
        for a, b in zip(R, R[1:]):
            dt = b["t"] - a["t"]
            cap = (g(b, "tx:media-source", "totalSamplesDuration") - g(a, "tx:media-source", "totalSamplesDuration")) / dt
            sent = (g(b, "tx:outbound-rtp", "packetsSent") - g(a, "tx:outbound-rtp", "packetsSent")) / dt
            caps.append(cap)
            if verbose:
                print(f"{b['t']:6.1f}s capture {cap:.2f}x  pkts/s {sent:5.1f}  level {g(b, 'tx:media-source', 'audioLevel'):.3f}"
                      f"  bitrate {g(b, 'tx:outbound-rtp', 'targetBitrate')}")
        tr = [r["track"] for r in R if r.get("track")]
        if len(tr) > 1:   # MediaStreamTrack.stats: frames the mic produced vs delivered to the page's sinks
            tot = tr[-1].get("totalFrames", 0) - tr[0].get("totalFrames", 0)
            dlv = tr[-1].get("deliveredFrames", 0) - tr[0].get("deliveredFrames", 0)
            parts.append(f"mic frames dropped {100 * (tot - dlv) / max(1, tot):.2f}% (latency avg "
                         f"{1000 * tr[-1].get('averageLatency', 0):.0f} ms)")
        cx = [r["ctx"] for r in R if r.get("ctx")]
        if cx:
            ps0, ps1 = cx[0].get("ps") or {}, cx[-1].get("ps") or {}
            parts.append(f"AudioContext {cx[-1]['rate']} Hz base {1000 * (cx[-1]['base'] or 0):.0f} ms; playback "
                         + ", ".join(f"{k} {ps1[k] - ps0.get(k, 0):.3g}" for k in ps1 if isinstance(ps1[k], (int, float))
                                     and k not in ("averageLatency", "minimumLatency", "maximumLatency")))
        if len(R) > 1 and any(r.get("tx:media-source") for r in R):
            wall = R[-1]["t"] - R[0]["t"]
            capt = g(R[-1], "tx:media-source", "totalSamplesDuration") - g(R[0], "tx:media-source", "totalSamplesDuration")
            parts.append(f"capture {capt / wall:.3f}x (worst 1 s {min(caps):.2f})")
    f = d / "arrival.jsonl"
    if f.exists():
        A = [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]
        if len(A) > 10:
            off = [a - r for r, a in A]
            base = sorted(off)[len(off) // 100]          # 1st percentile = the "on time" delay
            late = sorted(o - base for o in off)
            n = len(late)
            gaps = sum(max(0.0, b[0] - a[0] - 0.02) for a, b in zip(A, A[1:]))
            span = A[-1][1] - A[0][1]
            parts.append(f"media clock {(A[-1][0] - A[0][0]) / span:.3f}x wall" if span > 0 else "")
            parts.append(f"far end: late>60ms {100 * sum(x > .06 for x in late) / n:.1f}% >120ms "
                         f"{100 * sum(x > .12 for x in late) / n:.1f}% p99 {1000 * late[int(n * .99)]:.0f} ms "
                         f"max {1000 * late[-1]:.0f} ms, RTP gaps {gaps:.2f} s of {A[-1][0]:.0f} s")
    return "webrtc: " + "; ".join(parts)


if __name__ == "__main__":
    print(summary(sys.argv[1], "-v" in sys.argv))
