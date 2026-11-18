# E0 results: simulated caller and test harness

**Status: DONE** (2026-11-18). Site page: `docs/E0.html`.

## What was built
- `scripts/sim_call.py`: a scripted TTS caller (edge-tts) that creates its own sinks (`virtmic_<tag>`, `callout_<tag>`) and runs any
  agent command against them. It waits for replies with an energy VAD on the agent's output, supports `interrupt: true` barge-in lines,
  records both sides, and writes wavs, transcript, `metrics.csv` and `summary.json` to `experiments/runs/<tag>_<script>_<ts>/`.
- `realtime_agent.py` now takes `--in-device`, `--out-device` and `--instructions-file`.
- `scripts/publish_run.py`: turns a sim run into a ≤60 s mp3 plus a transcript/metrics JS file for `docs/`.
- Sample scripts in `experiments/E0/scripts/`: `basic_qa.yaml`, `interruption.yaml`, `hinglish.yaml`.

## Results (gpt-realtime, server VAD, 500 ms silence)
| script | turns answered | median latency | p90 latency | barge-in: agent stopped after |
|---|---|---|---|---|
| basic_qa | 4/4 | 1.38 s | 1.49 s | n/a |
| interruption | 4/4 | 1.22 s | 1.40 s | 1.54 s |
| hinglish | 4/4 | 1.17 s | 1.23 s | n/a |

Latency is measured from the end of the caller's voice to the first audible agent audio, on the recorded tracks.

## Findings
- Works end to end. Every caller turn got a relevant spoken answer, and the agent switched to Hindi when asked in Hindi.
- **The earlier figure of "0.3–0.6 s" was wrong as an end-to-end number.** It measured only from the reply request to the first audio delta.
  Real end-to-end latency is about 1.2–1.4 s, including 500 ms of end-of-turn silence detection plus network and generation time.
- Barge-in works but is slow: about 1.5 s from the caller starting to talk until the agent goes quiet.
- Natural pauses inside a caller's sentence end the turn early, so the agent starts a reply that gets cut off.
- Once, the agent switched to Hindi mid-story after a misheard caller phrase.
- Speech-to-text writes some short Hindi phrases in Urdu script (an STT limit). The agent's own text log is correct Devanagari.

## Harness gotchas (fixed)
- `parec` can drop about 1 s of samples early in a run. All timing uses each track's own sample clock. The caller's speech start and end are
  found in the caller track and mapped onto the agent track. Wall-clock times are never mixed with audio times.
- `module-suspend-on-idle` must be unloaded, otherwise silent sinks pause and tracks lose alignment.
- edge-tts occasionally fails, so the harness retries with backoff.

## Next
- Tune turn detection (silence 700–900 ms or semantic VAD) and compare in E3.
- Pin the reply language unless the caller clearly switches.
