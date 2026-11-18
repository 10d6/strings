#!/usr/bin/env python3
"""Phase 0 spike: can a bowed cello note be rebuilt from the model the plan proposes?

    python3 -I tools/spike.py <bigcat checkout> <out dir> [--cases C3_mf_d,...]

Each case is rebuilt several ways and compared with its recording by the perceptual distance
(tools/perceptual.py; 0-3 s: attack 0-80 ms, early 80-500 ms, sustain 0.5-3 s):

  resynth      harmonics + residual as analysed (a check: should be ~0)
  harmonics    the analysed harmonics alone, no residual (how much the noise matters)
  model        the plan's model with nothing recorded: each harmonic's own swell for the first
               0.3 s, then a fixed spectrum (this note's own) times the note's level envelope, at a
               steady pitch, plus steady noise shaped like the note's residual
  +onset       model, with the first 0.3 s of the residual (scratch, catch) as recorded
  +onset body  the same, but the steady spectrum is source × body (tools/bodyfit.py) fitted without
               this note: what the synth would play for a note between the sampled ones
  +onset pitch +onset, with the recording's own pitch wander instead of a steady pitch

  +onset neighbour   +onset with the steady spectrum of the nearest sampled note below, by harmonic
               number (what transposing a neighbour gives), the fair comparison for +onset body
  +onset other bow   +onset with the steady spectrum of the same note's other bow direction: the
               recordings' own variation, the yardstick for the two above

and, as whole recordings (another performance: its own envelope and onset as well as its timbre):

  other bow    the same note and dynamic, the other bow direction
  sampler      the nearest sampled note below, transposed to this pitch (what a sampler plays)

The level envelope (the bow's dynamics) is the recording's, smoothed over 100 ms, in every model
variant: the spike tests the timbre, not a player. Writes one WAV per case (recording, +onset,
+onset body, +onset neighbour, sampler, with a gap between) and spike.json.
"""
import argparse
import json
import os
import sys

import numpy as np
import soundfile as sf
from scipy.signal import resample, welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bodyfit as B  # noqa: E402
import common as C  # noqa: E402
import harmonics as H  # noqa: E402
import perceptual as P  # noqa: E402

LEN = 3.0
T_ON, XF = 0.30, 0.10          # onset kept as measured up to T_ON, crossfaded over XF
DEFAULT_CASES = ["C1_mf_d", "Eb2_mf_d", "C3_mf_d", "C3_p_d", "C3_f_d", "A3_mf_d", "Gb4_mf_d"]


def smooth(x, n):
    n = max(1, int(n))
    c = np.concatenate([[0.0], np.cumsum(x)])
    i = np.arange(len(x))
    lo, hi = np.clip(i - n // 2, 0, len(x)), np.clip(i + n // 2 + 1, 0, len(x))
    return (c[hi] - c[lo]) / (hi - lo)


def onset_fade(n, sr):
    t = np.arange(n) / sr
    c = np.clip((T_ON + XF / 2 - t) / XF, 0, 1)
    return 0.5 - 0.5 * np.cos(np.pi * c)          # 1 during the onset, 0 after, raised cosine


def shaped_noise(resid, sr, a, b, n, rng):
    """White noise with the residual's steady spectrum and level."""
    seg = resid[int(a * sr):int(b * sr)]
    f, p = welch(seg, sr, nperseg=2048)
    w = rng.standard_normal(n)
    W = np.fft.rfft(w)
    fr = np.fft.rfftfreq(n, 1 / sr)
    W *= np.sqrt(np.interp(fr, f, p))
    y = np.fft.irfft(W, n)
    return y * np.sqrt(np.mean(seg ** 2)) / (np.sqrt(np.mean(y ** 2)) + 1e-20)


def synth(an, sr, n, spectrum, pitch="steady", onset_resid=False, noise=None):
    a = an["a"][:, :n]
    K = a.shape[0]
    mag = np.abs(a)
    E = smooth(np.sqrt(2 * (mag ** 2).sum(axis=0)), 0.1 * sr)
    c = onset_fade(n, sr)
    t = np.arange(n) / sr
    if pitch == "steady":
        phi = 2 * np.pi * an["fmed"] * t
    else:
        phi = an["phi"][:n]
    i_ref = int(T_ON * sr)
    out = np.zeros(n)
    for k in range(1, K + 1):
        amp = c * mag[k - 1] + (1 - c) * spectrum[k - 1] * E
        th = np.angle(a[k - 1, i_ref]) + k * (an["phi"][i_ref] - phi[i_ref])
        out += 2 * amp * np.cos(k * phi + th)
    if noise is not None:
        a0, b0 = 0.4, min(LEN, n / sr) - 0.1
        Es = np.median(E[int(a0 * sr):int(b0 * sr)])
        nz = noise * E / Es
        if onset_resid:
            nz = c * an["resid"][:n] + (1 - c) * nz
        out += nz
    return out


def own_spectrum(an, sr, n):
    mag = np.abs(an["a"][:, :n])
    E = np.sqrt(2 * (mag ** 2).sum(axis=0))
    a0, b0 = int(0.4 * sr), int((min(LEN, n / sr) - 0.1) * sr)
    return np.median(mag[:, a0:b0] / (E[a0:b0] + 1e-12), axis=1)


def body_spectrum(model, dyn, f0, K, own):
    pred = B.predict(model, dyn, f0, min(K, B.KMAX))
    s = 10 ** (pred / 20)
    s = np.concatenate([s, own[len(s):] * 0])                         # above KMAX: nothing
    return s * np.sqrt(np.sum(own ** 2) / np.sum(s ** 2))


def match(y, ref, sr):
    a, b = int(0.4 * sr), int(LEN * sr)
    return y * np.sqrt(np.mean(ref[a:b] ** 2) / (np.mean(y[a:b] ** 2) + 1e-20))


def find(sus, name, dyn, bow):
    return next((s for s in sus if s["name"] == name and s["dyn"] == dyn and s["bow"] == bow), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("out")
    ap.add_argument("--cases", default=",".join(DEFAULT_CASES))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    sus = C.sustains(a.root)
    notes = sorted({s["midi"] for s in sus})
    print("measuring every sustain for the body fit…", flush=True)
    rows = B.measure_all(a.root)
    rng = np.random.default_rng(1)
    results = []
    for case in a.cases.split(","):
        name, dyn, bow = case.split("_")
        s = find(sus, name, dyn, bow)
        x, sr = C.load(s["path"])
        n = min(len(x), int(LEN * sr))
        x = x[:n]
        an = H.analyse(x, sr, C.mtof(s["midi"]))
        own = own_spectrum(an, sr, n)
        noise = shaped_noise(an["resid"], sr, 0.4, n / sr - 0.1, n, rng)
        model = B.fit([r for r in rows if r["midi"] != s["midi"]])
        body = body_spectrum(model, dyn, an["fmed"], an["K"], own)
        v = {}
        v["resynth"] = an["harm"] + an["resid"]
        v["harmonics"] = an["harm"]
        v["model"] = synth(an, sr, n, own, noise=noise)
        v["+onset"] = synth(an, sr, n, own, onset_resid=True, noise=noise)
        v["+onset body"] = synth(an, sr, n, body, onset_resid=True, noise=noise)
        v["+onset pitch"] = synth(an, sr, n, own, pitch="track", onset_resid=True, noise=noise)
        o = find(sus, name, dyn, "g" if bow == "d" else "d")
        xo, _ = C.load(o["path"])
        ao = H.analyse(xo[:n], sr, C.mtof(s["midi"]), kmax=an["K"])
        so = own_spectrum(ao, sr, n)
        so = np.concatenate([so, np.zeros(an["K"] - len(so))])
        v["other bow"] = match(xo[:n], x, sr)
        lower = max([m for m in notes if m < s["midi"]], default=None) or \
            min(m for m in notes if m > s["midi"])
        nb = next(q for q in sus if q["midi"] == lower and q["dyn"] == dyn and q["bow"] == bow)
        xn, _ = C.load(nb["path"])
        ratio = C.mtof(s["midi"]) / C.mtof(lower)
        anb = H.analyse(xn[:int(LEN * sr)], sr, C.mtof(lower))
        snb = own_spectrum(anb, sr, min(len(xn), int(LEN * sr)))[:an["K"]]
        snb = np.concatenate([snb, np.zeros(an["K"] - len(snb))])
        v["+onset neighbour"] = synth(an, sr, n, snb * np.sqrt(np.sum(own ** 2) / np.sum(snb ** 2)),
                                      onset_resid=True, noise=noise)
        v["+onset other bow"] = synth(an, sr, n, so * np.sqrt(np.sum(own ** 2) / np.sum(so ** 2)),
                                      onset_resid=True, noise=noise)
        xn = resample(xn, int(len(xn) / ratio))
        xn = np.concatenate([xn, np.zeros(max(0, n - len(xn)))])[:n]
        v["sampler"] = match(xn, x, sr)
        Nr = P.loudness(x, sr, LEN)
        row = dict(case=case, note=C.note_name(s["midi"]), f0=round(an["fmed"], 2), harmonics=an["K"])
        for k, y in v.items():
            d = P.distance(Nr, P.loudness(y, sr, LEN))
            row[k] = d
        results.append(row)
        print("%-9s %-4s " % (case, row["note"]) + "  ".join("%s %.1f" % (k, row[k]["score"]) for k in v), flush=True)
        gap = np.zeros(int(0.6 * sr))
        seq = [x, gap, v["+onset"], gap, v["+onset body"], gap, v["+onset neighbour"], gap, v["sampler"]]
        y = np.concatenate(seq)
        sf.write(os.path.join(a.out, "%s.wav" % case), 0.9 * y / max(1e-9, np.abs(y).max()), sr, subtype="PCM_16")
    keys = [k for k in results[0] if isinstance(results[0][k], dict)]
    print("\nmedian distance (%) over the cases: score / attack / early / sustain")
    for k in keys:
        sc = [r[k] for r in results]
        print("  %-13s %5.1f  %5.1f %5.1f %5.1f" % (k, np.median([d["score"] for d in sc]),
              np.median([d["attack"] for d in sc]), np.median([d["early"] for d in sc]),
              np.median([d["sustain"] for d in sc])))
    with open(os.path.join(a.out, "spike.json"), "w") as f:
        json.dump(results, f, indent=1)


if __name__ == "__main__":
    main()
