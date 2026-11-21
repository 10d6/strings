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
KEEP = 2                # round robins kept per note and dynamic: one bowed each way where there is one
TREM_LEN = 0.2          # a tremolo grain: from where the take's stroke starts (the longest stroke, ~170 ms, and its change)
TREM_PRE = 0.002        # ... which is this long before it stands 30 dB under its peak


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
    # the tremolo (docs/TREMOLO.md): where the stroke starts, its early level, which way it was bowed, and
    # the fundamental's pitch and phase there, so the engine can line a stroke up with the one before
    on = max(0, int(np.argmax(sm > peak - 30)) - int(TREM_PRE * sr))
    early = float(10 * np.log10(np.mean(P[on + int(0.01 * sr):on + int(0.07 * sr)]) + 1e-24))
    w0, w1 = on + int(0.01 * sr), on + int(0.15 * sr)
    a1, a2 = an["a"][0, w0:w1], an["a"][1, w0:w1]
    r = a2 * np.conj(a1) ** 2
    z = np.sum(np.abs(a1) ** 2 * np.abs(a2) * r / (np.abs(r) + 1e-30))
    tf0 = float(np.median(an["f0"][on + int(0.02 * sr):on + int(0.12 * sr)]))
    ir = on + int(0.05 * sr)
    ph_ref = float(np.angle(an["a"][0, ir]) + an["phi"][ir])
    tph = float(np.mod(ph_ref - 2 * np.pi * tf0 * (ir - on) / sr, 2 * np.pi))
    env = sm[:int(0.8 * sr):int(0.005 * sr)]
    return dict(midi=s["midi"], dyn=s["dyn"], path=os.path.basename(s["path"]), level=peak, t_off=float(t_off),
                t_hand=float(t_h), fade=fade, hand_f0=hf0, hand_db=hdb.tolist(), hand_ph=hph.tolist(),
                t_sp=t_sp, sp_level=float(sm[int(tc_sp * sr)]), sp_f0=sf0, sp_db=sdb.tolist(), sp_ph=sph.tolist(),
                K=int(an["K"]), rel=rel, env=env.tolist(), rr=int(s["path"][-5]), t_on=on / sr, early=early,
                dirz=[float(z.real), float(z.imag)], t_f0=tf0, t_ph=tph), x[:int(round(ONSET_LEN * sr))], sr


def main():
    root, out_json, out_npz = sys.argv[1:4]
    takes = A.staccatos(root)
    with Pool(2) as pool:
        res = pool.map(take_data, takes)
    notes = sorted({r["midi"] for r, _, _ in res})
    sr = res[0][2]
    # which way each take was bowed: a bow change turns the string's motion over, which flips the 2nd
    # harmonic's phase against the fundamental's (docs/TREMOLO.md). Per note, the two states are read
    # against all its takes; "+" is the one the first round robins mostly have (bigcat alternates its
    # round robins' bows, though not always from the same one)
    for m in notes:
        rs = [r for r, _, _ in res if r["midi"] == m]
        zs = [complex(*r["dirz"]) for r in rs]
        th = np.angle(np.sum([z * z / (abs(z) + 1e-30) for z in zs])) / 2
        cs = [np.cos(np.angle(z) - th) for z in zs]
        odd = np.mean([c for c, r in zip(cs, rs) if r["rr"] % 2 == 1])
        for c, r in zip(cs, rs):
            r["dir"] = int(np.sign(c * (1 if odd >= 0 else -1)) or 1)
            r["dir_sure"] = float(abs(c))
    cells, onsets, levels, trem, extras = [], [], {}, [], []
    early_all = []
    for m in notes:
        for d in C.DYNAMICS:
            rs = [(r, o) for r, o, _ in res if r["midi"] == m and r["dyn"] == d]
            n = min(len(e["env"]) for e, _ in rs)
            envs = np.array([e["env"][:n] for e, _ in rs])
            med = np.median(envs, axis=0)
            dist = np.sqrt(np.mean((envs - med) ** 2, axis=1))
            order = list(np.argsort(dist))
            levels[(m, d)] = float(np.median([r["level"] for r, _ in rs]))
            # the staccato keeps the closest take bowed each way (repeated staccatos alternate bows), or
            # the closest two where every take reads the same way
            kept = []
            for want in (1, -1):
                j = next((j for j in order if rs[j][0]["dir"] == want and j not in kept), None)
                if j is not None:
                    kept.append(j)
            for j in order:
                if len(kept) < KEEP and j not in kept:
                    kept.append(j)
            base = len(onsets)
            for j in kept:
                r, o = rs[j]
                r = dict(r)
                r.pop("env")
                r["dist"] = float(dist[j])
                cells.append(r)
                onsets.append(np.pad(o, (0, max(0, int(round(ONSET_LEN * sr)) - len(o)))))
            # the tremolo plays every take: the kept ones from their onsets, the others as grains of their own
            cell_trem = []
            for j in order:
                r, o = rs[j]
                if j in kept:
                    src = base + kept.index(j)
                    start = int(round(r["t_on"] * sr))
                    avail = len(onsets[src]) - start
                else:
                    src = -1 - len(extras)
                    g = o[int(round(r["t_on"] * sr)):]
                    g = g[:int(round(TREM_LEN * sr))]
                    extras.append(np.pad(g, (0, int(round(TREM_LEN * sr)) - len(g))))
                    start, avail = 0, len(g)
                cell_trem.append(dict(src=src, start=start, avail=avail, dir=r["dir"], sure=r["dir_sure"],
                                      early=r["early"], f0=r["t_f0"], ph=r["t_ph"], level=r["level"], path=r["path"]))
                early_all.append(r["level"] - r["early"])
            trem.append(cell_trem)
            print("  %-4s %-2s level %.1f dB; kept %s (envelope %.1f, %.1f dB from the median; bowed %s); bow off %s s; "
                  "spiccato %s s; tremolo %d takes (%s)" % (
                      C.note_name(m), d, levels[(m, d)], ", ".join(rs[j][0]["path"] for j in kept),
                      dist[kept[0]], dist[kept[1]], "/".join("%+d" % rs[j][0]["dir"] for j in kept),
                      "/".join("%.2f" % rs[j][0]["t_off"] for j in kept),
                      "/".join("%.3f" % rs[j][0]["t_sp"] for j in kept), len(cell_trem),
                      " ".join("%+d" % t["dir"] for t in cell_trem)), flush=True)
    # a tremolo stroke's level: its early level (10-70 ms in: a tremolo's strokes never get further), which
    # the engine plays at a held note's level for the dynamic (a staccato's early part is ~11 dB under its
    # peak, about at a held note's); each take keeps ±1.5 dB of its own against its note and dynamic's median
    off = float(np.median(early_all))
    for cell_trem in trem:
        cm = float(np.median([t["early"] for t in cell_trem]))
        for t in cell_trem:
            t["ref"] = cm + float(np.clip(t["early"] - cm, -1.5, 1.5))
    data = dict(notes=notes, dynamics=C.DYNAMICS, keep=KEEP, onset_rate=sr, onset_len=ONSET_LEN, xf=XF,
                sp_xf=SP_XF, levels=[[levels[(m, d)] for d in C.DYNAMICS] for m in notes], cells=cells,
                trem=trem, trem_len=TREM_LEN)
    with open(out_json, "w") as f:
        json.dump(data, f)
    o, g = np.array(onsets), np.array(extras)
    scale = max(float(np.max(np.abs(o))), float(np.max(np.abs(g)))) / 32767
    np.savez_compressed(out_npz, onsets=np.round(o / scale).astype(np.int16), trem=np.round(g / scale).astype(np.int16),
                        scale=scale)
    sure = [t["sure"] for c in trem for t in c]
    print("tremolo: %d takes, %d as grains of their own; bowed each way: %d / %d; read unclear (|cos| < 0.5): %d; "
          "early level %.1f dB under the peak (median)" % (len(sure), len(extras), sum(t["dir"] > 0 for c in trem for t in c),
                                                         sum(t["dir"] < 0 for c in trem for t in c), sum(v < 0.5 for v in sure), off))
    print("bow off: median %.2f s (%.2f-%.2f); handed over by the recording at %.2f s at most" % (
        np.median([c["t_off"] for c in cells]), min(c["t_off"] for c in cells), max(c["t_off"] for c in cells), MAX_HAND))


if __name__ == "__main__":
    main()
