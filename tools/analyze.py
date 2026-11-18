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

The bow's movement while a note is held (tools/life.py, over every sustain's steady part):

  life      per note (its 4 dynamics × 2 bows pooled, then smoothed across notes): the rms per
            octave of modulation frequency (0.25-32 Hz) of its pitch (cents), its level (dB) and
            its harmonics' own movement against the level (dB, a mean over harmonics)
  patterns  the harmonics don't move independently but in a few shared patterns (the strongest three
            hold 70 % of their movement): per note and dynamic, from its down-bow recording (whose
            onset the engine plays: a note's recordings don't share their patterns), the three
            principal components of its harmonics' movement (shape over harmonics 1-20), how fast each
            moves (rms per octave of modulation frequency), and what is left over, per harmonic (rms)
            and over time (spectrum), played independently
  lifeK     how much more a harmonic moves the higher it is (1.3 dB on the fundamental, about 3 by
            the 20th: a ratio to the mean, a line in log2 k fitted to k ≤ 20, held from 1.25× the
            20th's: a judgment above it)
  grain     per note and dynamic (down bow): the bow noise's pulse at the string's period, per
            band, its depth and where in the fundamental's period it peaks (bands that can't be
            seen between the harmonics take the nearest band's)

Takes about 6 minutes.
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
import life as LF  # noqa: E402

NPAT = 3                # the harmonics' shared patterns kept per note
ONSET_LEN = 0.40
T_ON, XF = 0.30, 0.10
T_C = T_ON + XF / 2
KMAX = B.KMAX
FMAX = 16000.0          # harmonics above it would be measured as noise (and played as hiss)
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
            corr = r["L"] - pred - g     # every harmonic: the weakest, near the noise, read high if anything
            cell.update(midi=m, dyn=d, corr=np.clip(corr, -40, 24).tolist(), fit_f0=r["f0"])
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
    print("the bow's movement…", flush=True)
    rng = np.random.default_rng(3)
    stats = {}
    for s in C.sustains(root):
        x, sr = C.load(s["path"])
        stats[(s["midi"], s["dyn"], s["bow"])] = LF.stats(x, sr, C.mtof(s["midi"]), 0.6, len(x) / sr - 0.15,
                                                          rng, bands=BANDS)
    life = {"pitch": [], "level": [], "harm": []}
    for m in notes:
        mine = [v for k, v in stats.items() if k[0] == m]
        for key, src in (("pitch", "pitch_oct"), ("level", "level_oct"), ("harm", "harm_oct")):
            life[key].append(np.median([v[src] for v in mine], axis=0))
    for key in life:   # smooth across notes: a median of three, in log
        L = np.log(np.maximum(np.array(life[key]), 1e-4))
        Ls = L.copy()
        for i in range(len(notes)):
            lo, hi = max(0, i - 1), min(len(notes), i + 2)
            Ls[i] = np.median(L[lo:hi], axis=0) if hi - lo == 3 else np.mean(L[lo:hi], axis=0)
        data["life_" + key] = np.exp(Ls).tolist()
    byk = {}
    for v in stats.values():
        med = np.median(v["harm_rms"])
        for k, r in zip(v["harm_k"], v["harm_rms"]):
            byk.setdefault(k, []).append(r / med)
    ks = np.array(sorted(byk))
    ratio = np.array([np.median(byk[k]) for k in ks])
    a1, a0 = np.polyfit(np.log2(ks), ratio, 1)
    kk = np.arange(1, KMAX + 1)
    law = np.minimum(a0 + a1 * np.log2(kk), 1.25 * (a0 + a1 * np.log2(20)))
    data["life_k"] = law.tolist()
    print("  harmonics move %.2f + %.2f·log2 k times the mean (k ≤ 20 measured)" % (a0, a1))
    # the patterns: per cell, from the down-bow recording whose onset the engine plays. A note's
    # recordings don't share them (pooled over its 8, the strongest three hold 48 %; in one, 70 %):
    # each performance has its own few.
    shapes, shape_oct, resid_k, resid_oct, explained = [], [], [], [], []
    for m in notes:
        for d in C.DYNAMICS:
            D = stats[(m, d, "d")]["_D"]
            kl = len(D)
            w, V = np.linalg.eigh(D @ D.T / D.shape[1])
            V = V[:, ::-1][:, :NPAT]
            explained.append(float(w[::-1][:NPAT].sum() / w.sum()))
            so = np.array([LF.per_octave(V[:, c] @ D) for c in range(NPAT)])
            R = D - V @ (V.T @ D)
            rk = R.std(axis=1)
            ro = np.mean([LF.per_octave(row) for row in R], axis=0)
            ro = ro / np.sqrt(np.sum(ro ** 2))
            full = np.zeros(KMAX)
            full[:kl] = rk
            full[kl:] = rk[-1]   # above the 20th, as the 20th (a judgment: higher up the recordings'
            #                      harmonics are too near the noise to measure how they move)
            sh = np.zeros((NPAT, LF.KMAXL))
            sh[:, :kl] = V.T
            shapes.append(sh.tolist())
            shape_oct.append(so.tolist())
            resid_k.append(full.tolist())
            resid_oct.append(ro.tolist())
    data["life_shape"] = shapes          # [note * dyn][pattern][harmonic]
    data["life_shape_oct"] = shape_oct   # [note * dyn][pattern][octave]
    data["life_resid_k"] = resid_k       # [note * dyn][harmonic]
    data["life_resid_oct"] = resid_oct   # [note * dyn][octave], unit power
    print("  patterns: the strongest %d hold %.0f %% of the harmonics' movement (median over cells)" % (
        NPAT, 100 * np.median(explained)))
    # the noise's pulse per cell (down bow); its phase between the bows, as a check it is a property
    gm, gp, agree = [], [], []
    for m in notes:
        for d in C.DYNAMICS:
            vd, vg = stats[(m, d, "d")], stats[(m, d, "g")]
            have = [b for b in range(len(BANDS)) if vd["noise_mod"][b] is not None]
            fill = lambda arr: [arr[b] if arr[b] is not None else arr[min(have, key=lambda h: abs(h - b))]
                                for b in range(len(BANDS))]
            gm.append(fill(vd["noise_mod"]))
            gp.append(fill(vd["noise_psi"]))
            for b in have:
                if vg["noise_mod"][b] is not None and vd["noise_mod"][b] > 0.15:
                    agree.append(abs(np.angle(np.exp(1j * (vd["noise_psi"][b] - vg["noise_psi"][b])))))
    data["grain_depth"] = gm
    data["grain_phase"] = gp
    print("  noise pulse: depth median %.2f; peak phase, down against up bow (depth > 0.15): median %.0f° apart" % (
        float(np.median(gm)), np.degrees(np.median(agree))))
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
