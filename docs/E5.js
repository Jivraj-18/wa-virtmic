/* E5 page data + a small media-timeline renderer (shared helpers live in app.js).
   Events come from media_events.jsonl of the two published simulated runs (t = seconds since the agent started). */
window.E5 = {
  timelines: {
    "media_controls": {end: 76, events: [
      {t: 16.7, e: "tool", n: "play_media"}, {t: 20.7, e: "play", title: "Team update, week 46"},
      {t: 26.9, e: "pause", why: "caller spoke"}, {t: 40.5, e: "tool", n: "resume_media"},
      {t: 44.9, e: "play", title: "Team update (resumed)"}, {t: 49.8, e: "pause", why: "caller spoke"},
      {t: 52.2, e: "tool", n: "next_track"}, {t: 54.4, e: "play", title: "Focus tones"},
      {t: 59.3, e: "pause", why: "caller spoke"}, {t: 61.5, e: "tool", n: "set_volume(up)"},
      {t: 66.3, e: "play", title: "Focus tones, louder"}, {t: 68.8, e: "pause", why: "caller spoke"},
      {t: 71.9, e: "tool", n: "stop_media"}]},
    "podcast": {end: 80, events: [
      {t: 18.8, e: "tool", n: "make_podcast"}, {t: 24.8, e: "play", title: "Podcast (first line ready)"},
      {t: 33.9, e: "mark", n: "all 8 lines synthesized"}, {t: 44.0, e: "pause", why: "caller spoke"},
      {t: 58.5, e: "tool", n: "resume_media"}, {t: 60.5, e: "play", title: "Podcast (resumed)"},
      {t: 71.9, e: "pause", why: "caller spoke"}, {t: 76.5, e: "tool", n: "stop_media"}]},
  },
  /* seconds; from media_events.jsonl (agent clock) and the harness metrics (recorded audio) */
  steps: [
    {short: "play", step: "play_media: caller stops talking → media plays", a: 4.44, b: 4.59, how: "speech_stopped → first media chunk"},
    {short: "continue", step: "resume_media (\"continue\")", a: 2.83, b: 3.02, how: "speech_stopped → first media chunk"},
    {short: "next", step: "next_track", a: 2.52, b: 3.22, how: "speech_stopped → first media chunk"},
    {short: "louder + resume", step: "set_volume(up) + resume", a: 5.16, b: 3.22, how: "speech_stopped → first media chunk"},
    {short: "podcast", step: "make_podcast: caller stops talking → podcast plays", a: 6.64, b: 6.97, how: "speech_stopped → first media chunk"},
    {short: "pause on speech", step: "Caller talks over media → media silent", a: 0.43, b: null, how: "median of 12 barge-ins, measured on the recordings"},
  ],
  podcast: [
    {run: "sim call (gateway TTS)", script: 3.7, first: 6.06, total: 15.12, audio: 78.4},
    {run: "sim call, earlier (gateway TTS)", script: 4.06, first: 6.56, total: null, audio: null},
    {run: "CLI, Nimbus (gateway TTS)", script: 3.97, first: 7.01, total: 17.05, audio: 78.0},
    {run: "CLI, team update (gateway TTS)", script: 4.06, first: 6.75, total: 14.34, audio: 55.4},
    {run: "CLI, Nimbus (edge-tts)", script: 3.81, first: 6.28, total: 43.32, audio: 61.1},
  ],
};

function renderTimeline(el, key) {
  const tl = window.E5.timelines[key], W = 760, L = 10, R = 10, H = 150, y0 = 60;
  const x = t => L + (W - L - R) * (t / tl.end);
  let out = "", playFrom = null, label = "";
  tl.events.forEach((ev, i) => {
    if (ev.e === "play") { playFrom = ev.t; label = ev.title; }
    if ((ev.e === "pause" || (ev.e === "tool" && ev.n === "stop_media")) && playFrom != null) {
      out += `<rect x="${x(playFrom)}" y="${y0}" width="${x(ev.t) - x(playFrom)}" height="22" rx="4" fill="var(--accent)" opacity=".75"><title>${esc(label)}: ${playFrom}–${ev.t}s</title></rect>`;
      playFrom = null;
    }
    if (ev.e === "pause") out += `<line x1="${x(ev.t)}" x2="${x(ev.t)}" y1="${y0 - 6}" y2="${y0 + 30}" stroke="var(--caller-b)" stroke-width="2"><title>paused: ${esc(ev.why)} @${ev.t}s</title></line>`;
    if (ev.e === "tool" || ev.e === "mark") {
      const up = i % 2 === 0;
      out += `<line x1="${x(ev.t)}" x2="${x(ev.t)}" y1="${up ? 30 : y0 + 22}" y2="${up ? y0 : y0 + 46}" stroke="var(--muted)" stroke-dasharray="3 2"/>
        <text x="${x(ev.t)}" y="${up ? 24 : y0 + 58}" font-size="11" fill="var(--muted)" text-anchor="middle">${esc(ev.n)}</text>`;
    }
  });
  let ticks = "";
  for (let t = 0; t <= tl.end; t += 10) ticks += `<text x="${x(t)}" y="${H - 6}" font-size="10" fill="var(--muted)" text-anchor="middle">${t}s</text>`;
  el.innerHTML = `<div class="chart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="media playback timeline for ${esc(key)}">
    <line x1="${L}" x2="${W - R}" y1="${y0 + 11}" y2="${y0 + 11}" stroke="var(--border)"/>${out}${ticks}</svg></div>
    <p class="note">Filled bars = media playing into the call. Red ticks = playback paused because the caller started talking.
    Dashed labels = tool calls by the realtime model. Seconds since the agent started.</p>`;
}
