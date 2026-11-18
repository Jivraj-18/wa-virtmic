#!/usr/bin/env bash
# Verify the virtual mic: play a 440 Hz tone into virtmic_sink, record 3 s from virtmic, print RMS.
# Usage: test_virtmic.sh            (tone test)
#        test_virtmic.sh -- CMD...  (record while CMD plays into virtmic_sink, e.g. speak.py)
set -euo pipefail
cd "$(dirname "$0")"
out=virtmic_test.wav
timeout "${DUR:-3}" parecord --device=virtmic --file-format=wav --format=s16le --rate=48000 --channels=1 "$out" &
rec=$!
sleep 0.3
if [[ "${1:-}" == "--" ]]; then shift; "$@"
else ffmpeg -loglevel error -f lavfi -i "sine=frequency=440:duration=2" -f wav - | paplay --device=virtmic_sink
fi
wait $rec || true
python3 rms.py "$out"
