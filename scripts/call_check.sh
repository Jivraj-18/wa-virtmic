#!/usr/bin/env bash
# Run while a WhatsApp call is CONNECTED in the noVNC Chrome.
#  1. ensure virtmic unmuted @100%
#  2. ensure Chrome records from virtmic and plays to callout_sink (move streams if not)
#  3. start a 10 s recording of callout_sink.monitor -> caller_test.wav
#  4. speak the test line into virtmic_sink
#  5. print RMS of the caller recording
set -uo pipefail
cd "$(dirname "$0")"
TEXT="${1:-Hello! This is an AI speaking through a virtual microphone. If you can hear me, please say yes.}"

pactl set-source-mute virtmic 0
pactl set-source-volume virtmic 100%
echo "== virtmic:"; pactl list sources | awk '/Name: virtmic$/{f=1} f&&/Mute:|Volume:/{print "  "$0} f&&/Base Volume/{exit}'

vid=$(pactl list short sources | awk '$2=="virtmic"{print $1}')
sid=$(pactl list short sinks   | awk '$2=="callout_sink"{print $1}')

echo "== Chrome source-outputs (mic streams):"
pactl list short source-outputs
for so in $(pactl list short source-outputs | awk '{print $1}'); do
  cur=$(pactl list short source-outputs | awk -v i="$so" '$1==i{print $2}')
  [[ "$cur" != "$vid" ]] && { echo "  moving source-output $so ($cur -> virtmic)"; pactl move-source-output "$so" virtmic; }
done
echo "== Chrome sink-inputs (playback streams):"
pactl list short sink-inputs
for si in $(pactl list short sink-inputs | awk '{print $1}'); do
  cur=$(pactl list short sink-inputs | awk -v i="$si" '$1==i{print $2}')
  [[ "$cur" != "$sid" ]] && { echo "  moving sink-input $si ($cur -> callout_sink)"; pactl move-sink-input "$si" callout_sink; }
done
echo "== after:"; pactl list short source-outputs; pactl list short sink-inputs
[[ -z "$(pactl list short source-outputs)" ]] && echo "WARNING: no source-output -> Chrome is NOT capturing any mic (permission denied / call not active?)"

timeout 10 parecord --device=callout_sink.monitor --file-format=wav --format=s16le --rate=48000 --channels=1 caller_test.wav &
rec=$!
echo "== speaking: $TEXT"
python3 speak.py "$TEXT"
wait $rec
python3 rms.py caller_test.wav
