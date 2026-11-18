#!/usr/bin/env python3
"""Calibrate the bow's movement: the renders should measure as the recordings do.

    python3 -I tools/calibrate_life.py <life.json from tools/life.py --render> tools/life_adjust.json

tools/life.py's spectra are biased in the slowest octaves (a 3 s stretch, its trend removed, a
2.6 s window): the data is built from those readings and the renders are read the same way, so the
bias counts twice and the renders measure low there. Per quantity (pitch, level, harmonics) and
octave, this compares the medians over notes (renders against recordings) and moves the correction
that tools/make_header.py multiplies into the life tables (a power of 0.8 of the ratio per pass,
held within 0.25-4×). The piano's calibrate_noise.py does the same for its noise. Two or three
passes, with make_header.py, a build and tools/life.py --render between.
"""
import json
import os
import sys

import numpy as np


def main():
    life, adj_path = sys.argv[1:3]
    d = json.load(open(life))
    adj = json.load(open(adj_path)) if os.path.exists(adj_path) else {}
    for key, src in (("pitch", "pitch_oct"), ("level", "level_oct"), ("harm", "harm_oct")):
        rec = np.median([r[src] for r in d["recordings"]], axis=0)
        ren = np.median([r[src] for r in d["renders"]], axis=0)
        old = np.array(adj.get(key, [1.0] * len(rec)))
        ratio = np.where(ren > 1e-3, rec / np.maximum(ren, 1e-3), 1.0)
        new = np.clip(old * ratio ** 0.8, 0.25, 4.0)
        if key == "harm":   # the engine plays a harmonic's own movement up to 16 Hz only (octaves 0-5)
            new[6:] = 1.0
        adj[key] = new.tolist()
        print("%-6s recordings %s\n       renders    %s\n       adjust     %s" % (
            key, " ".join("%.2f" % v for v in rec), " ".join("%.2f" % v for v in ren),
            " ".join("%.2f" % v for v in new)))
    with open(adj_path, "w") as f:
        json.dump(adj, f, indent=1)


if __name__ == "__main__":
    main()
