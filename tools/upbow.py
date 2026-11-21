#!/usr/bin/env python3
"""The up-bow onsets: each cell's up-bow take, measured as the down-bow onsets are.

    python3 -I tools/upbow.py <bigcat checkout> tools/upbow.json tools/upbow_onsets.npz   # ~3 min
    python3 -I tools/make_upbow_header.py tools/upbow.json tools/upbow_onsets.npz src/UpbowData.h

bigcat bows every sustain both ways. The engine played only the down-bow onsets, so a repeated note
started with the same recording every time; with Bowing at Alternate, every other bow starts from
the up-bow take (src/UpbowData.h). Per cell: the take's first 0.4 s, its pitch, level and each
harmonic's level and phase at the hand-off (tools/analyze.py's `sustain_data`, unchanged). The
sustain after the hand-off is still the cell's own (the down-bow fit and corrections).

Up-bow takes dip more than the down-bow ones (tools/onset_choice.py): the same test picks the take.
A take whose level falls more than DIP_MAX dB within its first 0.4 s plays the same note's up-bow
take at a neighbouring dynamic falling less than DIP_OK (one layer away at most: further, a p note
would start with an f attack), else the cell has no up-bow onset and plays its down-bow onset for
either bow. Each take is stored once (`takes`); cells point at theirs.
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import common as C  # noqa: E402
from onset_choice import DIP_MAX, DIP_OK, dip  # noqa: E402


def main():
    root, out_json, out_npz = sys.argv[1:4]
    ups = {(s["midi"], s["dyn"]): s for s in C.sustains(root) if s["bow"] == "g"}
    dips = {k: dip(*C.load(s["path"])) for k, s in ups.items()}
    notes = sorted({m for m, _ in ups})
    cells, onsets, measured, index = [], [], {}, {}
    for m in notes:
        for d in C.DYNAMICS:
            use = d if dips.get((m, d), 99) <= DIP_MAX else None
            if use is None:
                i = C.DYNAMICS.index(d)
                cands = [(abs(C.DYNAMICS.index(e) - i), dips[(m, e)], e) for e in C.DYNAMICS
                         if (m, e) in dips and dips[(m, e)] < DIP_OK and abs(C.DYNAMICS.index(e) - i) == 1]
                use = min(cands)[2] if cands else None
            if use is not None and (m, use) not in measured:
                cell, onset, sr = A.sustain_data(ups[(m, use)])
                measured[(m, use)] = (cell, onset, sr)
                index[(m, use)] = len(onsets)
                onsets.append(onset)
            if use is None:
                cells.append(dict(midi=m, dyn=d, take=None, index=-1))
                print("  %s %-2s up-bow falls %.1f dB, none steady: the down-bow onset" % (
                    C.note_name(m), d, dips.get((m, d), np.nan)), flush=True)
                continue
            cell, onset, sr = measured[(m, use)]
            c = {k: cell[k] for k in ("level", "hand_f0", "hand_db", "hand_phase", "K")}
            c.update(midi=m, dyn=d, take=use, dip=dips[(m, use)], index=index[(m, use)])
            cells.append(c)
            print("  %s %-2s up-bow take %-2s (falls %.1f dB), level %.1f dB, f0 at hand-off %.2f Hz" % (
                C.note_name(m), d, use, dips[(m, use)], c["level"], c["hand_f0"]), flush=True)
    with open(out_json, "w") as f:
        json.dump(dict(notes=notes, dynamics=C.DYNAMICS, onset_rate=sr, cells=cells), f)
    np.savez_compressed(out_npz, onsets=np.array(onsets, np.float32))
    print("%d of %d cells have an up-bow onset, from %d takes" % (
        sum(c["take"] is not None for c in cells), len(cells), len(onsets)))


if __name__ == "__main__":
    main()
