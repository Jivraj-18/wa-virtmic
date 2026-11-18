# WhatsApp Web call with a TTS virtual microphone (proof of concept)

Goal: a TTS voice acts as the **microphone** for a WhatsApp Web voice call, entirely inside this Codespace.

## Audio routing

```
speak.py ──edge-tts──ffmpeg──paplay──▶ virtmic_sink ──monitor──▶ virtmic (DEFAULT SOURCE) ──▶ Chrome mic ──▶ caller
caller ──▶ Chrome speaker ──▶ callout_sink (DEFAULT SINK) ──monitor──▶ callout_sink.monitor (record caller here)
```

## Files

| File | Purpose |
|---|---|
| `install.sh` | apt: Google Chrome stable (.deb), pulseaudio, pulseaudio-utils, ffmpeg. pip: edge-tts, numpy, playwright, websockets, pyyaml. Claude Code. Idempotent (devcontainer `postCreateCommand`) |
| `demo.sh` | `make demo` / `make stop`: one-command start (audio, Chrome, auto_answer), noVNC URL, QR walk-through. `--dry-run` |
| `doctor.py` | `make doctor`: read-only health check with a fix per failure. `--offline`, `--redact`, `--url`, `--wait-login SECS` |
| `win_agent.py` | Windows path (untested): the same realtime agent with `sounddevice` I/O for WhatsApp Desktop + VB-Cable. See `WINDOWS.md` |
| `audio_setup.sh` | Starts the PulseAudio user daemon and creates `virtmic_sink`, `virtmic`, `callout_sink`. Can be re-run safely |
| `test_virtmic.sh` | Plays a 440 Hz tone into `virtmic_sink`, records 3 s from `virtmic`, prints RMS. `DUR=12 ./test_virtmic.sh -- CMD` records while CMD plays |
| `rms.py` | Prints the RMS/dBFS of a WAV file |
| `speak.py` | `python scripts/speak.py "text"`: synthesizes speech with edge-tts (en-IN-NeerjaNeural) and plays it into `virtmic_sink` |
| `launch_chrome.sh` | Headed Chrome on DISPLAY :1 with PULSE_SERVER, a persistent profile (`~/.config/wa-chrome-profile`) and CDP on :9222. Opens web.whatsapp.com |
| `cdp_eval.py` | Inspects the WhatsApp tab over CDP: `status`, `console SECS`, `js EXPR` |
| `auto_answer.py` | Watches WhatsApp Web over CDP, pre-grants mic permission, clicks **Accept** on incoming calls, moves Chrome's streams to virtmic/callout_sink, speaks the greeting, and **records every call end to end** into `calls/<ts>/`: `ai.wav` (what we sent), `caller.wav` (what we received), `call_stereo.wav` (L=AI, R=caller), `call_mix.mp3`, and `transcript.txt` (timestamped). Recording stops 3 s after hang-up. Log: `auto_answer.log` |
| `realtime_agent.py` | **Live two-way voice agent** (default mode of `auto_answer.py`). Streams caller audio (callout_sink.monitor) to OpenAI `gpt-realtime` and plays its replies into virtmic_sink. The caller can interrupt, and a live transcript goes to `calls/<ts>/transcript_live.txt`. The LLM gateway can't proxy WebSockets, so it fetches a short-lived key from `/openai/v1/realtime/client_secrets` (plain HTTP, with a unique nonce to avoid the gateway cache) and connects directly to `wss://api.openai.com`. Measured with the E0 harness: median **1.2–1.4 s** from the end of the caller's voice to the AI's first audio (the earlier "0.3–0.6 s" figure counted only from the reply request). Standalone test: `python3 scripts/realtime_agent.py --seconds 30` |
| `sim_call.py` | **E0 test harness**: a scripted TTS caller with private sinks (`virtmic_<tag>`/`callout_<tag>`) that runs any agent, records both sides and writes latency metrics. See `experiments/E0/` |
| `publish_run.py` | Copies a simulated run (≤60 s clip, transcript, metrics) into `docs/media/<ID>/` for the results site |
| `transcribe.py` | Speech-to-text via the LLM gateway `/openai/v1/audio/transcriptions` (gpt-4o-transcribe). `segments()` splits a track into utterances by energy and transcribes each one with real timestamps |
| `.env` (gitignored, see `.env.example`) | `LLM_GATEWAY_BASE`, `LLM_GATEWAY_TOKEN` for an OpenAI-compatible LLM gateway (TTS `/openai/v1/audio/speech` gpt-4o-mini-tts, STT, Realtime client secrets). `speak.py` uses it by default, `--engine edge` uses edge-tts |
| `gateway.py` | Reads the gateway settings and builds the auth header |
| `call_check.sh` | During a call: checks/fixes Chrome's stream routing, speaks the test line, records the caller |

## Run order

One-command flow (E6). Every step is idempotent.

1. **(automatic)** Creating/rebuilding the container runs `bash scripts/install.sh` (`postCreateCommand`: Chrome .deb, pulseaudio,
   ffmpeg, Python modules, Claude Code; skips what is already installed). Every start runs `bash scripts/audio_setup.sh`
   (`postStartCommand`). Both can be run by hand any time (`make install`, `make audio`).
2. **(manual, once)** `cp scripts/.env.example scripts/.env` and fill in `LLM_GATEWAY_BASE` / `LLM_GATEWAY_TOKEN`.
3. `make demo` (or `bash scripts/demo.sh`): runs `audio_setup.sh`, `launch_chrome.sh` (if Chrome isn't up yet) and
   `auto_answer.py` in the background (log: `scripts/auto_answer.log`; not started twice), prints the noVNC URL, then watches the
   WhatsApp login. `make demo-dry` / `--dry-run` only checks and prints what it would do.
4. **(manual, first time only)** Open the printed noVNC URL (`https://<codespace>-6080.app.github.dev/vnc.html?autoconnect=true&resize=scale`,
   also in the **Ports** tab, port 6080; password `vscode`). Scan the WhatsApp QR with your phone (WhatsApp > Linked devices >
   Link a device). `make demo` prints "WhatsApp Web is logged in." when done.
5. `make doctor` (`python3 scripts/doctor.py`): read-only PASS/WARN/FAIL for PulseAudio, devices, noVNC, Chrome CDP, WhatsApp
   login, auto_answer, `.env`, gateway, a realtime key and `api.openai.com`, with the exact fix for each failure.
6. **(manual)** Have someone WhatsApp voice-call this account. Don't answer on the phone. Ask whether they heard the AI voice.
7. `make stop` stops `auto_answer.py` (Chrome keeps running; `bash scripts/demo.sh stop --chrome` closes it too).

Without a phone: `make sim` (E0 `basic_qa` simulated call on private sinks; `TAG=...` names the run).

Manual equivalents (what `make demo` runs): `bash scripts/install.sh`, `bash scripts/audio_setup.sh` (then `bash scripts/test_virtmic.sh`
should print AUDIO PRESENT), `bash scripts/launch_chrome.sh`, `python3 scripts/cdp_eval.py status` (`chatList: True` once logged in),
`setsid nohup python3 -u scripts/auto_answer.py > scripts/auto_answer.log 2>&1 < /dev/null &` (`--once` stops after one call;
`--mode greeting` plays the fixed greeting instead of the live agent). Manual alternative to auto-answer: answer in noVNC Chrome,
click Allow, then run `bash scripts/call_check.sh`.

## Verified results

- Step 3 (tone → virtmic): RMS 2762.6 (−21.5 dBFS), AUDIO PRESENT. Silence control: RMS 0.
- Step 4 (speak.py → virtmic): RMS 1609.5 (−26.2 dBFS), AUDIO PRESENT. edge-tts needs about 4 s of network time before playback starts.
- Gateway TTS (gpt-4o-mini-tts) → virtmic: RMS 3080.9 (−20.5 dBFS), AUDIO PRESENT. About 4 s per request.
- Step 5: Chrome 158 headed on :1, CDP on :9222, WhatsApp Web loaded and showing its QR code.
- Step 6 call test (2026-11-18 07:36): auto-answered through the Accept button, with no mic prompt thanks to the CDP grant. Chrome played the call into callout_sink.
  The caller recording had RMS 1307 (that audio was later deleted by mistake; the transcript survives in `calls/20261118_073603/`). Transcript: caller said "Hello", and right after the AI greeting, **"I can hear you."**
  **Result:** the friend said they heard the AI voice. Clarity was not confirmed, because the user wasn't on the call. Later calls are recorded on both sides in `calls/` so the sent audio can be checked.
  Known gap: we can record what we send and what we receive, but not what the caller's phone actually played. Network breakups on their side wouldn't show up.

- Call 2026-11-18 07:53 (friend, 30 s, `calls/20261118_075302/`): the caller said "Hello" several times. The greeting played only at 0:20, because a gateway TTS request took about 12 s during that call (1.3 s normally). The caller hung up about 7 s after it without replying.
  Fix: the greeting is now generated when the watcher starts (`greeting.wav`) and plays as soon as Chrome's mic is live.
- **Call 2026-11-18 07:56 (test caller, 42 s, `calls/20261118_075626/`): PASS.** Answered automatically, greeting at 0:03.
  The caller replied **"Yes."** (0:10) and **"I could hear you."** (0:14). Both sides were recorded and transcribed.
  The TTS voice works as the WhatsApp Web microphone. The caller confirmed it by voice; it was not rated for clarity.

- The test caller's chat feedback after the 07:56 call: "same… can you hear me say yes… that's all". The AI only ever said one fixed line. **Change:** the AI now holds a live realtime conversation (gpt-realtime). In a simulated test it heard "What is two plus two?" and answered "Two plus two is four." 0.3 s later. Not yet tested on a real call.

## Notes / gotchas
- WhatsApp Web call signalling is an E2E-encrypted binary WebSocket. Incoming calls are detected from the DOM (`aria-label="Accept"`), not from network traffic.
- Our own `parecord`/`paplay` streams are also Pulse clients. Only streams whose process is Chrome are moved, otherwise the recorder gets rerouted.
- `module-suspend-on-idle` is unloaded by `audio_setup.sh`. Otherwise `virtmic` is suspended while silent, `ai.wav` only starts when the greeting plays, and the AI/caller timelines drift apart. The two calls above were realigned afterwards.
- Speech-to-text on very short noises produces junk ("Gua", "Logo.", Korean text), even with `language=en`. Treat 1-word lines with low confidence.
- LLM gateway limits: (1) it can't proxy WebSocket upgrades (`missing Sec-WebSocket-Key`), so `/openai/v1/realtime` and Gemini Live can't be used through it directly. (2) It caches identical POST bodies (`X-Cache`), so the same ephemeral key/session came back. (3) It returns 429 on bursts. (4) Gemini `auth_tokens` could not be tested (429).
- Mic permission granted over CDP lasts only for that Chrome session. `auto_answer.py` grants it again on every start.
