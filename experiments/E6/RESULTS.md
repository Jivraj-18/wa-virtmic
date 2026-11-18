# E6 results: one-command setup for demos

**Status: DONE** (2026-11-18), with two parts untested (container rebuild, Windows). Site page: `docs/E6.html`.

## What was built
- `.devcontainer/devcontainer.json`: `postCreateCommand: bash scripts/install.sh`, `postStartCommand: bash scripts/audio_setup.sh` (never fails
  the start; log in `/tmp/wa-audio-setup.log`), `postAttachCommand` prints a hint. `desktop-lite`, port 6080 and `--shm-size=1g` kept.
- `scripts/install.sh`: idempotent. Only installs missing apt packages (Chrome .deb only if `google-chrome` is absent, or `FORCE_CHROME=1`),
  only missing pip modules, and Claude Code via the official native installer (`curl -fsSL https://claude.ai/install.sh | bash`,
  npm `@anthropic-ai/claude-code` as fallback; `SKIP_CLAUDE=1` to skip).
- `Makefile`: `make demo`, `demo-dry`, `stop`, `doctor` (`ARGS=--redact|--offline`), `sim` (`TAG=`), `install`, `audio`, `url`.
- `scripts/demo.sh`: the same without make. Steps: software (runs install.sh if anything is missing) → `.env` (copies the example and
  stops if missing) → `audio_setup.sh` → noVNC check → `launch_chrome.sh` if CDP is down → `auto_answer.py` in the background
  (`scripts/auto_answer.log`, pid in `/tmp/wa-auto_answer.pid`; skipped if any python `scripts/auto_answer.py` already runs) → prints the
  noVNC URL (`CODESPACE_NAME` + `GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN`, fallback `http://localhost:6080/...`) → polls the WhatsApp
  login read-only and prints the next step on every state change. `--dry-run` changes nothing. `stop` kills only this checkout's
  `auto_answer.py`; `stop --chrome` also closes the CDP Chrome.
- `scripts/doctor.py`: read-only checks with PASS/WARN/FAIL and the exact fix. The WhatsApp check is a raw CDP `Runtime.evaluate` of a
  DOM probe (same selectors as `cdp_eval.py status`), no Playwright attach, no clicks/navigation. Network: TCP/TLS connect to the gateway,
  **one** realtime client-secret POST (nonce inside, via `realtime_agent.client_secret`), TCP connect to `api.openai.com:443`.
  `WA_CDP=` overrides the CDP URL (used for testing).
- `WINDOWS.md` + `scripts/win_agent.py`: WhatsApp Desktop + VB-CABLE (AI mic) + VB-CABLE A (caller capture). `win_agent.py` runs the
  unchanged `realtime_agent.Agent`, replacing its `parec`/`pacat` subprocesses with sounddevice streams (patches
  `asyncio.create_subprocess_exec` in its own process only). `--wait` opens the realtime session only once caller audio is heard.

## Tested here vs untested
| Piece | Status |
|---|---|
| `install.sh` re-run | tested: 2 s, "already installed" for apt, pip and Claude Code |
| `devcontainer.json` | JSONC validated (comments stripped, `json.loads`); commands run by hand. **Rebuild path untested end to end** (can't rebuild from inside) |
| `install.sh` "missing package" branches | not exercised (everything is installed; reinstalling was off limits) |
| `make doctor` | tested: 15/15 PASS. FAIL paths tested: CDP unreachable (`WA_CDP` on a closed port), `.env` missing (copy of scripts/), QR state (separate throwaway headless Chrome on :9333, killed afterwards) |
| `make demo` | `--dry-run` only (pass case live; fail case with `.env` missing in a copy). A real start was not run, to keep the live demo untouched |
| `--wait-login` | tested on the live tab (logged in, returns at once) and on the throwaway Chrome (loading → QR → timeout) |
| `make stop` | run for real (matches only this checkout's auto_answer: nothing to stop); `--chrome` dry-run only |
| `make sim TAG=E6` | tested: 4/4 turns, median 1.35 s, p90 1.39 s. Published to `docs/media/E6/basic_qa.*` |
| `win_agent.py` | Linux with a stub `sounddevice` (WAV in, raw out): real realtime session, greeting + correct answer ("Paris"), barge-in flush worked; `--wait` detection tested. **Untested on Windows / real VB-Cable** |

## Findings
- A GET on the gateway root timed out (10 s) once while the API worked fine, so doctor's reachability check is a TCP/TLS connect, and
  the client-secret POST is the real test.
- `pgrep -f scripts/auto_answer.py` also matches shells whose command line mentions the path; demo.sh and doctor only count python processes.
- The live watcher can run from another checkout; demo.sh treats any running `auto_answer.py` as "already running" so it never starts a second
  one that would race to click Accept.

## Doctor output (sanitized)
```
$ make doctor ARGS=--redact
wa-virtmic doctor (read-only)

PASS  binaries + modules       chrome, pulseaudio-utils, ffmpeg, python modules
PASS  claude code              installed
PASS  pulseaudio daemon        server 16.1
PASS  virtual audio devices    virtmic_sink, virtmic, callout_sink
PASS  default devices          source=virtmic sink=callout_sink
PASS  noVNC (port 6080)        listening -> https://<codespace-name>-6080.app.github.dev/vnc.html?autoconnect=true&resize=scale
PASS  X display                :1 present
PASS  /dev/shm                 1024 MB
PASS  chrome CDP (:9222)       Chrome/158.0.8127.36
PASS  whatsapp login           chat list visible
PASS  auto_answer.py           running (pid 108536)
PASS  scripts/.env             LLM_GATEWAY_BASE + LLM_GATEWAY_TOKEN set
PASS  gateway reachable        https connect in 0.45s
PASS  realtime client secret   obtained in 1.0s
PASS  realtime host reachable  api.openai.com:443

15 checks: 15 pass, 0 warn, 0 fail
Ready. Have someone WhatsApp voice-call this account; the AI answers. Logs: scripts/auto_answer.log
```

## How to run
```
cp scripts/.env.example scripts/.env   # OpenAI-compatible LLM gateway URL + token
make demo         # or: bash scripts/demo.sh
make doctor       # or: python3 scripts/doctor.py
make sim TAG=E6   # simulated call, no phone
make stop
```

## Shared-file changes
- `scripts/install.sh`: rewritten to be idempotent (same packages + Claude Code). Same command line, same end state.
- `.devcontainer/devcontainer.json`: added `postCreateCommand`, `postStartCommand`, `postAttachCommand`.
- `README.md`: added a "Quick start (Codespace)" section. `scripts/README.md`: new "Run order", 4 rows in the Files table.
- No changes to `realtime_agent.py`, `auto_answer.py`, `sim_call.py`, `gateway.py`, `audio_setup.sh`, `launch_chrome.sh`.
