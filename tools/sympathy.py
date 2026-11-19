#!/usr/bin/env python3
"""Do the cello's open strings ring along? Measured in the staccatos' releases.

    python3 -I tools/sympathy.py <bigcat checkout> [--json out.json]

When the bow leaves a staccato, each harmonic rings down at its string's own rate (tools/analyze.py's
release). A harmonic at the frequency of an open string's partial (C2 G2 D3 A3, partials 1-20, within
±15 cents) has a free string beside it, driven through the bridge while the note sounded: if it rings
along, that harmonic decays slower than its neighbours in the same octave band, and its last part
(36-50 dB down) holds more of it. Per staccato, per harmonic: the decay rate (dB/s, from 6 dB under
the peak to 36 dB, as the release) and the level 0.3 and 0.8 s after the 36 dB point against the note's peak.
The note's own open string is left out (a note on an open string is that string).

Prints, per band, the median decay rate of harmonics on an open string's partial against those that
aren't, and how many staccatos each comes from.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

OPEN = [36, 43, 50, 57]
TOL_C = 15.0


def on_open(f, own_midi):
    for o in OPEN:
        if abs(own_midi - o) < 0.5:
            continue
        f0 = C.mtof(o)
        k = max(1, round(f / f0))
        if k <= 20 and abs(1200 * np.log2(f / (k * f0))) < TOL_C:
            return True
    return False


def decays(path, midi):
    x, sr = C.load(path)
    an = H.analyse(x, sr, C.mtof(midi), kmax=30, fmax=6000)
    p = 2 * np.abs(an["a"])
    E = np.sqrt(np.sum(p ** 2, axis=0) / 2)
    Edb = 20 * np.log10(E + 1e-12)
    ip = int(np.argmax(Edb))
    after = np.arange(len(E)) > ip
    i6 = np.where(after & (Edb < Edb[ip] - 6))[0]
    i36 = np.where(after & (Edb < Edb[ip] - 36))[0]
    if not len(i6) or not len(i36) or i36[0] - i6[0] < int(0.05 * sr):
        return []
    t = np.arange(i6[0], i36[0], int(0.005 * sr))
    late = i36[0] + int(0.3 * sr)
    later = i36[0] + int(0.8 * sr)
    out = []
    for k in range(an["K"]):
        lv = 20 * np.log10(p[k, t] + 1e-12)
        if lv[0] < Edb[ip] - 45:
            continue
        ok = lv > lv[0] - 40
        if ok.sum() < 6:
            continue
        rate = -np.polyfit(t[ok] / sr, lv[ok], 1)[0]
        f = (k + 1) * an["fmed"]
        tail = float(20 * np.log10(p[k, late] + 1e-12) - Edb[ip]) if late < p.shape[1] else None
        tail2 = float(20 * np.log10(p[k, later] + 1e-12) - Edb[ip]) if later < p.shape[1] else None
        out.append(dict(k=k + 1, f=float(f), rate=float(rate), tail=tail, tail2=tail2, open=on_open(f, midi)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--json")
    a = ap.parse_args()
    rows = []
    for s in A.staccatos(a.root):
        for h in decays(s["path"], s["midi"]):
            h.update(midi=s["midi"], dyn=s["dyn"])
            rows.append(h)
    print("band (Hz)     on an open string's partial      elsewhere            ratio")
    for lo in (62.5, 125, 250, 500, 1000, 2000):
        R = [r for r in rows if lo <= r["f"] < 2 * lo]
        on = [r["rate"] for r in R if r["open"]]
        off = [r["rate"] for r in R if not r["open"]]
        if len(on) < 5 or len(off) < 5:
            continue
        print("%5.0f-%5.0f   %6.1f dB/s (n %4d)        %6.1f dB/s (n %4d)   %.2f" % (
            lo, 2 * lo, np.median(on), len(on), np.median(off), len(off), np.median(on) / np.median(off)))
    on_t = [r["tail"] for r in rows if r["open"] and r["tail"] is not None]
    off_t = [r["tail"] for r in rows if not r["open"] and r["tail"] is not None]
    print("level 0.3 s after the note is 36 dB down, against its peak: on %.1f dB (n %d), elsewhere %.1f dB (n %d)" % (
        np.median(on_t), len(on_t), np.median(off_t), len(off_t)))
    # the ringing's own decay: where a harmonic on an open string's partial is still 6 dB over the
    # others' late level at 0.3 s, its fall from 0.3 to 0.8 s
    floor = np.median(off_t)
    for lo in (62.5, 250, 1000):
        R = [r for r in rows if r["open"] and lo <= r["f"] < 4 * lo and r["tail"] is not None and r["tail2"] is not None
             and r["tail"] > floor + 6]
        if len(R) >= 5:
            print("ringing at %4.0f-%4.0f Hz: falls %.1f dB/s (n %d)" % (lo, 4 * lo, np.median([(r["tail"] - r["tail2"]) / 0.5 for r in R]), len(R)))
    if a.json:
        json.dump(rows, open(a.json, "w"))


if __name__ == "__main__":
    main()
