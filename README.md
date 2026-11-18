# wa-virtmic

A proof of concept: an AI voice acts as the **microphone** for a WhatsApp Web voice call, all inside a GitHub Codespace.

- Headed Chrome runs on a noVNC desktop (devcontainer `desktop-lite`)
- PulseAudio virtual devices: `virtmic` is Chrome's mic, and `callout_sink` receives the call audio
- `auto_answer.py` answers incoming calls over CDP, runs a **live two-way voice agent** (OpenAI `gpt-realtime`), and records and transcribes both sides

## Quick start (Codespace)

1. Open the repo in a Codespace (or rebuild the container). Dependencies install automatically (`postCreateCommand`), and the
   audio devices are created on every start (`postStartCommand`).
2. `cp scripts/.env.example scripts/.env` and fill in your OpenAI-compatible LLM gateway URL and token.
3. `make demo` starts audio, Chrome and the call auto-answerer, prints the noVNC desktop URL (password `vscode`) and waits while you
   scan the WhatsApp QR code with your phone (first time only).
4. `make doctor` checks everything (read-only) and prints the exact fix for anything that fails. `make sim` runs a simulated call
   without a phone, `make stop` stops the auto-answerer.

No `make`? Use `bash scripts/demo.sh` and `python3 scripts/doctor.py`. On Windows (WhatsApp Desktop + VB-Cable, untested) see
[`WINDOWS.md`](WINDOWS.md).

See [`scripts/README.md`](scripts/README.md) for the details, the manual steps and test results.

## Experiments and results

- Plan: [`EXPERIMENTS.md`](EXPERIMENTS.md) (E0 to E6). Per-experiment notes are in `experiments/<ID>/RESULTS.md`.
- Results site (GitHub Pages from `docs/`): https://jivraj-18.github.io/wa-virtmic/
- Test without a phone: `python3 scripts/sim_call.py experiments/E0/scripts/basic_qa.yaml --tag E0`
