#!/usr/bin/env bash
# Launch headed Chrome on the noVNC desktop, wired to PulseAudio, with a persistent profile
# (WhatsApp login survives restarts) and CDP on :9222 for Playwright.
#   CHROME_EXTRA_ARGS   extra flags appended as-is (space-separated), e.g. "--no-sandbox" under
#                       proot-distro on Termux, where Chrome's sandbox hits a syscall proot's ptrace-based
#                       emulation can't handle ("Trace/breakpoint trap"). Empty/unset elsewhere - no-op.
#   CHROME_LOG          optional file for Chrome's stderr (ERROR level and up), capped at CHROME_LOG_MAX_BYTES
#                       (default 5 MB) - use it only to debug a Chrome that won't start. Unset (default): Chrome's
#                       output is discarded. Nothing in wa-virtmic reads it; an unbounded chrome.log in the
#                       profile once grew to 50 GB and filled a phone.
#   CHROME_PULSE_LATENCY_MSEC (default 150) / CHROME_AUDIO_BUFFER_SIZE (default 2048): bigger PulseAudio buffers.
#                       WhatsApp Web's call audio (mic included) runs in WebAudio, clocked by Chrome's audio OUTPUT;
#                       with Chrome's default ~10 ms buffers that output starves under proot, WebAudio runs at
#                       0.35-0.9x real time and our mic audio is dropped (stutter at the other end). Bench
#                       (bench_call.py --worklet --burn 2, 3+ runs): media clock 0.61x -> 0.98x, output gaps 25 % -> 0.6 %.
#                       Set either to 0 to use Chrome's default.
set -euo pipefail
cd "$(dirname "$0")"
bash ./audio_setup.sh >/dev/null   # bash: native Termux has no /usr/bin/env without termux-exec
export DISPLAY="${DISPLAY:-:1}"
export PULSE_SERVER="unix:$(pactl info | sed -n 's/^Server String: //p')"
PROFILE="${CHROME_PROFILE:-$HOME/.config/wa-chrome-profile}"
mkdir -p "$PROFILE"
if curl -s localhost:9222/json/version >/dev/null; then echo "Chrome already running on :9222"; exit 0; fi
rm -f "$PROFILE/chrome.log"  # old unbounded log location - never written any more
free_mb=$(df -Pk "$PROFILE" | awk 'NR==2{print int($4/1024)}')   # -k: Termux's df has no -m
if [ "$free_mb" -lt $(( ${DISK_MIN_FREE_GB:-2} * 1000 )) ]; then
  echo "WARNING: only ${free_mb} MB free - Chrome log disabled; free up space before calls (recordings will be skipped)" >&2
  CHROME_LOG=""
fi
CHROME_ARGS=(--user-data-dir="$PROFILE" --remote-debugging-port=9222 --no-first-run --no-default-browser-check
             --disable-dev-shm-usage --start-maximized)
# shellcheck disable=SC2206
CHROME_ARGS+=(${CHROME_EXTRA_ARGS:-})
# Native Termux (no proot): the bigger buffers are not needed and make Chrome drop ~4 % of mic frames (bench,
# 2026-11-23: 6 runs with vs 3 without: mic frames dropped 4.2 % vs 0.00 %), so they default to off there.
if [ "$(uname -o)" = Android ]; then : "${CHROME_PULSE_LATENCY_MSEC:=0}" "${CHROME_AUDIO_BUFFER_SIZE:=0}"; fi
if [ "${CHROME_PULSE_LATENCY_MSEC:-150}" != 0 ]; then export PULSE_LATENCY_MSEC="${CHROME_PULSE_LATENCY_MSEC:-150}"; fi
if [ "${CHROME_AUDIO_BUFFER_SIZE:-2048}" != 0 ]; then CHROME_ARGS+=(--audio-buffer-size="${CHROME_AUDIO_BUFFER_SIZE:-2048}"); fi
if [ -n "${CHROME_LOG:-}" ]; then
  # awk keeps draining the pipe after the cap (so Chrome never sees a broken stderr) but stops writing.
  nohup google-chrome --log-level=2 "${CHROME_ARGS[@]}" https://web.whatsapp.com 2>&1 </dev/null \
    | awk -v max="${CHROME_LOG_MAX_BYTES:-5000000}" '{ n += length($0) + 1; if (n <= max) { print; fflush() } }' \
      >"$CHROME_LOG" &
else
  nohup google-chrome --log-level=3 "${CHROME_ARGS[@]}" https://web.whatsapp.com >/dev/null 2>&1 </dev/null &
fi
for _ in $(seq 40); do curl -s localhost:9222/json/version >/dev/null && break; sleep 0.5; done
curl -s localhost:9222/json/version | grep -E '"Browser"'
echo "Chrome started (PULSE_SERVER=$PULSE_SERVER, profile=$PROFILE)"
