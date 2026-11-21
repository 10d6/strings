#!/usr/bin/env python3
"""The tremolo's rhythm, its dips at the changes and its level, rendered (docs/TREMOLO.md).

    python3 -I tools/measure_trem.py build/strings_render [id=value ...]

A tremolo has no recording to compare with in these libraries, and its strokes follow random paths, so
this reads statistics: strokes per second, how much their lengths vary (sd, as a share of the median),
whether a long stroke is followed by a short one (lag-1 correlation), the level dip at each change, and
the tremolo's rms against a held note's at the same velocity. The reference is a solo cellist's (the
Philharmonia Orchestra's free cello tremolos, measured only; their licence lets nothing of them ship):
12-13.5 strokes a second, lengths 12-18 % sd, lag-1 -0.15 to -0.36, dips 6-10 dB.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf
from scipy.signal import butter, find_peaks, sosfiltfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

NOTES = [36, 43, 49, 55, 63, 70, 81]
HOLD = 3.5


def render(exe, notes, art, vel, extra, tmp):
    params = dict(C.DRY)
    params["play.articulation"] = art
    params.update(extra)
    sc = dict(patch="init", sampleRate=44100, length=HOLD + 1.5, params=params,
              events=[dict(t=0, on=n, vel=vel) for n in notes] + [dict(t=HOLD, off=n) for n in notes])
    js, wav = os.path.join(tmp, "t.json"), os.path.join(tmp, "t.wav")
    with open(js, "w") as f:
        json.dump(sc, f)
    subprocess.run([exe, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav)
    return y.mean(axis=1), sr


def strokes(y, sr):
    """the changes: the level's dips (as the solo recordings were read)"""
    e = 10 * np.log10(np.maximum(sosfiltfilt(butter(2, 40, "lowpass", fs=sr, output="sos"), y * y), 0) + 1e-12)
    d, _ = find_peaks(-e, distance=int(0.045 * sr), prominence=1.5)
    e2 = sosfiltfilt(butter(2, 150, "lowpass", fs=sr, output="sos"), np.abs(y))
    d = np.array([i - 200 + np.argmin(e2[max(i - 200, 0):i + 200]) for i in d])
    depth = [np.max(e[max(0, i - int(0.03 * sr)):i + int(0.03 * sr)]) - e[i] for i in d]
    return d, depth


def main():
    exe = sys.argv[1]
    extra = dict(a.split("=", 1) for a in sys.argv[2:])
    extra = {k: float(v) for k, v in extra.items()}
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for n in NOTES:
            for vel in (60, 110):
                y, sr = render(exe, [n], 4, vel, extra, tmp)
                held = y[int(0.1 * sr):int((HOLD - 0.05) * sr)]
                d, depth = strokes(held, sr)
                g = np.diff(d) / sr
                g = g[(g > 0.03) & (g < 0.25)]
                r = g / np.median(g) - 1
                a, _ = render(exe, [n], 0, vel, extra, tmp)
                rms = lambda z: 10 * np.log10(np.mean(z[int(0.3 * sr):int(1.8 * sr)] ** 2))  # noqa: E731
                rows.append(dict(note=n, vel=vel, rate=len(g) / (HOLD - 0.15), sd=100 * np.std(r),
                                 lag1=float(np.corrcoef(r[:-1], r[1:])[0, 1]), dip=float(np.median(depth)),
                                 level=rms(y) - rms(a)))
                print("  %-4s vel %3d  %.1f strokes/s, lengths sd %4.1f %%, lag-1 %+.2f, dip %.1f dB, rms against a held note %+.1f dB"
                      % (C.note_name(n), vel, rows[-1]["rate"], rows[-1]["sd"], rows[-1]["lag1"], rows[-1]["dip"], rows[-1]["level"]))
    med = {k: float(np.median([r[k] for r in rows])) for k in ("rate", "sd", "lag1", "dip", "level")}
    print("median: %.1f strokes/s, lengths sd %.1f %%, lag-1 %+.2f, dip %.1f dB, rms against a held note %+.1f dB"
          % (med["rate"], med["sd"], med["lag1"], med["dip"], med["level"]))
    print("a solo cellist (Philharmonia): 12-13.5 strokes/s, sd 12-18 %, lag-1 -0.15 to -0.36, dips 6-10 dB")


if __name__ == "__main__":
    main()
