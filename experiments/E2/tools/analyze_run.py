#!/usr/bin/env python3
"""E2 per-question timing + correctness for a sim_call run of `scripts/tools.py agent`.

  python3 experiments/E2/tools/analyze_run.py experiments/runs/E2_<script>_<ts> [--script experiments/E2/scripts/x.yaml]

Inputs (run folder): agent.wav, metrics.csv (harness, audio clock), e2_events.jsonl + tool_calls.jsonl (agent, wall clock).
The agent's wall clock is mapped onto the recorded audio by aligning the greeting's first audio delta with the first
voice onset in agent.wav. A response's audible start = max(its first audio delta, end of the audio queued before it)
(the player plays responses back to back), snapped to the nearest voice onset in agent.wav.

Per caller turn that used tools:
  t_first_audio_s : caller voice end -> first agent audio (holding line: the model's own preface or our forced filler)
  t_answer_s      : caller voice end -> first audio of the answer (the response requested after the last tool result)
Writes tool_timing.csv and adds "e2" (aggregates + rows) to summary.json, so publish_run.py carries it to docs/.
"""
import argparse, csv, json, re, statistics, wave
from pathlib import Path

import numpy as np
import yaml

RATE, FRAME, VAD = 16000, 320, 200.0


def onsets(wav: Path, gap=0.35):
    with wave.open(str(wav)) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float64)
    n = len(a) // FRAME
    rms = np.sqrt((a[: n * FRAME].reshape(n, FRAME) ** 2).mean(axis=1))
    on, out, last = rms > VAD, [], -9.0
    for i in np.where(on)[0]:
        t = i * FRAME / RATE
        if t - last > gap:
            out.append(t)
        last = t
    return out


def norm(s: str) -> str:
    s = s.lower().replace(",", "").replace("$", "")
    s = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s)
    return re.sub(r"\s+", " ", s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--script", help="YAML with optional expect: [...] per line (default: from summary.json name)")
    a = ap.parse_args()
    run = Path(a.run)
    summ = json.loads((run / "summary.json").read_text())
    script = Path(a.script) if a.script else Path(__file__).resolve().parents[1] / "scripts" / f"{summ['script']}.yaml"
    lines = yaml.safe_load(script.read_text())["lines"] if script.exists() else []
    metrics = list(csv.DictReader(open(run / "metrics.csv")))
    ev = [json.loads(x) for x in open(run / "e2_events.jsonl")]
    calls = [json.loads(x) for x in open(run / "tool_calls.jsonl")] if (run / "tool_calls.jsonl").exists() else []
    ons = onsets(run / "agent.wav")

    # responses with audio, in order; audible start with queue model
    resp, order = {}, []
    for e in ev:
        if e["ev"] == "response_created":
            resp[e["id"]] = {"id": e["id"], "kind": e["kind"], "created": e["t"], "first": None, "dur": 0, "text": ""}
            order.append(e["id"])
        elif e["ev"] == "first_audio" and e["id"] in resp:
            resp[e["id"]]["first"] = e["t"]
        elif e["ev"] == "response_done" and e["id"] in resp:
            resp[e["id"]]["dur"] = e.get("audio_s") or 0
        elif e["ev"] == "transcript" and e["id"] in resp:
            resp[e["id"]]["text"] = e["text"]
    q_end = 0.0  # wall time at which the player's queue runs dry
    for e in ev:
        if e["ev"] == "speech_started":  # barge-in: the agent flushes the player
            q_end = min(q_end, e["t"])
        elif e["ev"] == "first_audio" and e["id"] in resp:
            r = resp[e["id"]]
            r["audible"] = max(r["first"], q_end)
            q_end = r["audible"] + r["dur"]
    greet = next(resp[r] for r in order if resp[r]["first"] is not None)
    off = ons[0] - greet["audible"]  # wall -> wav seconds

    def to_wav(t, snap=True):
        x = t + off
        if snap and ons:
            near = min(ons, key=lambda o: abs(o - x))
            if abs(near - x) < 0.6:
                return near
        return x

    # group tool calls by caller turn (last caller voice end before the tool started)
    ends = [float(m["caller_end_s"]) for m in metrics]
    turns = {}
    for c in calls:
        ts = to_wav(c["t_start"], snap=False)
        k = max([i for i, e in enumerate(ends) if e <= ts + 0.2], default=None)
        if k is not None:
            turns.setdefault(k, []).append(c)
    rows = []
    for k, cs in sorted(turns.items()):
        ce = ends[k]
        t_last_end = max(c["t_end"] for c in cs)
        nxt = float(metrics[k + 1]["caller_start_s"]) if k + 1 < len(metrics) else 1e9
        first = [resp[r] for r in order if resp[r]["first"] is not None and ce < to_wav(resp[r]["audible"]) < nxt]
        ans = [r for r in first if r["created"] >= t_last_end - 0.05]
        hold = [r for r in first if r["created"] < t_last_end - 0.05]
        fillers = [f["source"] for c in cs for f in c["fillers"]]
        source = ("forced" if "forced" in fillers else "model" if hold else "none")
        answer_text = " ".join(r["text"] for r in ans[:1])
        exp = (lines[k].get("expect") if k < len(lines) else None) or []
        ok = all(norm(x) in norm(answer_text) for x in exp) if exp else None
        rows.append({
            "turn": k + 1, "question": metrics[k]["caller_text"],
            "tools": "+".join(c["tool"] for c in cs), "tool_s": round(sum(c["seconds"] for c in cs), 2),
            "hold_source": source, "hold_text": " / ".join(r["text"] for r in hold),
            "t_first_audio_s": round(to_wav(first[0]["audible"]) - ce, 2) if first else None,
            "t_answer_s": round(to_wav(ans[0]["audible"]) - ce, 2) if ans else None,
            "answer": answer_text, "expected": "; ".join(exp), "correct": ok,
        })
    with open(run / "tool_timing.csv", "w", newline="") as f:
        if rows:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    med = lambda v: round(statistics.median(v), 2) if v else None
    fa = [r["t_first_audio_s"] for r in rows if r["t_first_audio_s"] is not None]
    an = [r["t_answer_s"] for r in rows if r["t_answer_s"] is not None]
    summ["e2"] = {"tool_turns": len(rows), "tool_calls": len(calls),
                  "first_audio_median_s": med(fa), "answer_median_s": med(an),
                  "answer_max_s": max(an) if an else None,
                  "correct": sum(r["correct"] is True for r in rows),
                  "checked": sum(r["correct"] is not None for r in rows), "rows": rows}
    (run / "summary.json").write_text(json.dumps(summ, indent=1, ensure_ascii=False))
    for r in rows:
        print(f"turn {r['turn']}: {r['tools']:<34} tool={r['tool_s']:>5}s hold={r['hold_source']:<6} "
              f"first_audio={r['t_first_audio_s']}s answer={r['t_answer_s']}s correct={r['correct']} | {r['answer'][:90]}")
    print(json.dumps({k: v for k, v in summ["e2"].items() if k != "rows"}))


if __name__ == "__main__":
    main()
