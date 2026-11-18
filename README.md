# wa-virtmic

A proof of concept: an AI voice acts as the **microphone** for a WhatsApp Web voice call, all inside a GitHub Codespace.

- Headed Chrome runs on a noVNC desktop (devcontainer `desktop-lite`)
- PulseAudio virtual devices: `virtmic` is Chrome's mic, and `callout_sink` receives the call audio
- `auto_answer.py` answers incoming calls over CDP, runs a **live two-way voice agent** (OpenAI `gpt-realtime`), and records and transcribes both sides

See [`scripts/README.md`](scripts/README.md) for the setup, the run order, the manual steps and test results.
