# Moving wa-virtmic from proot Debian to native Termux

For a Claude Code session running **directly in Termux** (not inside `proot-distro login debian`).

## Why

Today everything (Xvfb, PulseAudio, Chromium with WhatsApp Web, the Python agent) runs inside proot Debian. proot
traces every syscall of every process through ONE ptrace tracer, and that is the remaining cause of bad call audio:

- WhatsApp Web sends our mic through WebAudio, clocked by Chrome's PulseAudio output. Under proot that output starved:
  WebAudio ran at 0.4-0.9x real time and dropped mic audio (stutter at the other end). Partly fixed with bigger
  buffers (`PULSE_LATENCY_MSEC=150` + `--audio-buffer-size=2048` in `scripts/launch_chrome.sh`): far-end dropouts
  25 % -> 0.3 %.
- What is left: PulseAudio itself freezes for 0.25-1.0 s now and then (our `pacat` writes into virtmic_sink block;
  proot at ~70 % of a core, syscall worst 15-20 ms). Each freeze = a hole + a burst -> "jitter" heard by the callee
  (2026-11-23 call: dropouts 0.3 % in the first 2 min, 3.4 % later). Details: `.claude/skills/wa-diag/SKILL.md`.

Everything we need exists natively in Termux (checked 2026-11-23): `chromium` (158), `xorg-server-xvfb`,
`pulseaudio`, `python-playwright`, `nodejs`, `python-numpy`, `ffmpeg`, `python-cryptography`. Not packaged: `aiortc`
(our WebRTC link to GPT-Live) -> `pip install aiortc` (builds PyAV against Termux's ffmpeg; may need `clang`,
`make`, `pkg-config`, `libsrtp`, `libvpx`/`opus` headers).

## Rules (same as in the proot setup)

- The proot stack (started by `~/wa-answer.sh` in a Termux session) may be answering real calls. Do NOT stop it,
  restart it, or touch its devices until the native stack is proven better on the bench AND the user says so.
- Never call anyone without the user's go. Test calls go to "Praveen Uppari Roommate Balaji Gents Pg" ONLY after the
  user says his laptop + OBS are ready, and tell the user before each call.
- Never stop a call with SIGINT (corrupts the WAVs); click End call (`auto_answer.END_CALL_JS`).
- Judge audio with numbers + Gemini via the gateway (`scripts/audio_score.py --gemini`), never by transcription.
  Never conclude from one bench run: >= 3 runs per variant, one change at a time.
- Commit as `git -c user.name=Claude -c user.email=noreply@anthropic.com`. Secrets live in `scripts/.env`
  (never commit or print it). Record findings in the wa-diag / wa-ops skills.
- proot shares the network namespace with Termux: ports collide. The live proot stack uses CDP :9222 and the bench
  :9335; give the native test stack other ports (e.g. CDP :9232, bench :9345) and its own X display (e.g. :98).

## Plan

1. **Working copy**: `git clone /data/data/com.termux/files/usr/var/lib/proot-distro/installed-rootfs/debian/home/phone/wa-virtmic ~/wa-virtmic`
   (local clone, no GitHub auth), `git checkout termux-phone-setup`. Copy `scripts/.env` from the same rootfs path.
2. **Packages** (Termux): `pkg install x11-repo && pkg install chromium xorg-server-xvfb pulseaudio python-playwright
   nodejs python-numpy ffmpeg python-cryptography python-pip clang make pkg-config`, then `pip install aiortc`
   (fix build deps as needed). Check: `python -c "import aiortc, av, numpy, playwright"`.
3. **Make the scripts portable** (keep them working in proot too - detect, don't hard-code):
   - Chromium binary name/path (`chromium-browser` in Termux?), `--no-sandbox` if needed;
   - `/tmp` -> `${TMPDIR:-/tmp}`; Xvfb from Termux (no patched copy in `~/.local/opt/xvfb`);
   - PulseAudio: Termux's own daemon (`pulseaudio --start --exit-idle-time=-1`; null sinks + remap source via
     `scripts/audio_setup.sh`); `parec`/`pacat`/`parecord` come with it;
   - `pgrep`/`pkill` patterns anchored on `^/usr/lib/chromium/chromium` -> make them match the Termux binary;
   - Python: `python` vs `python3`, `#!/usr/bin/env python3` is fine in Termux after `termux-fix-shebang` if needed.
4. **Native bench** (no WhatsApp, own `bench_*` devices on the NATIVE PulseAudio):
   `python scripts/bench_call.py --worklet --burn 2 --pulse-latency 150 --chrome-args=--audio-buffer-size=2048`
   x3, plus `--rounds 3 --seconds 280` x2 (4-min calls; the proot PulseAudio froze 1.0 s at ~2:15 in one).
   Compare with proot (`python3 scripts/bench_table.py`; proot, same flags: media clock 0.983x (0.95-1.0),
   Chrome output gaps 0.6 %, `pacat write` longest up to 1031 ms in a 4-min run, CPU chrome ~200 %, proot ~70 %).
   Also try the native stack WITHOUT the buffer flags - they may be unnecessary outside proot (less latency).
   Report a before/after table to the user.
5. **Only if native is clearly better and the user agrees**: stop the proot supervisor (user stops `~/wa-answer.sh`),
   start the native stack. WhatsApp login: first try copying the proot Chrome profile
   (`.../installed-rootfs/debian/home/phone/.config/wa-chrome-profile`, with BOTH Chromes stopped) into the native
   profile dir; if WhatsApp shows the QR, re-link with `scripts/wa_link.py <number>` (link code, the user types it
   on their phone - ask them for the number). Write a native `~/wa-answer.sh` (wake lock, restart loop, no
   proot-distro) and update `scripts/termux/`, `docs/TERMUX.md`, the wa-ops skill.
6. **Confirm on a real call** (tell the user first; Praveen + OBS): `python scripts/call_diag.py` (Chrome audio I/O
   gaps < 2 %, pacat write < 250 ms), and score Praveen's OBS recording against our `ai.wav` with
   `scripts/audio_score.py --gemini` (see wa-diag for how the 2026-11-23 recordings were aligned).
7. Secondary, after the stutter: lower reply latency (~3 s ours, mostly GPT-Live turn-taking; the user is open to a
   different model), and the open issues: outgoing calls stuck on "Connecting...", incoming calls seen late
   ("no Accept button matched" in auto_answer.log).
