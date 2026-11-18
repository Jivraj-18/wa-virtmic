# Running the AI voice on Windows (WhatsApp Desktop + VB-Cable)

> **UNTESTED ON WINDOWS.** This path was written and checked on Linux only (the audio adapter was exercised with a
> stub audio backend, see `experiments/E6/RESULTS.md`). Expect to adjust device names. The supported, tested path is the
> Codespace (`make demo`, see the root README).

The Codespace path uses WhatsApp **Web** in Chrome plus PulseAudio virtual devices. On a Windows PC you can do the same
with the **WhatsApp Desktop** app and two virtual audio cables. The AI logic is the same file
(`scripts/realtime_agent.py`); only the audio I/O changes, from `parec`/`pacat` to `sounddevice`
(`scripts/win_agent.py` is a small adapter).

## What's different from the Codespace

| | Codespace (tested) | Windows (untested) |
|---|---|---|
| WhatsApp | WhatsApp Web in Chrome | WhatsApp Desktop app |
| AI's microphone | PulseAudio `virtmic_sink` -> `virtmic` | VB-Cable 1: play `CABLE Input` -> WhatsApp mic `CABLE Output` |
| Caller's voice | Chrome speaker -> `callout_sink.monitor` | VB-Cable 2: WhatsApp speaker `CABLE-A Input` -> record `CABLE-A Output` |
| Answering | `auto_answer.py` clicks Accept over CDP | **you click Accept** (no automation hook in the desktop app) |
| Recording, post-call transcript | `auto_answer.py` | not included; the live transcript is written |

## Audio routing

```
AI (win_agent.py) --plays--> "CABLE Input"   ==VB-Cable 1==>  "CABLE Output"   --> WhatsApp microphone --> caller
caller --> WhatsApp speaker  --> "CABLE-A Input" ==VB-Cable 2==> "CABLE-A Output" --records--> AI (win_agent.py)
```

Two separate cables are needed. With one cable the AI would hear itself (its own voice would loop back as "caller audio").

## Step by step

1. **Install the virtual cables** (needs admin, then a reboot):
   - VB-CABLE (free): https://vb-audio.com/Cable/ - gives `CABLE Input` / `CABLE Output`.
   - VB-CABLE A+B (donationware, same site) - gives `CABLE-A Input` / `CABLE-A Output` (and B, unused).
   Run each `VBCABLE_Setup_x64.exe` as administrator, reboot.
2. **Keep Windows from using the cables as defaults.** Settings > System > Sound: set Output to your real
   speakers/headphones and Input to your real mic, so other apps don't play into the cables.
3. **Install Python 3.11+** from python.org (tick "Add python.exe to PATH"). Then in a terminal in the repo folder:
   ```
   pip install sounddevice numpy websockets
   ```
4. **Gateway settings:** copy `scripts\.env.example` to `scripts\.env` and fill in `LLM_GATEWAY_BASE` and
   `LLM_GATEWAY_TOKEN` (your OpenAI-compatible LLM gateway). The realtime WebSocket goes straight to `api.openai.com`, so
   that host must be reachable from the PC (corporate proxies may block WebSockets).
5. **Check the device names:**
   ```
   python scripts\win_agent.py --list
   ```
   Each cable shows up several times (MME, DirectSound, WASAPI). Any unique part of the name works, or pass the index.
   If you get "Invalid sample rate", pick the **MME** entry's index (MME resamples to 24 kHz for you), or set the cable
   to 48000 Hz in its Properties > Advanced.
6. **Install WhatsApp Desktop** (Microsoft Store) and link it to the phone (Linked devices > Link a device > scan QR).
7. **Point WhatsApp at the cables:** WhatsApp Desktop > Settings > (Audio / Video and voice) or, during a call,
   the "..." menu:
   - Microphone: **CABLE Output (VB-Audio Virtual Cable)**
   - Speakers: **CABLE-A Input (VB-Audio Cable A)**
   If WhatsApp has no device picker in your version, use Windows: Settings > System > Sound > Volume mixer > WhatsApp,
   and set its Output to `CABLE-A Input` and Input to `CABLE Output`.
8. **Start the agent, waiting for a call:**
   ```
   python scripts\win_agent.py --in "CABLE-A Output" --out "CABLE Input" --wait
   ```
   `--wait` opens the realtime session only once caller audio is heard, so nothing is spent while idle.
9. **Have someone call; click Accept in WhatsApp Desktop.** The AI greets the caller and talks. The live transcript goes to
   `transcript_<time>.txt` in the current folder. Press Ctrl+C when the call ends, then start step 8 again for the next call.
10. **To listen in** (optional): Sound Control Panel > Recording > `CABLE-A Output` > Properties > Listen >
    "Listen to this device" on your headphones. You will hear only the caller; the AI's own voice is in `CABLE Output`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: sounddevice` | `pip install sounddevice` (it ships PortAudio on Windows) |
| `ValueError: No input device matching 'CABLE-A Output'` | VB-CABLE A+B not installed, or a different name: run `--list` and pass a name part or index |
| `Multiple input devices found` | the name matches several host APIs: pass the index from `--list` |
| `Invalid sample rate` | use the MME index, or set the cable's default format to 48000 Hz |
| Caller hears nothing | WhatsApp mic must be `CABLE Output`; agent `--out` must be `CABLE Input` |
| AI never answers / answers itself | WhatsApp speaker must be `CABLE-A Input`, agent `--in` `CABLE-A Output`, and the two must be different cables |
| `HTTP 401/429` when starting | check `scripts\.env`; 429 = gateway rate limit, wait a minute |
| Connects but times out | `api.openai.com:443` blocked (proxy/firewall) |

## Limits

- No auto-answer: WhatsApp Desktop has no debugging port like Chrome's CDP. Desktop UI automation (pywinauto) could click
  Accept, but is not included.
- One call at a time, same as the Codespace.
- `sim_call.py` and `make doctor` are Linux/PulseAudio only.
