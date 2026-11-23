#!/usr/bin/env python3
"""Passive audio probe for the live WhatsApp tab (CDP :9222). Changes NO behaviour; lasts until the page reloads.

    python3 scripts/wa_audio_probe.py install      # hook getUserMedia / AudioContext / AudioWorklet (idempotent)
    python3 scripts/wa_audio_probe.py show         # what WhatsApp created so far (constraints, contexts, tracks)
    python3 scripts/wa_audio_probe.py watch 60     # during a call: every 1 s, per AudioContext the clock rate vs
                                                   # wall (1.000 = real time; < 1 = the mic FIFO must drop audio),
                                                   # playback underruns, and mic track frames dropped -> probe.jsonl

Hooks are on prototypes, so they also catch constructors WhatsApp cached at boot.
"""
import json, sys, time
from pathlib import Path

from playwright.sync_api import sync_playwright

INSTALL_JS = r"""() => {
  if (window.__waProbe) return 'already installed';
  const P = window.__waProbe = {gum: [], ctxs: [], tracks: [], modules: [], nodes: [], t: Date.now()};
  const seen = c => { if (c && !P.ctxs.includes(c)) P.ctxs.push(c); };
  const gum = MediaDevices.prototype.getUserMedia;
  MediaDevices.prototype.getUserMedia = async function (c) {
    P.gum.push({t: Date.now(), c: JSON.parse(JSON.stringify(c || {}))});
    const s = await gum.call(this, c);
    s.getAudioTracks().forEach(t => P.tracks.push(t));
    return s;
  };
  for (const m of ['createMediaStreamSource', 'createMediaStreamDestination', 'createScriptProcessor', 'createGain']) {
    const f = BaseAudioContext.prototype[m] || AudioContext.prototype[m];
    if (!f) continue;
    BaseAudioContext.prototype[m] = function (...a) {
      seen(this); P.nodes.push({t: Date.now(), m, rate: this.sampleRate});
      if (m === 'createMediaStreamSource' && a[0]) a[0].getAudioTracks().forEach(t => P.tracks.includes(t) || P.tracks.push(t));
      return f.apply(this, a);
    };
  }
  const add = AudioWorklet.prototype.addModule;
  AudioWorklet.prototype.addModule = function (u, o) { P.modules.push({t: Date.now(), u: String(u).slice(0, 120)}); return add.call(this, u, o); };
  return 'installed';
}"""

SAMPLE_JS = r"""() => {
  const P = window.__waProbe;
  if (!P) return null;
  return {now: performance.now() / 1000,
          gum: P.gum, modules: P.modules, nodes: P.nodes.slice(-20),
          ctxs: P.ctxs.map((c, i) => ({i, rate: c.sampleRate, state: c.state, t: c.currentTime,
                  base: c.baseLatency, out: c.outputLatency, sinkId: c.sinkId,
                  ps: c.playbackStats && c.playbackStats.toJSON ? c.playbackStats.toJSON() : null})),
          tracks: P.tracks.map((t, i) => ({i, state: t.readyState, enabled: t.enabled, muted: t.muted, label: t.label,
                  settings: t.getSettings(), stats: t.stats ? t.stats.toJSON() : null}))};
}"""


def page_of(br):
    return next(p for c in br.contexts for p in c.pages if "web.whatsapp.com" in p.url)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    with sync_playwright() as pw:
        page = page_of(pw.chromium.connect_over_cdp("http://127.0.0.1:9222"))
        if cmd == "install":
            print(page.evaluate(INSTALL_JS))
        elif cmd == "show":
            print(json.dumps(page.evaluate(SAMPLE_JS), indent=1)[:6000])
        elif cmd == "watch":
            secs = float(sys.argv[2]) if len(sys.argv) > 2 else 60
            out = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("probe.jsonl")
            prev = None
            with open(out, "a") as f:
                end = time.time() + secs
                while time.time() < end:
                    try:
                        s = page.evaluate(SAMPLE_JS)
                        if s is None:   # page (re)loaded: hooks gone -> reinstall (catches the next call)
                            print(time.strftime("%H:%M:%S"), "probe", page.evaluate(INSTALL_JS), flush=True)
                            prev = None
                            page.wait_for_timeout(1000)
                            continue
                    except Exception as e:  # noqa: BLE001 - navigation in progress
                        print(time.strftime("%H:%M:%S"), "page busy:", str(e)[:80], flush=True)
                        prev = None
                        page.wait_for_timeout(1000)
                        continue
                    f.write(json.dumps(s) + "\n"); f.flush()
                    if prev:
                        dt = s["now"] - prev["now"]
                        parts = []
                        for c in s["ctxs"]:
                            p = next((x for x in prev["ctxs"] if x["i"] == c["i"]), None)
                            if p and c["state"] == "running":
                                ur = (c["ps"] or {}).get("underrunEvents", 0) - ((p["ps"] or {}).get("underrunEvents", 0))
                                parts.append(f"ctx{c['i']} {c['rate']}Hz clock {(c['t'] - p['t']) / dt:.3f}x underruns {ur}")
                        for t in s["tracks"]:
                            p = next((x for x in prev["tracks"] if x["i"] == t["i"]), None)
                            if p and t["state"] == "live" and t["stats"] and p["stats"]:
                                tot = t["stats"]["totalFrames"] - p["stats"]["totalFrames"]
                                dl = t["stats"]["deliveredFrames"] - p["stats"]["deliveredFrames"]
                                parts.append(f"mic{t['i']} {tot / dt:.0f} fr/s dropped {tot - dl}"
                                             f"{' MUTED' if t['muted'] or not t['enabled'] else ''}")
                        print(time.strftime("%H:%M:%S"), "; ".join(parts) or "(no running context / live mic)", flush=True)
                    prev = s
                    page.wait_for_timeout(1000)


if __name__ == "__main__":
    main()
