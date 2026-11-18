#!/usr/bin/env python3
"""Measure the cello for the engine: everything src/CelloData.h holds.

    python3 -I tools/analyze.py <bigcat checkout> tools/cello.json tools/cello_onsets.npz

Per measured note (17, C2-C6 a minor third apart) and dynamic (p, mp, mf, f), from the down-bow
sustain:

  onset     the recording's first ONSET_LEN s, played as recorded (the bow's catch, its scratch and
            its pitch glide: docs/PHASE0.md); the engine crossfades from it to the model over
            [T_ON, T_ON + XF]
  hand_f0   the pitch at the crossfade's middle (T_C), which the engine transposes to its target
  hand      each harmonic's level and phase at T_C (heterodyned; harmonics.analyse), so the model's
            harmonics take over in step with the recording
  level     the steady harmonic level (dB re full scale, rms of the harmonic part, 0.4 s to the end)
  noise     the residual's steady power in octave bands (dB, relative to level): the bow noise
  corr      the note's own steady spectrum against source × body, per harmonic (dB)

For the whole instrument (bodyfit.py, both bows of every sustain):

  source    S[dynamic][harmonic] (dB) and body B(f) (dB on knots every 1/24 octave)

Per measured note, from its staccatos (every dynamic and round robin):

  release   each octave band's decay rate after the bow stops (dB/s): the sustains are cut
            mid-bow, so this is the only release in the library (docs/PHASE0.md)

Takes about 4 minutes.
"""
import json
import os
import re
import sys

import numpy as np
from scipy.signal import welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bodyfit as B  # noqa: E402
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

ONSET_LEN = 0.40
T_ON, XF = 0.30, 0.10
T_C = T_ON + XF / 2
KMAX = B.KMAX
FMAX = 12000.0
BANDS = [62.5 * 2 ** i for i in range(9)]          # octave bands, 62.5 Hz-16 kHz (centres)


def band_powers_db(seg, sr):
    f, p = welch(seg, sr, nperseg=4096)
    out = []
    for fc in BANDS:
        sel = (f >= fc / np.sqrt(2)) & (f < fc * np.sqrt(2))
        out.append(10 * np.log10(np.sum(p[sel]) * (f[1] - f[0]) + 1e-20))
    return out


def sustain_data(s):
    x, sr = C.load(s["path"])
    an = H.analyse(x, sr, C.mtof(s["midi"]), kmax=KMAX, fmax=FMAX)
    a, K = an["a"], an["K"]
    p = 2 * np.abs(a)                                  # peak amplitude per harmonic
    E = np.sqrt(np.sum(p ** 2, axis=0) / 2)            # rms of the harmonic part
    i0, i1 = int(0.4 * sr), int((len(x) / sr - 0.1) * sr)
    level = 20 * np.log10(np.median(E[i0:i1]))
    ic = int(T_C * sr)
    w = int(0.02 * sr)
    hand_f0 = float(np.median(an["f0"][ic - w:ic + w]))
    phase = np.angle(a[:, ic]) + np.arange(1, K + 1) * an["phi"][ic]
    hand_db = 20 * np.log10(p[:, ic] + 1e-9)
    noise = np.array(band_powers_db(an["resid"][i0:i1], sr)) - level
    onset = x[:int(ONSET_LEN * sr)]
    return dict(level=float(level), hand_f0=hand_f0, hand_db=hand_db.tolist(),
                hand_phase=np.mod(phase, 2 * np.pi).tolist(), noise=noise.tolist(), K=K), onset, sr


def staccatos(root):
    d = os.path.join(root, "Samples", "staccato")
    out = []
    for f in sorted(os.listdir(d)):
        m = re.fullmatch(r"([A-G]b?\d)_?(p|mp|mf|f)_?(\d)\.wav", f)
        if m:
            out.append(dict(name=m.group(1), midi=C.midi_of(m.group(1)), dyn=m.group(2),
                            path=os.path.join(d, f)))
    return out


def release_rates(path, midi):
    """Each octave band's decay after the bow stops, from one staccato: per harmonic, the slope of
    its level from where the note has fallen 6 dB from its peak to 36 dB (or its own floor)."""
    x, sr = C.load(path)
    an = H.analyse(x, sr, C.mtof(midi), kmax=40, fmax=8000)
    p = 2 * np.abs(an["a"])
    E = np.sqrt(np.sum(p ** 2, axis=0) / 2)
    Edb = 20 * np.log10(E + 1e-12)
    ip = int(np.argmax(Edb))
    after = np.arange(len(E)) > ip
    i6 = np.where(after & (Edb < Edb[ip] - 6))[0]
    if not len(i6):
        return None
    t0 = i6[0]
    i36 = np.where(after & (Edb < Edb[ip] - 36))[0]
    t1 = i36[0] if len(i36) else len(E) - int(0.02 * sr)
    if t1 - t0 < int(0.05 * sr):
        return None
    t = np.arange(t0, t1, int(0.005 * sr))
    rates = {}
    for k in range(an["K"]):
        lv = 20 * np.log10(p[k, t] + 1e-12)
        if lv[0] < Edb[ip] - 45:
            continue
        ok = lv > lv[0] - 40
        if ok.sum() < 6:
            continue
        slope = np.polyfit(t[ok] / sr, lv[ok], 1)[0]
        f = (k + 1) * an["fmed"]
        b = int(np.argmin(np.abs(np.log2(np.array(BANDS) / f))))
        rates.setdefault(b, []).append(-slope)
    return {b: float(np.median(v)) for b, v in rates.items()}


def fill_bands(d):
    """Bands without a value take the nearest band's."""
    have = sorted(d)
    return [float(d[min(have, key=lambda h: abs(h - b))]) for b in range(len(BANDS))]


def main():
    root, out_json, out_npz = sys.argv[1:4]
    print("source × body…", flush=True)
    rows = B.measure_all(root)
    model = B.fit(rows)
    notes = sorted({r["midi"] for r in rows})
    data = dict(notes=notes, dynamics=C.DYNAMICS, onset_rate=None, onset_len=ONSET_LEN, t_on=T_ON, xf=XF,
                t_c=T_C, kmax=KMAX, fmax=FMAX, bands=BANDS,
                source=model["S"].tolist(), body=model["B"].tolist(), knots=model["knots"].tolist(),
                cells=[], release=[])
    onsets = []
    for m in notes:
        for d in C.DYNAMICS:
            s = next(q for q in C.sustains(root) if q["midi"] == m and q["dyn"] == d and q["bow"] == "d")
            cell, onset, sr = sustain_data(s)
            r = next(q for q in rows if q["midi"] == m and q["dyn"] == d and q["bow"] == "d")
            pred = B.predict(model, d, r["f0"], len(r["L"]))
            w = B.weights(r["L"])
            g = np.sum(w * (r["L"] - pred)) / np.sum(w)
            corr = np.where(w > 0, r["L"] - pred - g, 0.0)
            cell.update(midi=m, dyn=d, corr=np.clip(corr, -24, 24).tolist(), fit_f0=r["f0"])
            data["cells"].append(cell)
            data["onset_rate"] = sr
            onsets.append(onset)
            print("  %s %-2s level %.1f dB, f0 at hand-off %.2f Hz, %d harmonics" % (
                C.note_name(m), d, cell["level"], cell["hand_f0"], cell["K"]), flush=True)
    print("releases from the staccatos…", flush=True)
    st = staccatos(root)
    for m in notes:
        per = [release_rates(q["path"], m) for q in st if q["midi"] == m]
        per = [p for p in per if p]
        merged = {}
        for p in per:
            for b, v in p.items():
                merged.setdefault(b, []).append(v)
        rel = fill_bands({b: float(np.median(v)) for b, v in merged.items()})
        data["release"].append(rel)
        print("  %s from %d staccatos: %s dB/s" % (C.note_name(m), len(per), " ".join("%.0f" % v for v in rel)))
    # one staccato set per note scatters from note to note (C5's fundamental 163 dB/s, A4's 31):
    # a median of three neighbouring notes per band, in log
    R = np.log(np.array(data["release"]))
    Rs = R.copy()
    for i in range(len(notes)):
        lo, hi = max(0, i - 1), min(len(notes), i + 2)
        Rs[i] = np.median(R[lo:hi], axis=0) if hi - lo == 3 else np.mean(R[lo:hi], axis=0)
    data["release_raw"] = data["release"]
    data["release"] = np.exp(Rs).tolist()
    with open(out_json, "w") as f:
        json.dump(data, f)
    o = np.array(onsets)
    scale = float(np.max(np.abs(o))) / 32767
    np.savez_compressed(out_npz, onsets=np.round(o / scale).astype(np.int16), scale=scale)


if __name__ == "__main__":
    main()
