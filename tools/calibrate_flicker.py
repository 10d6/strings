#!/usr/bin/env python3
"""Calibrate the harmonics' movement by what the ear hears: how each band's level moves.

    python3 -I tools/calibrate_flicker.py <bigcat checkout> build/strings_render tools/flicker_adjust.json

The harmonics' movement is measured per harmonic in dB (tools/life.py), and on a weak harmonic the
noise around it makes that reading jumpy: the recording's band moves much less than its weak
harmonics seem to. Played as measured, C3's upper band (2-8 kHz) swelled 2.6× and fluttered 2× as
much as its recordings' (the owner heard fast muting of the highs at 15-20 Hz, with dips about once
a second). So per cell (note and dynamic) this renders the note (its middle velocity, held), takes
the level of two bands (0.5-2 and 2-8 kHz) every 5 ms, and compares how much it moves (0.25-25 Hz,
dB rms) with the cell's two recordings (down and up bow); a gain per cell on the harmonics' movement
(0.8 of the ratio per pass, held within 0.2-2×) that tools/make_header.py applies. Two or three
passes, make_header.py and a build between. `--report` only measures.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt, welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

VEL = {"p": 16, "mp": 48, "mf": 80, "f": 112}
BANDS = [(500, 2000), (2000, 8000)]


def movement(x, sr, t0=1.0, t1=3.6):
    """dB rms of each band's level, 0.25-25 Hz."""
    t1 = min(t1, len(x) / sr - 0.15)     # some recordings are 3 s long
    seg = x[int(t0 * sr):int(t1 * sr)]
    out = []
    for lo, hi in BANDS:
        b = sosfiltfilt(butter(4, [lo, hi], "band", fs=sr, output="sos"), seg)
        h = int(0.005 * sr)
        env = np.sqrt(np.convolve(b * b, np.ones(h) / h, "same"))[::h]
        e = 20 * np.log10(env + 1e-12)
        e -= np.polyval(np.polyfit(np.arange(len(e)), e, 1), np.arange(len(e)))
        f, p = welch(e, 200, nperseg=min(256, len(e)))
        sel = (f >= 0.25) & (f < 25)
        out.append(float(np.sqrt(np.sum(p[sel]) * (f[1] - f[0]))))
    return np.array(out)


def render(tool, midi, vel, tmp):
    sc = dict(patch="init", sampleRate=44100, length=4.0,
              events=[dict(t=0, on=int(midi), vel=int(vel)), dict(t=3.8, off=int(midi))])
    js, wav = os.path.join(tmp, "s.json"), os.path.join(tmp, "s.wav")
    with open(js, "w") as f:
        json.dump(sc, f)
    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav, always_2d=True)
    return y.mean(axis=1), sr


def main():
    root, tool, adj_path = sys.argv[1:4]
    report = "--report" in sys.argv
    adj = json.load(open(adj_path)) if os.path.exists(adj_path) else {}
    sus = C.sustains(root)
    ratios = []
    with tempfile.TemporaryDirectory() as tmp:
        for m in sorted({s["midi"] for s in sus}):
            for d in C.DYNAMICS:
                rec = np.median([movement(*C.load(s["path"])) for s in sus if s["midi"] == m and s["dyn"] == d], axis=0)
                ren = movement(*render(tool, m, VEL[d], tmp))
                ratio = float(np.exp(np.mean(np.log(rec / np.maximum(ren, 1e-3)))))
                ratios.append((m, d, ratio))
                key = "%d_%s" % (m, d)
                if not report:
                    adj[key] = float(np.clip(adj.get(key, 1.0) * ratio ** 0.8, 0.2, 2.0))
    r = np.array([v for _, _, v in ratios])
    worst = sorted(ratios, key=lambda v: abs(np.log(v[2])))[-4:]
    print("bands' movement, recordings over renders: median %.2f, 10-90 %% %.2f-%.2f; furthest: %s" % (
        np.median(r), np.percentile(r, 10), np.percentile(r, 90),
        ", ".join("%s %s %.2f" % (C.note_name(m), d, v) for m, d, v in worst)))
    if not report:
        with open(adj_path, "w") as f:
            json.dump(adj, f, indent=1)


if __name__ == "__main__":
    main()
