#!/usr/bin/env bash
# Unattended call answering on the phone (Termux + proot-distro): keeps PulseAudio, a virtual X display, Chromium
# (WhatsApp Web) and auto_answer.py alive, and restarts whatever dies or hangs. Safe to run overnight.
#
#   bash scripts/answer_daemon.sh start     # start in the background (idempotent: one instance only)
#   bash scripts/answer_daemon.sh stop      # stop the supervisor and auto_answer.py (Chrome + Xvfb keep running)
#   bash scripts/answer_daemon.sh status
#   tail -f scripts/answer_daemon.log
#
# For "never goes down", run it from Termux (outside proot) with scripts/termux/wa-answer.sh instead: proot-distro
# runs with --kill-on-exit, so anything started from an interactive proot shell (or a Claude session) dies when
# that shell exits. wa-answer.sh owns its own proot instance and restarts the supervisor if it ever exits.
#
# Why a virtual display: Chrome used to draw on Termux:X11, an Android app. When that app is in the background
# Android pauses it, and every Chrome call into X blocks - CDP stops answering and incoming calls are missed.
# Xvfb (no root: extracted into ~/.local/opt/xvfb, see XVFB_HOME) is a normal process Android doesn't pause.
#
# Env: VOICE_ENGINE (default live = full-duplex gpt-live-1), AA_ARGS (extra auto_answer.py args),
#      WA_DISPLAY (default :99), CHECK_SECS (default 20).
set -uo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
LOG="$S/answer_daemon.log"
AA_LOG="$S/auto_answer.log"
RUN="${XDG_RUNTIME_DIR:-$HOME/.cache}/wa-virtmic"; mkdir -p "$RUN"
PIDFILE="$RUN/answer_daemon.pid"
AA_PIDFILE="$RUN/auto_answer.pid"
HEARTBEAT="$RUN/auto_answer.heartbeat"
XVFB_HOME="${XVFB_HOME:-$HOME/.local/opt/xvfb}"
WA_DISPLAY="${WA_DISPLAY:-:99}"
CHECK_SECS="${CHECK_SECS:-20}"
PROFILE="${CHROME_PROFILE:-$HOME/.config/wa-chrome-profile}"
PY="${PY:-python3}"

log() { echo "$(date '+%F %T') $*" >>"$LOG"; }
alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
cap() { # keep a log file under $2 bytes without breaking writers that hold it open with O_APPEND
  local f=$1 max=$2
  [ -f "$f" ] && [ "$(stat -c %s "$f")" -gt "$max" ] || return 0
  tail -c $((max / 2)) "$f" >"$f.tmp" && cat "$f.tmp" >"$f"; rm -f "$f.tmp"
}
chrome_pids() { pgrep -f '^/usr/lib/chromium/chromium' ; }   # anchored: never matches our own shell
cdp_ok() { curl -s -m 15 -o /dev/null localhost:9222/json/version; }

case "${1:-start}" in
  stop)
    alive "$PIDFILE" && kill "$(cat "$PIDFILE")" && echo "supervisor stopped"
    alive "$AA_PIDFILE" && kill "$(cat "$AA_PIDFILE")" && echo "auto_answer.py stopped"
    rm -f "$PIDFILE" "$AA_PIDFILE"; exit 0 ;;
  status)
    alive "$PIDFILE" && echo "supervisor: running (pid $(cat "$PIDFILE"))" || echo "supervisor: NOT running"
    alive "$AA_PIDFILE" && echo "auto_answer: running (pid $(cat "$AA_PIDFILE"))" || echo "auto_answer: NOT running"
    cdp_ok && echo "chrome CDP: ok" || echo "chrome CDP: NOT responding"
    tail -5 "$LOG"; exit 0 ;;
  start)
    if alive "$PIDFILE"; then echo "already running (pid $(cat "$PIDFILE"))"; exit 0; fi
    setsid nohup bash "$0" run </dev/null >>"$LOG" 2>&1 &
    sleep 1; echo "started (pid $(cat "$PIDFILE" 2>/dev/null)); log: $LOG"; exit 0 ;;
  run) ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac

# ------------------------------------------------------------------------------------------------ supervisor
# Clean slate: a new supervisor takes over from any old one and (re)starts the whole stack as its OWN children,
# so nothing it depends on lives in another proot instance that may exit later.
if alive "$PIDFILE" && [ "$(cat "$PIDFILE")" != $$ ]; then
  log "taking over from supervisor pid $(cat "$PIDFILE")"; kill "$(cat "$PIDFILE")" 2>/dev/null; sleep 2
fi
echo $$ >"$PIDFILE"
alive "$AA_PIDFILE" && kill "$(cat "$AA_PIDFILE")" 2>/dev/null
pkill -f '^/usr/lib/chromium/chromium' 2>/dev/null
pkill -f "^$XVFB_HOME/usr/bin/Xvfb.patched $WA_DISPLAY" 2>/dev/null
pulseaudio --kill 2>/dev/null
sleep 3
pkill -9 -f '^/usr/lib/chromium/chromium' 2>/dev/null; rm -f "$AA_PIDFILE"
trap 'log "supervisor exiting"; rm -f "$PIDFILE"; exit 0' TERM INT
log "supervisor started (pid $$, display $WA_DISPLAY, engine ${VOICE_ENGINE:-live})"
[ -x /data/data/com.termux/files/usr/bin/termux-wake-lock ] && \
  /data/data/com.termux/files/usr/bin/termux-wake-lock >/dev/null 2>&1 && log "termux wake lock requested"

export CHROME_EXTRA_ARGS="${CHROME_EXTRA_ARGS:---no-sandbox}"
export VOICE_ENGINE="${VOICE_ENGINE:-live}"
export AA_HEARTBEAT="$HEARTBEAT"
cdp_fail=0; aa_fails=0; last_wa=""

ensure_audio() {
  if ! pactl info >/dev/null 2>&1; then
    log "pulseaudio not running - starting it (and restarting Chrome, whose audio was on the old server)"
    "$S/audio_setup.sh" >/dev/null 2>&1
    [ -n "$(chrome_pids)" ] && restart_chrome "pulseaudio restarted"
  fi
  pactl list short sinks 2>/dev/null | grep -q virtmic_sink || { log "virtual audio devices missing - creating"; "$S/audio_setup.sh" >/dev/null 2>&1; }
}

ensure_x() {
  DISPLAY=$WA_DISPLAY timeout 5 xdpyinfo >/dev/null 2>&1 && return 0
  log "X display $WA_DISPLAY not answering - (re)starting Xvfb"
  pkill -f "^$XVFB_HOME/usr/bin/Xvfb.patched $WA_DISPLAY" 2>/dev/null; sleep 1
  ln -sfn "$XVFB_HOME/usr/bin" /tmp/xkb   # Xvfb.patched looks for xkbcomp in /tmp/xkb (was /usr/bin, needs root)
  rm -f "/tmp/.X${WA_DISPLAY#:}-lock" "/tmp/.X11-unix/X${WA_DISPLAY#:}"
  LD_LIBRARY_PATH="$XVFB_HOME/usr/lib/aarch64-linux-gnu" setsid nohup "$XVFB_HOME/usr/bin/Xvfb.patched" "$WA_DISPLAY" \
    -screen 0 1280x800x24 -nolisten tcp </dev/null >/dev/null 2>&1 &
  for _ in $(seq 20); do DISPLAY=$WA_DISPLAY timeout 3 xdpyinfo >/dev/null 2>&1 && return 0; sleep 0.5; done
  log "ERROR: Xvfb did not come up"; return 1
}

kill_aa() { alive "$AA_PIDFILE" && { kill "$(cat "$AA_PIDFILE")"; sleep 2; kill -9 "$(cat "$AA_PIDFILE")" 2>/dev/null; }; rm -f "$AA_PIDFILE"; }

restart_chrome() {
  log "restarting Chrome ($*)"
  kill_aa
  local p; p=$(chrome_pids); [ -n "$p" ] && { kill $p 2>/dev/null; sleep 3; p=$(chrome_pids); [ -n "$p" ] && kill -9 $p 2>/dev/null; sleep 1; }
  rm -f "$PROFILE/SingletonLock" "$PROFILE/SingletonCookie" "$PROFILE/SingletonSocket"
  DISPLAY=$WA_DISPLAY timeout 60 bash "$S/launch_chrome.sh" >/dev/null 2>&1
  cdp_ok && log "Chrome up on $WA_DISPLAY" || log "ERROR: Chrome did not come up"
  cdp_fail=0
}

wa_state() { # loaded | qr | loading | ? - WhatsApp Web's own state, via CDP
  timeout 40 "$PY" "$S/cdp_eval.py" status 2>/dev/null | grep -oE "'(qr|loading|chatList)': True" | head -1
}

start_aa() {
  cap "$AA_LOG" 5000000
  touch "$HEARTBEAT"
  ( cd "$S/.." && setsid nohup "$PY" -u "$S/auto_answer.py" ${AA_ARGS:-} >>"$AA_LOG" 2>&1 </dev/null & echo $! >"$AA_PIDFILE" )
  log "auto_answer.py started (pid $(cat "$AA_PIDFILE"), engine $VOICE_ENGINE)"
}

while true; do
  cap "$LOG" 2000000; cap "$AA_LOG" 5000000
  ensure_audio
  ensure_x
  if [ -z "$(chrome_pids)" ]; then restart_chrome "not running"
  elif ! cdp_ok; then
    cdp_fail=$((cdp_fail + 1)); log "Chrome CDP not responding ($cdp_fail/3)"
    [ $cdp_fail -ge 3 ] && restart_chrome "CDP hung for ~$((3 * (CHECK_SECS + 15)))s"
  else cdp_fail=0; fi

  if cdp_ok; then
    if ! alive "$AA_PIDFILE"; then
      [ -f "$AA_PIDFILE" ] && { aa_fails=$((aa_fails + 1)); log "auto_answer.py died (#$aa_fails): $(tail -2 "$AA_LOG" | tr '\n' ' ' | cut -c1-300)"; }
      [ $aa_fails -ge 3 ] && sleep $((aa_fails > 10 ? 300 : 30 * aa_fails))   # back off if it keeps crashing (network down?)
      start_aa
    elif [ $(( $(date +%s) - $(stat -c %Y "$HEARTBEAT" 2>/dev/null || echo 0) )) -gt 900 ]; then
      log "auto_answer.py heartbeat stale >15 min - restarting it"; kill_aa
    else
      [ $(( $(date +%s) - $(stat -c %Y "$HEARTBEAT") )) -lt 5 ] && aa_fails=0
    fi
    # Every ~5 min, note whether WhatsApp is still logged in (a QR screen needs a human; we can only report it).
    if [ $(( $(date +%s) / 300 )) != "${last_check:-}" ]; then
      last_check=$(( $(date +%s) / 300 )); st=$(wa_state)
      [ "$st" != "$last_wa" ] && log "WhatsApp state: ${st:-unknown}"; last_wa=$st
    fi
  fi
  sleep "$CHECK_SECS"
done
