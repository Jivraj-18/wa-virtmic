#!/data/data/com.termux/files/usr/bin/bash
# Native Termux (no proot) version of wa-answer.sh: keeps the wa-virtmic call answerer up for good.
#   cp scripts/termux/wa-answer-native.sh ~/wa-answer.sh && bash ~/wa-answer.sh   # in its own Termux session
# Also works from Termux:Boot (copy to ~/.termux/boot/). Holds a wake lock and restarts the supervisor if it exits.
# Do NOT run it while the proot answerer (wa-answer.sh) is up: both would use CDP :9222 and answer the same calls.
REPO=${REPO:-$HOME/wa-virtmic}
LOG=$HOME/wa-answer.log
export PATH="$HOME/.local/bin:$PATH"   # google-chrome -> chromium-browser symlink (install_native.sh)
termux-wake-lock
while true; do
  [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 1000000 ] && tail -c 200000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  echo "$(date '+%F %T') starting supervisor (native)" >> "$LOG"
  (cd "$REPO" && bash scripts/answer_daemon.sh run)
  echo "$(date '+%F %T') supervisor exited ($?) - restarting in 10s" >> "$LOG"
  sleep 10
done
