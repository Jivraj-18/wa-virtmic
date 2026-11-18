/* E1 page helper: after-call summary.md files (docs/media/E1/summaries.js) shown as tabs, with tiny Markdown rendering. */
function renderSummaries(el, names) {
  const S = window.E1_SUMMARIES || {};
  names = names.filter(n => S[n]);
  if (!names.length) { el.innerHTML = '<p class="note">No summaries published.</p>'; return; }
  const md = t => esc(t).split("\n").map(l =>
      l.startsWith("## ") ? `<h3>${l.slice(3)}</h3>` :
      l.startsWith("# ") ? `<p><strong>${l.slice(2)}</strong></p>` :
      /^- \[ \] /.test(l) ? `<div>☐ ${l.slice(6)}</div>` :
      l.startsWith("- ") ? `<div>• ${l.slice(2)}</div>` :
      /^_.*_$/.test(l) ? `<p class="note">${l.slice(1, -1)}</p>` : (l ? `<div>${l}</div>` : ""))
    .join("").replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  el.innerHTML = `<div class="demo-tabs" role="tablist">${names.map(n =>
    `<button role="tab" data-n="${esc(n)}">${esc(n.replace(/_/g, " "))}</button>`).join("")}</div><div class="panel"></div>`;
  const body = el.querySelector(".panel");
  const show = n => {
    el.querySelectorAll("button").forEach(b => b.setAttribute("aria-selected", b.dataset.n === n));
    body.innerHTML = md(S[n]);
  };
  el.querySelector(".demo-tabs").addEventListener("click", e => { const b = e.target.closest("button"); if (b) show(b.dataset.n); });
  show(names[0]);
}
