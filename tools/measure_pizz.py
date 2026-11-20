#!/usr/bin/env python3
"""The pizzicato against its recordings: every plucked note and round robin, rendered and compared.

    python3 -I tools/measure_pizz.py <bigcat checkout> build/strings_render [--json out.json] [id=value ...]

Each of the 13 notes is played four times on its key (Articulation Pizzicato, velocity 127, which
plays a take at its recorded level; Even Notes off; dry), so each key's round robins come in order and
each render is compared with its own take over 0-3 s by the perceptual distance (tools/perceptual.py):

  score       the render against its recording (attack 0-80 ms, early 80-500 ms, sustain 0.5-3 s)
  other take  the next round robin's recording against it: the same note plucked again, the yardstick
  hand-off    the largest difference of the 10 ms level, render against recording, over 0.04-0.2 s (dB):
              the crossfade from the recorded pluck to the modes is at 0.06-0.10 s
  decay       the level 0.5 s and 1 s after the hand-off, against 0.1 s, in the render minus the
              recording (dB): how well the modes ring down
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import measure as Me  # noqa: E402
import perceptual as P  # noqa: E402
import pizz as PZ  # noqa: E402

GAP = 4.0       # seconds between the plucks of one key
HOLD = 3.6
LEN = 3.0


def render_key(tool, midi, n, tmp, params):
    ev = []
    for i in range(n):
        ev += [dict(t=i * GAP, on=int(midi), vel=127), dict(t=i * GAP + HOLD, off=int(midi))]
    pr = dict(C.DRY, **{"play.articulation": 1.0, "play.even": 0.0})
    pr.update(params)
    sc = dict(patch="init", sampleRate=Me.SR, length=n * GAP, params=pr, events=ev)
    js, wav = os.path.join(tmp, "pz_%d.json" % midi), os.path.join(tmp, "pz_%d.wav" % midi)
    with open(js, "w") as f:
        json.dump(sc, f)
    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav, always_2d=True)
    y = y.mean(axis=1) * 10 ** (-Me.TRIM_DB / 20)
    return [y[int(i * GAP * sr):int((i * GAP + LEN) * sr)] for i in range(n)]


def level_db(y, sr, t, win=0.01):
    i = int(t * sr)
    seg = y[max(0, i - int(win * sr / 2)):i + int(win * sr / 2)]
    return 10 * np.log10(np.mean(seg ** 2) + 1e-20)


def pad(x, n):
    return np.concatenate([x[:n], np.zeros(max(0, n - len(x)))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("tool")
    ap.add_argument("--json")
    ap.add_argument("params", nargs="*", help="id=value, for every render")
    a = ap.parse_args()
    params = {k: float(v) for k, v in (p.split("=") for p in a.params)}
    fl = PZ.files(a.root)
    notes = sorted({q["midi"] for q in fl})
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for m in notes:
            takes = [q for q in fl if q["midi"] == m]
            ys = render_key(a.tool, m, len(takes), tmp, params)
            xs = [C.load(q["path"])[0] for q in takes]
            sr = Me.SR
            for i, (q, x, y) in enumerate(zip(takes, xs, ys)):
                n = int(LEN * sr)
                x, y = pad(x, n), pad(y, n)
                xo = pad(xs[(i + 1) % len(xs)], n)
                Nr = P.loudness(x, sr, LEN)
                r = dict(note=C.note_name(m), midi=m, rr=q["rr"], score=P.distance(Nr, P.loudness(y, sr, LEN)),
                         other=P.distance(Nr, P.loudness(xo, sr, LEN)))
                tt = np.arange(0.04, 0.2, 0.005)
                r["handoff"] = float(np.max(np.abs([level_db(y, sr, t) - level_db(x, sr, t) for t in tt])))
                ref = level_db(y, sr, 0.2, 0.05) - level_db(x, sr, 0.2, 0.05)
                r["decay"] = [float(level_db(y, sr, 0.1 + d, 0.05) - level_db(x, sr, 0.1 + d, 0.05) - ref)
                              if 0.1 + d < len(xs[i]) / sr - 0.05 else None for d in (0.5, 1.0)]
                rows.append(r)
                print("%-4s rr %d  score %5.1f (attack %4.1f early %4.1f sustain %4.1f)  other take %5.1f  "
                      "hand-off %4.1f dB  decay %s" % (
                          r["note"], r["rr"], r["score"]["score"], r["score"]["attack"], r["score"]["early"],
                          r["score"]["sustain"], r["other"]["score"], r["handoff"],
                          " ".join("%+.1f" % d if d is not None else "  -" for d in r["decay"])), flush=True)
    print("\nmedian %: score / attack / early / sustain")
    for k in ("score", "other"):
        print("  %-10s %5.1f  %5.1f %5.1f %5.1f" % (k, *[np.median([r[k][w] for r in rows])
                                                    for w in ("score", "attack", "early", "sustain")]))
    d5 = [r["decay"][0] for r in rows if r["decay"][0] is not None]
    d10 = [r["decay"][1] for r in rows if r["decay"][1] is not None]
    print("hand-off: largest level difference 0.04-0.2 s, median %.1f dB (worst %.1f)" % (
        np.median([r["handoff"] for r in rows]), max(r["handoff"] for r in rows)))
    print("decay, render minus recording: at +0.5 s median %+.1f dB (abs %.1f), at +1 s %+.1f (abs %.1f)" % (
        np.median(d5), np.median(np.abs(d5)), np.median(d10), np.median(np.abs(d10))))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rows, f, indent=1)


if __name__ == "__main__":
    main()
