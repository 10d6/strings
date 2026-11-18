"""How different two sounds are to a listener: the piano's perceptual distance, for mono.

Ported from 10d6/piano `tools/measure/perceptual.py` (where it agrees with the owner's ears on 7 of
8 fixes and with two blind listening tests). Same ear model:

  1. A gammatone filterbank, one band per ERB, 40 Hz-16 kHz.
  2. Each band's power over 8 ms, every 2 ms.
  3. Specific loudness per band (Zwicker's form) above the threshold of hearing, at a playback level
     where a full-scale sine is 100 dB SPL.
  4. The difference per band and frame, less 5 % of the louder (about 1 dB).

The distance in a window is the audible difference summed over the reference's loudness there, in %:
the attack (0-80 ms), the early sound (80-500 ms) and the sustain (0.5-3 s); the score is their mean.
Signed versions per region say which way it is wrong.

Differences from the piano's: mono; no mains-hum notch (these recordings have none to speak of) and
no background floor (the bigcat files start at the attack and are cut mid-bow, so there is no silence
to measure one from).
"""
import numpy as np
import scipy.signal as sig

HOP = 0.002
SMOOTH = 0.008
TOL = 0.05
WINDOWS = [("attack", 0.0, 0.08), ("early", 0.08, 0.5), ("sustain", 0.5, 3.0)]
REGIONS = [("low", 0, 500), ("mid", 500, 4000), ("high", 4000, 1e9)]


def erb_centres(lo=40.0, hi=16000.0, step=1.0):
    e = lambda f: 21.4 * np.log10(1 + 0.00437 * f)
    inv = lambda E: (10 ** (E / 21.4) - 1) / 0.00437
    return inv(np.arange(e(lo), e(hi) + 1e-9, step))


CENTRES = erb_centres()


def band_power(x, sr, fc):
    erb = 24.7 * (4.37e-3 * fc + 1)
    a = np.exp(-2 * np.pi * 1.019 * erb / sr)
    y = x * np.exp(-2j * np.pi * fc * np.arange(len(x)) / sr)
    for _ in range(4):
        y = sig.lfilter([1 - a], [1, -a], y)
    return np.abs(y) ** 2 / 2


def threshold_db(f):
    k = f / 1000.0
    return 3.64 * k ** -0.8 - 6.5 * np.exp(-0.6 * (k - 3.3) ** 2) + 1e-3 * k ** 4


def loudness(x, sr, length=3.0, spl=100.0):
    """Specific loudness [frame, band] of a mono signal."""
    n = int(length * sr)
    x = np.asarray(x, float)[:n]
    if len(x) < n:
        x = np.concatenate([x, np.zeros(n - len(x))])
    step, L = int(HOP * sr), int(SMOOTH * sr)
    idx = np.arange(0, n - L, step)
    P = []
    for fc in CENTRES:
        if fc > sr / 2 * 0.95:
            P.append(np.zeros(len(idx)))
            continue
        c = np.concatenate([[0.0], np.cumsum(band_power(x, sr, fc))])
        P.append((c[idx + L] - c[idx]) / L)
    P = np.array(P).T
    thr = 10 ** (threshold_db(CENTRES) / 10)
    E = P * 2 * 10 ** (spl / 10)
    return np.maximum(0.08 * thr ** 0.23 * ((0.5 + 0.5 * E / thr) ** 0.23 - 1), 0)


def distance(Nr, Nm):
    f = min(Nr.shape[0], Nm.shape[0])
    Nr, Nm = Nr[:f], Nm[:f]
    t = np.arange(f) * HOP + SMOOTH / 2
    diff = Nm - Nr
    aud = np.maximum(np.abs(diff) - TOL * np.maximum(Nr, Nm), 0)
    res, scores = {}, []
    for name, t0, t1 in WINDOWS:
        sel = (t >= t0) & (t < t1)
        ref = Nr[sel].sum()
        if not sel.any() or ref <= 0:
            continue
        d = 100 * aud[sel].sum() / ref
        res[name] = round(float(d), 2)
        scores.append(d)
        for rn, f0, f1 in REGIONS:
            b = (CENTRES >= f0) & (CENTRES < f1)
            res[f"{name}_{rn}"] = round(float(100 * diff[sel][:, b].sum() / ref), 2)
    res["score"] = round(float(np.mean(scores)), 2)
    return res


def between(a, b, sr, length=3.0):
    """Distance of b from a (a is the reference)."""
    return distance(loudness(a, sr, length), loudness(b, sr, length))
