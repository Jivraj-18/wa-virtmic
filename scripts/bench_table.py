#!/usr/bin/env python3
"""Before/after table of bench runs, grouped by their settings (the 'bench: chrome=...' line of call.log).

    python3 scripts/bench_table.py                    # every run under scripts/bench/
    python3 scripts/bench_table.py --since 20261123_1350
Per group: number of runs, then mean (min-max) of each far-end metric (see audio_score.py / bench_webrtc.py)."""
import argparse, json, re
from pathlib import Path

import bench_webrtc

BENCH = Path(__file__).resolve().parent / "bench"
COLS = [("clock", "media clock x"), ("spk_gaps_pct", "chrome-out gaps %"), ("dropout_pct", "dropout %"),
        ("lost_pct", "lost %"), ("lsd_db", "lsd dB"), ("gain_db", "gain dB"), ("noise_db", "noise dB"),
        ("gemini", "gemini /10")]


def row(d):
    cfg = next((ln.split("bench: ", 1)[1] for ln in (d / "call.log").read_text().splitlines()
                if "bench: chrome=" in ln), None) if (d / "call.log").exists() else None
    if not cfg or not (d / "score.json").exists():
        return None, None
    r = json.loads((d / "score.json").read_text())
    if isinstance(r.get("gemini"), dict):
        r["gemini"] = r["gemini"].get("score")
    m = re.search(r"media clock ([\d.]+)x", bench_webrtc.summary(d))
    r["clock"] = float(m.group(1)) if m else None
    cfg = re.sub(r"\b(\w+)=(None|False|0|''|interactive|44100)(?=\s|$)", "", cfg.replace("chrome=on ", "")).split()
    cfg = " ".join(c for c in cfg if not c.startswith(("connect_after", "apm=True")))
    return cfg or "default", r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="")
    a = ap.parse_args()
    groups = {}
    for d in sorted(BENCH.glob("2*")):
        if d.name >= a.since:
            cfg, r = row(d)
            if cfg:
                groups.setdefault(cfg, []).append(r)
    print("| settings | runs | " + " | ".join(c[1] for c in COLS) + " |")
    print("|---" * (len(COLS) + 2) + "|")
    for cfg, rs in groups.items():
        cells = []
        for k, _ in COLS:
            v = [x[k] for x in rs if isinstance(x.get(k), (int, float))]
            cells.append("-" if not v else f"{sum(v) / len(v):.3g}" + (f" ({min(v):.3g}-{max(v):.3g})" if len(v) > 1 else ""))
        print(f"| {cfg} | {len(rs)} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
