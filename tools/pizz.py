#!/usr/bin/env python3
"""Measure the cello's pizzicato for the engine: everything src/PizzData.h holds.

    python3 -I tools/pizz.py <bigcat checkout> tools/pizz.json tools/pizz_onsets.npz   # ~10 min

bigcat has 13 plucked notes (C2-C5, a minor third apart) × 4 round robins, which span no dynamic
(within about 3 dB of each other). A plucked note is a free decay, so after the pluck it is the
string's harmonics ringing down, each as a few **modes** (the piano's way, its docs/MODEL.md: Modes):
decaying sinusoids a little apart in frequency, from the string's two polarisations and its coupling
to the body. One mode per harmonic leaves the beating and the two-stage decay out (8.4 dB median
error against the recordings' envelopes over 56 harmonics tried); two give 2.9 dB, three 2.1. So each
harmonic is played as one or two modes, and the pluck itself as recorded.

Per file (note and round robin):

  onset     the recording's first ONSET_LEN s, played as recorded (the finger's snap and the
            string's first moment); the engine crossfades from it to the modes over [T_ON, T_ON + XF]
  f0        the pitch it rings at (0.25-1 s), which the onset is transposed from
  dev       where each harmonic really is (cents from k·f0): a free string is a little stiff and
            its partials sit a little off the harmonic series (C2's 8th-12th 13-17 cents sharp), as
            the piano's do (its docs/MODEL.md: Where partials really are). Each is moved to its peak
            in the spectrum of T_C-1.1 s, within ±60 cents; a peak more than 15 cents from the median
            of its five neighbours (D#2's 2nd sits on one mode of a beating pair, 57 cents off)
            takes the median. A stiff-string line through them (f_k = k f0 √(1 + B k²)) fitted
            worse: 0.9 → 7.0 dB on A3, its B pulled to 4e-4, far stiffer than a wound string.
  modes     per harmonic kept (60 dB under the strongest at T_C at most, and 15 dB over its own
            floor): one or two modes, each its decay (dB/s), its offset from where the harmonic is
            (Hz), its peak level and phase at T_C
  level     how loud it is heard: the recording's rms over its first 0.3 s (dB re full scale). The
            harmonics' level at T_C lands in beat troughs (F#3 read −33 dB, though it peaks at −16)
  decay     how fast the whole note falls over its first second (dB/s, energy-weighted)

The harmonics are heterodyned at the fixed f0, so the modes' frequency offsets carry what reads as a
pitch glide in the first 0.2 s: it swings up and down (C2 +22, −14, +14 cents at 40, 60, 80 ms) the
same way in every round robin of a note, which is modes beating, not the string's tension settling.

Fit (per harmonic): the complex envelope from T_C until it last stands 10 dB over its own floor and
within 50 dB of the note (at most 4 s), weighted by the note's level^-0.9 (each moment counted about
as it is heard then, as the piano's fit: weighted by its own level instead, a harmonic's noisy tail
counted as much as its start, and the fits followed the noise). A second mode is kept only where it lowers the error by more than 15 % and
passes the guards: neither mode more than 12 dB over the envelope at T_C (modes nearly cancelling),
decays 3-400 dB/s, offsets within ±6 Hz (not on the bound). Every take was recorded until it had
rung into the noise, so no mode may stand more than 6 dB over the harmonic's own envelope at any time
after T_C (its running maximum over 0.2 s, so a beat's trough doesn't count, and no lower than its
floor, the quietest 0.1 s level's 10th percentile): one that would decays as fast as that needs. At
first the weak harmonics' tails, noise, were fitted as modes that never decayed (0 dB/s at −47 to
−86 dB), and a slow mode fitted over a short window rang on past it: D#3 rang on above 1 kHz 15-30 dB
over its recording.
"""
import json
import os
import re
import sys
from multiprocessing import Pool

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import fftconvolve

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

ONSET_LEN = 0.22
T_ON, XF = 0.15, 0.06    # a hand-off at 0.06-0.10 s left the modes 2-7 dB under their recordings until
#                          0.15 s on mid and high notes: the pluck's own ring (the body, the finger)
T_C = T_ON + XF / 2
FMAX = 10000.0
FS = 250.0              # the envelopes' rate for the fit
FLOOR_DB = 60.0         # harmonics this far under the strongest at T_C aren't kept
OWN_FLOOR_DB = 15.0     # ... nor any less than this over their own noise floor
MAX_DECAY = 400.0       # dB/s
MIN_DECAY = 3.0
MAX_DF = 6.0            # Hz
NEPER_DB = 20 / np.log(10)


def files(root):
    d = os.path.join(root, "Samples", "pizzcato")
    out = []
    for f in sorted(os.listdir(d)):
        m = re.fullmatch(r"([A-G]b?\d)_(\d)\.wav", f)
        if m:
            out.append(dict(name=m.group(1), midi=C.midi_of(m.group(1)), rr=int(m.group(2)),
                            path=os.path.join(d, f)))
    return sorted(out, key=lambda q: (q["midi"], q["rr"]))


def ring_f0(x, sr, f_guess):
    a, b = 0.25, min(1.0, len(x) / sr - 0.1)
    if b - a < 0.2:
        a, b = 0.12, len(x) / sr - 0.05
    seg = x[int(a * sr):int(b * sr)]
    _, f0, _ = C.track_f0(seg, sr, f_guess, win=max(0.1, 8 / f_guess))
    return float(np.nanmedian(f0))


def partial_freqs(x, sr, f, K):
    """Each harmonic's peak in the spectrum of T_C-1.1 s, within ±60 cents (and ±0.3 f) of k·f, outliers
    against their neighbours replaced by the neighbours' median: (cents from k·f, frequencies)."""
    a, b = int(T_C * sr), min(len(x), int(1.1 * sr))
    seg = x[a:b] * np.hanning(b - a)
    nfft = 1 << int(np.ceil(np.log2(len(seg))) + 2)
    S = np.abs(np.fft.rfft(seg, nfft))
    out = []
    for k in range(1, K + 1):
        fk = k * f
        half = min(fk * (2 ** (60 / 1200) - 1), 0.3 * f)
        lo, hi = int((fk - half) * nfft / sr), int((fk + half) * nfft / sr) + 1
        j = lo + int(np.argmax(S[lo:hi]))
        al, be, ga = np.log(S[j - 1:j + 2] + 1e-20)
        pk = 0.5 * (al - ga) / (al - 2 * be + ga) if (al - 2 * be + ga) != 0 else 0.0
        out.append(C.cents((j + pk) * sr / nfft, fk))
    dev = np.array(out)
    med = np.array([np.median(dev[max(0, k - 2):k + 3]) for k in range(K)])
    dev = np.where(np.abs(dev - med) > 15, med, dev)
    return dev, f * np.arange(1, K + 1) * 2 ** (dev / 1200)


def envelope(x, sr, f, fk):
    """A harmonic's complex amplitude, heterodyned at fk, at FS (block means after a Hann window 3
    periods of f long)."""
    t = np.arange(len(x)) / sr
    n = int(max(3.0 / f, 0.008) * sr) | 1
    w = np.hanning(n)
    w /= w.sum()
    a = fftconvolve(x * np.exp(-2j * np.pi * fk * t), w, mode="same")
    dec = int(round(sr / FS))
    m = len(a) // dec
    return a[:m * dec].reshape(m, dec).mean(axis=1), dec


def smooth_db(z, n):
    k = np.ones(n) / n
    return 10 * np.log10(np.convolve(np.abs(z) ** 2, k, "same") + 1e-24)


def basis(p, t, nm):
    return np.stack([np.exp((-p[2 * m] + 2j * np.pi * p[2 * m + 1]) * t) for m in range(nm)], axis=1)


def fit_modes(t, z, w, nm, inits):
    def res(p):
        B = basis(p, t, nm) * w[:, None]
        c, *_ = np.linalg.lstsq(B, z * w, rcond=None)
        r = B @ c - z * w
        return np.concatenate([r.real, r.imag])
    lb = [MIN_DECAY / NEPER_DB, -MAX_DF] * nm
    ub = [MAX_DECAY / NEPER_DB, MAX_DF] * nm
    best = None
    for p0 in inits:
        p0 = np.clip(p0, np.array(lb) + 1e-6, np.array(ub) - 1e-6)
        s = least_squares(res, p0, bounds=(lb, ub), x_scale="jac", max_nfev=200)
        if best is None or s.cost < best.cost:
            best = s
    B = basis(best.x, t, nm)
    c, *_ = np.linalg.lstsq(B * w[:, None], z * w, rcond=None)
    return best.x, c, B @ c


def db_error(z, m, heard):
    """Median dB difference of the envelopes (smoothed over 40 ms) where the harmonic is heard
    (within 40 dB of the note)."""
    n = max(3, int(0.04 * FS))
    e = np.abs(smooth_db(z, n) - smooth_db(m, n))
    sel = heard.copy()
    if sel.sum() < 4:
        sel = np.ones_like(sel)
    return float(np.median(e[sel]))


def fit_harmonic(z, i0, floor_db, note_db):
    """Modes of one harmonic's envelope from sample i0 (T_C), given the note's level (dB, smoothed,
    per sample of z). Returns (modes, err1, err2, n_used)."""
    sm = smooth_db(z, int(0.1 * FS))
    above = np.where((sm[i0:] > floor_db + 10) & (sm[i0:] > note_db[i0:] - 50))[0]
    end = i0 + (above[-1] + 1 if len(above) else 0)
    end = int(min(max(end, i0 + int(0.1 * FS)), i0 + 4 * FS, len(z)))
    zz = z[i0:end]
    t = np.arange(len(zz)) / FS
    w = 10 ** (-0.9 * note_db[i0:end] / 20)
    w /= w.max()
    heard = smooth_db(zz, max(3, int(0.04 * FS))) > note_db[i0:end] - 40
    lv = 20 * np.log10(np.abs(zz) + 1e-12)
    a0 = max(0.5, -np.polyfit(t, lv, 1)[0]) / NEPER_DB
    ph = np.unwrap(np.angle(zz[:max(4, len(zz) // 2)]))
    f0 = float(np.clip(np.polyfit(t[:len(ph)], ph, 1)[0] / (2 * np.pi), -MAX_DF + 0.1, MAX_DF - 0.1))
    p1, c1, m1 = fit_modes(t, zz, w, 1, [np.array([a0, f0]), np.array([a0, 0.0])])
    e1 = db_error(zz, m1, heard)
    modes = [(p1, c1, 1)]
    a, df = p1
    inits = [np.array(v) for v in ([3 * a, df + 0.5, 0.5 * a, df - 0.5], [3 * a, df, 0.5 * a, df],
                                   [2 * a, df + 1.5, 0.7 * a, df - 1.0], [a, df + 1.0, a, df - 1.0])]
    p2, c2, m2 = fit_modes(t, zz, w, 2, inits)
    e2 = db_error(zz, m2, heard)
    start = np.sqrt(np.mean(np.abs(zz[:3]) ** 2))
    ok = (e2 < 0.85 * e1
          and np.all(np.abs(c2) <= 4 * start)
          and np.all(np.abs(p2[1::2]) < MAX_DF - 0.05)
          and np.all(p2[0::2] < MAX_DECAY / NEPER_DB - 0.01))
    if ok:
        modes = [(p2, c2, 2)]
    p, c, nm = modes[0]
    return [(float(p[2 * m] * NEPER_DB), float(p[2 * m + 1]), complex(c[m])) for m in range(nm)], e1, (e2 if ok else e1), len(zz)


def analyse_file(q):
    x, sr = C.load(q["path"])
    f = ring_f0(x, sr, C.mtof(q["midi"]))
    K = int(FMAX // f)
    dev, fks = partial_freqs(x, sr, f, K)
    zs = [envelope(x, sr, f, fk)[0] for fk in fks]
    i0 = int(round(T_C * FS))
    note_db = smooth_db(np.sqrt(np.sum([np.abs(z) ** 2 for z in zs], axis=0)), int(0.04 * FS))
    lvl0 = np.array([20 * np.log10(np.abs(z[i0]) + 1e-12) for z in zs])
    top = lvl0.max()
    harm = []
    e1s, e2s, two, capped = [], [], 0, 0
    for k, z in enumerate(zs, start=1):
        floor = float(np.percentile(smooth_db(z, int(0.1 * FS))[i0:], 10))
        if lvl0[k - 1] < max(top - FLOOR_DB, floor + OWN_FLOOR_DB):
            harm.append([])
            continue
        modes, e1, e2, _ = fit_harmonic(z, i0, floor, note_db)
        e1s.append(e1)
        e2s.append(e2)
        two += len(modes) == 2
        out = []
        sm = smooth_db(z, int(0.1 * FS))[i0:]
        w2 = int(0.1 * FS)
        bound = np.maximum(np.array([sm[max(0, j - w2):j + w2 + 1].max() for j in range(len(sm))]), floor) + 6
        tb = np.arange(len(sm)) / FS
        late = tb >= 0.15
        for dec, df, c in modes:
            peak = 2 * abs(c)                                   # a cosine's peak amplitude
            lv0 = 20 * np.log10(abs(c) + 1e-12)                 # in the envelope's terms, as floor
            need = float(np.max((lv0 - bound[late]) / tb[late])) if late.any() else 0.0
            if need > dec:
                dec = min(need, MAX_DECAY)
                capped += 1
            phase = np.angle(c) + 2 * np.pi * fks[k - 1] * T_C  # absolute, at T_C
            out.append([dec, df, float(20 * np.log10(peak + 1e-12)), float(np.mod(phase, 2 * np.pi))])
        harm.append(out)
    while harm and not harm[-1]:
        harm.pop()
    dev = dev[:len(harm)].tolist()

    # the level at T_C and the first second's decay, from the modes themselves
    tt = np.linspace(0, 1.0, 201)
    E = np.zeros_like(tt)
    for modes in harm:
        zsum = np.zeros_like(tt, dtype=complex)
        for dec, df, lv, ph in modes:
            zsum += 10 ** (lv / 20) * np.exp((-dec / NEPER_DB + 2j * np.pi * df) * tt + 1j * ph)
        E += 0.5 * np.abs(zsum) ** 2
    Edb = 10 * np.log10(E + 1e-30)
    wts = 10 ** (Edb / 10)
    decay = float(-np.polyfit(tt, Edb, 1, w=np.sqrt(wts / wts.max()))[0])
    onset = x[:int(round(ONSET_LEN * sr))]
    heard = float(20 * np.log10(np.sqrt(np.mean(x[:int(0.3 * sr)] ** 2)) + 1e-12))
    print("  %-4s rr %d: f0 %+.1f c, %3d harmonics (%d with two modes), level %.1f dB, decay %.0f dB/s, "
          "fit %.1f → %.1f dB, %d decays held to the recording" % (C.note_name(q["midi"]), q["rr"], C.cents(f, C.mtof(q["midi"])), len(harm), two,
                                   heard, decay, np.median(e1s), np.median(e2s), capped), flush=True)
    return dict(midi=q["midi"], rr=q["rr"], f0=f, dev=dev, harm=harm, level=heard, decay=decay,
                err1=float(np.median(e1s)), err2=float(np.median(e2s)), sr=sr), onset


def main():
    root, out_json, out_npz = sys.argv[1:4]
    fl = files(root)
    with Pool(2) as pool:
        res = pool.map(analyse_file, fl)
    notes = sorted({r["midi"] for r, _ in res})
    rrs = sorted({r["rr"] for r, _ in res})
    data = dict(notes=notes, rr=len(rrs), onset_len=ONSET_LEN, t_on=T_ON, xf=XF, t_c=T_C, fmax=FMAX,
                onset_rate=res[0][0]["sr"], cells=[r for r, _ in res])
    print("fit error, median over files: one mode %.1f dB, as kept %.1f dB" % (
        np.median([r["err1"] for r, _ in res]), np.median([r["err2"] for r, _ in res])))
    with open(out_json, "w") as f:
        json.dump(data, f)
    o = np.array([on for _, on in res])
    scale = float(np.max(np.abs(o))) / 32767
    np.savez_compressed(out_npz, onsets=np.round(o / scale).astype(np.int16), scale=scale)


if __name__ == "__main__":
    main()
