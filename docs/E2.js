/* E2 page helpers: per-question tool timing from RUNS[key].summary.e2.rows (written by experiments/E2/tools/analyze_run.py). */
function e2Rows(keys) {
  const out = [];
  for (const k of keys) {
    const r = window.RUNS[k]; if (!r || !r.summary.e2) continue;
    for (const x of r.summary.e2.rows) out.push({run: k.split("/")[1].replace(/_/g, " "), ...x});
  }
  return out;
}

function renderE2(tableEl, chartEl, keys) {
  const rows = e2Rows(keys);
  const s = v => v == null ? "–" : (+v).toFixed(2);
  renderTable(tableEl, rows, [
    {key: "run", label: "Run"},
    {key: "question", label: "Caller asked"},
    {key: "tools", label: "Tools called", fmt: v => (v || "").replace(/\+/g, " + ")},
    {key: "tool_s", label: "Tool time (s)", num: true, fmt: s},
    {key: "hold_source", label: "Holding line", fmt: v => ({model: "model's own", forced: "forced filler", none: "none"}[v] || v)},
    {key: "t_first_audio_s", label: "To first audio (s)", num: true, fmt: s},
    {key: "t_answer_s", label: "To answer (s)", num: true, fmt: s},
    {key: "correct", label: "Correct", fmt: v => v === true ? "yes" : v === false ? "NO" : "–"},
  ]);
  const short = {"deep facts": "facts", "deep facts nopreface": "facts, no preface", "synthesis": "synth",
                 "synthesis still": "synth, still", "synthesis fallback": "synth, fallback"};
  renderBars(chartEl, rows.map(r => ({label: `${short[r.run] || r.run} · T${r.turn}`,
      value: r.t_first_audio_s, value2: r.t_answer_s})),
    {unit: " s", label1: "caller stops → first agent audio (holding line)", label2: "caller stops → answer audio",
     title: "Time to holding line and to answer per question"});
}
