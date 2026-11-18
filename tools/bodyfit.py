#!/usr/bin/env python3
"""Does a bowed note's spectrum factor into a source and a body?

    python3 -I tools/bodyfit.py <bigcat checkout> [--json out.json]

For every sustain, each harmonic's steady level (harmonics.steady_levels) is fitted as

    L[file, k] = g[file] + S[dyn, k] + B(k·f0)

g: the file's level; S: the bowed string's spectrum by harmonic number, one per dynamic; B: one body
response for the instrument, piecewise linear in log-frequency (knots every 1/24 octave, 55 Hz-16 kHz, smoothed).
Weighted least squares; harmonics more than 50 dB under the file's strongest are left out.

The question is whether it predicts a note it has not seen better than what a sampler does. Leave
one note out (all four dynamics and both bows), predict each of its files' spectrum (only the level g
is fitted to it) and compare, in rms dB over its harmonics weighted by level, with:
  - neighbour: the nearest sampled note's spectrum, by harmonic number, at the same dynamic and bow
    (a sampler transposing its neighbour);
  - the yardstick: the same note's other bow (down against up), the recordings' own variation.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

KNOT_STEP = 1 / 24
F_LO, F_HI = 55.0, 16000.0
RANGE_DB = 50.0
WEAK = 0.1
LAMBDA = 0.3           # smoothness of B (second differences); 1/24 octave and 0.3 predict unseen notes best (4.05 dB; 1/6 and 3: 5.1)
KMAX = 160          # harmonics fitted per note (C2: to 10.5 kHz)


def measure_all(root):
    rows = []
    for s in C.sustains(root):
        x, sr = C.load(s["path"])
        f_et = C.mtof(s["midi"])
        f0s, _, _ = H.f0_per_sample(x, sr, f_et)
        f0 = float(np.median(f0s[int(0.4 * sr):int(min(len(x) / sr - 0.3, 3.0) * sr)]))
        L = H.steady_levels(x, sr, f0, 0.4, min(len(x) / sr - 0.3, 3.0), fmax=F_HI)[:KMAX]
        rows.append(dict(s, f0=f0, L=L))
    return rows


def knots():
    return np.arange(np.log2(F_LO), np.log2(F_HI) + KNOT_STEP, KNOT_STEP)


def hat(logf, kn):
    """Piecewise-linear basis on the knots: (n, len(kn))."""
    i = np.clip(np.searchsorted(kn, logf) - 1, 0, len(kn) - 2)
    t = np.clip((logf - kn[i]) / (kn[i + 1] - kn[i]), 0, 1)
    M = np.zeros((len(logf), len(kn)))
    M[np.arange(len(logf)), i] = 1 - t
    M[np.arange(len(logf)), i + 1] = t
    return M


def weights(L):
    """By level: the strongest harmonics count most. Harmonics more than RANGE_DB under the strongest
    still count a little (WEAK): left out, the fit never saw how the top falls away, and predicted a
    note's weakest high harmonics 8-21 dB too loud (heard as a fizz, and its flicker as a flutter)."""
    return np.maximum(np.clip((L - (L.max() - RANGE_DB)) / RANGE_DB, 0, 1) ** 0.5, WEAK)


def fit(rows):
    kn = knots()
    files = list(range(len(rows)))
    dyns = C.DYNAMICS
    nG, nS, nB = len(files), len(dyns) * KMAX, len(kn)
    A, y, W = [], [], []
    for fi, r in enumerate(rows):
        L = r["L"]
        w = weights(L)
        k = np.arange(1, len(L) + 1)
        sel = w > 0
        n = sel.sum()
        M = np.zeros((n, nG + nS + nB))
        M[:, fi] = 1
        M[np.arange(n), nG + dyns.index(r["dyn"]) * KMAX + (k[sel] - 1)] = 1
        M[:, nG + nS:] = hat(np.log2(k[sel] * r["f0"]), kn)
        A.append(M)
        y.append(L[sel])
        W.append(w[sel])
    A, y, W = np.vstack(A), np.concatenate(y), np.concatenate(W)
    # smoothness of B, of S along k, and a weak pull of S towards 0 (fixes the split between them)
    D = np.zeros((nB - 2, nG + nS + nB))
    for i in range(nB - 2):
        D[i, nG + nS + i:nG + nS + i + 3] = [1, -2, 1]
    Ds = []
    for d in range(len(dyns)):
        for k in range(KMAX - 2):
            row = np.zeros(nG + nS + nB)
            row[nG + d * KMAX + k:nG + d * KMAX + k + 3] = [1, -2, 1]
            Ds.append(row)
    Ds = np.array(Ds)
    R = np.zeros((nS, nG + nS + nB))
    R[:, nG:nG + nS] = np.eye(nS)
    Aw = np.vstack([A * W[:, None], LAMBDA * D, 0.3 * Ds, 0.01 * R])
    yw = np.concatenate([y * W, np.zeros(len(D) + len(Ds) + nS)])
    p, *_ = np.linalg.lstsq(Aw, yw, rcond=None)
    return dict(S=p[nG:nG + nS].reshape(len(dyns), KMAX), B=p[nG + nS:], knots=kn)


def predict(model, dyn, f0, n):
    k = np.arange(1, n + 1)
    return model["S"][C.DYNAMICS.index(dyn), :n] + hat(np.log2(k * f0), model["knots"]) @ model["B"]


def err(pred, L):
    """rms dB, level fitted, weighted by the recording's levels."""
    n = min(len(pred), len(L))
    pred, L = pred[:n], L[:n]
    w = weights(L)
    g = np.sum(w * (L - pred)) / np.sum(w)
    return float(np.sqrt(np.sum(w * (L - pred - g) ** 2) / np.sum(w)))


def loo(rows):
    notes = sorted({r["midi"] for r in rows})
    res = []
    for m in notes:
        train = [r for r in rows if r["midi"] != m]
        model = fit(train)
        lower = max([n for n in notes if n < m], default=None)
        upper = min([n for n in notes if n > m], default=None)
        for r in [r for r in rows if r["midi"] == m]:
            pb = predict(model, r["dyn"], r["f0"], len(r["L"]))
            out = dict(file="%s_%s_%s" % (r["name"], r["dyn"], r["bow"]), midi=m, dyn=r["dyn"],
                       body=err(pb, r["L"]))
            nb = []
            for nm in (lower, upper):
                if nm is None:
                    continue
                o = next(q for q in rows if q["midi"] == nm and q["dyn"] == r["dyn"] and q["bow"] == r["bow"])
                nb.append(err(o["L"], r["L"]))
            out["neighbour"] = float(np.mean(nb))
            other = next(q for q in rows if q["midi"] == m and q["dyn"] == r["dyn"] and q["bow"] != r["bow"])
            out["other_bow"] = err(other["L"], r["L"])
            res.append(out)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = measure_all(a.root)
    res = loo(rows)
    print("leave one note out: rms dB of each file's harmonic levels (level fitted, weighted)")
    print("%-10s %6s %9s %9s" % ("file", "body", "neighbour", "other bow"))
    for r in res:
        print("%-10s %6.1f %9.1f %9.1f" % (r["file"], r["body"], r["neighbour"], r["other_bow"]))
    for key in ("body", "neighbour", "other_bow"):
        v = [r[key] for r in res]
        print("%-10s median %.1f dB, mean %.1f" % (key, np.median(v), np.mean(v)))
    print("body nearer than neighbour in %d of %d files" % (sum(r["body"] < r["neighbour"] for r in res), len(res)))
    full = fit(rows)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(loo=res, S=full["S"].tolist(), B=full["B"].tolist(), knots=full["knots"].tolist(),
                           files=[dict(name=r["name"], dyn=r["dyn"], bow=r["bow"], f0=r["f0"], L=r["L"].tolist())
                                  for r in rows]), f)


if __name__ == "__main__":
    main()
