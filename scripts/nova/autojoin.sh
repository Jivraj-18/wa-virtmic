#!/data/data/com.termux/files/usr/bin/bash
# Nova's autojoin service: keeps `nova.py autojoin` (Calendar watcher) alive, restarts it if it exits or its heartbeat
# goes stale, keeps Nova's Chrome (CDP 9333, display :97) and audio devices (maya_*) up between meetings.
# Never touches the WhatsApp answerer (CDP 9222, display :99, virtmic*).
#
#   bash scripts/nova/autojoin.sh start    # background, one instance only (idempotent)
#   bash scripts/nova/autojoin.sh stop     # stops the watcher; a meeting in progress continues (nova leave ends it)
#   bash scripts/nova/autojoin.sh status
#   bash scripts/nova/autojoin.sh run      # foreground (used by start / by a Termux session that owns it)
# Logs: ~/.cache/nova/autojoin.log (capped). Durable across Claude exits: start it from a Termux session, or
# `nohup bash scripts/nova/autojoin.sh run &` there (see the nova-meet skill).
set -uo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$S/../.." && pwd)"
RUN="$HOME/.cache/nova"; mkdir -p "$RUN"
LOG="$RUN/autojoin.log"
PIDFILE="$RUN/autojoin_supervisor.pid"
CHILD_PIDFILE="$RUN/autojoin_watcher.pid"
HB="$RUN/autojoin.heartbeat"
PY="${PY:-python}"
export PATH="$HOME/.local/bin:$PATH" MAYA_NAME="${MAYA_NAME:-Nova}" GOOGLE_WORKSPACE_CLI_KEYRING_BACKEND=file

log() { echo "$(date '+%F %T') $*" >>"$LOG"; }
alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
cap() { [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 1000000 ] && tail -c 200000 "$LOG" >"$LOG.tmp" && mv "$LOG.tmp" "$LOG"; }

case "${1:-status}" in
  start)
    if alive "$PIDFILE"; then echo "autojoin already running (pid $(cat "$PIDFILE"))"; exit 0; fi
    setsid nohup bash "$S/autojoin.sh" run </dev/null >/dev/null 2>&1 &
    sleep 1; echo "autojoin started (pid $(cat "$PIDFILE" 2>/dev/null)); log $LOG"; exit 0 ;;
  stop)
    alive "$PIDFILE" && kill "$(cat "$PIDFILE")" && echo "supervisor stopped"
    alive "$CHILD_PIDFILE" && kill "$(cat "$CHILD_PIDFILE")" && echo "watcher stopped"
    rm -f "$PIDFILE" "$CHILD_PIDFILE" "$HB"; exit 0 ;;
  status)
    if alive "$PIDFILE"; then echo "supervisor: running (pid $(cat "$PIDFILE"))"; else echo "supervisor: NOT running"; fi
    if alive "$CHILD_PIDFILE"; then echo "watcher: running (pid $(cat "$CHILD_PIDFILE"))"; else echo "watcher: NOT running"; fi
    [ -f "$HB" ] && echo "heartbeat: $(( $(date +%s) - $(stat -c %Y "$HB") ))s ago: $(cat "$HB")"
    tail -3 "$LOG" 2>/dev/null; exit 0 ;;
  run) ;;
  *) echo "usage: $0 start|stop|status|run"; exit 2 ;;
esac

if alive "$PIDFILE" && [ "$(cat "$PIDFILE")" != $$ ]; then echo "already running"; exit 0; fi
echo $$ >"$PIDFILE"
command -v termux-wake-lock >/dev/null && termux-wake-lock
CHILD=""
# Clean up only OUR OWN child and pid file: a stopping old supervisor once deleted the new one's pid file and killed
# its watcher (bash runs the trap only after `sleep` returns - hence `sleep & wait` below, which is interruptible).
trap '[ -n "$CHILD" ] && kill "$CHILD" 2>/dev/null; [ "$(cat "$PIDFILE" 2>/dev/null)" = $$ ] && rm -f "$PIDFILE"; exit 0' TERM INT
log "supervisor start (pid $$)"
n=0
while true; do
  cap
  in_meeting=$($PY - <<'EOF' 2>/dev/null
import json, os, pathlib
try:
    s = json.loads((pathlib.Path.home() / ".cache/nova/state.json").read_text())
    os.kill(int(s["pid"]), 0)
    print("yes" if s.get("phase") not in ("left", "failed") else "no")
except Exception:
    print("no")
EOF
)
  if [ "$in_meeting" = no ]; then
    # between meetings: keep Chrome + devices ready (both idempotent; the WhatsApp daemon may restart PulseAudio)
    (cd "$REPO" && $PY scripts/nova/nova.py chrome up >>"$LOG" 2>&1) || log "chrome up failed"
  fi
  if ! alive "$CHILD_PIDFILE"; then
    log "starting watcher"
    (cd "$REPO" && exec $PY -u scripts/nova/nova.py autojoin >>"$LOG" 2>&1) &
    CHILD=$!; echo $CHILD >"$CHILD_PIDFILE"
  elif [ -f "$HB" ] && [ $(( $(date +%s) - $(stat -c %Y "$HB") )) -gt 180 ]; then
    log "watcher heartbeat stale - restarting it"; kill "$(cat "$CHILD_PIDFILE")" 2>/dev/null; sleep 2
    kill -9 "$(cat "$CHILD_PIDFILE")" 2>/dev/null; rm -f "$CHILD_PIDFILE"; continue
  fi
  n=$((n + 1))
  if [ $((n % 360)) -eq 1 ]; then  # every ~6 h: is the Google session still alive?
    (cd "$REPO" && $PY scripts/nova/nova.py login-check 2>&1 | tail -1 | sed "s/^/$(date '+%F %T') login-check: /" >>"$LOG")
  fi
  [ "$(cat "$PIDFILE" 2>/dev/null)" = $$ ] || echo $$ >"$PIDFILE"   # self-heal the pid file
  sleep 60 & wait $!
done
