#!/usr/bin/env bash
# RAM / CPU / disk snapshot, to compare the phone "before" vs "after" running the Termux/proot-distro
# stack (see docs/TERMUX.md). Works the same inside Termux or inside a proot-distro login - /proc is
# the real kernel's, not virtualized by proot, so readings are consistent either way.
#
#   bash scripts/measure_resources.sh before     # run once, before installing anything
#   ...set up proot-distro, Debian, chromium, pulseaudio, Chrome, demo.sh...
#   bash scripts/measure_resources.sh after       # run once everything is up
#   bash scripts/measure_resources.sh diff        # unified diff of the two snapshots
#
# Snapshots are plain text under ~/wa-virtmic-metrics/<label>.txt (METRICS_DIR to change).
set -euo pipefail
DIR="${METRICS_DIR:-$HOME/wa-virtmic-metrics}"
mkdir -p "$DIR"
label="${1:-snapshot}"

if [ "$label" = diff ]; then
  b="$DIR/before.txt"; a="$DIR/after.txt"
  [ -f "$b" ] && [ -f "$a" ] || { echo "need both $b and $a - run 'before' and 'after' first" >&2; exit 1; }
  diff -u "$b" "$a" || true
  exit 0
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

{
  echo "# wa-virtmic resource snapshot: $label @ $(date -u +%FT%TZ)"
  echo
  echo "## memory (/proc/meminfo)"
  awk '/^(MemTotal|MemFree|MemAvailable|SwapTotal|SwapFree):/{printf "%-16s %8.1f MB\n", $1, $2/1024}' /proc/meminfo
  echo
  echo "## cpu load (/proc/loadavg) and core count"
  cat /proc/loadavg
  echo "cores: $(nproc 2>/dev/null || echo '?')"
  echo
  echo "## top 15 processes by RSS"
  if command -v ps >/dev/null 2>&1; then
    { ps -eo pid,comm,%cpu,%mem,rss --sort=-rss 2>/dev/null || ps aux 2>/dev/null | awk '{print $2,$11,$3,$4,$6}'; } | head -16
  fi
  echo
  echo "## disk: df -h"
  df -h "$HOME" / 2>/dev/null || df -h "$HOME" 2>/dev/null
  echo
  echo "## this repo checkout"
  du -sh "$ROOT" 2>/dev/null
  echo
  echo "## proot-distro rootfs(es) (only visible from Termux's own shell, not from inside a distro login)"
  for d in "${PREFIX:-}"/var/lib/proot-distro/installed-rootfs/*; do
    [ -d "$d" ] && du -sh "$d" 2>/dev/null
  done
  echo
  echo "## wake lock / battery (Termux only)"
  command -v termux-wake-lock >/dev/null 2>&1 && echo "termux-wake-lock available" || echo "termux-api not installed (optional)"
} | tee "$DIR/$label.txt"

echo
echo "saved: $DIR/$label.txt"
[ -f "$DIR/before.txt" ] && [ "$label" = after ] && echo "compare with: bash $0 diff"
