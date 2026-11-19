#!/data/data/com.termux/files/usr/bin/bash
# Run in TERMUX (not inside proot): keeps the wa-virtmic call answerer up for good.
#   bash ~/wa-answer.sh            # foreground, in its own Termux session (swipe in from the left -> NEW SESSION)
# Also works from Termux:Boot (copy to ~/.termux/boot/) so it comes back after a phone reboot.
# It holds a wake lock, runs answer_daemon.sh in its own proot-distro instance, and restarts it if it ever exits.
DISTRO=${DISTRO:-debian}; PUSER=${PUSER:-phone}; REPO=${REPO:-/home/phone/wa-virtmic}
LOG=$HOME/wa-answer.log
termux-wake-lock
while true; do
  [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 1000000 ] && tail -c 200000 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
  echo "$(date '+%F %T') starting supervisor" >> "$LOG"
  proot-distro login "$DISTRO" --user "$PUSER" -- bash -lc "cd $REPO && exec bash scripts/answer_daemon.sh run"
  echo "$(date '+%F %T') supervisor exited ($?) - restarting in 10s" >> "$LOG"
  sleep 10
done
