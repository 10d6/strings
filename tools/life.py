#!/usr/bin/env python3
"""How a held bowed note moves: the bow's wander, measured in the recordings (and in renders).

    python3 -I tools/life.py <bigcat checkout> [--render build/strings_render] [--json out.json]

Over each sustain's steady part (0.6 s to 0.15 s before its end; renders: 0.6-3.8 s of a 4 s note):

  pitch      the f0 track in cents, linear trend removed: rms, and its spectrum (how fast it moves)
  level      the harmonic part's level in dB (rms over harmonics), trend removed: rms, spectrum
  harmonics  each harmonic's level against the note's level (dB, k ≤ 20, within 40 dB of the
             strongest), trend removed: rms per harmonic, spectrum, and how alike the harmonics move
             (mean correlation between them: 1 would be one common movement)
  noise      the bow noise's modulation at the string's period, per octave band: the residual with
             every harmonic notched out (±f0/4), band-passed, its envelope e's component at the
             fundamental's own phase θ (the phase of its first harmonic, as the engine has it):
             depth 2|<e·exp(-jθ)>| / <e>, and where in the period it peaks, ψ = -arg <e·exp(-jθ)>;
             and the depth at a frequency 7 % off (the null: what chance gives with this much data)

Spectra are given as rms per octave of modulation frequency (0.25-32 Hz), so their shapes compare
directly. With --render, every cell is also rendered (the dynamic's middle velocity) and measured the
same way: the engine's movement should look like the recordings'.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
from scipy.signal import hilbert, welch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import harmonics as H  # noqa: E402

RATE = 200.0                                    # tracks are taken every 5 ms
OCT = [0.25 * 2 ** i for i in range(8)]         # modulation octaves: 0.25-32 Hz (lower edges)
BANDS = [250 * 2 ** i for i in range(7)]        # noise bands, 250 Hz-16 kHz (centres)
KMAXL = 20


def detrend(y):
    t = np.arange(len(y))
    return y - np.polyval(np.polyfit(t, y, 1), t)


def per_octave(y):
    """rms of y in each octave of modulation frequency (OCT)."""
    f, p = welch(y, RATE, nperseg=min(len(y), 512))
    df = f[1] - f[0]
    return [float(np.sqrt(np.sum(p[(f >= lo) & (f < 2 * lo)]) * df)) for lo in OCT]


def noise_modulation(resid, theta, f0, sr, a, b, rng, bands=BANDS):
    """Per band: (depth, peak phase ψ, null depth), or None where the band can't be seen between the
    harmonics (below 2·f0, or too few bins)."""
    seg = resid[a:b]
    ph = theta[a:b]
    n = len(seg)
    X = np.fft.rfft(seg)
    fr = np.fft.rfftfreq(n, 1 / sr)
    k = np.round(fr / f0)
    X[(k >= 1) & (np.abs(fr - k * f0) < f0 / 4)] = 0     # between the harmonics only
    out = []
    for fc in bands:
        sel = (fr >= fc / np.sqrt(2)) & (fr < fc * np.sqrt(2)) & (fr < sr / 2 - 100)
        if sel.sum() < 50 or fc / np.sqrt(2) < 2 * f0:
            out.append(None)
            continue
        e = np.abs(hilbert(np.fft.irfft(np.where(sel, X, 0), n)))
        c = np.mean(e * np.exp(-1j * ph))
        null = 2 * np.abs(np.mean(e * np.exp(-1j * (ph * 1.07 + rng.uniform(0, 6.28))))) / np.mean(e)
        out.append((float(2 * np.abs(c) / np.mean(e)), float(-np.angle(c)), float(null)))
    return out


def stats(x, sr, f_guess, t0, t1, rng, bands=BANDS):
    x = x[:int((t1 + 0.2) * sr)]
    an = H.analyse(x, sr, f_guess, kmax=KMAXL, fmax=8000)
    hop = int(sr / RATE)
    a, b = int(t0 * sr), int(t1 * sr)
    idx = np.arange(a, b, hop)
    fm = np.median(an["f0"][a:b])
    pitch = detrend(C.cents(an["f0"][idx], fm))
    p = 2 * np.abs(an["a"][:, idx])
    E = 20 * np.log10(np.sqrt(np.sum(p ** 2, axis=0) / 2) + 1e-12)
    level = detrend(E)
    Ld = 20 * np.log10(p + 1e-12)
    top = Ld.mean(axis=1).max()
    keep = [k for k in range(len(Ld)) if Ld[k].mean() > top - 40]
    diff = np.array([detrend(Ld[k] - E) for k in keep])
    cc = np.corrcoef(diff) if len(diff) > 1 else np.ones((1, 1))
    mcorr = float((cc.sum() - len(cc)) / (len(cc) * (len(cc) - 1))) if len(cc) > 1 else 1.0
    theta = an["phi"] + np.angle(an["a"][0])         # the fundamental's own phase
    nmod = noise_modulation(an["resid"], theta, fm, sr, a, b, rng, bands)
    return dict(pitch_rms=float(np.std(pitch)), pitch_oct=per_octave(pitch),
                level_rms=float(np.std(level)), level_oct=per_octave(level),
                harm_rms=[float(np.std(d)) for d in diff], harm_k=[k + 1 for k in keep],
                harm_oct=np.mean([per_octave(d) for d in diff], axis=0).tolist(), harm_corr=mcorr,
                noise_mod=[v[0] if v else None for v in nmod], noise_psi=[v[1] if v else None for v in nmod],
                noise_null=[v[2] if v else None for v in nmod])


def summary(rows, label):
    med = lambda key: np.median([r[key] for r in rows])
    oct_ = lambda key: np.median([r[key] for r in rows], axis=0)
    print("%s: %d notes" % (label, len(rows)))
    print("  pitch     rms %.2f c   per octave 0.25-32 Hz: %s" % (med("pitch_rms"), " ".join("%.2f" % v for v in oct_("pitch_oct"))))
    print("  level     rms %.2f dB  per octave: %s" % (med("level_rms"), " ".join("%.2f" % v for v in oct_("level_oct"))))
    hr = [np.median(r["harm_rms"]) for r in rows]
    print("  harmonics rms %.2f dB (median over harmonics), correlation between them %.2f; per octave: %s" % (
        np.median(hr), med("harm_corr"), " ".join("%.2f" % v for v in oct_("harm_oct"))))
    for i, fc in enumerate(BANDS):
        m = [r["noise_mod"][i] for r in rows if r["noise_mod"][i] is not None]
        n = [r["noise_null"][i] for r in rows if r["noise_null"][i] is not None]
        if m:
            print("  noise %5d Hz: modulation at the period %.2f (null %.2f), %d notes" % (fc, np.median(m), np.median(n), len(m)))


def render(tool, midi, vel, tmp, length=4.2, off=4.0):
    import soundfile as sf
    sc = dict(patch="init", sampleRate=44100, length=length,
              events=[dict(t=0, on=int(midi), vel=int(vel)), dict(t=off, off=int(midi))])
    js, wav = os.path.join(tmp, "s.json"), os.path.join(tmp, "r.wav")
    with open(js, "w") as f:
        json.dump(sc, f)
    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav, always_2d=True)
    return y.mean(axis=1), sr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--render")
    ap.add_argument("--json")
    ap.add_argument("--dyn", default="p,mp,mf,f")
    a = ap.parse_args()
    rng = np.random.default_rng(3)
    dyns = a.dyn.split(",")
    rec = []
    for s in C.sustains(a.root):
        if s["dyn"] not in dyns:
            continue
        x, sr = C.load(s["path"])
        r = stats(x, sr, C.mtof(s["midi"]), 0.6, len(x) / sr - 0.15, rng)
        r.update(midi=s["midi"], dyn=s["dyn"], bow=s["bow"])
        rec.append(r)
    summary(rec, "recordings")
    for lo, hi, name in ((36, 52, "C2-E3"), (53, 67, "F3-G4"), (68, 84, "G#4-C6")):
        summary([r for r in rec if lo <= r["midi"] <= hi], "  recordings " + name)
    out = dict(recordings=rec)
    if a.render:
        vel = {"p": 16, "mp": 48, "mf": 80, "f": 112}
        ren = []
        with tempfile.TemporaryDirectory() as tmp:
            for m in sorted({r["midi"] for r in rec}):
                for d in dyns:
                    y, sr = render(a.render, m, vel[d], tmp)
                    r = stats(y, sr, C.mtof(m), 0.6, 3.8, rng)
                    r.update(midi=m, dyn=d)
                    ren.append(r)
        summary(ren, "renders")
        out["renders"] = ren
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f)


if __name__ == "__main__":
    main()
