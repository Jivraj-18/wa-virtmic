"""Nova's single output stream (scripts/meet/live_meet.py Voice): never two voices at once.

    python tests/test_nova_voice.py
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import numpy as np
from meet.live_meet import Voice

N = 960 * 2                      # one 20 ms frame, 48 kHz mono s16
SIL = b"\0" * N
MODEL = np.full(960, 5000, np.int16).tobytes()   # the model talking
OWN = np.full(960, -7000, np.int16).tobytes()    # her report


def run(v, frames, t0):
    out = []
    for i, f in enumerate(frames):
        time.time = lambda i=i: t0 + i * 0.02     # 50 frames per second
        out.append(v.frame(f))
    return out


def test_report_replaces_model():
    real = time.time
    try:
        v = Voice(log=lambda *_: None)
        called = []
        v.on_turn = lambda: (called.append(1), "hold")[1]
        # model quiet 1 s, then starts a turn (= she was called on): its frames must be dropped
        out = run(v, [SIL] * 50 + [MODEL] * 20, 1000.0)
        assert called == [1] and all(o == b"" for o in out[50:]), "model turn while hand up must be held"
        v.on_turn = None
        v.say(OWN * 30)                               # report ready: 30 frames
        out = run(v, [MODEL] * 30 + [MODEL] * 10 + [SIL] * 60 + [MODEL] * 5, 1002.0)
        assert all(o == OWN for o in out[:30]), "report plays, alone"
        assert all(o == b"" for o in out[30:40]), "model's leftover turn after the report is dropped"
        assert out[-1] == MODEL, "after a quiet gap the model speaks again"
        # never both: every frame is exactly one of model / own / nothing
        for o in out:
            assert o in (b"", OWN, MODEL, SIL)
    finally:
        time.time = real


def test_pass_through():
    real = time.time
    try:
        v = Voice(log=lambda *_: None)
        out = run(v, [SIL] * 10 + [MODEL] * 10, 2000.0)
        assert out[10:] == [MODEL] * 10
    finally:
        time.time = real


if __name__ == "__main__":
    test_report_replaces_model(); test_pass_through(); print("OK")
