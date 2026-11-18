#!/usr/bin/env python3
"""Calibrate the bow noise: the renders' residual should measure as the recordings' does.

    python3 -I tools/calibrate_noise.py build/strings_render tools/cello.json tools/noise_adjust.json

tools/analyze.py reads the noise as the residual once the harmonics are taken out, and its
harmonics (heterodyned over 3 periods) take in the noise within about ±1/3 of the harmonic spacing:
on low notes, where the harmonics are 65 Hz apart, most of it. The stored levels are low by that much
(7-8 dB at C2, nothing above F#5), and the engine, which plays them faithfully, measures low by it
again. As the piano's calibrate_noise.py does, this renders every cell (as recorded: its middle
velocity, held), measures its residual the same way, and moves a correction per cell and band
(0.8 of the difference per pass) that tools/make_header.py adds to the targets before its solve.
Two or three passes, with make_header.py and a build between.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

VEL = {"p": 16, "mp": 48, "mf": 80, "f": 112}


def residual_bands(tool, midi, vel, tmp):
    sc = dict(patch="init", sampleRate=44100, length=3.4,
              events=[dict(t=0, on=int(midi), vel=int(vel)), dict(t=3.2, off=int(midi))])
    js, wav = os.path.join(tmp, "s.json"), os.path.join(tmp, "s.wav")
    with open(js, "w") as f:
        json.dump(sc, f)
    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav, always_2d=True)
    y = y.mean(axis=1)
    an = H.analyse(y, sr, C.mtof(midi), kmax=A.KMAX, fmax=A.FMAX)
    p = 2 * np.abs(an["a"])
    E = np.sqrt(np.sum(p ** 2, axis=0) / 2)
    i0, i1 = int(0.6 * sr), int(3.0 * sr)
    return np.array(A.band_powers_db(an["resid"][i0:i1], sr)) - 20 * np.log10(np.median(E[i0:i1]))


def main():
    tool, js, adj_path = sys.argv[1:4]
    d = json.load(open(js))
    adj = json.load(open(adj_path)) if os.path.exists(adj_path) else {}
    errs = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in d["cells"]:
            key = "%d_%s" % (c["midi"], c["dyn"])
            meas = residual_bands(tool, c["midi"], VEL[c["dyn"]], tmp)
            diff = np.array(c["noise"]) - meas
            errs.append(diff)
            old = np.array(adj.get(key, [0.0] * len(diff)))
            adj[key] = np.clip(old + 0.8 * diff, -20, 20).tolist()
    errs = np.array(errs)
    print("before this pass, recording − render per band (dB, median over cells): %s; median |·| %.1f dB" % (
        " ".join("%+.1f" % v for v in np.median(errs, axis=0)), np.median(np.abs(errs))))
    with open(adj_path, "w") as f:
        json.dump(adj, f)


if __name__ == "__main__":
    main()
