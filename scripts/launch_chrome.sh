#!/usr/bin/env bash
# Launch headed Chrome on the noVNC desktop, wired to PulseAudio, with a persistent profile
# (WhatsApp login survives restarts) and CDP on :9222 for Playwright.
#   CHROME_EXTRA_ARGS   extra flags appended as-is (space-separated), e.g. "--no-sandbox" under
#                       proot-distro on Termux, where Chrome's sandbox hits a syscall proot's ptrace-based
#                       emulation can't handle ("Trace/breakpoint trap"). Empty/unset elsewhere - no-op.
set -euo pipefail
cd "$(dirname "$0")"
./audio_setup.sh >/dev/null
export DISPLAY="${DISPLAY:-:1}"
export PULSE_SERVER="unix:$(pactl info | sed -n 's/^Server String: //p')"
PROFILE="${CHROME_PROFILE:-$HOME/.config/wa-chrome-profile}"
mkdir -p "$PROFILE"
if curl -s localhost:9222/json/version >/dev/null; then echo "Chrome already running on :9222"; exit 0; fi
# shellcheck disable=SC2086
nohup google-chrome \
  --user-data-dir="$PROFILE" \
  --remote-debugging-port=9222 \
  --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage \
  --start-maximized \
  ${CHROME_EXTRA_ARGS:-} \
  https://web.whatsapp.com >"$PROFILE/chrome.log" 2>&1 &
for _ in $(seq 40); do curl -s localhost:9222/json/version >/dev/null && break; sleep 0.5; done
curl -s localhost:9222/json/version | grep -E '"Browser"'
echo "Chrome started (PULSE_SERVER=$PULSE_SERVER, profile=$PROFILE)"
