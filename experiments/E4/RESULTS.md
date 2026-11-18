# E4 results: Google Meet agent "Maya"

**Status: PARTIAL** (2026-11-18). Built and tested on simulated meetings; the real Google Meet test is **BLOCKED** on the user
(a separate Google account logged in by hand + a Meet URL). Site page: `docs/E4.html`.

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

## 2. Design (what was built)

| file | what |
|---|---|
| `scripts/meet/maya.py` | `Maya` class + CLI. `agent` subcommand = listen/speak logic on any PulseAudio devices (used with the E0 harness). Wraps `realtime_agent.Agent` with `greeting=None`, `turn_detection.create_response=false` (the model never auto-replies), `interrupt_response=true`, transcription `gpt-4o-transcribe` (en). |
| `scripts/meet/addressing.py` | Rules for "is this utterance addressed to Maya?". Vocative at the start ("Maya, …", "Hey/OK so, Maya …"), set off by commas mid-sentence, at the end ("…, Maya?"), or name + 2nd-person cue ("Maya can you"); **not** when she is the object/subject in 3rd person ("Maya's", "Maya said", "ask/to/with/thanks Maya"). Name look-alikes from STT (Maia, Mayah, Mya…) count. `early_address()` fires on the *streaming* transcript delta when the name comes first, so the reply starts before the final transcript. |
| `scripts/meet/suggester.py` | Background thread: every 20 s checks; if ≥ `min_interval` (default 180 s) since the last attempt, ≥ 60 s into the meeting and ≥ 4 new lines, asks `gpt-4.1-mini` (gateway chat completions, 429 back-off) for ONE ≤ 20-word suggestion or `NONE`. Posts via a callback (Meet chat in `join`, `maya_events.jsonl` in `agent`). |
| `scripts/meet/browser.py` | Maya's own Chrome (`~/.config/maya-chrome-profile`, CDP **:9333**, refuses 9222) with `PULSE_SINK=maya_out`, `PULSE_SOURCE=maya_mic`; PulseAudio devices `maya_out` (speaker), `maya_mic_sink` + remap source `maya_mic` (microphone); Meet control over Playwright CDP: join (guest-name fallback, camera off, mic on, Join now/Ask to join, wait in lobby), chat send, leave, `probe` (dump visible buttons). A stream-routing fallback moves only streams whose PID belongs to the :9333 Chrome process tree. Selectors are documented in the module docstring. Subcommands: `devices up/down`, `login`, `join <url>`, `leave`, `probe`. |
| `scripts/meet/score_sim.py` | Scores a harness run against the YAML's `addressed: true` flags: false triggers, addressed latency, barge-in stop, suggestions. |
| `experiments/E4/scripts/meeting.yaml`, `meeting_hard.yaml` | 4-voice (edge-tts) simulated meetings, 15 and 14 lines; 3 addressed lines each; hard negatives; one talk-over each. |
| `tests/test_meet_addressing.py`, `test_meet_suggester.py`, `test_meet_browser.py` + `tests/meet_mock.html` | Plain-python tests (no pytest install). The browser test launches **headless** Chrome with a temp profile on :9334 against a mock Meet page (join → lobby → admitted → chat → leave) and creates/removes throwaway `mayatest_*` devices. All pass. |

Barge-in: besides the server VAD, Maya runs a **local energy VAD** (parec 16 kHz on the meeting audio, RMS > 400 for
120 ms) while her audio is still playing (tracked from the bytes queued to pacat). On trigger: kill/restart pacat,
`response.cancel` (if still generating), `conversation.item.truncate` to what was actually played, and late audio
deltas of the cancelled response are dropped.

### Shared-file changes (minimal, backward compatible)
- `scripts/realtime_agent.py`: `greeting=None`/`""` skips the opening `response.create` (2 lines). Default unchanged.
- `scripts/sim_call.py`: optional per-line `reply_timeout` (how long the harness waits for a reply after that line) so
  unaddressed lines don't wait the full 20 s. Default unchanged.

## 3. Simulated results (E0 harness, `--tag E4`)

Runs: `meeting` (09:04) and `meeting_hard` (10:39, re-run after the Codespace restart; an earlier 09:09 run of the same
script gave the same picture: 0 false triggers, latency 1.62–1.96 s, stop 0.14 s).

| meeting | lines not for Maya | false triggers | lines to Maya | answered | answer latency (median / max) | stopped after talk-over |
|---|---|---|---|---|---|---|
| meeting | 12 | **0** | 3 | 3 | 1.80 / 2.02 s | **0.16 s** |
| meeting_hard | 11 | **0** | 3 | 3 | 1.86 / 1.92 s | **≤ 0.1 s** (0.00 measured*) |
| meeting_hard (09:09) | 11 | 0 | 3 | 3 | 1.68 / 1.96 s | 0.14 s |

\* the harness found ≥ 0.3 s of silence right at the interrupter's voice onset, i.e. Maya was already quiet or in a
breath pause; the local VAD fired at that moment. E0's plain agent needed 1.54 s.

- **False-trigger rate 0/34** non-addressed lines over the three runs, incl. "Maria, can you…", "Ravi, what do you
  think…", "Maya's summary…", "I think Maya and the on-call team…", "Can you ask Maya to…", "Let's ask Maya…",
  "…sent the mock-ups to Maya…", and a question to the room without a name.
- **Addressed: 9/9 answered**, latency 1.6–2.0 s (vs ~1.2–1.4 s for the always-replying E0 agent: the extra ≈0.5 s is
  waiting for the transcript). 4 of 6 were early triggers on the streaming partial ("Maya, can…").
- Answers used meeting context ("I'd suggest aiming for the following week, after we've fully tested").
- After the talk-over, Maya stayed silent (the interrupter addressed someone else) and the next "…, Maya?" got an answer.

Chat suggestions (simulated: logged to `maya_events.jsonl`; interval shortened to 45 s for the 3-minute test):
- "Could we prioritize fixing payment error screens and run a quick load test to ensure stability before launch?"
- "Can someone confirm the payment provider sandbox availability today to finalize the launch timeline?"
- "Maybe consider running the backfill on a small dataset first to monitor impact before full execution."
- "Maybe confirm a rollback test on staging before Friday to ensure rollback time estimates are accurate."
- Bad one (09:09 run): "I'll send the checklist and runbook to everyone right after this meeting" — it answered a
  3rd-person request with a promise. The prompt now forbids promises/answering requests; the re-run had none.

Issues seen
- A harmless `response_cancel_not_active` error on barge-in (the server's own `interrupt_response` cancels at the same time).
- The harness's STT once wrote an English line in Devanagari (transcript only; Maya's own transcript was right).
- A websocket 1011 close at shutdown (SIGINT from the harness) — cosmetic.
- No diarisation: Maya hears one mixed stream and doesn't know who spoke.

## 4. BLOCKED: real Google Meet test (needs the user)

Nothing here was run against meet.google.com; the visible Maya Chrome was never started on DISPLAY :1 (it would cover
the WhatsApp window). Needed: (1) a **separate Google account for Maya**, logged in by the user in noVNC;
(2) a **Meet URL** of a test meeting the user hosts.

Steps:
1. `cd /workspaces/temp` (after merging) and `python3 -m scripts.meet.maya devices up`
2. `python3 -m scripts.meet.maya login` → a second Chrome window opens on noVNC at accounts.google.com. Log in with
   Maya's account (profile `~/.config/maya-chrome-profile`, kept across restarts; not the WhatsApp profile). Then
   minimise that window so the WhatsApp window stays visible.
3. Start a Meet from your own account; then
   `python3 -m scripts.meet.maya join https://meet.google.com/xxx-yyyy-zzz` (default suggestion interval 180 s;
   `--suggest-interval 60` to see tips sooner). If Maya ends up in the lobby, admit her.
4. Talk normally for a minute (she must stay silent), then say **"Maya, what do you think about …?"** (she answers),
   ask **"Maya, explain X in detail"** and talk over her (she stops), and wait for a chat tip.
5. If a button isn't found: `python3 -m scripts.meet.maya probe` prints the visible buttons; adjust `RX` in
   `scripts/meet/browser.py`. Output (transcript, events) goes to `~/maya_meetings/<ts>/` (outside the repo).
6. `python3 -m scripts.meet.maya leave`, then `python3 -m scripts.meet.maya devices down` when done.
