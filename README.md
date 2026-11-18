# wa-virtmic

A proof of concept: an AI voice acts as the **microphone** for a WhatsApp Web voice call, all inside a GitHub Codespace.

- Headed Chrome runs on a noVNC desktop (devcontainer `desktop-lite`)
- PulseAudio virtual devices: `virtmic` is Chrome's mic, and `callout_sink` receives the call audio
- `auto_answer.py` answers incoming calls over CDP, runs a **live two-way voice agent** (OpenAI `gpt-realtime`), and records and transcribes both sides

See [`scripts/README.md`](scripts/README.md) for the setup, the run order, the manual steps and test results.

## Experiments and results

- Plan: [`EXPERIMENTS.md`](EXPERIMENTS.md) (E0 to E6). Per-experiment notes are in `experiments/<ID>/RESULTS.md`.
- Results site (GitHub Pages from `docs/`): https://jivraj-18.github.io/wa-virtmic/
- Test without a phone: `python3 scripts/sim_call.py experiments/E0/scripts/basic_qa.yaml --tag E0`
