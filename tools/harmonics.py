"""A bowed note as harmonics over time, plus what is left (the residual).

`analyse(x, sr, f_guess)`: tracks f0 (common.track_f0), integrates it to a phase φ(t), and for each
harmonic k heterodynes the signal by e^{-jkφ(t)} and low-passes it (a Hann window ~3 periods long):
a_k(t) is the k-th harmonic's complex amplitude, which follows its level, its phase and any small
deviation of its frequency from k·f0. The harmonic part is Σ 2·Re(a_k e^{jkφ}); the residual is the
recording minus that (bow noise, the onset's scratch, whatever isn't periodic).

`steady_levels(x, sr, f0, a, b)`: each harmonic's level (dB) over a steady stretch from one long
spectrum, the power within ±(0.5 % of its frequency + 3 bins): cheap, for fitting across files.
"""
import numpy as np
from scipy.signal import fftconvolve

import common as C


def f0_per_sample(x, sr, f_guess):
    times, f0, lev = C.track_f0(x, sr, f_guess)
    ok = np.isfinite(f0)
    f0 = np.interp(times, times[ok], f0[ok])
    return np.interp(np.arange(len(x)) / sr, times, f0), times, lev


def analyse(x, sr, f_guess, kmax=None, fmax=16000.0):
    f0s, _, _ = f0_per_sample(x, sr, f_guess)
    phi = 2 * np.pi * np.cumsum(f0s) / sr
    fm = float(np.median(f0s))
    K = int(min(fmax, sr / 2 - 200) // fm)
    if kmax:
        K = min(K, kmax)
    n = int(max(3.0 / fm, 0.01) * sr) | 1
    w = np.hanning(n)
    w /= w.sum()
    a = np.zeros((K, len(x)), complex)
    h = np.zeros(len(x))
    for k in range(1, K + 1):
        base = x * np.exp(-1j * k * phi)
        ak = fftconvolve(base, w, mode="same")
        a[k - 1] = ak
        h += 2 * np.real(ak * np.exp(1j * k * phi))
    return dict(a=a, phi=phi, f0=f0s, fmed=fm, harm=h, resid=x - h, K=K)


def steady_levels(x, sr, f0, a, b, fmax=12000.0):
    seg = x[int(a * sr):int(b * sr)]
    n = len(seg)
    nfft = 1 << int(np.ceil(np.log2(n)) + 1)
    S = np.abs(np.fft.rfft(seg * np.hanning(n), nfft)) ** 2
    S /= (np.hanning(n) ** 2).sum() * n / 2      # a sine of amplitude A → about A²/2·(2/n)… relative only
    out = []
    k = 1
    while k * f0 < min(fmax, sr / 2 - 200):
        fk = k * f0
        half = 0.005 * fk + 3 * sr / nfft
        lo, hi = int((fk - half) * nfft / sr), int((fk + half) * nfft / sr) + 1
        out.append(10 * np.log10(S[lo:hi].sum() + 1e-30))
        k += 1
    return np.array(out)
