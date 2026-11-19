"""Shared helpers for the analysis tools: loading the bigcat cello, note names, pitch tracking.

The recordings are read from a checkout of github.com/sfzinstruments/karoryfer-bigcat.cello,
passed on the command line (never imported from: the data directory is untrusted).
"""
import os
import re

import numpy as np
import soundfile as sf

NOTE_INDEX = {"C": 0, "Db": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "Gb": 6, "G": 7, "Ab": 8,
              "A": 9, "Bb": 10, "B": 11}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# The library names its notes an octave below scientific pitch: its "C1" is the cello's open C
# string (C2, 65.4 Hz). Measured: every file's f0 is 12 semitones above its name in the
# C4 = 60 convention (tools/inventory.py prints the check).
NAME_OCTAVE_OFFSET = 1

DYNAMICS = ["p", "mp", "mf", "f"]
# What every render compared with a recording starts from: the recordings are dry and close-miked,
# so no reverb (the synth's room, Phase 3d, is on by default)
DRY = {"space.room": 0.0}


def midi_of(name):
    """Library note name ('Eb2') -> MIDI note of the sound, with the library's octave offset."""
    m = re.fullmatch(r"([A-G]b?)(-?\d)", name)
    if not m:
        raise ValueError(name)
    return 12 * (int(m.group(2)) + 1 + NAME_OCTAVE_OFFSET) + NOTE_INDEX[m.group(1)]


def note_name(midi):
    return "%s%d" % (NAMES[midi % 12], midi // 12 - 1)


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def load(path):
    x, sr = sf.read(path, always_2d=True, dtype="float64")
    return x.mean(axis=1), sr


def sustains(root):
    """Every bowed sustain: dict(name, midi, dyn, bow, path). bow: 'd' (down) or 'g' (up)."""
    out = []
    d = os.path.join(root, "Samples", "sus")
    for f in sorted(os.listdir(d)):
        m = re.fullmatch(r"([A-G]b?\d)_(p|mp|mf|f)_([dg])\.wav", f)
        if m:
            out.append(dict(name=m.group(1), midi=midi_of(m.group(1)), dyn=m.group(2),
                            bow=m.group(3), path=os.path.join(d, f)))
    return out


def onset(x, sr, frac=0.05):
    """Index where the smoothed envelope first reaches frac of its peak, less 2 ms (as the piano)."""
    env = np.sqrt(np.convolve(x * x, np.ones(int(0.005 * sr)) / int(0.005 * sr), "same"))
    i = int(np.argmax(env >= frac * env.max()))
    return max(0, i - int(0.002 * sr))


def track_f0(x, sr, f_guess, hop=0.005, win=None, nharm=8):
    """Frame-by-frame f0 near f_guess: the weighted mean of the first harmonics' peak
    frequencies (each found by parabolic interpolation within ±1 semitone of n·f).
    Returns times, f0 (Hz; NaN where too quiet), frame level (dB)."""
    if win is None:
        win = max(0.04, 6.0 / f_guess)
    n = int(win * sr)
    nfft = 1 << int(np.ceil(np.log2(n * 4)))
    w = np.hanning(n)
    h = int(hop * sr)
    times, f0s, lev = [], [], []
    for start in range(0, len(x) - n, h):
        seg = x[start:start + n] * w
        S = np.abs(np.fft.rfft(seg, nfft))
        lev.append(20 * np.log10(np.sqrt(np.mean(seg ** 2)) + 1e-12))
        times.append((start + n / 2) / sr)
        est, wsum = 0.0, 0.0
        for k in range(1, nharm + 1):
            fk = k * f_guess
            lo = int(fk * 2 ** (-1 / 12) * nfft / sr)
            hi = int(fk * 2 ** (1 / 12) * nfft / sr) + 1
            if hi >= len(S) - 1 or lo < 1:
                break
            j = lo + int(np.argmax(S[lo:hi]))
            a, b, c = np.log(S[j - 1:j + 2] + 1e-12)
            p = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
            fj = (j + p) * sr / nfft / k
            wgt = S[j] ** 2
            est += wgt * fj
            wsum += wgt
        f0s.append(est / wsum if wsum > 0 else np.nan)
    times, f0s, lev = np.array(times), np.array(f0s), np.array(lev)
    f0s[lev < lev.max() - 40] = np.nan
    return times, f0s, lev


def cents(f, ref):
    return 1200 * np.log2(f / ref)
