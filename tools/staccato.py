#!/usr/bin/env python3
"""Measure the cello's staccato (and the spiccato judged from it) for the engine: src/StaccData.h.

    python3 -I tools/staccato.py <bigcat checkout> tools/stacc.json tools/stacc_onsets.npz   # ~5 min

bigcat's staccatos: 17 notes × 4 dynamics × 4 round robins (two missing), each a whole short stroke,
0.6-1.1 s: the bow bites, the stroke peaks at 0.12-0.31 s, the bow leaves (the level 6 dB under its
peak) at 0.16-0.67 s, and the string rings down (the arco notes' release is measured from these).

A staccato is played as the arco notes are (docs/MODEL.md: the engine), from its own take: the take
recorded until T_H = min(bow-off, MAX_HAND), crossfading over XF into the harmonic bank started in
phase with it, the model carrying the stroke until the take's own bow-off, then the measured release.
Two round robins per note and dynamic are kept (the two closest to the four's median envelope; the
others measure the yardstick): repeated staccatos are what the articulation is for, and one take
would repeat exactly. Recording each stroke to its bow-off would take 2.7 MB a round robin.

The spiccato is a judgment from the same takes: bounced, so the bow leaves just after the stroke
has reached its level, 40 ms after it stands 10 dB under its peak (50-120 ms), the take one dynamic
lighter; the string rings down from there.

Per take: the onset (ONSET_LEN s), where the bow leaves, how each harmonic decays after it (its own
release: the arco notes' release, octave bands pooled over every take of a note and smoothed across
notes, left the staccatos' tails 6.6 dB too bright at 1-2 kHz 0.15-0.45 s after the bow left), the hand-off point and each harmonic's level
and phase there (as tools/analyze.py's: heterodyned at the tracked pitch), for the staccato and for
the spiccato; the stroke's level (its harmonics' peak rms, dB); the pitch at the hand-off.
"""
import json
import os
import sys
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

XF = 0.05               # the crossfade to the bank (s)
MAX_HAND = 0.25         # the latest the recording hands over: the model plays the rest of a longer stroke
ONSET_LEN = MAX_HAND + XF + 0.01
SP_XF = 0.03            # the spiccato's crossfade
SP_AFTER = 0.04         # the spiccato's bow leaves this long after the stroke is 10 dB under its peak
SP_MIN, SP_MAX = 0.05, 0.12
KEEP = 2                # round robins kept per note and dynamic


def hand_at(an, tc, sr):
    a, K = an["a"], an["K"]
    ic = int(tc * sr)
    w = int(0.02 * sr)
    p = 2 * np.abs(a[:, ic])
    ph = np.angle(a[:, ic]) + np.arange(1, K + 1) * an["phi"][ic]
    f0 = float(np.median(an["f0"][max(0, ic - w):ic + w]))
    return 20 * np.log10(p + 1e-9), np.mod(ph, 2 * np.pi), f0


def release_db_s(p, sr, i_off, peak):
    """Each harmonic's decay (dB/s) after the bow leaves: the slope of its level from bow-off until it has
    fallen 30 dB, its floor, or 0.5 s on; weak harmonics (under the peak by 50 dB at bow-off) and failed
    fits take the median of their neighbours (five each side)."""
    K = p.shape[0]
    rates = np.full(K, np.nan)
    i1 = min(p.shape[1] - int(0.02 * sr), i_off + int(0.5 * sr))
    t = np.arange(i_off, i1, int(0.005 * sr))
    if len(t) < 8:
        return [60.0] * K
    for k in range(K):
        lv = 20 * np.log10(p[k, t] + 1e-12)
        lv = np.convolve(lv, np.ones(3) / 3, "same")
        if lv[1] < peak - 50:
            continue
        ok = np.arange(len(t)) < (np.argmax(lv < lv[1] - 30) if np.any(lv < lv[1] - 30) else len(t))
        if ok.sum() < 6:
            continue
        r = -np.polyfit(t[ok] / sr, lv[ok], 1)[0]
        if 3 < r < 600:
            rates[k] = r
    good = np.isfinite(rates)
    if not good.any():
        return [60.0] * K
    out = rates.copy()
    for k in range(K):
        if not good[k]:
            nb = rates[max(0, k - 5):k + 6]
            nb = nb[np.isfinite(nb)]
            out[k] = np.median(nb) if len(nb) else np.median(rates[good])
    return out.tolist()


def take_data(s):
    x, sr = C.load(s["path"])
    an = H.analyse(x, sr, C.mtof(s["midi"]), kmax=A.KMAX, fmax=A.FMAX)
    p = 2 * np.abs(an["a"])
    P = np.sum(p ** 2, axis=0) / 2
    # smoothed in power: smoothed in dB, the edges' zero padding read as 0 dB, the loudest moment
    sm = 10 * np.log10(np.convolve(P, np.ones(int(0.005 * sr)) / int(0.005 * sr), "same") + 1e-24)
    ip = int(np.argmax(sm))
    peak = float(sm[ip])
    after = np.where(sm[ip:] < peak - 6)[0]
    t_off = (ip + after[0]) / sr if len(after) else len(x) / sr - 0.05
    rel = release_db_s(p, sr, int(t_off * sr), peak)
    t_h = min(t_off, MAX_HAND)
    tc = t_h + XF / 2
    # a stroke longer than the recording plays: how it fades from the hand-off to its bow-off (dB/s),
    # which the model follows (gliding to a held note's level instead, the bow left 200-345 ms late)
    fade = float((sm[int(t_off * sr)] - sm[int(tc * sr)]) / (t_off - tc)) if t_off > tc + 0.02 else 0.0
    hdb, hph, hf0 = hand_at(an, tc, sr)
    t10 = np.argmax(sm > peak - 10) / sr
    t_sp = float(np.clip(t10 + SP_AFTER, SP_MIN, SP_MAX))
    tc_sp = t_sp + SP_XF / 2
    sdb, sph, sf0 = hand_at(an, tc_sp, sr)
    env = sm[:int(0.8 * sr):int(0.005 * sr)]
    return dict(midi=s["midi"], dyn=s["dyn"], path=os.path.basename(s["path"]), level=peak, t_off=float(t_off),
                t_hand=float(t_h), fade=fade, hand_f0=hf0, hand_db=hdb.tolist(), hand_ph=hph.tolist(),
                t_sp=t_sp, sp_level=float(sm[int(tc_sp * sr)]), sp_f0=sf0, sp_db=sdb.tolist(), sp_ph=sph.tolist(),
                K=int(an["K"]), rel=rel, env=env.tolist()), x[:int(round(ONSET_LEN * sr))], sr


def main():
    root, out_json, out_npz = sys.argv[1:4]
    takes = A.staccatos(root)
    with Pool(2) as pool:
        res = pool.map(take_data, takes)
    notes = sorted({r["midi"] for r, _, _ in res})
    cells, onsets, levels = [], [], {}
    for m in notes:
        for d in C.DYNAMICS:
            rs = [(r, o) for r, o, _ in res if r["midi"] == m and r["dyn"] == d]
            n = min(len(e["env"]) for e, _ in rs)
            envs = np.array([e["env"][:n] for e, _ in rs])
            med = np.median(envs, axis=0)
            dist = np.sqrt(np.mean((envs - med) ** 2, axis=1))
            order = np.argsort(dist)
            levels[(m, d)] = float(np.median([r["level"] for r, _ in rs]))
            for j in order[:KEEP]:
                r, o = rs[j]
                r = dict(r)
                r.pop("env")
                r["dist"] = float(dist[j])
                cells.append(r)
                onsets.append(np.pad(o, (0, max(0, int(round(ONSET_LEN * res[0][2])) - len(o)))))
            print("  %-4s %-2s level %.1f dB; kept %s (envelope %.1f, %.1f dB from the median); bow off %s s; "
                  "spiccato %s s" % (C.note_name(m), d, levels[(m, d)], ", ".join(rs[j][0]["path"] for j in order[:KEEP]),
                                     dist[order[0]], dist[order[1]],
                                     "/".join("%.2f" % rs[j][0]["t_off"] for j in order[:KEEP]),
                                     "/".join("%.3f" % rs[j][0]["t_sp"] for j in order[:KEEP])), flush=True)
    data = dict(notes=notes, dynamics=C.DYNAMICS, keep=KEEP, onset_rate=res[0][2], onset_len=ONSET_LEN, xf=XF,
                sp_xf=SP_XF, levels=[[levels[(m, d)] for d in C.DYNAMICS] for m in notes], cells=cells)
    with open(out_json, "w") as f:
        json.dump(data, f)
    o = np.array(onsets)
    scale = float(np.max(np.abs(o))) / 32767
    np.savez_compressed(out_npz, onsets=np.round(o / scale).astype(np.int16), scale=scale)
    print("bow off: median %.2f s (%.2f-%.2f); handed over by the recording at %.2f s at most" % (
        np.median([c["t_off"] for c in cells]), min(c["t_off"] for c in cells), max(c["t_off"] for c in cells), MAX_HAND))


if __name__ == "__main__":
    main()
