#!/usr/bin/env python3
"""Write src/CelloData.h from tools/cello.json and tools/cello_onsets.npz (tools/analyze.py).

    python3 -I tools/make_header.py tools/cello.json tools/cello_onsets.npz src/CelloData.h

The noise bands' gains are solved here, against the engine's own filters (two RBJ band-pass stages,
Q 1.2, per octave band: `kNoiseQ`), so that their overlapping outputs add up to each cell's measured
band powers (tools/analyze.py `noise`) for unit-variance white noise at kOnsetRate, a separate noise
per band (so their powers add). The engine scales them by its sample rate.
"""
import json
import os
import sys

import numpy as np
from scipy.signal import freqz

NOISE_Q = 1.2


def rbj_bandpass(fc, q, sr):
    w = 2 * np.pi * fc / sr
    al = np.sin(w) / (2 * q)
    b = np.array([al, 0, -al])
    a = np.array([1 + al, -2 * np.cos(w), 1 - al])
    return b / a[0], a / a[0]


def band_matrix(bands, sr):
    """M[i, j]: power in analysis band i of filter j's output, for unit-variance white noise."""
    f = np.linspace(0, sr / 2, 1 << 15)
    df = f[1] - f[0]
    M = np.zeros((len(bands), len(bands)))
    for j, fc in enumerate(bands):
        fcj = min(fc, 0.45 * sr)
        b, a = rbj_bandpass(fcj, NOISE_Q, sr)
        _, h = freqz(b, a, worN=f, fs=sr)
        P = np.abs(h) ** 4 / (sr / 2)          # two stages; white noise of variance 1: density 1/(sr/2)
        for i, fi in enumerate(bands):
            sel = (f >= fi / np.sqrt(2)) & (f < fi * np.sqrt(2))
            M[i, j] = np.sum(P[sel]) * df
    return M


def solve_gains(M, target_db):
    """Power gains g ≥ 0 with M g ≈ target, matched in dB (a quiet band mustn't switch its loud
    neighbour off, as solving in power would let it: the piano's lesson)."""
    T = 10 ** (np.array(target_db) / 10)
    g = T / np.diag(M)
    for _ in range(400):
        g *= (T / (M @ g)) ** 0.5
    g = np.maximum(g, 1e-12)   # a band whose neighbours already pass more than its target: off
    return 10 * np.log10(g), 10 * np.log10(M @ g) - np.array(target_db)


def grain_table():
    """The noise pulse's shape: u^p with u = (1 + cos θ) / 2. Its depth (2<e cos θ>/<e>, what
    tools/life.py measures) for each exponent p, inverted on a grid of depths 0-1.9 by 0.05."""
    th = np.linspace(0, 2 * np.pi, 4096, endpoint=False)
    u = (1 + np.cos(th)) / 2
    ps = np.linspace(0, 40, 4001)
    depth = np.array([2 * np.mean(u ** p * np.cos(th)) / np.mean(u ** p) for p in ps])
    grid = np.arange(0, 1.9001, 0.05)
    return grid, np.interp(grid, depth, ps)


def arr(name, ctype, values, fmt, per_line=16):
    flat = list(values)
    lines = []
    for i in range(0, len(flat), per_line):
        lines.append("  " + ", ".join(fmt(v) for v in flat[i:i + per_line]))
    return "constexpr %s %s = {\n%s};\n" % (ctype, name, ",\n".join(lines))


def ff(v):
    t = "%.6g" % v
    if not any(c in t for c in ".en"):
        t += ".0"
    return t + "f"


def main():
    js, npz, out = sys.argv[1:4]
    d = json.load(open(js))
    # the movement's calibration (tools/calibrate_life.py), kept apart so re-analysing keeps it
    adj_path = os.path.join(os.path.dirname(os.path.abspath(js)), "life_adjust.json")
    if os.path.exists(adj_path):
        adj = json.load(open(adj_path))
        for key in ("pitch", "level"):
            if key in adj:
                d["life_" + key] = (np.array(d["life_" + key]) * np.array(adj[key])).tolist()
        if "harm" in adj:   # the harmonics' own movement: its patterns and what is left over
            h = np.array(adj["harm"])
            d["life_shape_oct"] = (np.array(d["life_shape_oct"]) * h).tolist()
            d["life_resid_oct"] = (np.array(d["life_resid_oct"]) * h).tolist()
    on = np.load(npz)
    onsets = on["onsets"].astype(np.float64)
    if "scale" in on:
        onsets *= float(on["scale"])
    notes, dyns, K, bands = d["notes"], d["dynamics"], d["kmax"], d["bands"]
    nN, nD, nB = len(notes), len(dyns), len(bands)
    sr = d["onset_rate"]
    cells = {(c["midi"], c["dyn"]): c for c in d["cells"]}
    # the harmonics' movement per cell, by how the bands move (tools/calibrate_flicker.py)
    fadj_path = os.path.join(os.path.dirname(os.path.abspath(js)), "flicker_adjust.json")
    if os.path.exists(fadj_path):
        fadj = json.load(open(fadj_path))
        so, rk = np.array(d["life_shape_oct"]), np.array(d["life_resid_k"])
        for i, m in enumerate(d["notes"]):
            for j, dy in enumerate(d["dynamics"]):
                g = fadj.get("%d_%s" % (m, dy), 1.0)
                so[i * len(d["dynamics"]) + j] *= g
                rk[i * len(d["dynamics"]) + j] *= g
        d["life_shape_oct"], d["life_resid_k"] = so.tolist(), rk.tolist()
    # the noise's calibration (tools/calibrate_noise.py): added to the targets before the solve
    nadj_path = os.path.join(os.path.dirname(os.path.abspath(js)), "noise_adjust.json")
    nadj = json.load(open(nadj_path)) if os.path.exists(nadj_path) else {}
    M = band_matrix(bands, sr)
    hand_db = np.full((nN, nD, K), -12000, int)
    hand_ph = np.zeros((nN, nD, K), int)
    corr = np.zeros((nN, nD, K), int)
    level = np.zeros((nN, nD))
    hand_f0 = np.zeros((nN, nD))
    fit_f0 = np.zeros((nN, nD))
    nk = np.zeros((nN, nD), int)
    noise = np.zeros((nN, nD, nB))
    worst = 0.0
    for i, m in enumerate(notes):
        for j, dy in enumerate(dyns):
            c = cells[(m, dy)]
            k = c["K"]
            nk[i, j] = k
            hand_db[i, j, :k] = np.clip(np.round(np.array(c["hand_db"]) * 100), -12000, 3000)
            hand_ph[i, j, :k] = np.round(np.array(c["hand_phase"]) / np.pi * 128).astype(int) % 256 - 128 * 0
            kc = len(c["corr"])
            corr[i, j, :kc] = np.round(np.array(c["corr"]) * 100)
            level[i, j] = c["level"]
            hand_f0[i, j] = c["hand_f0"]
            fit_f0[i, j] = c["fit_f0"]
            target = np.array(c["noise"]) + np.array(nadj.get("%d_%s" % (m, dy), [0.0] * nB))
            g, resid = solve_gains(M, target)
            noise[i, j] = g
            worst = max(worst, float(np.max(np.abs(resid))))
    hand_ph = np.where(hand_ph > 127, hand_ph - 256, hand_ph)
    scale = float(np.max(np.abs(onsets))) / 32767
    q = np.round(onsets / scale).astype(int)
    L = onsets.shape[1]
    src = [
        "// Generated by tools/make_header.py from tools/cello.json and tools/cello_onsets.npz",
        "// (tools/analyze.py), measured from the Karoryfer x bigcat cello (Karoryfer Samples and bigcat",
        "// instruments, cellist Kamila Borowiak; CC0). The onsets are excerpts of its recordings.",
        "// Do not edit by hand.",
        "#pragma once",
        "",
        "namespace cello_data {",
        "",
        "constexpr int kOnsetRate = %d;" % sr,
        "constexpr int kNotes = %d;      // measured notes, a minor third apart" % nN,
        "constexpr int kDyns = %d;       // p, mp, mf, f" % nD,
        "constexpr int kHarm = %d;     // harmonics per note at most" % K,
        "constexpr int kBands = %d;      // noise and release: octave bands" % nB,
        "constexpr float kTOn = %s, kXf = %s, kTC = %s;   // the onset's crossfade to the model (s)" % (
            ff(d["t_on"]), ff(d["xf"]), ff(d["t_c"])),
        "constexpr float kFMax = %s;   // the highest harmonic the model plays (Hz)" % ff(d["fmax"]),
        "constexpr float kNoiseQ = %s;" % ff(NOISE_Q),
        "constexpr int kOnsetLen = %d;" % L,
        "constexpr float kOnsetScale = %.6ef;" % scale,
        "",
        arr("noteMidi[kNotes]", "int", notes, str),
        arr("bandHz[kBands]", "float", bands, ff),
        "// steady harmonic level, rms dBFS, per note and dynamic",
        arr("level[kNotes][kDyns]", "float", level.flatten(), ff, 4),
        "// the pitch at the hand-off (Hz), and the pitch the spectrum was fitted at",
        arr("handF0[kNotes][kDyns]", "float", hand_f0.flatten(), ff, 4),
        arr("fitF0[kNotes][kDyns]", "float", fit_f0.flatten(), ff, 4),
        "// harmonics measured per cell (up to kFMax)",
        arr("handCount[kNotes][kDyns]", "short", nk.flatten(), str, 4),
        "// each harmonic at the hand-off: peak level (centi-dB re full scale) and phase (1/128 of pi)",
        arr("handDb[kNotes][kDyns][kHarm]", "short", hand_db.flatten(), str, 20),
        arr("handPh[kNotes][kDyns][kHarm]", "signed char", hand_ph.flatten(), str, 32),
        "// the note's own steady spectrum against source x body, per harmonic (centi-dB)",
        arr("corr[kNotes][kDyns][kHarm]", "short", corr.flatten(), str, 20),
        "// bow noise: each band filter's power gain (dB, re the cell's level) for unit white noise",
        "// at kOnsetRate (the solve's worst band is %.1f dB off)" % worst,
        arr("noiseDb[kNotes][kDyns][kBands]", "float", noise.flatten(), ff, 9),
        "// the release: each band's decay after the bow stops (dB/s), from the staccatos",
        arr("releaseDbS[kNotes][kBands]", "float", np.array(d["release"]).flatten(), ff, 9),
        "// source x body: S[dyn][harmonic] (dB) and B on log2(f) knots (dB)",
        arr("source[kDyns][kHarm]", "float", np.array(d["source"]).flatten(), ff, 10),
        "constexpr int kKnots = %d;" % len(d["knots"]),
        "constexpr float kKnot0 = %s, kKnotStep = %s;   // log2(Hz)" % (ff(d["knots"][0]), ff(d["knots"][1] - d["knots"][0])),
        arr("body[kKnots]", "float", d["body"], ff, 10),
        "// the bow's movement while a note is held (tools/life.py): per note, the rms in each octave of",
        "// modulation frequency (lower edges kLifeOct0 · 2^i Hz) of its pitch (cents) and level (dB)",
        "constexpr int kOct = %d;" % len(d["life_pitch"][0]),
        "constexpr float kLifeOct0 = 0.25f;",
        arr("lifePitch[kNotes][kOct]", "float", np.array(d["life_pitch"]).flatten(), ff, 8),
        arr("lifeLevel[kNotes][kOct]", "float", np.array(d["life_level"]).flatten(), ff, 8),
        "// the harmonics' own movement (dB, against the level), per note and dynamic from its down-bow",
        "// recording: kPat shared patterns (a shape over harmonics 1-kPatHarm, and the rms per octave",
        "// of how it moves), and what is left over, per harmonic (rms) and its spectrum (unit power)",
        "constexpr int kPat = %d, kPatHarm = %d;" % (len(d["life_shape"][0]), len(d["life_shape"][0][0])),
        arr("lifeShape[kNotes * kDyns][kPat][kPatHarm]", "float", np.array(d["life_shape"]).flatten(), ff, 10),
        arr("lifeShapeOct[kNotes * kDyns][kPat][kOct]", "float", np.array(d["life_shape_oct"]).flatten(), ff, 8),
        arr("lifeResidK[kNotes * kDyns][kHarm]", "float", np.array(d["life_resid_k"]).flatten(), ff, 10),
        arr("lifeResidOct[kNotes * kDyns][kOct]", "float", np.array(d["life_resid_oct"]).flatten(), ff, 8),
        "// the bow noise's pulse at the string's period, per note, dynamic and band (down bow): its depth",
        "// (2<e cos θ>/<e>) and where in the fundamental's period it peaks (rad)",
        arr("grainDepth[kNotes][kDyns][kBands]", "float", np.array(d["grain_depth"]).flatten(), ff, 9),
        arr("grainPhase[kNotes][kDyns][kBands]", "float", np.array(d["grain_phase"]).flatten(), ff, 9),
        "// the pulse u^p (u = (1 + cos θ) / 2) that has a depth: p at depths 0, 0.05 … 1.9",
        "constexpr int kGrainSteps = %d;" % len(grain_table()[0]),
        arr("grainExp[kGrainSteps]", "float", grain_table()[1], ff, 10),
        "// the onsets, per note and dynamic: kOnsetLen samples at kOnsetRate, times kOnsetScale",
        arr("onset[kNotes * kDyns][kOnsetLen]", "short", q.flatten(), str, 24),
        "}  // namespace cello_data",
        "",
    ]
    with open(out, "w") as f:
        f.write("\n".join(src))
    print("wrote %s: %d onsets of %d samples; noise solve within %.1f dB" % (out, len(q), L, worst))


if __name__ == "__main__":
    main()
