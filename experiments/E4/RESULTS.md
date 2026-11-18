# E4 results: Google Meet agent "Maya"

**Status: IN PROGRESS** (research done, building next).

## 1. Research: reuse an open-source meeting bot, or our own stack?

Checked 2026-11-18 (GitHub/PyPI pages):

| project | licence | how it joins Meet | audio in/out | can speak? | footprint | maintenance |
|---|---|---|---|---|---|---|
| [joinly](https://github.com/joinly-ai/joinly) | MIT | Browser automation (Playwright) inside its Docker image; guest join by filling the name field and clicking "Join"/"Ask to join"; VNC option for debugging | Virtual audio inside the container; local Whisper STT + TTS models | Yes (`speak_text` MCP tool, also chat) | Docker image ~2.3 GB (browser + models); CUDA variant | Active (≈570 stars, 800+ commits) |
| [Attendee](https://github.com/attendee-labs/attendee) | see repo LICENSE | Full Chrome instance running Meet (Zoom via SDK) | Inside the bot container | Partly (audio output API) | Django + Postgres + Redis + Celery/Kubernetes, AWS settings, Deepgram key | Very active (≈800 stars, 5k commits) |
| [meeto](https://pypi.org/project/meeto/) ([repo](https://github.com/ResearchifyLabs/meeto)) | MIT | Playwright Chromium; guest mode (needs Xvfb, Google blocks headless guests) or authenticated `storage_state.json` | Capture only, Deepgram STT | No | pip + Playwright Chromium (~150 MB) | Small, v0.3.3 (Apr 2026) |
| [Vexa](https://github.com/Vexa-ai/vexa) | Apache-2.0 | Bot container joins as participant | Transcription service (hosted token or GPU Whisper) | No (`/speak` returns 404 in open core) | ~10 containers (gateway, APIs, Redis, Postgres, storage), Docker ≥ 26 | Very active (≈3k stars) |

What they have in common: **every one of them drives a real (headed or Xvfb) Chrome on meet.google.com** and routes
audio through virtual devices. Google offers no bot API for Meet media, so there is no shortcut. The useful thing to
take from them is the **DOM knowledge** (joinly's selectors: name placeholder `/name/i`, button `/join/i` excluding
"other ways", `Turn on/off mic` buttons, `Chat` button, `textarea[placeholder*='Send a message']` + Enter,
"asking to be let in" / "Leave call" to detect join), and their warnings (guests wait in the lobby; headless is
detected; Meet's mic/speaker pickers must point at the virtual devices).

### Decision: reuse our own Chrome + PulseAudio + gpt-realtime stack; borrow selectors, not code

Reasons:
1. **We already have the hard parts working**: headed Chrome on the noVNC desktop, PulseAudio virtual mic/speaker,
   a streaming `gpt-realtime` agent with barge-in, and a test harness (E0) that measures it. A Meet bot is the same
   pipeline pointed at a different web page.
2. **Resources**: 2 CPUs / 7 GB RAM / ~5 GB disk shared with five other experiments. joinly's 2.3 GB image (plus local
   Whisper/TTS on CPU), Attendee's Postgres/Redis/Celery stack and Vexa's ~10 containers don't fit, and Docker isn't
   part of our setup. Maya needs **no new installs** (Playwright, Chrome, PulseAudio, websockets are already there).
3. **Speaking**: only joinly speaks into the meeting, and it does it with its own STT→LLM→TTS loop. We want
   `gpt-realtime` (≈1.2 s end-to-end in E0, native barge-in). Swapping joinly's voice loop out would be more work
   than writing the ~150 lines of Meet page control.
4. **Login as a separate Google account**: the user logs in by hand in noVNC. A persistent Chrome profile (like our
   WhatsApp profile) does this naturally; meeto's `storage_state.json` and joinly's guest join are the alternatives.
   Guest join also works with our code (fallback: fill the name field, "Ask to join"), but the host must admit Maya.
5. **Licences** (MIT for joinly/meeto) would allow copying; we only reuse ideas (selector patterns), credited here.

Risk accepted: Meet's DOM changes often, so selectors are best-effort, written as several fallbacks each, and
tested against a local mock page only (no real Meet from this sandbox).
