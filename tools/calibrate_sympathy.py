#!/usr/bin/env python3
"""Compare the sympathetic strings' ring with the recordings' (tools/sympathy.py).

    python3 -I tools/calibrate_sympathy.py <bigcat checkout> build/strings_render [string.resonance=dB]

In the staccatos' releases, the harmonics on an open string's partial are still well over the rest
0.3 s after the note has fallen 36 dB: free strings ringing along (sympathy.py). This renders a short
note (held STACC s, dry, Even Notes off) for every staccato note at mf and f, twice: as set, and with
the strings ringing 60 dB less. Their difference is the ring alone, read at the same harmonics at the
same moment (0.3 s after the note, without the ring, is 36 dB down: a loud ring would move it),
against the note's peak; in the recordings, the open-partial harmonics with the noise floor (the other
harmonics by then) taken out. Medians (a mean of power is dominated by a few loud low harmonics in the
recordings).

It isn't what sets the coupling (docs/MODEL.md: Sympathetic strings). Matching the staccatos took a
coupling 30 dB over the default (kSympK 69 against 2.2), at which a held note rings the free strings
as loud as itself (G3 on the open G 16 dB louder). A bank driven by the sound can't give both: the
recordings' late ring is likely the note's own string coupled to its open neighbour (the pair decays
together, slower: 37 against 48 dB/s at 125-250 Hz), which this doesn't model. So kSympK is a judgment,
and this reports how far its ring is under the staccatos'.
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
import sympathy as S  # noqa: E402

STACC = 0.25
VEL = {"mf": 80, "f": 112}


def ring_db(rows):
    """The mean power of the late level of harmonics on an open string's partial, with the others'
    (the floor) taken out. Power, not the median: the few harmonics in unison with an open partial
    ring far more than the near ones, in a cello as in the model."""
    on = np.array([r["tail"] for r in rows if r["open"] and r["tail"] is not None])
    off = np.array([r["tail"] for r in rows if not r["open"] and r["tail"] is not None])
    if not len(on):
        return None, None
    p_on = np.mean(10 ** (on / 10))
    p_off = np.mean(10 ** (off / 10)) if len(off) else 0.0
    return 10 * np.log10(max(p_on - p_off, 1e-30)), 10 * np.log10(p_off + 1e-30)


def ring_alone(dry, ring, sr, midi):
    """The ring's level at the note's harmonics on an open string's partial, 0.3 s after the note is
    36 dB down, against its peak (as sympathy.decays reads a recording). The moment is the note's own,
    from the render without the ring: a ring as loud as the note would otherwise move it."""
    an = H.analyse(dry, sr, C.mtof(midi), kmax=30, fmax=6000)
    p = 2 * np.abs(an["a"])
    Edb = 20 * np.log10(np.sqrt(np.sum(p ** 2, axis=0) / 2) + 1e-12)
    ip = int(np.argmax(Edb))
    i36 = np.where((np.arange(len(Edb)) > ip) & (Edb < Edb[ip] - 36))[0]
    if not len(i36):
        return []
    late = i36[0] + int(0.3 * sr)
    out = []
    # the ring is at the open strings' partials, a few cents from the note's harmonics: read it as
    # the power within ±25 cents of each harmonic, in a 100 ms window at the moment
    w = int(0.1 * sr)
    seg = ring[max(0, late - w // 2):late + w // 2] * np.hanning(min(w, len(ring) - max(0, late - w // 2)))
    if len(seg) < w // 2:
        return []
    spec = np.abs(np.fft.rfft(seg, 8 * len(seg))) ** 2
    fr = np.fft.rfftfreq(8 * len(seg), 1 / sr)
    norm = (np.sum(np.hanning(len(seg)) ** 2) / 2)
    for k in range(an["K"]):
        f = (k + 1) * an["fmed"]
        if not S.on_open(f, midi):
            continue
        sel = (fr > f * 2 ** (-25 / 1200)) & (fr < f * 2 ** (25 / 1200))
        amp = np.sqrt(np.sum(spec[sel]) / norm / len(seg) * 2) if sel.any() else 0
        out.append(dict(k=k + 1, f=float(f), open=True, tail=float(20 * np.log10(amp + 1e-12) - Edb[ip])))
    return out


def main():
    root, tool = sys.argv[1:3]
    params = dict(C.DRY, **{"play.even": 0.0})
    params.update({k: float(v) for k, v in (a.split("=") for a in sys.argv[3:])})
    rec, ren = [], []
    notes = sorted({s["midi"] for s in A.staccatos(root)})
    for s in A.staccatos(root):
        if s["dyn"] in VEL:
            for h in S.decays(s["path"], s["midi"]):
                rec.append(h)
    with tempfile.TemporaryDirectory() as tmp:
        for m in notes:
            for d, v in VEL.items():
                ys = []
                for extra in (0.0, -60.0):
                    pr = dict(params)
                    pr["string.resonance"] = pr.get("string.resonance", 0.0) + extra
                    sc = dict(patch="init", sampleRate=44100, length=STACC + 2.5, params=pr,
                              events=[dict(t=0, on=int(m), vel=v), dict(t=STACC, off=int(m))])
                    js, wav = os.path.join(tmp, "s.json"), os.path.join(tmp, "s.wav")
                    json.dump(sc, open(js, "w"))
                    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
                    y, sr = sf.read(wav, always_2d=True)
                    ys.append(y.mean(axis=1))
                ren.extend(ring_alone(ys[1], ys[0] - ys[1], sr, m))
    a, fa = ring_db(rec)
    b = float(10 * np.log10(np.mean([10 ** (r["tail"] / 10) for r in ren])))
    on = np.array([r["tail"] for r in rec if r["open"] and r["tail"] is not None])
    off = np.array([r["tail"] for r in rec if not r["open"] and r["tail"] is not None])
    med_rec = 10 * np.log10(max(10 ** (np.median(on) / 10) - 10 ** (np.median(off) / 10), 1e-30))
    med_ren = float(np.median([r["tail"] for r in ren]))
    print("  medians: recordings %.1f dB (floor %.1f taken out), renders %.1f dB: the renders' ring is %.1f dB under" % (
        med_rec, np.median(off), med_ren, med_rec - med_ren))
    print("the free strings' late ring at the note's harmonics on an open string's partial (0.3 s after")
    print("the note is 36 dB down, re its peak):")
    print("  as mean power: recordings %.1f dB (their floor, %.1f, taken out), renders %.1f dB (%d harmonics)" % (
        a, fa, b, len(ren)))


if __name__ == "__main__":
    main()
