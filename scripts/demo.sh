#!/usr/bin/env bash
# One command for the WhatsApp AI-voice demo (same as `make demo` / `make stop`).
#
#   bash scripts/demo.sh                 start audio, Chrome and auto_answer, print the noVNC URL, walk through the QR scan
#   bash scripts/demo.sh --dry-run       only check preconditions and print what it would do (starts/changes nothing)
#   bash scripts/demo.sh --no-wait       don't wait for the WhatsApp login
#   bash scripts/demo.sh stop            stop the auto_answer.py started from this checkout (Chrome keeps running)
#   bash scripts/demo.sh stop --chrome   ...and also close the demo Chrome (WhatsApp stays linked: the profile persists)
#
# Env: AA_ARGS="--mode greeting"   extra auto_answer.py arguments;  LOGIN_WAIT=600   seconds to wait for the QR scan
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$ROOT/scripts"
LOG="$S/auto_answer.log"
PIDFILE="${TMPDIR:-/tmp}/wa-auto_answer.pid"
PY="${PYTHON:-python3}"

cmd=start; DRY=0; WAIT=1; CHROME=0
for a in "$@"; do
  case "$a" in
    start|stop) cmd=$a ;;
    --dry-run|-n) DRY=1 ;;
    --no-wait) WAIT=0 ;;
    --chrome) CHROME=1 ;;
    -h|--help) sed -n '2,11p' "$0"; exit 0 ;;
    *) echo "unknown argument: $a (see --help)"; exit 2 ;;
  esac
done

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B= G= Y= R= N=; fi
step() { echo; echo "${B}== $*${N}"; }
ok()   { echo "  ${G}ok${N}    $*"; }
warn() { echo "  ${Y}warn${N}  $*"; }
bad()  { echo "  ${R}FAIL${N}  $*"; }
would(){ echo "  ${Y}dry-run${N} would: $*"; }
cdp_up() { curl -s -m 2 localhost:9222/json/version >/dev/null 2>&1; }
# auto_answer.py from any checkout (one watcher per Chrome is enough); python processes only, not shells mentioning it
aa_pids() { pgrep -af 'scripts/auto_answer\.py' | awk '$2 ~ /python/ {print $1}'; }

novnc_url() {
  if [ -n "${CODESPACE_NAME:-}" ] && [ -n "${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-}" ]; then
    echo "https://${CODESPACE_NAME}-6080.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN}/vnc.html?autoconnect=true&resize=scale"
  else
    echo "http://localhost:6080/vnc.html?autoconnect=true&resize=scale"
  fi
}

# ------------------------------------------------------------------------------------------- stop
if [ "$cmd" = stop ]; then
  step "Stopping auto_answer.py (this checkout: $S/auto_answer.py)"
  pids=""
  if [ -f "$PIDFILE" ] && ps -p "$(cat "$PIDFILE")" -o args= 2>/dev/null | grep -q "$S/auto_answer.py"; then
    pids=$(cat "$PIDFILE")
  fi
  pids="$pids $(pgrep -af "$S/auto_answer\.py" | awk '$2 ~ /python/ {print $1}')"
  pids=$(echo $pids | tr ' ' '\n' | sort -u | tr '\n' ' ')
  if [ -z "${pids// }" ]; then ok "not running"
  elif [ $DRY = 1 ]; then would "kill $pids"
  else kill $pids && ok "stopped pid(s) $pids"; rm -f "$PIDFILE"; fi
  if [ $CHROME = 1 ]; then
    step "Closing the demo Chrome (CDP :9222)"
    cpids=$(pgrep -f -- '--remote-debugging-port=9222' | head -1)
    if [ -z "$cpids" ]; then ok "not running"
    elif [ $DRY = 1 ]; then would "kill Chrome pid $cpids (profile is kept, WhatsApp stays linked)"
    else kill "$cpids" && ok "Chrome closed"; fi
  else
    echo "  Chrome left running (WhatsApp stays open). Use: bash scripts/demo.sh stop --chrome"
  fi
  exit 0
fi

# ------------------------------------------------------------------------------------------- start
[ $DRY = 1 ] && echo "${B}DRY RUN: nothing will be started or changed${N}"
fail=0

step "1/6 Software"
missing=""
for b in google-chrome pulseaudio pactl parec pacat paplay parecord ffmpeg curl; do
  command -v "$b" >/dev/null 2>&1 || missing="$missing $b"
done
for m in numpy playwright websockets yaml; do
  "$PY" -c "import $m" 2>/dev/null || missing="$missing py:$m"
done
if [ -z "$missing" ]; then ok "all binaries and python modules present"
elif [ $DRY = 1 ]; then warn "missing:$missing"; would "bash scripts/install.sh"
else warn "missing:$missing -> running install.sh"; bash "$S/install.sh" || { bad "install.sh failed"; exit 1; }; fi

step "2/6 LLM gateway settings (scripts/.env)"
if [ -f "$S/.env" ] && grep -qE '^LLM_GATEWAY_TOKEN=.+' "$S/.env" && grep -qE '^LLM_GATEWAY_BASE=.+' "$S/.env"; then
  ok "scripts/.env has LLM_GATEWAY_BASE and LLM_GATEWAY_TOKEN"
else
  bad "scripts/.env missing or incomplete"
  if [ $DRY = 1 ]; then [ -f "$S/.env" ] || would "cp scripts/.env.example scripts/.env"
  else [ -f "$S/.env" ] || cp "$S/.env.example" "$S/.env"; fi
  echo "  -> edit scripts/.env: set LLM_GATEWAY_BASE (your OpenAI-compatible gateway) and LLM_GATEWAY_TOKEN, then re-run."
  fail=1
  [ $DRY = 1 ] || exit 1
fi

step "3/6 Audio (PulseAudio virtual mic)"
if [ $DRY = 1 ]; then
  if pactl info >/dev/null 2>&1; then ok "PulseAudio running"; else warn "PulseAudio not running"; fi
  for d in "sinks virtmic_sink" "sources virtmic" "sinks callout_sink"; do
    set -- $d; pactl list short "$1" 2>/dev/null | awk '{print $2}' | grep -qx "$2" && ok "$2 exists" || warn "$2 missing"
  done
  would "bash scripts/audio_setup.sh   (idempotent)"
else
  bash "$S/audio_setup.sh" >/dev/null && ok "virtmic (mic) and callout_sink (speaker) ready" || { bad "audio_setup.sh failed"; exit 1; }
fi

step "4/6 Desktop (noVNC)"
URL=$(novnc_url)
if (exec 3<>/dev/tcp/127.0.0.1/6080) 2>/dev/null; then ok "noVNC listening on :6080"
else bad "noVNC is not listening on :6080 -> run: /usr/local/share/desktop-init.sh true  (or rebuild the container)"; fail=1; fi

step "5/6 Chrome with WhatsApp Web (CDP :9222)"
if cdp_up; then ok "Chrome already running ($(curl -s localhost:9222/json/version | sed -n 's/.*"Browser": "\(.*\)".*/\1/p'))"
elif [ $DRY = 1 ]; then would "bash scripts/launch_chrome.sh   (headed Chrome on :1, profile ~/.config/wa-chrome-profile)"
else bash "$S/launch_chrome.sh" | tail -1; cdp_up && ok "Chrome started" || { bad "Chrome did not start: rerun with CHROME_LOG=/tmp/chrome.log bash scripts/launch_chrome.sh and read that (capped at 5 MB)"; exit 1; }; fi

step "6/6 Call auto-answer + AI voice agent (auto_answer.py)"
running=$(aa_pids | tr '\n' ' ')
if [ -n "${running// }" ]; then ok "already running (pid $running) - not starting a second copy"
elif [ $DRY = 1 ]; then would "setsid nohup $PY -u scripts/auto_answer.py ${AA_ARGS:-} > scripts/auto_answer.log 2>&1 &"
else
  cd "$ROOT"
  # shellcheck disable=SC2086
  setsid nohup "$PY" -u "$S/auto_answer.py" ${AA_ARGS:-} >"$LOG" 2>&1 </dev/null &
  echo $! >"$PIDFILE"
  sleep 3
  if ps -p "$(cat "$PIDFILE")" >/dev/null; then ok "started (pid $(cat "$PIDFILE")), log: scripts/auto_answer.log"
  else bad "auto_answer.py exited: tail scripts/auto_answer.log"; tail -5 "$LOG"; exit 1; fi
fi

step "Open the desktop"
echo "  noVNC:     ${B}$URL${N}"
echo "  password:  vscode"
echo "  (Codespaces: or open the Ports tab and click the globe icon next to port 6080.)"

step "Link WhatsApp (first time only)"
if [ $DRY = 1 ]; then
  echo -n "  current state: "; "$PY" "$S/doctor.py" --wait-login 0 | tail -1 | cut -d' ' -f2-
elif [ $WAIT = 1 ] && cdp_up; then
  "$PY" "$S/doctor.py" --wait-login "${LOGIN_WAIT:-600}" | sed 's/^/  /' || fail=1
fi

step "Next"
echo "  1. Have someone WhatsApp voice-call this account (don't answer on the phone)."
echo "  2. The AI answers by itself; follow along: tail -f scripts/auto_answer.log"
echo "  3. Recordings + transcripts: scripts/calls/<timestamp>/"
echo "  Check everything: make doctor      Stop: make stop      Test without a phone: make sim"
[ $DRY = 1 ] && echo && echo "${B}DRY RUN finished${N} (preconditions $([ $fail = 0 ] && echo OK || echo 'NOT met'))"
exit $fail
