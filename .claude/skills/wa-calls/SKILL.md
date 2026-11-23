---
name: wa-calls
description: Place a WhatsApp voice call with the AI agent, send/read WhatsApp messages, look up a contact's number, or review what was said on a past call (transcripts, recordings). Use for "call X", "message X", "what did X say", "how did the call go".
---

# WhatsApp calls & messages (cheap path: scripts, never screenshots)

Everything goes through the logged-in WhatsApp Web in Chromium (CDP `localhost:9222`). Never take screenshots or
search the UI: contacts resolve from WhatsApp Web's own IndexedDB, chats open by number. Run from the repo root.

| Task | Command |
|---|---|
| Find a contact's number | `python3 scripts/wa_call.py --lookup "name part"` |
| Call (AI talks, waits for them to say hello) | `setsid nohup python3 -u scripts/wa_call.py "Exact Name" --brief "purpose/context" > scripts/wa_call_<who>.log 2>&1 < /dev/null &` |
| Send a message | `python3 scripts/wa_msg.py "Exact Name" "text"` (or a number with country code instead of the name) |
| Read last N messages | `python3 scripts/wa_msg.py "Exact Name" --read 8` |
| WhatsApp logged in? | `python3 scripts/cdp_eval.py status` (`chatList: True` = OK, `qr: True` = logged out -> wa-ops skill) |

- A name must match exactly ONE saved contact, else the script lists candidates and exits 2: pick the right one
  (ask the user only if genuinely ambiguous) and pass a longer name or the number.
- `--brief` is the call's purpose; the AI says it's an AI assistant. Never have it impersonate a real person.
- Engine: `--engine live` (default, full-duplex gpt-live-1) or `realtime` (turn-based gpt-realtime-2.1).
- The call script hangs up by itself (hangup.py: caller asks to end + AI says bye), and when the caller's audio has
  been digital silence for 30 s. Max length `--max 600` s.
- Follow a call cheaply: `grep -E "\] (AI|CALLER)|hangup|call ended|FAILED" scripts/wa_call_<who>.log` — poll every
  ~30-60 s with a sleep loop, don't tail continuously.
- "call ended" after ~20 s with no AI/CALLER lines = not answered. Check `wa_msg.py ... --read 3` — they often text back.
- Group calls cannot be auto-answered; ask people to call one-to-one.

## Call center (since 2026-11-24, branch termux-native)
Every call (incoming and outgoing) has Claude Code as the voice AI's back office: GPT-Live delegates, Claude
(`scripts/claude_tool.py`, one resumed `claude -p` session per call, web + desk only) works the desk
`scripts/cc.py`, scoped to the person on the line: `who`, `chat`, `photo`, `send`, `remind`, `note`, `escalate`
(WhatsApp to the owner's own chat, prefixed `[AI desk]`), `calls`, `transcript`, `status`. The voice model gets a
caller card (name, past calls + summaries, notes, latest chat) at call start; after hang-up Claude wraps up (notes,
promised messages, escalation, `summary` in call_meta.json). Per-person notes/reminders: `scripts/contacts/`
(git-ignored); the supervisor sends due reminders (`cc.py due`). Desk actions of a call: `calls/<ts>/desk.log`.
WhatsApp access during calls goes through `scripts/wa_store.py` (in-memory models, NO page reload - wa_msg.py's
send?phone= reload would drop a live call). Turn off: LIVE_CLAUDE_TOOL=0.

## Reviewing a call
Call went badly (cracky voice, slow replies, didn't hang up)? Run `python3 scripts/call_diag.py` -> skill **wa-diag**.
Each call has a folder `scripts/calls/<YYYYmmdd_HHMMSS>/` (latest: `ls -t scripts/calls | head -1`):
- `transcript_live.txt` — what the AI and caller said, from the live session. Most reliable; read this first.
- `transcript.txt` — offline transcription after the call. Garbles quiet or Hindi speech into other languages,
  so trust it less.
- `call_mix.mp3` to listen, `call_stereo.wav` (L = AI, R = caller), `ai.wav` / `caller.wav`.
- Incoming calls are logged in `scripts/auto_answer.log`. The caller's name is in `scripts/call_ui_last.html`
  (strip the tags).
- Who was audible, and when: compute the RMS of `ai.wav` and `caller.wav` over 2 s windows with numpy. This is
  cheap and tells you whether the AI went silent.
