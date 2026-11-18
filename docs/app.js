/* Shared helpers for the results pages. Plain JS, no build step, works from file://.
   Data files (docs/media/<ID>/<name>.js) define window.RUNS["<ID>/<name>"] = {transcript, metrics, summary, clip}.
   Card files (docs/cards/<ID>.js) call card({...}). */
window.RUNS = window.RUNS || {};
window.CARDS = window.CARDS || [];
function card(c) { window.CARDS.push(c); }

const esc = s => String(s ?? "").replace(/[&<>"]/g, ch => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[ch]));
const fmt = t => { t = +t; const m = Math.floor(t / 60), s = (t % 60).toFixed(1).padStart(4, "0"); return `${String(m).padStart(2, "0")}:${s}`; };

/* index page: render cards into #cards, ordered by id */
function renderCards(el) {
  const cards = [...window.CARDS].sort((a, b) => a.id.localeCompare(b.id));
  el.innerHTML = cards.map(c => `
    <a class="card panel" href="${esc(c.id)}.html">
      <div class="row"><span class="id">${esc(c.id)}</span><span class="badge ${esc(c.status)}">${esc(c.status)}</span></div>
      <div class="t">${esc(c.title)}</div>
      <div class="f">${esc(c.finding)}</div>
    </a>`).join("");
}

/* demo block: tabs per run, audio player, chat transcript synced to playback */
function renderDemo(el, keys) {
  keys = keys.filter(k => window.RUNS[k]);
  if (!keys.length) { el.innerHTML = '<p class="note">No simulated run published yet.</p>'; return; }
  el.innerHTML = `<div class="demo-tabs" role="tablist"></div><audio controls preload="none"></audio>
    <div class="chat panel" aria-live="polite"></div>
    <p class="note">Simulated call (E0 harness): the caller is a TTS voice. Left bubbles = AI agent, right = caller. Click a timestamp to jump.</p>`;
  const tabs = el.querySelector(".demo-tabs"), audio = el.querySelector("audio"), chat = el.querySelector(".chat");
  let cur = null;
  const show = k => {
    cur = window.RUNS[k];
    tabs.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", b.dataset.k === k));
    audio.src = cur.clip;
    chat.innerHTML = cur.transcript.map((m, i) => `<div class="msg ${esc(m.who)}" data-i="${i}" data-t="${m.t}">
      <span class="who">${m.who === "CALLER" ? "CALLER" : "AI AGENT"}</span><span class="ts" data-t="${m.t}">${fmt(m.t)}</span>
      <div>${esc(m.text)}</div></div>`).join("");
  };
  tabs.innerHTML = keys.map(k => `<button role="tab" data-k="${esc(k)}">${esc(k.split("/")[1].replace(/_/g, " "))}</button>`).join("");
  tabs.addEventListener("click", e => { const b = e.target.closest("button"); if (b) show(b.dataset.k); });
  chat.addEventListener("click", e => { const t = e.target.closest(".ts"); if (t) { audio.currentTime = +t.dataset.t; audio.play(); } });
  audio.addEventListener("timeupdate", () => {
    const t = audio.currentTime; let last = null;
    chat.querySelectorAll(".msg").forEach(m => { m.classList.remove("now"); if (+m.dataset.t <= t) last = m; });
    if (last) last.classList.add("now");
  });
  show(keys[0]);
}

/* generic table: cols = [{key, label, num, fmt}] */
function renderTable(el, rows, cols) {
  el.innerHTML = `<div class="tbl"><table><thead><tr>${cols.map(c => `<th class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(r => `<tr>${cols.map(c => { const v = r[c.key]; return `<td class="${c.num ? "num" : ""}">${esc(c.fmt ? c.fmt(v, r) : (v === "" || v == null ? "–" : v))}</td>`; }).join("")}</tr>`).join("")}</tbody></table></div>`;
}

/* horizontal bar chart. data = [{label, value, value2?}], opts {unit, label1, label2, max} */
function renderBars(el, data, opts = {}) {
  const unit = opts.unit || "", rowH = 30, left = 170, w = 640, right = 70;
  const max = opts.max || Math.max(...data.flatMap(d => [d.value || 0, d.value2 || 0])) * 1.1 || 1;
  const two = data.some(d => d.value2 != null);
  const h = data.length * rowH * (two ? 1.6 : 1) + 30;
  const x = v => left + (w - left - right) * (v / max);
  let y = 10, out = "";
  for (const d of data) {
    out += `<text x="${left - 8}" y="${y + 15}" text-anchor="end">${esc(d.label)}</text>`;
    if (d.value != null) out += `<rect class="bar" x="${left}" y="${y + 3}" width="${Math.max(1, x(d.value) - left)}" height="16" rx="3"/><text class="v" x="${x(d.value) + 6}" y="${y + 16}">${(+d.value).toFixed(2)}${unit}</text>`;
    if (two) { y += rowH * .6; if (d.value2 != null) out += `<rect class="bar2" x="${left}" y="${y + 3}" width="${Math.max(1, x(d.value2) - left)}" height="16" rx="3"/><text class="v" x="${x(d.value2) + 6}" y="${y + 16}">${(+d.value2).toFixed(2)}${unit}</text>`; }
    y += rowH;
  }
  out += `<line class="axis" x1="${left}" y1="4" x2="${left}" y2="${y}"/>`;
  const legend = two ? `<p class="note"><span style="color:var(--accent)">■</span> ${esc(opts.label1 || "")} &nbsp; <span style="color:var(--agent-b)">■</span> ${esc(opts.label2 || "")}</p>` : "";
  el.innerHTML = `<div class="chart"><svg viewBox="0 0 ${w} ${y + 6}" role="img" aria-label="${esc(opts.title || "chart")}">${out}</svg></div>${legend}`;
}

/* per-turn metrics table for a published run */
function renderRunMetrics(el, key) {
  const r = window.RUNS[key]; if (!r) return;
  renderTable(el, r.metrics, [
    {key: "turn", label: "Turn", num: true},
    {key: "caller_text", label: "Caller said"},
    {key: "interrupt", label: "Barge-in", fmt: v => v === "True" ? "yes" : ""},
    {key: "first_audio_latency_s", label: "Latency (s)", num: true},
    {key: "reply_duration_s", label: "Reply (s)", num: true},
    {key: "agent_stop_latency_s", label: "Agent stopped after (s)", num: true},
  ]);
}
