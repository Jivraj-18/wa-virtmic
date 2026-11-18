/* E4 page helpers (uses esc/renderTable from app.js). */
function renderMayaTurns(el, key) {
  const r = window.RUNS[key]; if (!r) { el.innerHTML = '<p class="note">Run not published.</p>'; return; }
  const addr = new Set(r.summary.addressed_turns || []);
  const rows = r.metrics.map(m => {
    const a = addr.has(+m.turn), spoke = m.first_audio_latency_s !== "" && m.first_audio_latency_s != null && m.first_audio_latency_s !== "None";
    const verdict = a ? (spoke ? "answered" : "MISSED") : (spoke ? "FALSE TRIGGER" : "silent (correct)");
    return {...m, addressed: a ? "yes" : "", verdict};
  });
  renderTable(el, rows, [
    {key: "turn", label: "Line", num: true},
    {key: "caller_text", label: "Participant said"},
    {key: "addressed", label: "To Maya?"},
    {key: "interrupt", label: "Talks over Maya", fmt: v => v === "True" ? "yes" : ""},
    {key: "verdict", label: "Maya"},
    {key: "first_audio_latency_s", label: "Answer after (s)", num: true, fmt: v => v === "" || v === "None" || v == null ? "–" : v},
    {key: "agent_stop_latency_s", label: "Stopped after (s)", num: true, fmt: v => v === "" || v === "None" || v == null ? "–" : v},
  ]);
}

function renderSuggestions(el, keys) {
  el.innerHTML = keys.filter(k => window.RUNS[k]).map(k => `<h3>${esc(k.split("/")[1].replace(/_/g, " "))}</h3><ul>` +
    (window.RUNS[k].summary.chat_suggestions || []).map(s => `<li>${esc(s)}</li>`).join("") + "</ul>").join("");
}
