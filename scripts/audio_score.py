#!/usr/bin/env python3
"""Score what the far end HEARD against what we SENT (numbers, plus an optional Gemini rating).

    python3 scripts/audio_score.py sent.wav heard.wav            # numbers
    python3 scripts/audio_score.py sent.wav heard.wav --gemini   # + Gemini 1-10 rating (gateway, ~30-90 s)
    python3 scripts/audio_score.py scripts/bench/<ts>            # a bench run: ai.wav vs heard.wav

Both files are decoded to 16 kHz mono (ffmpeg) and aligned per 4 s window (the far end's jitter buffer
stretches time), so they need not be pre-aligned. Only the part of `sent` that overlaps `heard` is scored.

Metrics (speech = 10 ms frames where sent is above -45 dBFS):
  gain       heard vs sent level in speech (dB, median). Real call: +6..+10 dB = WhatsApp's AGC boost.
  dropout    % of speech frames where heard is >15 dB under sent (after gain): the stutter / missing slices.
  lost       seconds (and %) of speech in dropout runs >= 100 ms: missing words / sentence starts.
  onset      median ms of each sentence start (after >= 0.5 s silence) lost before heard catches up.
  clip       % of heard samples at |x| >= 0.98 full scale.
  noise      heard level where sent is digital silence, dB under heard speech (bigger = cleaner).
  hf         3-7 kHz energy relative to 0.3-3 kHz, heard minus sent (dB; negative = muffled).
  lsd        log-spectral distance in speech (dB; 0 = identical; robotic/metallic/PLC raise it).
"""
import argparse, base64, json, re, subprocess, sys, urllib.request
from pathlib import Path

import numpy as np

SR = 16000
HOP = 160          # 10 ms


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<i2").astype(np.float32) / 32768


def clip_pct(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    x = np.abs(np.frombuffer(raw, "<i2").astype(np.int32))
    return 100 * float(np.mean(x >= 32112)) if len(x) else 0.0


def env_db(x):
    n = len(x) // HOP
    f = x[:n * HOP].reshape(n, HOP)
    return 10 * np.log10(np.mean(f * f, axis=1) + 1e-12)


def best_lag(a, b, lo, hi):
    """lag (frames) maximising corr of a[i] with b[i+lag], over at least half of the shorter signal."""
    best, bl = -2.0, 0
    for lag in range(lo, hi + 1):
        i0, i1 = max(0, -lag), min(len(a), len(b) - lag)
        if i1 - i0 < max(50, min(len(a), len(b)) // 2):
            continue
        x, y = a[i0:i1], b[i0 + lag:i1 + lag]
        if x.std() < 1e-6 or y.std() < 1e-6:
            continue
        c = float(np.corrcoef(x, y)[0, 1])
        if c > best:
            best, bl = c, lag
    return bl, best


def align(s, h):
    """Return heard shifted onto sent's timeline per 4 s window (envelope correlation at 2.5 ms; the far end's
    jitter buffer changes the delay during a call) and a mask of samples that have a heard counterpart."""
    def env(x, hop=40):
        n = len(x) // hop
        f = x[:n * hop].reshape(n, hop)
        return np.maximum(10 * np.log10(np.mean(f * f, axis=1) + 1e-12), -70)
    es, eh = env(s), env(h)

    def corr(a, b0):
        if b0 < 0 or b0 + len(a) > len(eh):
            return -2.0
        b = eh[b0:b0 + len(a)]
        if a.std() < 1e-3 or b.std() < 1e-3:
            return -2.0
        return float(np.corrcoef(a, b)[0, 1])
    # global lag on 25 ms envelopes, any offset
    c, g = best_lag(es[::10], eh[::10], -len(es) // 10, len(eh) // 10)[::-1]
    g *= 10
    out, valid = np.zeros_like(s), np.zeros(len(s), bool)
    W = 1600   # 4 s
    for w0 in range(0, len(es), W):
        a = es[w0:w0 + W]
        lag = g
        if a.max() > -45:
            cands = [(corr(a, w0 + g + d), g + d) for d in range(-60, 61)]   # +-150 ms around the last lag
            c, l2 = max(cands)
            if c > 0.3:
                lag = l2
        x0, x1 = w0 * 40, min(len(s), (w0 + W) * 40)
        y0 = x0 + lag * 40
        if y0 < 0 or y0 + (x1 - x0) > len(h):
            continue
        out[x0:x1] = h[y0:y0 + x1 - x0]
        valid[x0:x1] = True
        g = lag
    return out, valid


def spec(x):
    n = len(x) // HOP - 3
    idx = np.arange(512)[None, :] + HOP * np.arange(n)[:, None]
    fr = x[idx] * np.hanning(512)
    return np.abs(np.fft.rfft(fr, axis=1)) ** 2   # (frames, 257), 31.25 Hz bins


def score(sent, heard):
    s, h0 = load(sent), load(heard)
    h, valid = align(s, h0)
    es, eh = env_db(s), env_db(h)
    n = min(len(es), len(eh))
    vf = valid[:n * HOP].reshape(n, HOP).all(axis=1)
    es, eh = es[:n], eh[:n]
    speech = (es > -45) & vf
    silence = (es < -80) & vf
    if speech.sum() < 100:
        return {"error": f"only {speech.sum() * 10} ms of overlapping speech"}
    # tolerate +-30 ms of residual misalignment: compare with the loudest heard frame nearby
    ehm = np.max(np.stack([np.roll(eh, k) for k in range(-3, 4)]), axis=0)
    gain = float(np.median(eh[speech] - es[speech]))
    d = ehm - es - gain
    drop = speech & (d < -15)
    runs, lost, i = [], 0, 0
    while i < n:
        if drop[i]:
            j = i
            while j < n and (drop[j] or not speech[j]) and j - i < 10_000:
                j += 1
            k = int(drop[i:j].sum())
            if j - i >= 10:
                lost += k
            i = j
        else:
            i += 1
    onsets = []
    for i in range(50, n):
        if speech[i] and not (es[i - 50:i] > -45).any() and vf[i - 50:i].all():
            k = 0
            while i + k < n and k < 200 and (d[i + k] < -10 or not speech[i + k]):
                k += 1
            onsets.append(k * 10)
    spk_lvl = float(np.median(eh[speech]))
    noise = float(np.median(eh[silence])) if silence.sum() > 50 else float("nan")
    S, H = spec(s), spec(h)
    m = min(len(S), len(speech))
    sp = speech[:m] & speech[np.minimum(np.arange(m) + 3, n - 1)]
    S, H = S[:m][sp], H[:m][sp] / 10 ** (gain / 10)
    band = lambda P, lo, hi: 10 * np.log10(P[:, int(lo / 31.25):int(hi / 31.25)].sum() + 1e-12)
    hf = (band(H, 3000, 7000) - band(H, 300, 3000)) - (band(S, 3000, 7000) - band(S, 300, 3000))
    lo, hi = int(100 / 31.25), int(7000 / 31.25)
    lsd = float(np.mean(np.sqrt(np.mean((10 * np.log10(S[:, lo:hi] + 1e-10) - 10 * np.log10(H[:, lo:hi] + 1e-10)) ** 2,
                                        axis=1))))
    return {"speech_s": round(speech.sum() / 100, 1), "gain_db": round(gain, 1),
            "dropout_pct": round(100 * drop.sum() / speech.sum(), 2),
            "lost_s": round(lost / 100, 2), "lost_pct": round(100 * lost / speech.sum(), 1),
            "onset_ms": int(np.median(onsets)) if onsets else None, "n_onsets": len(onsets),
            "clip_pct": round(clip_pct(heard), 3),
            "noise_db": round(noise - spk_lvl, 1) if noise == noise else None,
            "hf_db": round(float(hf), 1), "lsd_db": round(lsd, 1)}


GEMINI_PROMPT = """You are an expert VoIP audio engineer. RECORDING A is a clean AI voice fed into a call's microphone.
RECORDING B is what the far end of the call played. Compare B against A: stutter/choppiness, dropped slices,
robotic/metallic artifacts, missing sentence starts, static/noise in pauses, clipping/over-loud, muffled sound.
Answer with ONLY a JSON object: {"score": <1-10 quality of B, 10 = identical to A>, "issues": "<one short sentence>"}"""


def gemini(sent, heard, model="gemini-3.1-pro-preview", seconds=80):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gateway

    def wav16(p):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-t", str(seconds), "-ac", "1", "-ar", "16000",
                               "-f", "wav", "-"], capture_output=True, check=True).stdout
    b64 = lambda b: base64.b64encode(b).decode()
    body = {"contents": [{"role": "user", "parts": [
        {"text": GEMINI_PROMPT},
        {"text": "RECORDING A:"}, {"inline_data": {"mime_type": "audio/wav", "data": b64(wav16(sent))}},
        {"text": "RECORDING B:"}, {"inline_data": {"mime_type": "audio/wav", "data": b64(wav16(heard))}}]}],
        "generationConfig": {"responseMimeType": "application/json"}}
    req = urllib.request.Request(f"{gateway.base()}/gemini/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(),
                                 headers={**gateway.auth_header(), "Content-Type": "application/json"})
    try:
        r = json.load(urllib.request.urlopen(req, timeout=280))
        txt = "".join(p.get("text", "") for p in r["candidates"][0]["content"]["parts"])
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {"score": None, "issues": txt[:200]}
    except Exception as e:  # noqa: BLE001
        return {"score": None, "issues": f"gemini failed: {e}"[:200]}


def line(r):
    if "error" in r:
        return r["error"]
    if "spk_gaps_pct" in r:
        g0 = f"  chrome-out gaps {r['spk_gaps_pct']}%"
    else:
        g0 = ""
    g = g0 + f"  gemini {r['gemini']['score']}/10 ({r['gemini']['issues']})" if "gemini" in r else g0
    return (f"speech {r['speech_s']}s  gain {r['gain_db']:+}dB  dropout {r['dropout_pct']}%  "
            f"lost {r['lost_s']}s ({r['lost_pct']}%)  onset {r['onset_ms']}ms  clip {r['clip_pct']}%  "
            f"noise {r['noise_db']}dB  hf {r['hf_db']:+}dB  lsd {r['lsd_db']}dB{g}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sent")
    ap.add_argument("heard", nargs="?")
    ap.add_argument("--gemini", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    sent, heard = (a.sent, a.heard) if a.heard else (Path(a.sent) / "ai.wav", Path(a.sent) / "heard.wav")
    r = score(sent, heard)
    if a.gemini:
        r["gemini"] = gemini(sent, heard)
    print(json.dumps(r) if a.json else line(r))


if __name__ == "__main__":
    main()
