---
name: wa-diag
description: Diagnose a bad WhatsApp AI call with numbers - crackly/cutting-out voice, slow or missing replies, the AI talking late, calls that never hang up, the other person hanging up early. Use for "why was the call bad", "voice is cracky", "it took long to answer", "call didn't end", or after any call that went wrong.
---

# Diagnosing a call (numbers first, never listen or screenshot)

Every call (incoming via auto_answer.py, outgoing via wa_call.py) leaves `scripts/calls/<ts>/` with:
`ai.wav` (what WhatsApp received from the AI), `caller.wav`, `transcript_live.txt`, `call.log` (that call's log
lines), `sysstats.jsonl` (phone load every 2 s). Older calls may lack `call.log`/`sysstats.jsonl`.

```bash
python3 scripts/call_diag.py                  # latest call: verdict per metric + one-line diagnosis
python3 scripts/call_diag.py 20261120_060624  # a given call
python3 scripts/call_diag.py --last 8         # trend: one line per call
```

## Reproduce without a person: the call bench (do this BEFORE trying fixes on real calls)
```bash
python3 scripts/bench_call.py --runs 3        # ~80 s each: scripted caller + GPT-Live + headless Chrome on the mic
python3 scripts/bench_call.py --wa-load       # also do handle_call's in-process work against the real WA page (read-only)
python3 scripts/bench_call.py --no-chrome     # without the Chrome mic consumer
```
Own devices (`bench_*`, same formats as virtmic_sink/callout_sink), never the WhatsApp ones; output in
`scripts/bench/<ts>/` (git-ignored), same files as a real call, so `call_diag.py scripts/bench/<ts>` works.
Results vary run to run: **never conclude from one run**. Compare >= 3 runs before vs after one change
(pooled per-reply latency via `call_diag.turns`), and change one thing at a time.

## Metrics and what they mean
| metric (call_diag line) | good | bad | if bad, it is usually |
|---|---|---|---|
| voice cut-outs (% of AI speech that is 10 ms gaps of digital silence) | < 1 % | > 3 % = "cracky" | AI audio arriving in bursts or our playback starved; see the next rows |
| reply latency per turn (caller stops -> AI audio) | < 2 s | > 4 s | `first AI audio` late, or AI audio queued behind ("behind" lines) |
| AI audio from OpenAI: frames per 5 s (250 = real time), longest wait | >= 240, < 200 ms | < 200, > 500 ms | network jitter, or our asyncio loop starved (check agent_py CPU) |
| pacat write (into the call's mic) | < 100 ms | > 250 ms (the playback buffer) | PulseAudio/proot stalls |
| RTP packets lost from OpenAI | < 1 % | > 3 % | mobile network; try Wi-Fi or `--engine realtime` (TCP, no loss) |
| caller audio to OpenAI vs real time | < +1.5 s | > +3 s | parec backlog; the model hears the caller late |
| phone load: syscall worst / swap / CPU of proot, chrome_wa, agent_py | worst < 20 ms | > 100 ms | phone overloaded: close Maya's Chrome, other apps; proot is a single ptrace tracer for ALL Debian processes |

The live engine (`scripts/live_agent.py`) logs `live: audio-in 5s: ...` every 5 s and `live: rtp-in ...` every 10 s;
`live: AI audio N s behind - dropping silence to catch up` means a backlog was found and trimmed (normal once at
start-up; repeated = bursty arrival).

## Known causes and fixes (history)
- **AI talks 10+ s late, caller hangs up** (2026-11-20): aiortc's remote-audio queue is unbounded and pacat only
  drains in real time, so a stall left a permanent backlog. Fixed: queued silent frames are skipped while behind.
- **Cracky voice, 10-18 % cut-outs on GPT-Live calls** (2026-11-20): gaps 13-145 ms in bursts ~140 ms apart, with
  60 ms playback buffer. Raised to 250 ms (`LIVE_PLAY_LATENCY_MS`). Confirm on the next real call: cut-outs < 1 %.
  If still bad, compare `longest wait` (arrival) vs `pacat write` (output) to place the fault.
- **Crackle confirmed fixed, but 'You are lagging'** (2026-11-20, call to Hritik): cut-outs 0.2 %, 0 RTP loss, yet
  pacat writes froze 0.9 / 3.0 / 3.7 s. At that moment CPU of every process dropped together and the sampler itself
  ran late, and ai.wav came out 1.3 s shorter than caller.wav: PulseAudio/the phone froze, not our code or the
  network. Try: phone on charger, Termux battery optimisation off, wake lock held (`termux-wake-lock`). The agent
  recovers by skipping queued silence. If it keeps happening, consider running virtmic_sink at 48 kHz (it is 44.1 kHz,
  everything else 48 kHz) - needs a WhatsApp answerer restart, ask the user first.
- **AI voice queued up to ~1 s ("lagging")** (2026-11-20, found with the bench): asyncio's write buffer (64 KB) +
  the pipe to pacat (64 KB) could hold ~1.4 s of the AI's voice; "pacat write 650-850 ms" = that queue full, not
  silence. Shrunk both to 8 KB (`LIVE_OUT_QUEUE_BYTES`); queue now <= 160 ms (`out-queue max` in the log), backlog
  stays in aiortc's queue where silence is skipped. Bench, 25 vs 21 replies: mean 1.99 -> 1.61 s, worst 3.8 -> 2.7 s.
- **Long freezes (3-24 s) on real calls** were the phone: every process' CPU dropped together, sampler late,
  swap 3.4-3.7 GB, syscalls up to 529 ms. After Termux "Always allow in background" + closing apps + stopping the
  unused Termux:X11, the next real call had no stall (worst syscall 13 ms). The WhatsApp tab grows (~620 MB after 9 h,
  mostly swapped out) - a periodic idle reload of the page is a candidate fix (needs the user's OK).
- **Other phone sees "muted", hears nothing / only some sentences** (2026-11-23): WhatsApp Web muted our mic by
  itself mid-call (call UI dumps: "Mute microphone" at answer, "Unmute microphone" 18 s later; none of our code clicks
  it). handle_call now clicks Unmute whenever it appears and logs `WhatsApp had MUTED our mic (Ns into the call)` -
  grep for it. The call-active check also missed the muted state, so hang-ups weren't noticed; fixed.
- **Incoming caller heard ~25 s of silence and hung up** (2026-11-23): GPT-Live only gets "greet when the call
  connects" as an instruction and waited ~18 s, on top of a slow session start (6-7 s vs ~2 s). Incoming live calls
  now play the recorded greeting (`greeting.wav`) as soon as Chrome's mic is up; the model is told it was said.
- **Other side hears stutter / metallic / lost sentence starts while ai.wav is clean** (2026-11-23, Praveen call,
  Gemini 3/10): WhatsApp Web does NOT use Chrome's native WebRTC audio; it runs its own WASM VoIP stack
  (WAWebVoipWebWasmLoader, data channel), so our mic goes getUserMedia -> WebAudio -> WASM. WebAudio is clocked by
  Chrome's AUDIO OUTPUT; under proot that PulseAudio output (~10 ms buffers) starves, the AudioContext runs at
  0.4-0.9x real time and the mic audio that doesn't fit is dropped. Live evidence: caller.wav (Chrome's output)
  has 4-50 % gaps on every call (`call_diag` line "Chrome audio I/O gaps"; Praveen call 41 %).
  Bench repro: `bench_call.py --worklet` (WhatsApp-like AudioWorklet capture -> data channel -> far end process);
  native-WebRTC bench is clean even at 260 % CPU. Screening (1 run each, + one partial run of a 3x round with
  --burn 2), media clock / Chrome output gaps: default 0.42-0.69x / 10-67 %; PULSE_LATENCY_MSEC=150 0.92-0.99x /
  1.7-3 %; --audio-buffer-size=2048 0.92-0.98x / 0-3 %; latencyHint playback, mic 48 kHz, dither: no help;
  --no-apm 0.88x / 3 % (1 run). 3+ runs with --burn 2: default 0.61x / 25 %; PULSE_LATENCY 150: 0.94x / 2.3 %;
  buffer 2048: 0.93x / 1.3 %; BOTH: 0.98x / 0.6 % -> now the default in launch_chrome.sh (2026-11-23 16:57).
  CONFIRMED on a real call (20261123_170450, Praveen): Chrome audio I/O gaps 41 % -> 1.5 %, Praveen: "the quality
  is perfect", one brief "bit of jitter" later. Probe tip: wa_call.py reloads the page (send?phone=), and WhatsApp
  builds its audio graph at dial time, so `wa_audio_probe.py install` must run after the reload and BEFORE dialing.
  Laptop OBS recording (bench/evidence_20261123_praveen2, track0 = speaker): audio_score dropout 25.5 % -> 0.3 %
  (first 2 min) / 3.4 % (later), lost speech 22.8 % -> 0-1.2 %, LSD 29.5 -> 11-13 dB; Gemini 3 -> 7 (early) / 4
  (late: "static in pauses", 1 run). The later jitter was OUR side: 17:07:38-17:08:03 pacat writes blocked up to
  385 ms, ai.wav gaps 1 % -> 3 % (PulseAudio/proot stall class, not Chrome). Mouth-to-ear in the counting game
  ~4 s (laptop mic vs speaker word timestamps): ~3 s ours (mostly GPT-Live turn-taking), ~0.5-1 s WhatsApp legs.
  The "+0.66 s vs real time" caller line is a constant start offset, not a backlog.
  Older notes:
  `wa_audio_probe.py watch` (passive hook, `install` after each page load) shows ctx clock ~1.000x.
  Far-end scoring: `audio_score.py sent.wav heard.wav [--gemini]` (unreliable while media clock < 0.97: time-
  compressed audio defeats alignment; use the clock + gaps instead).
- **Ruled out (tested, don't re-test)**: Python GIL / other threads (loop lag <= 75 ms during freezes); PulseAudio
  null sink running 2 s blocks (sink at 10 ms during freezes); opening new streams / resampling / pactl listings
  (no write blocking in an isolated test); Chrome consuming the mic (bench with and without: same); network (RTP loss
  0-0.5 % on most calls).
- **Call recorded 18 min, only 6 spoken**: before 2026-11-20 nothing hung up after goodbyes. Now hangup.py +
  30 s digital-silence rule end the call; check `call.log` for `hang-up requested` / `digital silence`.
- **Turn-based engine (`--engine realtime`) had 0.4 % cut-outs** vs GPT-Live's 4-18 %: a fallback if live
  stays cracky.

## Rules
- The WhatsApp answerer may be in live use: ask the user before restarting it or anything in its stack (wa-ops).
  Outgoing calls (`wa_call.py`) start a fresh process and pick up code changes without any restart.
- To test audio changes without a call, use throwaway PulseAudio devices (never virtmic/callout_sink), e.g. load
  two null sinks `lt_in`/`lt_out`, run `LiveAgent(in_device="lt_in.monitor", out_device="lt_out")`, play a WAV
  into `lt_in` and record `lt_out.monitor`; `pactl suspend-sink lt_out 1` for N s simulates a stalled player.
