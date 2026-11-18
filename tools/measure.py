#!/usr/bin/env python3
"""The engine against the recordings: every measured note and dynamic, rendered and compared.

    python3 -I tools/measure.py <bigcat checkout> build/strings_render [--json out.json] [--dyn mf]

Each cell is rendered as it was recorded (one note, the dynamic's middle velocity: 16, 48, 80, 112,
held past 3 s, at 44.1 kHz) and compared with its down-bow sustain over 0-3 s by the perceptual
distance (tools/perceptual.py):

  raw         the render as it is. The recording also holds the cellist's bow (its level moving over
              the note), which the synth can't know: this is the whole difference.
  timbre      the render with the recording's level envelope applied after the hand-off (100 ms rms,
              recording over render): the timbre alone, comparable with docs/PHASE0.md's spike.
  other bow   the same note's up-bow recording against the down-bow: another performance of it, the
              yardstick for raw.

Then the keyboard's evenness: every semitone C2-C6 at mf, its steady level and brightness (centroid,
in harmonic numbers), and the largest step between neighbours, against the steps between measured
neighbours a minor third apart.
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
import perceptual as P  # noqa: E402

SR = 44100
LEN = 3.0
VEL = {"p": 16, "mp": 48, "mf": 80, "f": 112}
TRIM_DB = -6.0          # the engine's headroom (kTrimDb in src/Synth.cpp): undone before comparing


def render(tool, midi, vel, tmp, length=3.4, off=3.2):
    sc = dict(patch="init", sampleRate=SR, length=length,
              events=[dict(t=0, on=int(midi), vel=int(vel)), dict(t=off, off=int(midi))])
    js = os.path.join(tmp, "sc_%d_%d.json" % (midi, vel))
    wav = os.path.join(tmp, "r_%d_%d.wav" % (midi, vel))
    with open(js, "w") as f:
        json.dump(sc, f)
    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav, always_2d=True)
    assert sr == SR
    return y.mean(axis=1) * 10 ** (-TRIM_DB / 20)


def env(x, sr, win=0.1):
    n = int(win * sr)
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    i = np.arange(len(x))
    lo, hi = np.clip(i - n // 2, 0, len(x)), np.clip(i + n // 2, 1, len(x))
    return np.sqrt((c[hi] - c[lo]) / (hi - lo) + 1e-20)


def envelope_matched(y, x, sr):
    """The render with the recording's level movement after the hand-off (from 0.3 s, fully 0.4)."""
    n = min(len(x), len(y))
    y, x = y[:n], x[:n]
    g = env(x, sr) / env(y, sr)
    t = np.arange(n) / sr
    w = np.clip((t - 0.3) / 0.1, 0, 1)
    return y * (1 - w + w * g)


def steady(y, sr, f0):
    seg = y[int(1.0 * sr):int(3.0 * sr)]
    S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / sr)
    lvl = 10 * np.log10(np.mean(seg ** 2) + 1e-20)
    cen = np.sum(f * S) / np.sum(S) / f0
    return lvl, cen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("tool")
    ap.add_argument("--json")
    ap.add_argument("--dyn", default="p,mp,mf,f")
    a = ap.parse_args()
    sus = C.sustains(a.root)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for m in sorted({s["midi"] for s in sus}):
            for d in a.dyn.split(","):
                rec = next(s for s in sus if s["midi"] == m and s["dyn"] == d and s["bow"] == "d")
                oth = next(s for s in sus if s["midi"] == m and s["dyn"] == d and s["bow"] == "g")
                x, sr = C.load(rec["path"])
                xo, _ = C.load(oth["path"])
                y = render(a.tool, m, VEL[d], tmp)
                Nr = P.loudness(x, sr, LEN)
                r = dict(note=C.note_name(m), midi=m, dyn=d,
                         raw=P.distance(Nr, P.loudness(y, sr, LEN)),
                         timbre=P.distance(Nr, P.loudness(envelope_matched(y, x, sr), sr, LEN)),
                         other_bow=P.distance(Nr, P.loudness(xo, sr, LEN)))
                rows.append(r)
                print("%-4s %-2s raw %5.1f  timbre %5.1f  other bow %5.1f" % (
                    r["note"], d, r["raw"]["score"], r["timbre"]["score"], r["other_bow"]["score"]), flush=True)
        print("\nmedian %: score / attack / early / sustain")
        for k in ("raw", "timbre", "other_bow"):
            print("  %-10s %5.1f  %5.1f %5.1f %5.1f" % (k, *[np.median([r[k][w] for r in rows])
                                                         for w in ("score", "attack", "early", "sustain")]))
        # evenness along the keyboard at mf
        ev = []
        for m in range(36, 85):
            y = render(a.tool, m, VEL["mf"], tmp)
            ev.append((m,) + steady(y, SR, C.mtof(m)))
        ev = np.array(ev)
        measured = sorted({s["midi"] for s in sus})
        step_l = np.abs(np.diff(ev[:, 1]))
        step_c = np.abs(np.diff(np.log2(ev[:, 2])))
        mi = [list(ev[:, 0]).index(m) for m in measured]
        ml, mc = np.abs(np.diff(ev[mi, 1])), np.abs(np.diff(np.log2(ev[mi, 2])))
        print("\nevenness at mf, C2-C6: level step between semitones max %.1f dB (median %.1f); "
              "between measured notes a third apart max %.1f (median %.1f)" % (
                  step_l.max(), np.median(step_l), ml.max(), np.median(ml)))
        print("  brightness step between semitones max %.2f octaves (median %.2f); measured neighbours max %.2f (median %.2f)" % (
            step_c.max(), np.median(step_c), mc.max(), np.median(mc)))
        worst = int(np.argmax(step_l))
        print("  largest level step: %s → %s" % (C.note_name(int(ev[worst, 0])), C.note_name(int(ev[worst + 1, 0]))))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(dict(cells=rows, evenness=ev.tolist()), f, indent=1)


if __name__ == "__main__":
    main()
