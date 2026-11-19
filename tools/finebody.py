#!/usr/bin/env python3
"""The body's fine detail: how each harmonic's level follows the pitch, measured in the recordings.

    python3 -I tools/finebody.py <bigcat checkout> [--json out.json] [--stats tools/finebody_stats.json]

A bowed note's pitch wanders by a cent or two. As it does, each harmonic slides along the body's
response, and where the body has a narrow resonance its level follows. Over each sustain's steady part
(0.6 s to 0.15 s before its end), per harmonic k, the slope of its level against the note's level
(dB) on the pitch (cents), both low-passed to 8 Hz and detrended, by least squares, with its standard
error.

Each note has 8 takes (4 dynamics x 2 bows) and its k-th harmonic is at the same frequency in all of
them, so if the slope is the body's the takes agree. The script reports:

  agreement  the correlation of two takes' slopes over harmonics (pairs of takes of one note), and the
             share of the slopes' variance that is common to the note's takes (the body) rather than
             each take's own (noise, or the bow)
  size       per octave band of frequency: the rms slope, the rms of the takes' mean (the note's best
             estimate of the body's slope there) and the noise's share of it

The takes agree only loosely (each note's estimate is about as noisy as it is large), so the body's
actual detail can't be read off note by note; its size can. --stats writes the body's slope per band
and the detail's size (the rms of the measured notes' corrections, tools/cello.json: what the fitted
body's 50-cent knots leave), and fine_curve() makes a fixed detail with those statistics for
tools/make_header.py (a judgment: the cello's statistics, not its exact resonances).
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import butter, sosfiltfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

RATE = 200          # Hz, the tracks' rate
KMAX = 40
FMAX = 8000.0
LP_HZ = 8.0


def lp_detrend(y, sos):
    y = sosfiltfilt(sos, y)
    t = np.arange(len(y))
    return y - np.polyval(np.polyfit(t, y, 1), t)


def slopes(x, sr, f_guess, t0, t1):
    x = x[:int((t1 + 0.2) * sr)]
    an = H.analyse(x, sr, f_guess, kmax=KMAX, fmax=FMAX)
    hop = int(sr / RATE)
    a, b = int(t0 * sr), int(t1 * sr)
    idx = np.arange(a, b, hop)
    sos = butter(4, LP_HZ, fs=RATE, output="sos")
    fm = float(np.median(an["f0"][a:b]))
    p = lp_detrend(C.cents(an["f0"][idx], fm), sos)
    amp = 2 * np.abs(an["a"][:, idx])
    E = 20 * np.log10(np.sqrt(np.sum(amp ** 2, axis=0) / 2) + 1e-12)
    Ld = 20 * np.log10(amp + 1e-12)
    top = Ld.mean(axis=1).max()
    out = []
    pp = p - p.mean()
    n_eff = max(4.0, len(p) * 2 * LP_HZ / RATE)       # independent samples after the low-pass
    for k in range(len(Ld)):
        mean = Ld[k].mean()
        y = lp_detrend(Ld[k] - E, sos)
        s = float(np.dot(pp, y) / np.dot(pp, pp))
        r = y - s * pp
        se = float(np.sqrt(np.var(r) / (np.var(pp) * n_eff)))
        out.append(dict(k=k + 1, f=(k + 1) * fm, db=float(mean - top), s=s, se=se))
    return dict(f0=fm, pitch_rms=float(np.std(p)), h=out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    ap.add_argument("--stats")
    ap.add_argument("--floor", type=float, default=40.0, help="dB below the strongest harmonic")
    a = ap.parse_args()
    takes = []
    for s in C.sustains(a.root):
        x, sr = C.load(s["path"])
        r = slopes(x, sr, C.mtof(s["midi"]), 0.6, len(x) / sr - 0.15)
        r.update(midi=s["midi"], dyn=s["dyn"], bow=s["bow"])
        takes.append(r)
        print(f"{C.note_name(s['midi'])} {s['dyn']:>2} {s['bow']:<4} pitch {r['pitch_rms']:.2f} c", file=sys.stderr)

    notes = sorted({t["midi"] for t in takes})
    corr, common_share, rows = [], [], []
    for m in notes:
        T = [t for t in takes if t["midi"] == m]
        K = min(len(t["h"]) for t in T)
        S = np.array([[t["h"][k]["s"] for k in range(K)] for t in T])           # takes x harmonics
        SE = np.array([[t["h"][k]["se"] for k in range(K)] for t in T])
        DB = np.array([[t["h"][k]["db"] for k in range(K)] for t in T])
        ok = (DB > -a.floor).all(axis=0)
        if ok.sum() < 4:
            continue
        S, SE = S[:, ok], SE[:, ok]
        for i in range(len(T)):
            for j in range(i + 1, len(T)):
                corr.append(np.corrcoef(S[i], S[j])[0, 1])
        mean = S.mean(axis=0)
        within = S.var(axis=0, ddof=1).mean()                   # each take's own
        between = mean.var() - within / len(T)                  # the note's common slope
        common_share.append(between / (between + within))
        f = np.array([T[0]["h"][k]["f"] for k in range(K)])[ok]
        for kk in range(len(f)):
            rows.append(dict(midi=m, f=float(f[kk]), s_mean=float(mean[kk]),
                             s_rms=float(np.sqrt(np.mean(S[:, kk] ** 2))),
                             se=float(np.sqrt(np.mean(SE[:, kk] ** 2))),
                             s_sd=float(S[:, kk].std(ddof=1)), n=len(T)))
        print(f"{C.note_name(m):>4}: take-pair corr {np.median(corr[-len(T) * (len(T) - 1) // 2:]):+.2f}, "
              f"common share {common_share[-1]:.2f}, harmonics {ok.sum()}")
    print(f"\nagreement: median take-pair correlation {np.median(corr):+.2f}; common share median "
          f"{np.median(common_share):.2f}")
    print("\nper octave band (dB per cent): rms slope, rms of the takes' mean, its noise (se/sqrt n), "
          "body estimate sqrt(mean^2 - noise^2)")
    for lo in (62.5, 125, 250, 500, 1000, 2000, 4000):
        R = [r for r in rows if lo <= r["f"] < 2 * lo]
        if not R:
            continue
        rms = np.sqrt(np.mean([r["s_rms"] ** 2 for r in R]))
        mean = np.sqrt(np.mean([r["s_mean"] ** 2 for r in R]))
        noise = np.sqrt(np.mean([(r["s_sd"] ** 2) / r["n"] for r in R]))
        body = np.sqrt(max(0.0, mean ** 2 - noise ** 2))
        print(f"  {lo:6.0f}-{2 * lo:5.0f} Hz  n {len(R):3d}  {rms:.3f}  {mean:.3f}  {noise:.3f}  {body:.3f}")
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(rows=rows, takes=[{k: v for k, v in t.items()} for t in takes]), f)
    if a.stats:
        bands, slope = [], []
        for lo in (125, 250, 500, 1000, 2000, 4000):
            R = [r for r in rows if lo <= r["f"] < 2 * lo]
            mean = np.sqrt(np.mean([r["s_mean"] ** 2 for r in R]))
            noise = np.sqrt(np.mean([(r["s_sd"] ** 2) / r["n"] for r in R]))
            bands.append(lo)
            slope.append(round(float(np.sqrt(max(0.0, mean ** 2 - noise ** 2))), 3))   # as printed
        with open(a.stats, "w") as f:
            json.dump(dict(bands_lo_hz=bands, slope_db_per_cent=slope, sigma_db=corr_sigma()), f, indent=1)


def corr_sigma(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "cello.json"), floor=40.0):
    """The rms of the measured notes' corrections (harmonics 1-40 within `floor` dB of the strongest):
    the detail the fitted body leaves."""
    d = json.load(open(path))
    v = []
    for c in d["cells"]:
        hd = np.array(c["hand_db"])
        for k in range(min(40, len(c["corr"]))):
            if hd[k] > hd.max() - floor:
                v.append(c["corr"][k])
    return float(np.std(v))


def fine_curve(x, stats, seed=7, passes=3):
    """A fixed fine detail (dB) on the log2(Hz) grid x (evenly spaced): the magnitude of a smooth
    complex Gaussian process (many overlapping resonances: sharp dips, rounder peaks), with its slope
    following the measured one per band (by stretching the frequency axis) and its rms the measured
    corrections'. Zero mean over any third of an octave, so the fitted body keeps its shape. The
    slope is checked on the grid itself (as the engine reads it) and the stretch corrected."""
    step_c = (x[1] - x[0]) * 1200.0
    lb = np.log2(np.array(stats["bands_lo_hz"]) * np.sqrt(2.0))
    c = np.polyfit(lb, np.array(stats["slope_db_per_cent"]), 1)   # a line in log f through the bands
    target = np.clip(np.polyval(c, x), 0.1, 0.5)
    sigma = stats["sigma_db"]
    rng = np.random.default_rng(seed)
    n = 80000
    w = 8.0
    t = np.arange(-int(4 * w), int(4 * w) + 1)
    ker = np.exp(-0.5 * (t / w) ** 2)
    z = np.convolve(rng.standard_normal(n) + 1j * rng.standard_normal(n), ker, mode="same")
    g = 20 * np.log10(np.abs(z) + 1e-12)
    g = np.maximum(g, np.median(g) - 25.0)             # dips as deep as a damped body's, not to -inf
    g = (g - g.mean()) / g.std()
    g1 = np.sqrt(np.mean(np.diff(g) ** 2))             # its slope per sample
    m3 = max(1, int(round(1 / 3 / (x[1] - x[0]))))     # a third of an octave
    m1 = 3 * m3                                         # an octave, for checking the slope
    s = target.copy()
    for _ in range(passes):
        tau = np.concatenate([[0.0], np.cumsum(s[:-1] * step_c / (sigma * g1))]) + 1000.0
        F = sigma * np.interp(tau, np.arange(n), g)
        F = F - np.convolve(F, np.ones(m3) / m3, mode="same")
        d2 = np.concatenate([np.diff(F) / step_c, [0.0]]) ** 2
        got = np.sqrt(np.convolve(d2, np.ones(m1) / m1, mode="same"))
        s = s * np.clip(target / np.maximum(got, 1e-3), 0.5, 2.0)
    return F


if __name__ == "__main__":
    main()
