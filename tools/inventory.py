#!/usr/bin/env python3
"""What the bigcat cello's recordings hold (Phase 0).

    python3 -I tools/inventory.py <karoryfer-bigcat.cello checkout> [--json out.json]

For every bowed sustain: the pitch it really sounds (checks the library's note names), its tuning
against equal temperament, how steady the pitch is (any vibrato?), how long it is and how it ends
(a natural release, or cut), its level and brightness per dynamic, the recording's noise floor and
how many harmonics stand above it. Then a summary of staccato, pizzicato and the noises.
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy.signal import welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402


def steady_window(lev, times, onset_t):
    """Frames from 0.3 s after the onset to where the level last stands within 6 dB of the
    middle second's median: the part a bow sustains."""
    mid = (times > onset_t + 1.0) & (times < onset_t + 2.0)
    ref = np.median(lev[mid]) if mid.any() else np.max(lev)
    ok = np.where(lev > ref - 6)[0]
    end = times[ok[-1]] if len(ok) else times[-1]
    return onset_t + 0.3, end, ref


def modulation(f0c, hop):
    """Strongest periodic pitch modulation 3-9 Hz in a cents track (detrended): rate, depth (±c)."""
    y = f0c - np.polyval(np.polyfit(np.arange(len(f0c)), f0c, 2), np.arange(len(f0c)))
    if len(y) < 64:
        return 0.0, 0.0
    f, p = welch(y, fs=1 / hop, nperseg=min(256, len(y)))
    band = (f >= 3) & (f <= 9)
    if not band.any():
        return 0.0, 0.0
    k = np.argmax(p[band])
    rate = f[band][k]
    # depth of a sinusoid at that rate, by projection
    t = np.arange(len(y)) * hop
    a = 2 * np.abs(np.mean(y * np.exp(-2j * np.pi * rate * t)))
    return float(rate), float(a)


def analyse_sustain(s):
    x, sr = C.load(s["path"])
    i0 = C.onset(x, sr)
    f_et = C.mtof(s["midi"])
    times, f0, lev = C.track_f0(x, sr, f_et)
    t_on = i0 / sr
    a, b, ref = steady_window(lev, times, t_on)
    sel = (times >= a) & (times <= b) & np.isfinite(f0)
    f_med = float(np.median(f0[sel]))
    c = C.cents(f0[sel], f_med)
    rate, depth = modulation(c, times[1] - times[0])
    # how the file starts and ends: the first 5 ms against the sustain (trimmed at the attack?),
    # the last 0.1 s against it and the last sample against the peak (cut mid-bow, or a release?)
    head_db = 20 * np.log10(np.sqrt(np.mean(x[:int(0.005 * sr)] ** 2)) + 1e-12)
    tail_db = float(np.median(lev[times > times[-1] - 0.1]))
    last = float(abs(x[-1]) / (np.abs(x).max() + 1e-12))
    seg = x[int(a * sr):int(b * sr)]
    rms_db = 20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12)
    # brightness: spectral centroid in harmonic numbers; harmonics standing 20 dB over the floor
    nfft = 1 << 16
    S = np.abs(np.fft.rfft(seg[:nfft] * np.hanning(min(nfft, len(seg))), nfft)) ** 2
    fr = np.arange(len(S)) * sr / nfft
    hs, hp = [], []
    for k in range(1, 400):
        fk = k * f_med
        if fk > sr / 2 - 500:
            break
        j = int(round(fk * nfft / sr))
        w = max(2, int(0.02 * f_med * nfft / sr))
        hp.append(S[j - w:j + w + 1].max())
        hs.append(k)
    hp = np.array(hp)
    hp_db = 10 * np.log10(hp + 1e-30)
    between = np.median(10 * np.log10(S[(fr > 50) & (fr < 16000)] + 1e-30))
    n_harm = int(np.sum(hp_db > between + 20))
    centroid = float(np.sum(np.array(hs) * hp) / np.sum(hp))
    return dict(file=os.path.basename(s["path"]), name=s["name"], midi=s["midi"],
                note=C.note_name(s["midi"]), dyn=s["dyn"], bow=s["bow"],
                dur=round(len(x) / sr, 2), onset=round(t_on, 3),
                steady=[round(a, 2), round(float(b), 2)],
                f0=round(f_med, 3), et_cents=round(float(C.cents(f_med, f_et)), 1),
                octave_check=round(float(C.cents(f_med, f_et) / 1200)),
                pitch_rms_c=round(float(np.std(c)), 2), mod_rate=round(rate, 2),
                mod_depth_c=round(depth, 2), drift_c=round(float(c[-20:].mean() - c[:20].mean()), 1),
                rms_db=round(float(rms_db), 1), head_db=round(float(head_db - rms_db), 1),
                last_sample=round(last, 3),
                tail_vs_steady_db=round(tail_db - ref, 1),
                harmonics=n_harm, centroid_h=round(centroid, 2))


def release_rate(x, sr):
    h = int(0.01 * sr)
    e = np.array([20 * np.log10(np.sqrt(np.mean(x[i:i + h] ** 2)) + 1e-12) for i in range(0, len(x) - h, h)])
    k = int(np.argmax(e))
    t = np.arange(len(e)) * 0.01
    sel = (np.arange(len(e)) > k) & (e < e[k] - 6) & (e > e[k] - 30)
    if sel.sum() < 4:
        return None
    return float(-np.polyfit(t[sel], e[sel], 1)[0])


def summarise_group(root, sub):
    d = os.path.join(root, "Samples", sub)
    fs = sorted(f for f in os.listdir(d) if f.endswith(".wav"))
    durs, rel = [], []
    for f in fs:
        x, sr = C.load(os.path.join(d, f))
        durs.append(len(x) / sr)
        if sub != "noises":
            r = release_rate(x, sr)
            if r:
                rel.append(r)
    out = dict(count=len(fs), dur_min=round(min(durs), 2), dur_max=round(max(durs), 2), files=fs)
    if rel:
        out["release_db_s"] = [round(float(np.percentile(rel, q)), 1) for q in (10, 50, 90)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = [analyse_sustain(s) for s in C.sustains(a.root)]
    print("Bowed sustains: %d files, %d notes, dynamics %s, bows %s" % (
        len(rows), len({r["midi"] for r in rows}), sorted({r["dyn"] for r in rows}, key=C.DYNAMICS.index),
        sorted({r["bow"] for r in rows})))
    print("octave check (sounding vs named + offset): %s" % sorted({r["octave_check"] for r in rows}))
    hdr = "%-7s %-4s %-3s %-2s %5s %6s %7s %7s %6s %6s %6s %6s %6s %5s %6s" % (
        "file", "note", "dyn", "bw", "dur", "ET c", "pitch", "mod Hz", "±c", "drift", "rms", "head",
        "tail", "harm", "cent")
    print(hdr)
    for r in rows:
        print("%-7s %-4s %-3s %-2s %5.2f %6.1f %7.2f %7.2f %6.2f %6.1f %6.1f %6.1f %6.1f %5d %6.2f" % (
            r["name"], r["note"], r["dyn"], r["bow"], r["dur"], r["et_cents"], r["pitch_rms_c"],
            r["mod_rate"], r["mod_depth_c"], r["drift_c"], r["rms_db"], r["head_db"],
            r["tail_vs_steady_db"], r["harmonics"], r["centroid_h"]))
    by = {d: [r for r in rows if r["dyn"] == d] for d in C.DYNAMICS}
    print("\nper dynamic (median): level dBFS, centroid (harmonic no.), harmonics over floor, pitch rms c")
    for d, rs in by.items():
        print("  %-3s %6.1f %6.2f %5.0f %6.2f" % (d, np.median([r["rms_db"] for r in rs]),
              np.median([r["centroid_h"] for r in rs]), np.median([r["harmonics"] for r in rs]),
              np.median([r["pitch_rms_c"] for r in rs])))
    print("all: tuning %+.1f c median (%.1f..%.1f), modulation depth median ±%.2f c (max ±%.2f), "
          "first 5 ms vs sustain median %.1f dB, last 0.1 s vs sustain median %.1f dB, "
          "last sample over 5 %% of peak in %d of %d files" % (
              np.median([r["et_cents"] for r in rows]), min(r["et_cents"] for r in rows),
              max(r["et_cents"] for r in rows), np.median([r["mod_depth_c"] for r in rows]),
              max(r["mod_depth_c"] for r in rows), np.median([r["head_db"] for r in rows]),
              np.median([r["tail_vs_steady_db"] for r in rows]),
              sum(r["last_sample"] > 0.05 for r in rows), len(rows)))
    groups = {g: summarise_group(a.root, g) for g in ("staccato", "pizzcato", "noises")}
    for g, v in groups.items():
        print("%s: %d files, %.2f-%.2f s%s" % (g, v["count"], v["dur_min"], v["dur_max"],
              "; decay after the peak %s dB/s (10/50/90 %%)" % v["release_db_s"] if "release_db_s" in v else ""))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(sustains=rows, groups=groups), f, indent=1)


if __name__ == "__main__":
    main()
