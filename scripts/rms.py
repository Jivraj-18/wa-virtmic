#!/usr/bin/env python3
"""Print RMS (dBFS) of a 16-bit WAV file. Usage: rms.py file.wav"""
import sys, wave, numpy as np
with wave.open(sys.argv[1]) as w:
    a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float64)
rms = float(np.sqrt(np.mean(a**2))) if a.size else 0.0
db = 20*np.log10(rms/32768) if rms > 0 else float("-inf")
print(f"{sys.argv[1]}: samples={a.size} RMS={rms:.1f} ({db:.1f} dBFS) -> {'SILENT' if rms < 30 else 'AUDIO PRESENT'}")
