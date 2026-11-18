#!/usr/bin/env python3
"""Is the hand-off from the recorded onset to the model seamless?

    python3 -I tools/handoff.py <bigcat checkout> build/strings_render [param=value ...]

For every measured note at mp and f: the lowest 10 ms level during the crossfade (0.27-0.44 s)
against the median level around it (0.18-0.26 and 0.47-0.6 s), in the render and in its recording.
The recordings dip by themselves (the bow's own movement); the render should dip no more.
The model's own movement (Life) starts after the crossfade but moves the level around it too, which
makes the measure noisier: life.amount=0 shows the hand-off alone.
"""
import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import measure as Me  # noqa: E402


def dip(y, sr=Me.SR):
    e = 20 * np.log10(Me.env(y, sr, 0.01))
    t = np.arange(len(y)) / sr
    during = e[(t > 0.27) & (t < 0.44)]
    ref = np.median(e[((t > 0.18) & (t < 0.26)) | ((t > 0.47) & (t < 0.6))])
    return float(during.min() - ref)


def main():
    root, tool = sys.argv[1:3]
    params = {k: float(v) for k, v in (a.split("=") for a in sys.argv[3:])}
    sus = C.sustains(root)
    rec, ren = [], []
    with tempfile.TemporaryDirectory() as tmp:
        for m in sorted({s["midi"] for s in sus}):
            for dyn in ("mp", "f"):
                x, sr = C.load(next(s for s in sus if s["midi"] == m and s["dyn"] == dyn and s["bow"] == "d")["path"])
                y = Me.render(tool, m, Me.VEL[dyn], tmp, length=1.0, off=0.9, params=params)
                rec.append(dip(x[:sr]))
                ren.append(dip(y))
                print("%-4s %-2s recording %5.1f  render %5.1f dB" % (C.note_name(m), dyn, rec[-1], ren[-1]))
    extra = np.array(ren) - np.array(rec)
    print("median dip: recording %.1f, render %.1f dB; the render's extra dip median %.1f, worst %.1f dB" % (
        np.median(rec), np.median(ren), np.median(extra), extra.min()))


if __name__ == "__main__":
    main()
