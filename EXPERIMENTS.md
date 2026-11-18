# wa-virtmic experiments

Drop this file in the repo root. In Claude Code: `Do experiment E3 from EXPERIMENTS.md`.

## How to run them in parallel

- **Do E0 first.** Every other experiment uses its simulated caller, so they can be tested without asking a friend to call each time.
- One Codespace has one WhatsApp login and one set of PulseAudio devices. For parallel work, give each experiment its own **git worktree + branch** (`git worktree add ../wa-E3 -b exp/E3`) and its own Claude Code session in a separate terminal. Each experiment must use **its own uniquely named sinks** (`virtmic_E3`, `callout_E3`) for simulated tests. Only one experiment at a time does a real WhatsApp call.
- Alternatively, use one Codespace per experiment (watch your Codespaces core-hour quota).
- Ground rules for every experiment: unoptimized is fine; get it working end to end; write results (what worked, what didn't, latency numbers) into `experiments/<ID>/RESULTS.md`; don't break `main`.

---

## E0: Simulated caller and test harness (do this first)

```
Build a test harness so voice experiments can be tested without a human caller.
- scripts/sim_call.py: takes a script file (YAML: list of caller lines with optional pauses) and an agent command.
  It creates its own PulseAudio sinks (names suffixed with --tag, e.g. virtmic_E3 / callout_E3), runs the agent pointed at them
  (realtime_agent.py must accept --in-device/--out-device; add CLI flags if missing), "speaks" each caller line with TTS into
  the agent's input, waits for the agent to reply (VAD on the agent's output), and records both sides.
- Output to experiments/runs/<tag>_<ts>/: stereo wav, transcript of both sides (transcribe.py), and metrics.csv with, per turn:
  caller_end -> agent_first_audio latency, agent reply duration, and interruptions.
- Support barge-in tests: a line marked `interrupt: true` starts while the agent is still talking.
- Include 3 sample scripts: basic Q&A, interruption test, Hindi/Hinglish caller.
- Document in README. Verify by running all 3 scripts against the current realtime_agent.py.
```

## E1: "Call center" mode controlled from a folder (the lead's core use case)

```
Implement the lead's idea: I edit plain files in VS Code, run one command, and my WhatsApp starts answering as my call center.
- A context folder, e.g. callcenter/: instructions.md (free text like "I'm travelling 2-6 pm, tell callers I'll call back"),
  knowledge/ (any .md/.txt/.pdf about a project that people will call about), and config.yaml (voice, language, max call length, greeting).
- CLI: `python scripts/callcenter.py start --context ./callcenter` / `stop` / `status`. Start runs auto_answer with the realtime agent
  using instructions built from instructions.md + config. Editing instructions.md takes effect on the next call (reload per call).
- Phase 1: stuff small knowledge/ files directly into the session instructions. Phase 2 lives in E2.
- After each call, write calls/<ts>/summary.md: who called (WhatsApp name/number from the DOM if available), what they wanted,
  what the AI promised, and follow-ups for me.
- Test with E0: a caller asks "Is the owner available?" and "When is G5 releasing?" (put a fake G5 note in knowledge/).
```

## E2: "Hold on, let me check": tool calls into local files and agents

```
Give the realtime voice agent tools so it can look things up mid-call, like the lead's "hold on 2 minutes... based on all the documents
I've checked" idea.
- Add realtime function calling with tools: search_knowledge(query) (ripgrep + simple ranking over the context folder),
  read_file(path), and ask_agent(question), which runs a slower background agent (`claude -p` headless with the context folder
  as working dir, with a timeout) and returns its answer.
- While a slow tool runs, the voice agent must keep the caller engaged ("Give me a moment, I'm checking the documents") and then
  speak the answer when it arrives. Measure: time to filler, time to answer.
- Log every tool call and result into the call folder.
- Test with E0 using questions whose answers exist only deep inside knowledge/ files.
```

## E3: Model bake-off (speed, quality, Hindi, cost)

```
Compare voice backends with the E0 harness on the same 3 scripts:
- OpenAI gpt-realtime (current) vs the newest gpt-realtime snapshot available through our gateway (check which model names work;
  note that the older gpt-realtime snapshots are scheduled for retirement), and gpt-realtime-mini if available.
- Gemini Live (if a key is available; otherwise leave a stub and mark it as blocked).
- A cascade over plain HTTP via the LLM gateway: Silero VAD -> STT (local faster-whisper small, and gpt-4o-transcribe via the gateway)
  -> streaming chat completion -> sentence-by-sentence TTS (gateway gpt-4o-mini-tts and edge-tts). Handle 429 with Retry-After/backoff.
- Put all of them behind a VoiceBackend interface selected by the VOICE_BACKEND env var.
- Report a table: median/p90 latency, interruption handling, Hindi/Hinglish quality (transcribe the agent's output and judge it),
  approximate cost per minute (from published pricing; cite the source), and failures.
```

## E4: Google Meet agent "Maya" (listens, speaks only when addressed)

```
First, research existing open-source meeting bots (e.g. joinly, Attendee, meeto) and decide whether to reuse one or reuse our own
Chrome + PulseAudio stack. Write the decision with reasons in RESULTS.md before building.
Then build a Meet agent named "Maya":
- It joins a Meet URL in the noVNC Chrome as a separate Google account (I'll log in manually), mic = its own virtmic, speaker = its own sink.
- It listens silently and keeps a live transcript.
- It speaks only when addressed by name ("Maya, what do you think?") and stops immediately when someone talks over it.
- In the background it posts short suggestions in Meet chat ("Maybe consider X", "You seem stuck on Y"), at most one every few minutes.
- Test first with E0-style simulated audio, then in a real Meet with me.
```

## E5: "Call me and I'll play it": audio on demand

```
The lead's "I call and you play music / give me a podcast" idea, as a call mode:
- The caller asks for something ("play the latest team update", "give me a 2-minute podcast about <topic from knowledge/>").
- Mode A: play an existing audio file from media/ (use only our own or royalty-free audio). Voice controls: pause, next, stop, louder.
- Mode B: generate a short two-voice podcast script from the knowledge/ folder with the LLM, synthesize it with two TTS voices, and play it.
- The realtime agent stays available: if the caller speaks, it pauses playback and answers.
```

## E6: One-command setup for demos (so client partners can run it)

```
Make this runnable by a non-developer in one go:
- Move install.sh into the devcontainer (Dockerfile or postCreateCommand) so a rebuild doesn't need a manual install;
  pre-install Claude Code too. Add postStartCommand for audio_setup.sh.
- `make demo` (or a single script): starts audio, Chrome and auto_answer, prints the noVNC URL, and walks through the QR scan.
- Health check: `make doctor` checks PulseAudio devices, the Chrome CDP connection, WhatsApp login, API key and gateway reachability,
  with a clear fix for each failure.
- Write a separate WINDOWS.md path: WhatsApp Desktop + VB-Cable (two cables: one for the mic, one for the speaker) with the same agent code
  using sounddevice device names instead of PulseAudio. Untested on Windows is fine; mark it as such.
```

## Later / parked

- **The lead's own voice** (voice cloning via a cascade TTS that supports cloning): only with explicit consent, and with callers told it's an AI.
- **Outbound calls**: the agent places WhatsApp calls (reminders, follow-ups from E1 summaries).
- **Multiple simultaneous calls**: not possible with one WhatsApp session; needs several linked sessions or accounts.
