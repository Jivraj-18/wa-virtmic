#!/usr/bin/env python3
"""Score an E4 sim_call run: false triggers, addressed-reply latency, barge-in stop time, chat suggestions.

  python3 -m scripts.meet.score_sim experiments/runs/E4_meeting_<ts> experiments/E4/scripts/meeting.yaml

Uses the line flags in the YAML (`addressed: true`) and the run's metrics.csv (one row per line, same order).
A *false trigger* = Maya audio after a line that was not addressed to her (incl. the barge-in line).
Writes score.json and merges the numbers into summary.json (so publish_run.py carries them to the docs).
"""
import csv, json, statistics, sys
from pathlib import Path

import yaml


def score(run: Path, script: Path) -> dict:
    lines = yaml.safe_load(script.read_text())["lines"]
    rows = list(csv.DictReader(open(run / "metrics.csv")))
    f = lambda v: None if v in (None, "", "None") else float(v)
    per, lat, false, stops = [], [], [], []
    for ln, r in zip(lines, rows):
        addressed = bool(ln.get("addressed"))
        first = f(r["first_audio_latency_s"])
        item = {"turn": int(r["turn"]), "addressed": addressed, "interrupt": bool(ln.get("interrupt")),
                "text": ln["text"], "maya_latency_s": first, "stop_s": f(r["agent_stop_latency_s"])}
        per.append(item)
        if addressed:
            if first is not None:
                lat.append(first)
        elif first is not None:
            false.append(item["turn"])
        if item["interrupt"] and item["stop_s"] is not None:
            stops.append(item["stop_s"])
    ev = []
    if (run / "maya_events.jsonl").exists():
        ev = [json.loads(x) for x in (run / "maya_events.jsonl").read_text().splitlines() if x.strip()]
    n_add = sum(p["addressed"] for p in per)
    n_not = len(per) - n_add
    out = {
        "addressed_lines": n_add, "addressed_turns": [p["turn"] for p in per if p["addressed"]], "addressed_answered": len(lat),
        "not_addressed_lines": n_not, "false_triggers": len(false), "false_trigger_turns": false,
        "false_trigger_rate": round(len(false) / n_not, 3) if n_not else None,
        "addressed_latency_median_s": round(statistics.median(lat), 2) if lat else None,
        "addressed_latency_max_s": round(max(lat), 2) if lat else None,
        "addressed_latencies_s": lat,
        "barge_in_stop_s": stops[0] if stops else None,
        "early_triggers": sum(1 for e in ev if e["kind"] == "addressed" and e.get("early")),
        "chat_suggestions": [e["text"] for e in ev if e["kind"] == "chat_suggestion"],
        "barge_in_events": [e.get("source") for e in ev if e["kind"] == "barge_in"],
        "per_line": per,
    }
    (run / "score.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    summ = json.loads((run / "summary.json").read_text())
    summ.update({k: v for k, v in out.items() if k != "per_line"})
    (run / "summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False))
    return out


if __name__ == "__main__":
    o = score(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps({k: v for k, v in o.items() if k != "per_line"}, indent=1, ensure_ascii=False))
    for p in o["per_line"]:
        tag = "ADDR" if p["addressed"] else ("INTR" if p["interrupt"] else "    ")
        print(f"  {p['turn']:2d} {tag} maya={p['maya_latency_s']} stop={p['stop_s']}  {p['text'][:70]}")
