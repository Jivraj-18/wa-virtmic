#!/usr/bin/env python3
"""Publish a SIMULATED (sim_call.py) run to the docs site: a short compressed clip + transcript + metrics.

  python3 scripts/publish_run.py experiments/runs/E0_basic_qa_20261118_084230 --id E0 [--name basic_qa] [--max-seconds 60]

Writes docs/media/<ID>/<name>.mp3 (mono, 32 kbps, <= max-seconds) and docs/media/<ID>/<name>.js, which defines
window.RUNS["<ID>/<name>"] = {transcript, metrics, summary} so pages work from file:// without fetch().
Only ever publish simulated runs: never real call recordings or transcripts (public repo).
"""
import argparse, csv, json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name")
    ap.add_argument("--max-seconds", type=float, default=60)
    ap.add_argument("--start", type=float, default=0, help="clip start (s) inside the run; transcript times are shifted")
    a = ap.parse_args()
    run = Path(a.run)
    summ = json.loads((run / "summary.json").read_text())
    if not str(run.name).startswith(summ.get("tag", "")):
        raise SystemExit("not a sim_call run folder?")
    name = a.name or summ["script"]
    out = ROOT / "docs" / "media" / a.id
    out.mkdir(parents=True, exist_ok=True)
    src = run / "call_stereo.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(a.start), "-i", str(src), "-t", str(a.max_seconds),
                    "-ac", "1", "-ar", "24000", "-b:a", "32k", str(out / f"{name}.mp3")], check=True)
    tr = json.loads((run / "transcript.json").read_text()) if (run / "transcript.json").exists() else []
    tr = [dict(x, t=round(x["t"] - a.start, 2), end=round(x["end"] - a.start, 2))
          for x in tr if a.start <= x["t"] <= a.start + a.max_seconds]
    rows = list(csv.DictReader(open(run / "metrics.csv"))) if (run / "metrics.csv").exists() else []
    data = {"transcript": tr, "metrics": rows, "summary": summ, "clip": f"media/{a.id}/{name}.mp3"}
    (out / f"{name}.js").write_text(
        f"window.RUNS = window.RUNS || {{}};\nwindow.RUNS[{json.dumps(a.id + '/' + name)}] = "
        + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    print(f"published {out / (name + '.mp3')} ({(out / (name + '.mp3')).stat().st_size // 1024} KB) and {name}.js")


if __name__ == "__main__":
    main()
