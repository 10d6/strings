#!/usr/bin/env python3
"""Leave one note out: how well the engine plays the notes between the measured ones.

    python3 -I tools/leave_one_out.py <bigcat checkout> [--work /tmp/loo] [--notes 39,42] [--json out.json]

Most notes played lie between the measured ones (a minor third apart). For each measured note, the
data is rebuilt without it, the engine built from that, and the note rendered (each dynamic, Even
Notes off, dry) and compared with its own down-bow recording, as tools/measure.py compares a measured
note:

- source × body refitted without the note's recordings (tools/bodyfit.py), and the other notes'
  own corrections recomputed against that fit (as tools/analyze.py does);
- the note's cells, onsets and release left out (the release smoothed again from the others' raw
  sets), so the engine plays it as any unmeasured note: the nearest measured note's onset transposed
  (now 3 semitones away), the level between its neighbours', corrections faded to nothing.
- Not refitted: the movement's per-note smoothing (a median of three notes: the left-out note's own
  recordings still count in its neighbours'), and the calibrations; neither is what the distance
  measures (the movement can't be judged by it, CLAUDE.md).

Each build is made in a copy of the repo (`--work`, rebuilt each note: ~2 min a note on two cores).
The copy lets the arco engine build with 16 notes (it relaxes the assertion that the staccato and
up-bow data share the sustains' notes; only held arco notes are rendered).

Reported per cell: `raw` and `timbre` (measure.py's), with the early (onset) and sustain windows, for
the full data (the note measured) and left out. The two ends (C2, C6) are extrapolations, reported
apart. The yardstick: **a sampler** at the same gap, each neighbour's recording transposed 3
semitones to the note (resampled), against the note's recording, the two neighbours averaged. A
real unmeasured note is 1-2 semitones from a measured one, not 3: leaving one out doubles the gap,
so every number here is pessimistic for the notes a player plays.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.signal import resample_poly

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import bodyfit as B  # noqa: E402
import common as C  # noqa: E402
import measure as Me  # noqa: E402
import perceptual as P  # noqa: E402

EVEN_OFF = {"play.even": 0.0}
PER_CELL = ("life_shape", "life_shape_oct", "life_resid_k", "life_resid_oct", "grain_depth", "grain_phase")
PER_NOTE = ("release_raw", "life_pitch", "life_level", "life_harm")


def reduced(d, onsets, rows, m):
    """cello.json and the onsets without note m, source × body refitted without its recordings"""
    i = d["notes"].index(m)
    nD = len(d["dynamics"])
    keep_cells = [c for c in range(len(d["notes"]) * nD) if c // nD != i]
    out = dict(d)
    out["notes"] = [n for n in d["notes"] if n != m]
    out["cells"] = [c for c in d["cells"] if c["midi"] != m]
    for k in PER_CELL:
        out[k] = [d[k][c] for c in keep_cells]
    for k in PER_NOTE:
        out[k] = [v for j, v in enumerate(d[k]) if j != i]
    # the release smoothed again across the notes left (a median of three, in log), as analyze.py
    R = np.log(np.array(out["release_raw"]))
    Rs = R.copy()
    for j in range(len(R)):
        lo, hi = max(0, j - 1), min(len(R), j + 2)
        Rs[j] = np.median(R[lo:hi], axis=0) if hi - lo == 3 else np.mean(R[lo:hi], axis=0)
    out["release"] = np.exp(Rs).tolist()
    train = [r for r in rows if r["midi"] != m]
    model = B.fit(train)
    out["source"], out["body"], out["knots"] = model["S"].tolist(), model["B"].tolist(), model["knots"].tolist()
    for c in out["cells"]:
        r = next(q for q in train if q["midi"] == c["midi"] and q["dyn"] == c["dyn"] and q["bow"] == "d")
        pred = B.predict(model, c["dyn"], r["f0"], len(r["L"]))
        w = B.weights(r["L"])
        g = np.sum(w * (r["L"] - pred)) / np.sum(w)
        c["corr"] = np.clip(r["L"] - pred - g, -40, 24).tolist()
    return out, onsets[keep_cells]


def prepare_copy(work):
    """the repo copied (without builds), the arco engine allowed to build with fewer notes"""
    src = os.path.join(work, "src")
    if not os.path.exists(src):
        ign = shutil.ignore_patterns("build*", ".git", "renders", "node_modules")
        shutil.copytree(REPO, work, ignore=ign, symlinks=True, dirs_exist_ok=True)
        p = os.path.join(src, "Synth.cpp")
        s = open(p).read()
        s = s.replace("static_assert(sd::kNotes == cd::kNotes", "static_assert(sd::kNotes >= cd::kNotes")
        s = s.replace("static_assert(upbow_data::kNotes == cd::kNotes", "static_assert(upbow_data::kNotes >= cd::kNotes")
        open(p, "w").write(s)
        subprocess.run(["cmake", "-S", work, "-B", os.path.join(work, "build"), "-G", "Ninja",
                        "-DCMAKE_BUILD_TYPE=Release"], check=True, capture_output=True)
    return os.path.join(work, "build", "strings_render")


def build(work, js, npz):
    subprocess.run([sys.executable, "-I", os.path.join(work, "tools", "make_header.py"), js, npz,
                    os.path.join(work, "src", "CelloData.h")], check=True, capture_output=True)
    subprocess.run(["cmake", "--build", os.path.join(work, "build"), "--target", "strings_render"],
                   check=True, capture_output=True)


def score(tool, m, d, x, sr, tmp):
    y = Me.render(tool, m, Me.VEL[d], tmp, params=EVEN_OFF)
    Nr = P.loudness(x, sr, Me.LEN)
    r = P.distance(Nr, P.loudness(y, sr, Me.LEN))
    return (r["score"], P.distance(Nr, P.loudness(Me.envelope_matched(y, x, sr), sr, Me.LEN))["score"],
            r["early"], r["sustain"])


def sampler(sus, notes, m, d, x, sr):
    """the neighbours' recordings transposed 3 semitones to the note (2^(3/12) ~ 53/50), averaged"""
    i = notes.index(m)
    Nr = P.loudness(x, sr, Me.LEN)
    raw, tim = [], []
    for j, num, den in ((i - 1, 50, 53), (i + 1, 53, 50)):
        if not 0 <= j < len(notes):
            continue
        y, _ = C.load(sus[(notes[j], d, "d")]["path"])
        y = resample_poly(y, num, den)
        y = np.pad(y, (0, max(0, len(x) - len(y))))
        raw.append(P.distance(Nr, P.loudness(y, sr, Me.LEN))["score"])
        tim.append(P.distance(Nr, P.loudness(Me.envelope_matched(y, x, sr), sr, Me.LEN))["score"])
    return float(np.mean(raw)), float(np.mean(tim))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root")
    ap.add_argument("--work", default=os.path.join(tempfile.gettempdir(), "strings-loo"))
    ap.add_argument("--notes", help="comma-separated MIDI notes (default: every measured note)")
    ap.add_argument("--json")
    a = ap.parse_args()
    d = json.load(open(os.path.join(HERE, "cello.json")))
    on = np.load(os.path.join(HERE, "cello_onsets.npz"))
    onsets = on["onsets"]
    notes = [int(n) for n in a.notes.split(",")] if a.notes else d["notes"]
    print("measuring the sustains for the fit…", flush=True)
    rows = B.measure_all(a.root)
    sus = {(s["midi"], s["dyn"], s["bow"]): s for s in C.sustains(a.root)}
    work = os.path.abspath(a.work)
    tool = prepare_copy(work)
    tdir = os.path.join(work, "tools")
    # the full data first: the same copy and build, so both sides differ only by the note
    build(work, os.path.join(HERE, "cello.json"), os.path.join(HERE, "cello_onsets.npz"))
    res = []
    with tempfile.TemporaryDirectory() as tmp:
        full = {}
        for m in notes:
            for dy in d["dynamics"]:
                x, sr = C.load(sus[(m, dy, "d")]["path"])
                full[(m, dy)] = score(tool, m, dy, x, sr, tmp)
        for m in notes:
            red, ons = reduced(d, onsets, rows, m)
            js, npz = os.path.join(tdir, "cello_loo.json"), os.path.join(tdir, "cello_loo_onsets.npz")
            json.dump(red, open(js, "w"))
            np.savez_compressed(npz, onsets=ons, scale=on["scale"])
            build(work, js, npz)
            for dy in d["dynamics"]:
                x, sr = C.load(sus[(m, dy, "d")]["path"])
                raw, tim, early, sus_ = score(tool, m, dy, x, sr, tmp)
                fr, ft, fe, fs = full[(m, dy)]
                sr_raw, sr_tim = sampler(sus, d["notes"], m, dy, x, sr)
                res.append(dict(midi=m, note=C.note_name(m), dyn=dy, raw=raw, timbre=tim, early=early, sustain=sus_,
                                full_raw=fr, full_timbre=ft, full_early=fe, full_sustain=fs,
                                sampler_raw=sr_raw, sampler_timbre=sr_tim))
                print("%-4s %-2s left out: raw %5.1f timbre %5.1f (early %5.1f sustain %5.1f)   "
                      "measured: raw %5.1f timbre %5.1f (early %5.1f sustain %5.1f)" % (
                          C.note_name(m), dy, raw, tim, early, sus_, fr, ft, fe, fs), flush=True)
    ends = (d["notes"][0], d["notes"][-1])
    inner = [r for r in res if r["midi"] not in ends]
    for label, rs in (("between measured notes", inner), ("the ends (extrapolated)", [r for r in res if r["midi"] in ends])):
        if not rs:
            continue
        med = lambda k: float(np.median([r[k] for r in rs]))  # noqa: E731
        print("\n%s, %d cells, median %%: left out raw %.1f, timbre %.1f (early %.1f, sustain %.1f); "
              "measured raw %.1f, timbre %.1f (early %.1f, sustain %.1f)" % (
                  label, len(rs), med("raw"), med("timbre"), med("early"), med("sustain"),
                  med("full_raw"), med("full_timbre"), med("full_early"), med("full_sustain")))
        print("  a sampler at the same gap: raw %.1f, timbre %.1f; the engine closer in %d of %d cells (timbre)" % (
            med("sampler_raw"), med("sampler_timbre"), sum(r["timbre"] < r["sampler_timbre"] for r in rs), len(rs)))
    if inner:
        byd = {dy: float(np.median([r["timbre"] for r in inner if r["dyn"] == dy])) for dy in d["dynamics"]}
        print("left out, timbre by dynamic: " + ", ".join("%s %.1f" % kv for kv in byd.items()))
        worst = sorted(inner, key=lambda r: -r["timbre"])[:5]
        print("worst (timbre): " + ", ".join("%s %s %.1f" % (r["note"], r["dyn"], r["timbre"]) for r in worst))
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
