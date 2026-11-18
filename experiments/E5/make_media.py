#!/usr/bin/env python3
"""Generate the E5 test media (own TTS + synthesized music, no third-party audio) into context/media/.

  python3 experiments/E5/make_media.py [--context experiments/E5/context]

The outputs are git-ignored (*.mp3); re-run after a fresh clone.
"""
import argparse, subprocess, sys, tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SR = 24000

TEAM_UPDATE = """Hi everyone, here's the team update for week forty-six.
First, release one point two of the locker app shipped on Tuesday. It adds QR pickup codes, so residents can open a
locker by scanning their phone.
Second, the Pune pilot crossed eighteen hundred deliveries this week. Ninety-seven percent of parcels were picked up
within a day.
Third, hiring: we're looking for one firmware engineer, and interviews start next week.
A quick schedule change: Friday demo day has moved to four p.m.
And finally, a reminder to submit your travel claims by the twenty-fifth.
That's it for this week. Thanks, everyone!"""


def note(f, dur, amp=0.2, attack=0.02, release=0.3):
    t = np.arange(int(dur * SR)) / SR
    env = np.minimum(1, t / attack) * np.minimum(1, np.maximum(0, (dur - t) / release))
    return amp * env * (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t))


def hz(midi):
    return 440 * 2 ** ((midi - 69) / 12)


def focus_tones(seconds=45):
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
    out = []
    while sum(len(x) for x in out) < seconds * SR:
        for ch in chords:
            seg = sum(note(hz(m), 4.0, 0.12, attack=0.8, release=1.5) for m in ch)
            seg += note(hz(ch[0] - 12), 4.0, 0.15, attack=0.5, release=1.5)
            t = np.arange(len(seg)) / SR
            out.append(seg * (0.8 + 0.2 * np.sin(2 * np.pi * 0.25 * t)))
    return np.concatenate(out)[: seconds * SR]


def arpeggio(seconds=30):
    pattern = [60, 64, 67, 72, 67, 64] * 2 + [62, 65, 69, 74, 69, 65] * 2 + [59, 62, 67, 71, 67, 62] * 2
    step = 0.18
    out = []
    while sum(len(x) for x in out) < seconds * SR:
        for i, m in enumerate(pattern):
            n = note(hz(m), step, 0.25, attack=0.005, release=0.12)
            if i % 6 == 0:
                n = n + note(hz(m - 24), step, 0.25, attack=0.005, release=0.15)
            out.append(n)
    return np.concatenate(out)[: seconds * SR]


def save(sig, path):
    sig = sig / max(1e-9, np.abs(sig).max()) * 0.5  # about -6 dBFS peak
    pcm = (sig * 32767).astype(np.int16).tobytes()
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                    "-b:a", "48k", str(path)], input=pcm, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", default=str(ROOT / "experiments" / "E5" / "context"))
    a = ap.parse_args()
    media = Path(a.context) / "media"
    media.mkdir(parents=True, exist_ok=True)
    save(focus_tones(), media / "focus_tones.mp3")
    save(arpeggio(), media / "upbeat_arpeggio.mp3")
    from speak import synth_wav
    with tempfile.TemporaryDirectory() as d:
        w = synth_wav(TEAM_UPDATE.replace("\n", " "), f"{d}/u.wav", voice="sage")
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", w, "-af", "loudnorm=I=-20", "-ac", "1",
                        "-ar", "24000", "-b:a", "48k", str(media / "team_update_week46.mp3")], check=True)
    for p in sorted(media.glob("*.mp3")):
        print(p, p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
