#!/usr/bin/env python3
"""Which recording each cell's onset comes from: its own down-bow take, unless that take's bow bounced.

    python3 -I tools/onset_choice.py <bigcat checkout> tools/onset_choice.json

A note's first 0.4 s is played from its down-bow recording (the down-bow onsets are the steadier of
the two: up-bow takes dip more in most cells). A few takes bounce: the level falls and comes back
within the first 0.4 s, which the owner heard on F4-A4 at mf as "the bow bounced a little" (F#4 mf's
take dips 7 dB at 0.08 and 0.22 s). Per take, the deepest fall below the level reached so far over
0.05-0.40 s (10 ms windows). A down-bow take falling more than DIP_MAX dB is replaced by the same
note's take at the nearest dynamic that falls less than DIP_OK (fewer dB first when two are as
near); the engine plays it at the cell's own level, and the sustain is still the cell's own.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

DIP_MAX = 5.5
DIP_OK = 4.0


def dip(x, sr):
    h = int(0.01 * sr)
    e = np.sqrt(np.convolve(x * x, np.ones(h) / h, "same"))[::h]
    seg = 20 * np.log10(e[5:40] + 1e-9)
    return float(np.max(np.maximum.accumulate(seg) - seg))


def main():
    root, out = sys.argv[1:3]
    dips = {}
    for s in C.sustains(root):
        if s["bow"] == "d":
            dips[(s["midi"], s["dyn"])] = dip(*C.load(s["path"]))
    choice = {}
    for (m, d), v in sorted(dips.items()):
        if v <= DIP_MAX:
            continue
        i = C.DYNAMICS.index(d)
        cands = [(abs(C.DYNAMICS.index(e) - i), dips[(m, e)], e) for e in C.DYNAMICS
                 if e != d and dips[(m, e)] < DIP_OK]
        if cands:
            alt = min(cands)[2]
            choice["%d_%s" % (m, d)] = alt
            print("%s %s: its take falls %.1f dB; plays %s's (%.1f)" % (C.note_name(m), d, v, alt, dips[(m, alt)]))
    with open(out, "w") as f:
        json.dump(choice, f, indent=1)


if __name__ == "__main__":
    main()
