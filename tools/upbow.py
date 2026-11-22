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
either bow. Each take is stored once per dynamic it plays at (`takes`); cells point at theirs.

**Levelled attacks** (a judgment, from the owner's ears): this cellist's up-bows start louder against
their steady level than the down-bows (the first 0.2 s, 2.6 dB median; C3 mf 7 dB), and in repeated
notes each turn to an up-bow sounded spiky. Each up-bow take's attack (its first 0.2 s, rms, against
its steady level) is brought down by one gain to the down-bow onset the same note plays, plus LIFT dB
(a slight lift: the two directions still differ), if it was louder than that (never raised, at most
12 dB); the gain tapers to nothing by 0.30 s, before the hand-off (which is unchanged), and the
attack keeps its own shape. (Matching the level window by window, the first try, overshot: the
up-bows came out 1.8 dB under the down-bows where their attacks rise at another moment.)
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402
import common as C  # noqa: E402
from onset_choice import DIP_MAX, DIP_OK, dip  # noqa: E402

LIFT = 1.0                   # dB an up-bow's attack may stand over the down-bow's
FULL, END = 0.20, 0.30       # the attack measured over 0-FULL; the gain in full until FULL, gone at END (s)


def attack_db(x, sr, level):
    """the attack's rms (0-FULL s) against the steady level"""
    return 10 * np.log10(np.mean(x[:int(FULL * sr)] ** 2) + 1e-20) - level


def level_attack(up, up_level, down, down_level, sr):
    """the up-bow onset with its attack brought to the down-bow's + LIFT, and the cut (dB)"""
    g = float(np.clip(attack_db(down, sr, down_level) + LIFT - attack_db(up, sr, up_level), -12.0, 0.0))
    t = np.arange(len(up)) / sr
    w = np.where(t < FULL, 1.0, 0.5 + 0.5 * np.cos(np.pi * np.clip((t - FULL) / (END - FULL), 0, 1)))
    return up * 10 ** (g * w / 20), g


def main():
    root, out_json, out_npz = sys.argv[1:4]
    here = os.path.dirname(os.path.abspath(__file__))
    cello = json.load(open(os.path.join(here, "cello.json")))
    downs = np.load(os.path.join(here, "cello_onsets.npz"))
    down_on = downs["onsets"].astype(np.float64) * float(downs["scale"])
    choice = json.load(open(os.path.join(here, "onset_choice.json")))
    nD = len(cello["dynamics"])

    def down_onset(m, d):
        """the down-bow onset the cell (m, d) plays (tools/onset_choice.py may swap it), and its level"""
        e = choice.get("%d_%s" % (m, d), d)
        c = next(c for c in cello["cells"] if c["midi"] == m and c["dyn"] == e)
        return down_on[cello["notes"].index(m) * nD + cello["dynamics"].index(e)], c["level"]
    ups = {(s["midi"], s["dyn"]): s for s in C.sustains(root) if s["bow"] == "g"}
    dips = {k: dip(*C.load(s["path"])) for k, s in ups.items()}
    notes = sorted({m for m, _ in ups})
    cells, onsets, measured, index, raw = [], [], {}, {}, {}
    for m in notes:
        for d in C.DYNAMICS:
            use = d if dips.get((m, d), 99) <= DIP_MAX else None
            if use is None:
                i = C.DYNAMICS.index(d)
                cands = [(abs(C.DYNAMICS.index(e) - i), dips[(m, e)], e) for e in C.DYNAMICS
                         if (m, e) in dips and dips[(m, e)] < DIP_OK and abs(C.DYNAMICS.index(e) - i) == 1]
                use = min(cands)[2] if cands else None
            # levelled against the down-bow onset this cell plays: a take lent to a neighbouring
            # dynamic is stored again, levelled for that cell (a p cell's down-bow attack is softer)
            key = (m, use) if use == d else (m, use, d)
            if use is not None and key not in measured:
                if (m, use) not in raw:
                    raw[(m, use)] = A.sustain_data(ups[(m, use)])
                cell, onset, sr = raw[(m, use)]
                cell = dict(cell)
                dn, dn_level = down_onset(m, d)
                onset, cut = level_attack(np.asarray(onset, np.float64), cell["level"], dn, dn_level, sr)
                cell["attack_cut"] = cut
                measured[key] = (cell, onset, sr)
                index[key] = len(onsets)
                onsets.append(onset)
            if use is None:
                cells.append(dict(midi=m, dyn=d, take=None, index=-1))
                print("  %s %-2s up-bow falls %.1f dB, none steady: the down-bow onset" % (
                    C.note_name(m), d, dips.get((m, d), np.nan)), flush=True)
                continue
            cell, onset, sr = measured[key]
            c = {k: cell[k] for k in ("level", "hand_f0", "hand_db", "hand_phase", "K", "attack_cut")}
            c.update(midi=m, dyn=d, take=use, dip=dips[(m, use)], index=index[key])
            cells.append(c)
            print("  %s %-2s up-bow take %-2s (falls %.1f dB), level %.1f dB, attack cut %.1f dB" % (
                C.note_name(m), d, use, dips[(m, use)], c["level"], c["attack_cut"]), flush=True)
    with open(out_json, "w") as f:
        json.dump(dict(notes=notes, dynamics=C.DYNAMICS, onset_rate=sr, cells=cells), f)
    np.savez_compressed(out_npz, onsets=np.array(onsets, np.float32))
    cuts = [c["attack_cut"] for c in cells if c["take"] is not None]
    print("attack cut: median %.1f dB, largest %.1f" % (np.median(cuts), min(cuts)))
    print("%d of %d cells have an up-bow onset, from %d takes" % (
        sum(c["take"] is not None for c in cells), len(cells), len(onsets)))


if __name__ == "__main__":
    main()
