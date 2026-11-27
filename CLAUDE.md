# wa-virtmic

AI voice agent that answers and places WhatsApp calls through WhatsApp Web. The live setup runs on an Android phone
(Termux → proot Debian → Chromium on Xvfb + PulseAudio). Keep token use low: use the scripts and don't take screenshots.

- Calls, messages, contacts, call transcripts → skill **wa-calls**
- Answerer service, re-login, crashes, gotchas, pushing → skill **wa-ops**
- Bad call quality / slow replies / diagnosis with metrics (`scripts/call_diag.py`) → skill **wa-diag**
- Nova (AI teammate on Google Meet: join/leave/status/autojoin, notes, Meet DOM breakage) → skill **nova-meet**
  (`python scripts/nova/nova.py ...`; issue #3)
- Nova changing her OWN code when asked in a meeting (worktree, tests, PR, deploy when idle, rollback) → skill
  **nova-self-update** (`scripts/nova/selfupdate.py status|rollback`)
- Google Workspace CLI `gws` (Calendar/Drive/Meet/Gmail, OAuth scopes, re-auth) → skill **nova-gws**
- Live dashboard (phone RAM/CPU per component, network latency + live call quality, services, Nova queue, every agent Claude session live, memory, logs),
  public via Cloudflare quick tunnel → skill **dashboard** (`bash scripts/dashboard.sh start|link|status|stop`)
- Escalation to a human: `scripts/handoff.py` (phone rings, the person takes over on http://localhost:8787 in the phone's Chrome)
- Rule: a task likely to be done again becomes a script or a skill, not a one-off command
- More detail: `scripts/README.md`, `docs/TERMUX.md`
