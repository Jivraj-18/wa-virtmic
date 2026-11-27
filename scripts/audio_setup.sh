#!/usr/bin/env bash
# Virtual audio for the WhatsApp call. Safe to re-run (idempotent).
#   virtmic_sink  : null sink we PLAY TTS into
#   virtmic       : remap source of virtmic_sink.monitor -> DEFAULT SOURCE (Chrome's mic)
#   callout_sink  : null sink -> DEFAULT SINK (call audio lands here; record callout_sink.monitor)
set -euo pipefail

# Any pactl call auto-spawns PulseAudio with the DEFAULT exit-idle-time (20 s): while no call plays it then quits,
# the virtual devices vanish and WhatsApp shows "Microphone not found" over the Accept button (2026-11-27).
CONF="${XDG_CONFIG_HOME:-$HOME/.config}/pulse/daemon.conf"
grep -qs '^exit-idle-time *= *-1' "$CONF" || { mkdir -p "$(dirname "$CONF")"; echo 'exit-idle-time = -1' >> "$CONF"; }

if ! pactl info >/dev/null 2>&1; then
  pulseaudio --kill 2>/dev/null || true
  pulseaudio --start --exit-idle-time=-1 --daemonize=yes
  for _ in $(seq 20); do pactl info >/dev/null 2>&1 && break; sleep 0.25; done
fi

have() { pactl list short "$1" | awk '{print $2}' | grep -qx "$2"; }

have sinks virtmic_sink || pactl load-module module-null-sink sink_name=virtmic_sink \
  sink_properties=device.description=VirtMic_Sink >/dev/null
have sources virtmic || pactl load-module module-remap-source master=virtmic_sink.monitor \
  source_name=virtmic source_properties=device.description=VirtMic >/dev/null
have sinks callout_sink || pactl load-module module-null-sink sink_name=callout_sink \
  sink_properties=device.description=CallOut_Sink >/dev/null

# Keep sources running while silent: otherwise parecord on virtmic gets no samples until audio plays,
# and ai.wav starts late (misaligned with caller.wav).
pactl unload-module module-suspend-on-idle 2>/dev/null || true

pactl set-default-source virtmic
pactl set-default-sink callout_sink
pactl set-source-mute virtmic 0
pactl set-source-volume virtmic 100%

echo "PULSE_SERVER=unix:$(pactl info | sed -n 's/^Server String: //p')"
pactl info | grep -E 'Default (Sink|Source)'
