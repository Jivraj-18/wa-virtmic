# wa-virtmic

AI voice agent that answers and places WhatsApp calls through WhatsApp Web. The live setup runs on an Android phone
(Termux → proot Debian → Chromium on Xvfb + PulseAudio). Keep token use low: use the scripts and don't take screenshots.

- Calls, messages, contacts, call transcripts → skill **wa-calls**
- Answerer service, re-login, crashes, gotchas, pushing → skill **wa-ops**
- Bad call quality / slow replies / diagnosis with metrics (`scripts/call_diag.py`) → skill **wa-diag**
- More detail: `scripts/README.md`, `docs/TERMUX.md`
