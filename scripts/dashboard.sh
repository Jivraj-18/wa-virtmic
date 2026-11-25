#!/data/data/com.termux/files/usr/bin/bash
# Live phone-stack dashboard (scripts/dashboard.py) + a Cloudflare quick tunnel, kept alive by a small supervisor.
#
#   bash scripts/dashboard.sh start    # background, one instance (idempotent); prints the private link
#   bash scripts/dashboard.sh link     # print the current private link (it changes when the tunnel restarts)
#   bash scripts/dashboard.sh status
#   bash scripts/dashboard.sh stop
#   bash scripts/dashboard.sh run      # foreground supervisor (what start runs)
# Link file: ~/.config/nova/dashboard_link (600). Revoke all links: rm ~/.config/nova/dashboard_token, then restart.
# Needs: pkg install cloudflared.  Env: DASH_PORT (8790; the handoff page owns 8787).
set -uo pipefail
umask 077
S="$(cd "$(dirname "$0")" && pwd)"
PORT="${DASH_PORT:-8790}"
CONF="$HOME/.config/nova"
RUN="$HOME/.cache/dashboard"
LINK="$CONF/dashboard_link"
mkdir -p "$CONF" "$RUN"
export DASH_PORT="$PORT"

alive() { [ -f "$1" ] && kill -0 "$(cat "$1")" 2>/dev/null; }
log() { echo "$(date '+%F %T') $*" >>"$RUN/supervisor.log"; }

start_server() {
  python "$S/dashboard.py" --port "$PORT" >>"$RUN/server.log" 2>&1 &
  echo $! >"$RUN/server.pid"
}
start_tunnel() {
  : >"$RUN/tunnel.log"
  rm -f "$LINK"
  cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:$PORT" >"$RUN/tunnel.log" 2>&1 &
  echo $! >"$RUN/tunnel.pid"
  for _ in $(seq 40); do
    URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$RUN/tunnel.log" | grep -v '//api\.' | head -n 1 || true)"
    if [ -n "$URL" ]; then
      [ -f "$CONF/dashboard_token" ] || sleep 2
      echo "$URL/#t=$(cat "$CONF/dashboard_token")" >"$LINK"
      log "tunnel up: $URL"
      return
    fi
    sleep 1
  done
  log "tunnel gave no URL; see $RUN/tunnel.log"
}

case "${1:-start}" in
  run)
    command -v cloudflared >/dev/null || { echo "cloudflared is missing: pkg install cloudflared" >&2; exit 1; }
    echo $$ >"$RUN/supervisor.pid"
    trap 'kill "$(cat "$RUN/server.pid" 2>/dev/null)" "$(cat "$RUN/tunnel.pid" 2>/dev/null)" 2>/dev/null; rm -f "$LINK" "$RUN/supervisor.pid"; exit 0' TERM INT
    log "supervisor started (pid $$, port $PORT)"
    while :; do
      alive "$RUN/server.pid" || { log "starting server"; start_server; sleep 2; }
      alive "$RUN/tunnel.pid" || { log "starting tunnel"; start_tunnel; }
      [ "$(stat -c %s "$RUN/server.log" 2>/dev/null || echo 0)" -gt 1000000 ] && : >"$RUN/server.log"
      sleep 15
    done ;;
  start)
    if alive "$RUN/supervisor.pid"; then echo "already running"; else
      setsid nohup bash "$0" run >/dev/null 2>&1 </dev/null &
      for _ in $(seq 45); do [ -s "$LINK" ] && break; sleep 1; done
    fi
    [ -s "$LINK" ] && { echo "Dashboard is up. Private link (anyone with it can view):"; cat "$LINK"; } \
                   || { echo "no link yet; see $RUN/supervisor.log and $RUN/tunnel.log" >&2; exit 1; } ;;
  link) cat "$LINK" 2>/dev/null || { echo "not running" >&2; exit 1; } ;;
  status)
    for n in supervisor server tunnel; do alive "$RUN/$n.pid" && echo "$n: running (pid $(cat "$RUN/$n.pid"))" || echo "$n: NOT running"; done
    [ -s "$LINK" ] && echo "link: $(cat "$LINK")" ;;
  stop)
    alive "$RUN/supervisor.pid" && kill "$(cat "$RUN/supervisor.pid")"
    sleep 1
    for n in server tunnel; do alive "$RUN/$n.pid" && kill "$(cat "$RUN/$n.pid")"; rm -f "$RUN/$n.pid"; done
    rm -f "$LINK"; echo "stopped" ;;
  *) echo "usage: $0 start|stop|status|link|run"; exit 1 ;;
esac
