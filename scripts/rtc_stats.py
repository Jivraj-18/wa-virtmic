"""Live network quality of the WebRTC calls in our Chromes (WhatsApp Web on CDP 9222, Nova's Meet on CDP 9333).

JS is installed at document start (mic_apm.install for WhatsApp, meet/browser.py for Meet). It only remembers each
RTCPeerConnection the page creates (no change to the page's behaviour) and adds window.__rtcStats(), which returns,
per open connection, the numbers that explain a bad-sounding call, measured over the time since the last read:
  rtt_ms          round trip to the other side (selected ICE pair)
  route           direct (host/srflx) or relay (TURN server: adds latency)
  in_*            what we receive: kbps, loss %, jitter ms, conceal % (samples Chrome had to invent = audible glitches)
  out_*           what we send: kbps; far_loss % / far_jitter ms as reported back by the other side

    python scripts/rtc_stats.py          # print the live calls once (what the dashboard reads every 2 s)

A page loaded before the hook existed gets it on first read (best effort: catches the connections made after that).
"""
import asyncio, json, sys, urllib.request

PORTS = {9222: "WhatsApp", 9333: "Nova (Meet)"}
PAGES = ("web.whatsapp.com", "meet.google.com")

JS = r"""(() => {
  if (window.__rtcHook || !window.RTCPeerConnection) return;
  window.__rtcHook = true;
  const pcs = [], prev = new WeakMap();
  const Orig = window.RTCPeerConnection;
  const Hooked = new Proxy(Orig, {construct(t, args, nt) {
    const pc = Reflect.construct(t, args, nt);
    try { pcs.push({ref: new WeakRef(pc), t0: Date.now()}); if (pcs.length > 20) pcs.shift(); } catch (e) {}
    return pc;
  }});
  window.RTCPeerConnection = Hooked;
  if (window.webkitRTCPeerConnection) window.webkitRTCPeerConnection = Hooked;
  window.__rtcStats = async () => {
    const out = [];
    for (const e of pcs) {
      const pc = e.ref.deref();
      if (!pc || pc.connectionState === 'closed') continue;
      let r;
      try { r = await pc.getStats(); } catch (x) { continue; }
      const s = {}; r.forEach(v => { (s[v.type] = s[v.type] || []).push(v); });
      const pair = (s['candidate-pair'] || []).find(p => p.state === 'succeeded' && p.nominated) || {};
      const cand = id => (s['local-candidate'] || []).concat(s['remote-candidate'] || []).find(c => c.id === id) || {};
      const inA = (s['inbound-rtp'] || []).filter(x => x.kind === 'audio');
      const outA = (s['outbound-rtp'] || []).filter(x => x.kind === 'audio');
      const far = (s['remote-inbound-rtp'] || []).filter(x => x.kind === 'audio');
      const sum = (a, k) => a.reduce((n, x) => n + (x[k] || 0), 0);
      const now = {t: performance.now(), rb: sum(inA, 'bytesReceived'), rp: sum(inA, 'packetsReceived'),
                   rl: sum(inA, 'packetsLost'), ts: sum(inA, 'totalSamplesReceived'), cs: sum(inA, 'concealedSamples'),
                   sb: sum(outA, 'bytesSent')};
      const p = prev.get(pc) || now; prev.set(pc, now);
      const dt = Math.max(0.001, (now.t - p.t) / 1000), dp = (now.rp - p.rp) + (now.rl - p.rl);
      const ms = v => v == null ? null : Math.round(v * 1000);
      const lc = cand(pair.localCandidateId), rc = cand(pair.remoteCandidateId);
      out.push({
        state: pc.connectionState, age_s: Math.round((Date.now() - e.t0) / 1000),
        rtt_ms: ms(pair.currentRoundTripTime), route: (lc.candidateType === 'relay' || rc.candidateType === 'relay') ? 'relay' : (lc.candidateType ? 'direct' : null),
        net: lc.networkType || null, audio: inA.length + outA.length > 0,
        in_kbps: Math.round((now.rb - p.rb) * 8 / dt / 1000), in_loss: dp > 0 ? +(100 * (now.rl - p.rl) / dp).toFixed(1) : 0,
        in_jitter_ms: ms(inA[0] && inA[0].jitter), in_conceal: now.ts > p.ts ? +(100 * (now.cs - p.cs) / (now.ts - p.ts)).toFixed(1) : 0,
        out_kbps: Math.round((now.sb - p.sb) * 8 / dt / 1000),
        far_loss: far.length && far[0].fractionLost != null ? +(100 * far[0].fractionLost).toFixed(1) : null,
        far_jitter_ms: ms(far[0] && far[0].jitter), far_rtt_ms: ms(far[0] && far[0].roundTripTime),
      });
    }
    return out;
  };
})()"""

# installs the hook if the page loaded before it existed, then reads
READ = "(async () => { %s; return window.__rtcStats ? await window.__rtcStats() : null; })()" % JS


def _targets(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1.5) as r:
            return [t for t in json.load(r) if t.get("type") == "page" and any(h in t.get("url", "") for h in PAGES)]
    except Exception:
        return []


async def _eval(ws_url, expr):
    import websockets
    async with websockets.connect(ws_url, max_size=2**22, open_timeout=3, ping_interval=None) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), 4))
            if m.get("id") == 1:
                return ((m.get("result") or {}).get("result") or {}).get("value")


async def _all():
    out = []
    for port, app in PORTS.items():
        for t in await asyncio.to_thread(_targets, port):
            try:
                conns = await _eval(t["webSocketDebuggerUrl"], READ)
            except Exception:
                continue
            for c in conns or []:
                if c.get("audio") and c.get("state") in ("connected", "connecting", "new", "disconnected"):
                    out.append({"app": app, **c})
    return out


def live_calls() -> list:
    """Open audio connections in both Chromes right now (empty when no call). Never raises."""
    try:
        return asyncio.run(_all())
    except Exception:
        return []


if __name__ == "__main__":
    calls = live_calls()
    print(json.dumps(calls, indent=1) if calls else "no live WebRTC call (or the page loaded before the hook)")
    sys.exit(0)
