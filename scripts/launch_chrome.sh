#!/usr/bin/env bash
# Launch headed Chrome on the noVNC desktop, wired to PulseAudio, with a persistent profile
# (WhatsApp login survives restarts) and CDP on :9222 for Playwright.
set -euo pipefail
cd "$(dirname "$0")"
./audio_setup.sh >/dev/null
export DISPLAY="${DISPLAY:-:1}"
export PULSE_SERVER="unix:$(pactl info | sed -n 's/^Server String: //p')"
PROFILE="${CHROME_PROFILE:-$HOME/.config/wa-chrome-profile}"
mkdir -p "$PROFILE"
if curl -s localhost:9222/json/version >/dev/null; then echo "Chrome already running on :9222"; exit 0; fi
nohup google-chrome \
  --user-data-dir="$PROFILE" \
  --remote-debugging-port=9222 \
  --no-first-run --no-default-browser-check \
  --disable-dev-shm-usage \
  --start-maximized \
  https://web.whatsapp.com >"$PROFILE/chrome.log" 2>&1 &
for _ in $(seq 40); do curl -s localhost:9222/json/version >/dev/null && break; sleep 0.5; done
curl -s localhost:9222/json/version | grep -E '"Browser"'
echo "Chrome started (PULSE_SERVER=$PULSE_SERVER, profile=$PROFILE)"
