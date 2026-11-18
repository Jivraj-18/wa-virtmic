# E1 results: "call center" mode controlled from a folder

**Status: DONE** (2026-11-18), tested in simulation only. A real WhatsApp call is still needed; see "Real-call check" below.
Site page: `docs/E1.html`.

## What was built
- **`scripts/context.py`** (new, reusable). It works on the agreed context-folder format:
  `instructions.md`, `config.yaml` (voice, language, max_call_seconds, greeting, owner_name, answer_only), `knowledge/` (.md/.txt/.pdf) and `media/` (E5, ignored here).
  - `load_context(path) -> dict`: returns `{path, instructions, config, knowledge:[{name,text}], warnings, loaded_at}`. Missing pieces fall back to defaults.
    PDFs are read with `pdftotext` if poppler-utils is installed, otherwise with `pypdf` (pip, installed for this test). Other file types are skipped with a warning.
  - `build_instructions(ctx, caller=None) -> str`: persona ("You are {owner}'s AI phone assistant…", short replies, answer only from the notes,
    never invent dates/prices/promises, take messages and read them back) + current date/time + caller name + `instructions.md` + knowledge.
    Knowledge is capped at 24,000 characters in total and 12,000 per file; a warning is added when something is cut.
  - `agent_kwargs(ctx, caller=None) -> dict`: `{instructions, greeting, tools: [], on_tool: None, on_event: None, session_extra: {}}`.
    This is the extension point for E2: merge tools and handlers into it.
  - `make_agent(ctx, caller=None, extra=None, **agent_args)`: builds a `realtime_agent.Agent` and applies `config.voice`.
    It does this by setting `realtime_agent.VOICE`, a module global that `Agent.run()` reads, so `realtime_agent.py` needs no change.
  - `caller_allowed(ctx, caller)` (the `answer_only` filter, a case-insensitive substring match) and `caller_from_text(popup_text)`.
- **`scripts/callcenter.py`** (new): `start --context DIR` / `stop` / `status`, plus:
  - `start --check`: validates the folder and prints the built instructions, then exits.
  - `start --dry-run`: launches a stand-in watcher instead of `auto_answer.py`. It doesn't touch Chrome or audio and re-reads the context every 5 s, so `status` and `stop` can be tested.
  - `agent --context DIR --in-device … --out-device … --transcript … --seconds …`: runs the context-built agent standalone, for `sim_call.py`.
  - `summarize <folder> --context DIR [--caller NAME]`.
  - Real `start` runs `auto_answer.py --context DIR [--greeting <config greeting>]` in its own process group and logs to `scripts/callcenter.log`.
    State is kept in `scripts/callcenter_state.json` (git-ignored). `start` **refuses to run if another `auto_answer.py` is running**,
    because two watchers would both click Accept; `--force` overrides this. `stop` only signals the process group that callcenter started.
    `status` shows RUNNING/DRY-RUN/STOPPED, the context summary, other `auto_answer.py` processes (read-only), the number of calls and summaries, and the log tail.
- **`scripts/call_summary.py`** (new): `summarize(folder, ctx, caller) -> Path` writes `summary.md` with the sections Caller,
  What they wanted, What the AI told them / promised, Follow-ups (checkboxes) and Issues. It uses a chat completion on the gateway
  (`/openai/v1/chat/completions`, `gpt-4.1-mini`; `gpt-4o-mini` also works) and retries with backoff on 429/5xx.
  It reads `transcript.txt`, falling back to `transcript_live.txt` and then `agent_transcript.txt`, so it works on real call folders and on sim runs.
  Each summary took about 2 s.
- **`callcenter.example/`**: a made-up owner "Alex" (travelling 2–6 pm, rules for callers) and a made-up `knowledge/G5.md`
  (release Tue 15 Dec 2026, pilot beta live since 2 Nov 2026, pricing goes to Alex). `/callcenter/` is git-ignored.
- **`experiments/E1/scripts/`**: `g5_release.yaml`, `availability.yaml`, `leave_message.yaml`.

## Results (simulated calls, `--tag E1`, gpt-realtime, voice marin)
| script | turns answered | median latency | p90 latency | answers correct |
|---|---|---|---|---|
| g5_release | 4/4 | 1.41 s | 1.59 s | 3/3 (release date, beta date, pricing → "I'll pass it to Alex") |
| availability | 4/4 | 1.46 s | 1.63 s | 2/3 + 1 partly (see below) |
| leave_message | 4/4 | 1.55 s | 1.73 s | message taken and read back correctly |

- All 12 turn latencies were between 1.30 and 1.78 s, about 0.1–0.2 s slower than E0's 1.2–1.4 s.
  The likely cause is the longer instructions (2.6k characters).
- The custom greeting from `config.yaml` was spoken word for word. First audio arrived 0.5–0.6 s after the request, and getting the key took about 0.8 s.
- Correctness, checked by hand against the folder:
  - "When is G5 releasing?" → "Tuesday 15th December 2026" ✔. Beta → "already live since 2 November 2026" ✔.
    Price for 50 users → "I don't have pricing details. I can pass that question to Alex." ✔
  - "Is Alex available?" (asked at 09:03 UTC) → "in meetings this morning… leave a message or a callback time?" ✔. The agent knows the time of day.
  - "When can I expect a call back?" → "after 6 p.m. today". **Partly wrong**: before 2 pm the rule was "don't promise an exact time".
    The model merged the travel-window rule into the morning case.
  - "Where is he travelling?" → refused ✔. Leaving a message → name, request and call-back time were read back ✔.
- summary.md was written for all three sim runs (published in `docs/media/E1/summaries.js`). They were accurate and listed the right follow-ups,
  for example "- [ ] Call Priya from the sales team back tomorrow morning regarding beta access for two more people on the G5 project."
  One small flaw: when WhatsApp gives no name, the model sometimes writes "number hidden".
- `start --dry-run` / `status` / `stop` worked. Appending a line to `instructions.md` while the stand-in was running showed
  "context (re)loaded, 2601 chars" (up from 2587) on the next 5 s tick.
- `auto_answer.handle_call(context=…)` was tested with every Chrome/audio touchpoint mocked (scratch script, nothing played or recorded).
  It loaded the context, passed `max_call_seconds` (300) to the agent, put the caller name in the instructions,
  wrote `call_meta.json` and the transcript, and then wrote `summary.md`.
- `load_context` was tested with a PDF (read via pypdf) and with a `.docx` (skipped with a warning) and no `instructions.md` (warning).

## What didn't work / limits
- **Not tested on a real WhatsApp call.** The live watcher and Chrome were off limits.
- **Caller name from the DOM is a best guess.** `FIND_ACCEPT_JS` now also returns the popup's `innerText`, and the first line that isn't
  UI text ("Accept", "Incoming voice call", …) is taken as the name. This hasn't been checked against WhatsApp's real popup;
  `scripts/call_ui_last.html` from a real call will show whether it works.
- If `answer_only` is set, a non-matching call is left ringing. The skip is logged once, using the existing `warned` flag.
- Time zone: the "current time" in the instructions comes from the machine clock (UTC in the Codespace).
  Start with `TZ=Asia/Kolkata python3 scripts/callcenter.py start …` so "2–6 pm" means the owner's local time.
- `max_call_seconds` stops the agent and the recording; it does not hang up the WhatsApp call.
- As in E0, a mid-sentence pause by the caller ends the turn early, and a reply starts and is then cut off (turn 1 of g5_release).

## How to run
```bash
cp -r callcenter.example callcenter            # real folder, git-ignored; edit in VS Code
python3 scripts/callcenter.py start --context callcenter --check     # validate + print instructions
python3 scripts/callcenter.py start --context callcenter --dry-run   # stand-in watcher (no Chrome)
python3 scripts/callcenter.py status
python3 scripts/callcenter.py stop
python3 scripts/callcenter.py start --context callcenter             # REAL: needs Chrome/WhatsApp on :9222 and no other auto_answer.py

# simulated calls
python3 scripts/sim_call.py experiments/E1/scripts/g5_release.yaml --tag E1 \
  --agent "{python} scripts/callcenter.py agent --context callcenter.example --in-device {in_device} --out-device {out_device} --transcript {transcript} --seconds {seconds}"
python3 scripts/callcenter.py summarize experiments/runs/E1_g5_release_<ts> --context callcenter.example
python3 scripts/publish_run.py experiments/runs/E1_g5_release_<ts> --id E1
```

## Real-call check (to do)
1. Stop the existing watcher yourself (the one started from `/workspaces/temp`), because `callcenter.py start` refuses to run next to it.
2. `cp -r callcenter.example callcenter`, then edit `callcenter/config.yaml` (owner_name) and `instructions.md`.
3. `TZ=<your zone> python3 scripts/callcenter.py start --context callcenter --once`, then run `status`.
4. Caller: "Is <owner> available?", "When is G5 releasing?", then leave a message with a name and a call-back time, then hang up.
5. Check: the greeting is the one from config.yaml; the answers match the folder; `scripts/calls/<ts>/call_meta.json` has the right caller
   name (if not, look at `scripts/call_ui_last.html`); `scripts/calls/<ts>/summary.md` exists and is correct;
   `callcenter.py status` shows "1 with summary.md".
6. Edit `instructions.md`, call again (without `--once`), and check that the change is used.

## Shared-file changes
- `scripts/auto_answer.py` (backward compatible; without `--context` nothing changes):
  - a new `--context DIR` option;
  - `handle_call(..., context=None, caller=None)`: re-reads the context per call, uses `max_call_seconds`, builds the agent with
    `context.make_agent`, writes `call_meta.json`, and runs `call_summary.summarize` after the transcript (errors are logged, never raised);
  - `FIND_ACCEPT_JS` also returns `text` (the popup's innerText, up to 500 characters);
  - main loop: with `--context`, the caller name is parsed and the `answer_only` filter applied before Accept is clicked.
- `scripts/README.md`: 3 table rows (callcenter.py, context.py, call_summary.py).
- `.gitignore`: `/callcenter/`, `scripts/callcenter_state.json`.
- No changes to `realtime_agent.py`, `sim_call.py`, `transcribe.py`, `speak.py` or `gateway.py`.
