---
name: dashboard
description: Live observability page for the phone stack, public through a Cloudflare quick tunnel - phone RAM/CPU per component, internet latency and live call quality (WebRTC), service health, Nova's queue, every agent Claude session (live steps), Nova's memory, log tails. Use for "dashboard", "give me the link", "the page shows connecting", "how much RAM is X using", "is the call network bad", "revoke the link", or adding a metric to the page.
---

# Dashboard

`scripts/dashboard.py` (stdlib server, 127.0.0.1:8790, ~30 MB) + `dashboard.html` (one page, polls every 2 s) +
`dashboard.sh` (supervisor: restarts the server or `cloudflared` if either dies, every 15 s).

| Task | Command |
|---|---|
| Start (idempotent), prints the private link | `bash scripts/dashboard.sh start` |
| Current link (changes whenever the tunnel restarts / phone reboots) | `bash scripts/dashboard.sh link` |
| Health | `bash scripts/dashboard.sh status`; logs in `~/.cache/dashboard/` (supervisor, server, tunnel) |
| Stop | `bash scripts/dashboard.sh stop` |
| Revoke every shared link | `rm ~/.config/nova/dashboard_token && bash scripts/dashboard.sh stop && bash scripts/dashboard.sh start` |
| Data without a browser | `python scripts/dashboard.py --once` (RAM, network, services as JSON) |
| Live call network numbers | `python scripts/rtc_stats.py` |
| Apply a code change | `kill $(cat ~/.cache/dashboard/server.pid)`; the supervisor restarts it within 15 s; viewers reload |

Durable across Claude exits: `start` uses `setsid nohup`. Not started at boot (Termux:Boot would do it).

## API (all need `Authorization: Bearer <token>`; "/" is the static page)
`/api/system` (2 s: RAM, components, services, network) · `/api/history` (1 h of points) ·
`/api/work?h=<hash>` (queue, sessions, memory, logs; `"work": null` when unchanged) · `/api/session?id=<folder>/<uuid>`
(steps of one Claude session, only agent folders accepted).

## What feeds what
- Components: `/proc/<pid>/stat` RSS + CPU deltas of our uid's processes, grouped by `component()` in dashboard.py
  (Chrome profile name decides WhatsApp vs Nova; children inherit the parent's group). Add a group there.
- Claude sessions: `~/.claude/projects/<folder>/*.jsonl`; `session_kind()` maps folders: `~/nova_work` = meeting desk,
  `~/nova_work/<id>` = Nova task, `~/nova_meetings/<id>` = memory update, `~/.cache/wa-virtmic/claude-tool` and
  `scripts/calls/*` = WhatsApp. A new agent folder elsewhere won't show until it is added there. Live = a `claude`
  process has that folder as cwd.
- Call quality: `rtc_stats.JS` is added at page start by `mic_apm.install` (WhatsApp) and `meet/browser.py` (Meet); it only
  records RTCPeerConnections. The dashboard reads it over CDP 9222/9333 every 2 s during a call (5 s otherwise).
- Latency: TCP connect to api.openai.com, web.whatsapp.com, meet.google.com, 1.1.1.1 every 10 s.

## Gotchas
- Android denies `/proc/stat`, `/proc/loadavg`, `/proc/net/*`, `/sys/class/net`, battery sysfs: no phone-wide CPU or
  data counters. CPU shown = our processes (100% = one core). Battery needs the Termux:API app.
- Do not switch the page back to one long streaming response: the quick tunnel delivers the first chunk and then
  stalls (tested: SSE, exact content type, chunked encoding all stall). Short polls work.
- RSS counts only what is in RAM; with a lot of swap in use, a process "grows" when it is touched again (swap-in).
- Testing the page in Nova's Chrome (CDP 9333) leaves renderer processes behind after the tab is closed; prefer
  `--once` and curl. Never leave test RTCPeerConnections/AudioContexts running there.
- Privacy: everything is passed through `redact()`; output of steps matching `PRIVATE` (gws, mail, credentials...) is
  withheld. Keep that for anything new you expose. Meeting links are masked.
- Port 8787 belongs to the handoff page; the dashboard is 8790 (`DASH_PORT`).
