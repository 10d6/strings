#!/usr/bin/env python3
"""The staccato against its recordings: every kept take, rendered and compared.

    python3 -I tools/measure_stacc.py <bigcat checkout> build/strings_render [--json out.json] [id=value ...]

Each note's dynamics are played on its key, twice each (Articulation Staccato, the dynamic's velocity
as the arco measure plays them, Even Notes off, dry), so the key's two kept round robins come in order;
each render is compared with its own take over 0-1 s, or as long as the take is (the files end where
the take was cut, some mid-ring: E♭3 p at 0.53 s), by the perceptual distance (tools/perceptual.py):

  score       the render against its recording
  other take  the same note and dynamic's takes that weren't kept, against it: another stroke
  bow off     where the render has fallen 6 dB from its peak, minus where the recording has (ms)
  level       the render's peak minus the recording's (dB)
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
import analyze as A  # noqa: E402
import common as C  # noqa: E402
import measure as Me  # noqa: E402
import perceptual as P  # noqa: E402

GAP = 2.0
LEN = 1.0
VEL = {"p": 16, "mp": 48, "mf": 80, "f": 112}   # the middle of each dynamic's velocities (dynOf)


def envelope_db(y, sr):
    P_ = np.convolve(y * y, np.ones(int(0.005 * sr)) / int(0.005 * sr), "same")
    return 10 * np.log10(P_ + 1e-20)


def bow_off(y, sr):
    e = envelope_db(y, sr)
    ip = int(np.argmax(e))
    after = np.where(e[ip:] < e[ip] - 6)[0]
    return (ip + after[0]) / sr if len(after) else len(y) / sr, e[ip]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("tool")
    ap.add_argument("--json")
    ap.add_argument("--art", type=float, default=2.0, help="the Articulation index (2 Staccato)")
    ap.add_argument("params", nargs="*")
    a = ap.parse_args()
    params = {k: float(v) for k, v in (p.split("=") for p in a.params)}
    kept = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "stacc.json")))["cells"]
    takes = A.staccatos(a.root)
    rows = []
    sr = Me.SR
    with tempfile.TemporaryDirectory() as tmp:
        for m in sorted({c["midi"] for c in kept}):
            ev, order = [], []
            t = 0.0
            for d in C.DYNAMICS:
                ks = [c for c in kept if c["midi"] == m and c["dyn"] == d]
                for c in ks:
                    ev += [dict(t=t, on=int(m), vel=VEL[d]), dict(t=t + 0.05, off=int(m))]
                    order.append((t, c))
                    t += GAP
            pr = dict(C.DRY, **{"play.articulation": a.art, "play.even": 0.0})
            pr.update(params)
            sc = dict(patch="init", sampleRate=sr, length=t + 0.5, params=pr, events=ev)
            js, wav = os.path.join(tmp, "s.json"), os.path.join(tmp, "s.wav")
            json.dump(sc, open(js, "w"))
            subprocess.run([a.tool, js, "--out", wav], check=True, capture_output=True)
            y, _ = sf.read(wav, always_2d=True)
            y = y.mean(axis=1) * 10 ** (-Me.TRIM_DB / 20)
            for t0, c in order:
                path = os.path.join(a.root, "Samples", "staccato", c["path"])
                x = C.load(path)[0]
                n = min(int(LEN * sr), len(x) - int(0.01 * sr))
                x = x[:n]
                yr = y[int(t0 * sr):int(t0 * sr) + n]
                others = [s for s in takes if s["midi"] == m and s["dyn"] == c["dyn"]
                          and os.path.basename(s["path"]) not in {k["path"] for k in kept if k["midi"] == m and k["dyn"] == c["dyn"]}]
                L = n / sr
                Nr = P.loudness(x, sr, L)
                oth = []
                for s in others:
                    xo = C.load(s["path"])[0][:n]
                    oth.append(P.distance(Nr, P.loudness(np.concatenate([xo, np.zeros(n - len(xo))]), sr, L))["score"])
                ty, py = bow_off(yr, sr)
                tx, px = bow_off(x, sr)
                r = dict(note=C.note_name(m), dyn=c["dyn"], take=c["path"], score=P.distance(Nr, P.loudness(yr, sr, L)),
                         other=float(np.median(oth)) if oth else None, bow_off_ms=1000 * (ty - tx), level=float(py - px))
                rows.append(r)
                print("%-4s %-2s %-13s score %5.1f (attack %4.1f early %4.1f sustain %4.1f)  other take %5.1f  "
                      "bow off %+4.0f ms  level %+4.1f dB" % (r["note"], r["dyn"], r["take"], r["score"]["score"],
                                                            r["score"].get("attack", np.nan), r["score"].get("early", np.nan), r["score"].get("sustain", np.nan),
                                                            r["other"] if r["other"] is not None else float("nan"),
                                                            r["bow_off_ms"], r["level"]), flush=True)
    print("\nmedian %: score / attack / early / sustain")
    print("  render     %5.1f  %5.1f %5.1f %5.1f" % tuple(np.nanmedian([r["score"].get(w, np.nan) for r in rows])
                                                      for w in ("score", "attack", "early", "sustain")))
    print("  other take %5.1f" % np.median([r["other"] for r in rows if r["other"] is not None]))
    print("bow off, render minus recording: median %+.0f ms (abs %.0f); level %+.1f dB (abs %.1f)" % (
        np.median([r["bow_off_ms"] for r in rows]), np.median(np.abs([r["bow_off_ms"] for r in rows])),
        np.median([r["level"] for r in rows]), np.median(np.abs([r["level"] for r in rows]))))
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
