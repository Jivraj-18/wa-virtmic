---
name: wa-ops
description: Keep the WhatsApp AI call answerer running on the Android phone (Termux + proot Debian) - check/start/stop the service, log WhatsApp back in (link code, no QR), recover a frozen Chrome, disk/process gotchas, and pushing to GitHub with a PAT. Use when calls aren't answered, WhatsApp is logged out, something crashed, or the user asks to push.
---

# Running the answerer on the phone

Stack (all supervised by `scripts/answer_daemon.sh`): PulseAudio virtual devices -> Xvfb `:99` (invisible display,
in `~/.local/opt/xvfb`, patched to find xkbcomp via the `/tmp/xkb` symlink) -> Chromium with WhatsApp Web
(profile `~/.config/wa-chrome-profile`, CDP :9222) -> `scripts/auto_answer.py` (VOICE_ENGINE=live).

| Task | Command |
|---|---|
| Health | `bash scripts/answer_daemon.sh status` and `tail -5 scripts/answer_daemon.log` |
| Start / stop | `bash scripts/answer_daemon.sh start` / `stop` (stop leaves Chrome + Xvfb running) |
| Exactly one answerer? | `ps -eo pid,args \| grep -E '^ *[0-9]+ python3 -u .*auto_answer'` (must be 1 line) |
| Reload answerer code | `kill $(cat ~/.cache/wa-virtmic/auto_answer.pid)` — supervisor restarts it within ~20-40 s |
| Logged in? | `python3 scripts/cdp_eval.py status` |

**Survives Claude exiting only if started from Termux**: proot-distro runs `--kill-on-exit`, so anything started
from a proot shell (including this session) dies with it. The durable way: in a plain Termux session (not proot)
`bash ~/wa-answer.sh` (copy of `scripts/termux/wa-answer.sh`; keeps a wake lock and restarts the supervisor forever).

## WhatsApp logged out (`qr: True`)
Nobody can see or scan the QR, because Chrome is on the invisible display. Use a link code instead:
1. Ask the user for the WhatsApp account's number. Don't store it in the repo.
2. Run `python3 scripts/wa_link.py <number with country code>`. It prints `CODE: XXXX-XXXX`.
3. Tell the user: WhatsApp → ⋮ → Linked devices → Link a device → Link with phone number instead → type the code.
4. The code rotates every few minutes. If the user gets "Incorrect code", run `python3 scripts/wa_link.py --code`
   and give them the new code immediately.

## Gotchas (each cost real time once)
- **Never restart Chrome in quick succession or kill -9 it**: that logged WhatsApp out. The supervisor stops it
  gracefully (SIGTERM, up to 30 s). Restart Chrome only if CDP is hung (`curl -m 15 localhost:9222/json/version` fails).
- Termux:X11 (`:0`) is NOT used any more: Android pauses that app in the background and Chrome froze with it.
- `pgrep -f`/`pkill -f` patterns match your own shell command line: anchor them (`'^/usr/lib/chromium/chromium'`,
  `'^python3 -u .*auto_answer'`). Browser process name is `chromium`, not `chrome`.
- Don't `sleep` in foreground; wait with `timeout N tail -f /dev/null` or a bounded poll loop.
- Stale `SingletonLock/Cookie/Socket` in the profile block a relaunch — remove only when no chromium is running.
- Storage is limited (once a 50 GB chrome.log filled the phone): Chrome output goes to /dev/null, recordings are
  pruned to 1 GB (`scripts/diskguard.py`), and the logs are capped. Never add unbounded writes.
- Secrets: `scripts/.env` (LLM_GATEWAY_BASE / LLM_GATEWAY_TOKEN, gitignored). Never print it. A 401 from the gateway
  means the token is stale; ask the user for a new one.
- sudo/apt install is not allowed; extract .debs with `apt-get download` + `dpkg -x` into `~/.local/opt` if needed.
- Commit with `git -c user.name=Claude -c user.email=noreply@anthropic.com commit ...`. There is no git identity
  configured, and a rebase needs the same `-c` flags.

## Push to GitHub (user supplies a PAT; never store it)
```bash
A=$(mktemp); printf '#!/bin/sh\ncase "$1" in Username*) echo x-access-token;; *) echo "$GH_PAT";; esac\n' > $A; chmod 700 $A
GH_PAT='<token>' GIT_ASKPASS=$A GIT_TERMINAL_PROMPT=0 git -c credential.helper= push origin <branch>; rm -f $A
```
If the push is rejected, the remote has new commits (other sessions push too). Fetch the same way, then
`git -c user.name=Claude -c user.email=noreply@anthropic.com rebase origin/<branch>`, then push.
Before any push, scan the diff for tokens and real phone numbers.
