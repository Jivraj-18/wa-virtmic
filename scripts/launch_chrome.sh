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
set -euo pipefail
cd "$(dirname "$0")"
./audio_setup.sh >/dev/null
export DISPLAY="${DISPLAY:-:1}"
export PULSE_SERVER="unix:$(pactl info | sed -n 's/^Server String: //p')"
PROFILE="${CHROME_PROFILE:-$HOME/.config/wa-chrome-profile}"
mkdir -p "$PROFILE"
if curl -s localhost:9222/json/version >/dev/null; then echo "Chrome already running on :9222"; exit 0; fi
rm -f "$PROFILE/chrome.log"  # old unbounded log location - never written any more
free_mb=$(df -Pm "$PROFILE" | awk 'NR==2{print $4}')
if [ "$free_mb" -lt $(( ${DISK_MIN_FREE_GB:-2} * 1000 )) ]; then
  echo "WARNING: only ${free_mb} MB free - Chrome log disabled; free up space before calls (recordings will be skipped)" >&2
  CHROME_LOG=""
fi
CHROME_ARGS=(--user-data-dir="$PROFILE" --remote-debugging-port=9222 --no-first-run --no-default-browser-check
             --disable-dev-shm-usage --start-maximized)
# shellcheck disable=SC2206
CHROME_ARGS+=(${CHROME_EXTRA_ARGS:-})
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
