# E5 results: "Call me and I'll play it" (audio on demand)

**Status: DONE in simulation** (2026-11-18). Not yet tried on a real WhatsApp call. Site page: `docs/E5.html`.

## What was built
| File | What |
|---|---|
| `scripts/media_player.py` | `MediaPlayer`: decodes audio to 24 kHz mono PCM (ffmpeg) and writes 20 ms chunks to `pacat --device=<out>` paced at real time with only ~0.12 s queued, so **pause/stop act within ~0.1 s** without killing the stream. Play/pause/resume/next/stop/volume, a queue, and "growing" items (a podcast still being synthesized). |
| `scripts/podcast.py` | Mode B. LLM (`gpt-4.1-mini` via the gateway's chat completions, JSON mode) writes a two-host script from `knowledge/`; each line is voiced with gateway `gpt-4o-mini-tts` (host A `coral`, host B `ash`; edge-tts `Ava`/`Andrew` as fallback or `--engine edge`). `generate()` yields audio **line by line**, so playback starts after the first line. CLI prints timings. |
| `scripts/media_agent.py` | The call agent: `realtime_agent.Agent` + 7 function tools (`play_media(query)`, `pause_media`, `resume_media`, `next_track`, `stop_media`, `set_volume(up/down)`, `make_podcast(topic, minutes)`). Reads the context folder directly (`instructions.md`, `config.yaml`, `knowledge/`, `media/` + optional `media/catalog.yaml`). Harness-compatible CLI. Writes `media_events.jsonl` (timings), `podcast.mp3`, `podcast_script.json` next to `--transcript`. |
| `experiments/E5/context/` | Fictional test context ("Lumen Labs", "Project Nimbus"), media catalog. |
| `experiments/E5/make_media.py` | Generates the test media: a 41 s TTS "team update" and two synthesized music loops (45 s chords, 30 s arpeggio). Output mp3s are git-ignored (regenerate after cloning). No third-party audio. |
| `experiments/E5/scripts/*.yaml` | E0 scripts: `media_controls` (play → question over it → continue → next → louder → stop), `podcast` (1-min podcast → question mid-podcast → continue → stop). |

### Key behaviours
- **Pause on speech:** `on_event` sees `input_audio_buffer.speech_started` and pauses the player immediately (reason `caller`), and
  inserts a system note "(playback paused because the caller started speaking)" so the model knows. The model answers and asks
  "Shall I continue?"; `resume_media` continues from the same position. `set_volume` also resumes a caller-paused item.
- **No voice/media overlap:** tools return at once; the model says one short line ("Here's the team update"); a pending task waits
  until that follow-up response is `done` *and* its audio has played out (sum of audio-delta durations), and the caller is not
  speaking, then starts the media. If the caller talks in the meantime, the start is deferred.
- **Podcast streaming:** `make_podcast` returns `{"status": "generating", "eta_seconds": 10}` immediately (the model tells the
  caller "It'll take about ten seconds"), the episode starts playing as soon as line 1 is synthesized, later lines arrive faster
  than real time. When an item finishes, the agent asks if they want anything else.

## Results
Two published simulated calls (`docs/media/E5/`) plus one earlier run of each (same scripts). The harness `--agent` was
`{python} scripts/media_agent.py --context experiments/E5/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}`.

**Every command did the right thing**: 8/8 commands per run pair (play, continue, next, louder, stop; podcast, continue, stop), both
mid-playback questions answered correctly from knowledge ("Demo day is at 4 p.m.", "18 lakh rupees"), every barge-in paused the media.

| Step (time until the media reacts) | run 1 | run 2 |
|---|---|---|
| play_media: caller stops talking → media plays | 4.44 s | 4.59 s |
| resume ("continue") | 2.83 s | 3.02 s |
| next_track | 2.52 s | 3.22 s |
| set_volume(up) + resume | 5.16 s | 3.22 s |
| make_podcast: caller stops talking → podcast plays | 6.64 s | 6.97 s |
| **caller talks over media → media silent** (on the recordings) | **median 0.43 s** (12 barge-ins, 0.10–0.54 s) | |

"Caller stops talking" = the server's `speech_stopped` event (~0.5 s after the voice really ends). Media start = first chunk written.
Internally the pause happens 0.1 ms after `speech_started`; the 0.43 s is the realtime server's speech detection + network.
For comparison, the agent's own voice took ~1.5 s to stop after a barge-in in E0. Command → playback is dominated by the
model's spoken acknowledgement (reply latency 1.5–2 s + ~1.5 s of speech).

Podcast generation, 1 minute requested:
| run | LLM script | first line playable | all lines done | episode length |
|---|---|---|---|---|
| sim call (gateway TTS) | 3.7 s | 6.06 s | 15.1 s | 78 s |
| sim call, earlier (gateway TTS) | 4.06 s | 6.56 s | – | – |
| CLI, Nimbus (gateway TTS) | 3.97 s | 7.01 s | 17.1 s | 78 s |
| CLI, team update (gateway TTS, 110 wpm budget) | 4.06 s | 6.75 s | 14.3 s | 55 s |
| CLI, Nimbus (edge-tts) | 3.81 s | 6.28 s | 43.3 s | 61 s |

Gateway TTS (2 requests in parallel) synthesizes ~5× faster than real time; edge-tts ~1.4×. No 429s were hit.

Harness metrics (E0 latency of agent replies, includes acks): media_controls median 1.78/1.86 s; podcast 1.2/2.06 s.

## What didn't work / caveats
- "Play X" → media takes ~4.5 s, mostly the spoken "Here's X". Option: skip the ack or use a short chime (~2 s).
- "1-minute" podcasts came out 55–78 s; the LLM overshoots the word budget. Budget lowered from 155 → 110 words/min.
- A caller line with an internal pause ("Okay, thanks. Continue please.") becomes two turns, so `resume_media` was called twice (idempotent, harmless).
- Any caller sound pauses the media (coughs, "mm-hm"); no auto-resume on empty transcripts yet.
- If podcast TTS ever falls behind playback (e.g. edge-tts under load), the player waits silently for the next line.
- Speech-to-text in the harness transcripts writes some Indian-English caller lines in Urdu/Devanagari script and transcribes
  music as junk words (known E0 STT limit). The agent's own transcripts are correct.
- The harness counts media as "agent talking": scripts use `interrupt: true` + `after:` to speak during playback. No harness change was needed.

## How to run
```
python3 experiments/E5/make_media.py          # once: generate media (git-ignored)
AGENT="{python} scripts/media_agent.py --context experiments/E5/context --seconds {seconds} --in-device {in_device} --out-device {out_device} --transcript {transcript}"
python3 scripts/sim_call.py experiments/E5/scripts/media_controls.yaml --tag E5 --max-seconds 200 --agent "$AGENT"
python3 scripts/sim_call.py experiments/E5/scripts/podcast.yaml --tag E5 --max-seconds 200 --agent "$AGENT"
python3 scripts/podcast.py --knowledge experiments/E5/context/knowledge --topic "Project Nimbus" --minutes 1 --out /tmp/pod.mp3
```

## Shared-file changes
None. `realtime_agent.py`, `sim_call.py`, `speak.py`, `gateway.py`, `auto_answer.py`, `transcribe.py` are unchanged; E5 uses the
existing `Agent(tools, on_tool, on_event)` hooks and sets `realtime_agent.VOICE` from `config.yaml` at runtime.

## Real call (not done)
`auto_answer.py` starts `realtime_agent.Agent` directly, so it can't run `media_agent.py` yet without a small hook. Steps for a
real test are in the E5 final report ("READY FOR REAL CALL"); things to check: media loudness vs the voice (player volume 1.0 ≈
−20 LUFS speech / −6 dBFS peak music), and whether WhatsApp's echo cancellation or noise suppression mangles music.
