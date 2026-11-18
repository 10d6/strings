# Phase 0: what the cello recordings hold, and does the model work?

Phase 0 of `docs/PLAN.md`: inventory the cello's recordings, then rebuild a few notes the way the plan
proposes and measure how close they come. **Result: the architecture holds.** A bowed note rebuilt
from its harmonics, its recorded onset and shaped noise is 2.5 % from its recording by the perceptual
distance, closer than the same note played with the other bow. A note the model has not seen, played
from one source × body fit, is 7 %, about half the distance of a neighbour transposed by harmonic
number (13 %).

Everything here is reproducible (needs `pip install numpy scipy soundfile matplotlib`):

```
git clone --depth 1 https://github.com/sfzinstruments/karoryfer-bigcat.cello ../bigcat   # 267 MB
python3 -I tools/inventory.py ../bigcat --json inventory.json     # 20 s
python3 -I tools/bodyfit.py ../bigcat --json bodyfit.json         # 25 s
python3 -I tools/spike.py ../bigcat spike-out                     # 70 s; WAVs to listen to
```

## The recordings (Karoryfer × bigcat cello)

From `tools/inventory.py`. The library is on GitHub (`sfzinstruments/karoryfer-bigcat.cello`, CC0),
which is the only place the workspace can download it from; Karoryfer's shop and the Iowa site are
out of reach (the Iowa recordings stay a candidate, to be attached by hand if needed).

| | |
|---|---|
| Format | mono, 44.1 kHz, 24-bit WAV; 479 files |
| Bowed sustain (`sus`) | 17 notes a minor third apart, **C2-C6** sounding; 4 dynamics (p, mp, mf, f); 2 takes each, `_d` and `_g` (down and up bow, Polish *dół* / *góra*): 136 files, 3-7 s |
| Staccato | the same notes, 4 dynamics × 4 round robins (270 files, 0.5-2 s), ending in the string's own decay |
| Pizzicato | 13 notes × 4 round robins (52 files, 0.75-7 s) |
| Noises | 4 harmonic slides (one per string), 17 knocks (`stuk`) |

Things to know:

- **Names are an octave low.** The library's "C1" sounds C2 (65.4 Hz), the open C string: every one of
  the 136 sustains measures 12 semitones above its name (`common.NAME_OCTAVE_OFFSET`).
- **No vibrato**, as advertised: the strongest periodic pitch movement at 3-9 Hz is ±0.25 cents
  (median; ±1.4 at most). The pitch wanders by 1-3 cents rms over a note, the bow's own unsteadiness.
  So the model's vibrato will be its own, on a clean note.
- **Tuning**: +1.9 cents from equal temperament (median), −12…+14 over all files.
- **Trimmed at the attack.** Every sustain starts at sample 0, its first 5 ms already 8 dB under the
  sustain (median). The first instant of the bow's catch may be clipped; nothing before it to measure
  a noise floor from.
- **Cut mid-bow.** The sustains end still sounding (the last 0.1 s is 0.5 dB under the sustain), and
  114 of 136 end on a sample over 5 % of full scale: they were cut for looping, so they have no release.
  **The release comes from the staccatos**, which end in the string's free decay: 26-160 dB/s after
  the bow stops (10th-90th percentile, median 48). Pizzicato decays at 12-45 dB/s (median 27).
- Level per dynamic (median, dBFS): p −32.7, mp −26.8, mf −23.1, f −20.8. 32-46 harmonics stand
  20 dB over the noise between them.

## Source × body (`tools/bodyfit.py`)

Each sustain's steady harmonic levels are fitted as one level per file, plus a **source** spectrum by
harmonic number per dynamic, plus one **body** response by frequency for the whole cello (piecewise
linear in log-frequency). The test is leave one note out: fit without a note (its 8 files), predict
its spectrum, and compare in rms dB per harmonic (level fitted, weighted by level).

| Prediction of an unseen note | median | mean | |
|---|---|---|---|
| **source × body** (1/24-octave body) | **4.0 dB** | 4.2 | nearer than the neighbour in **136 of 136** files |
| the nearest sampled note, by harmonic number (a sampler transposing it) | 7.6 dB | 7.9 | |
| the same note's other bow (the recordings' own variation) | 3.1 dB | 3.1 | |

The body is detailed: knots every 1/6 octave gave 5.1 dB, 1/12 4.4, **1/24 4.05** (smoothing λ 0.3),
1/48 4.1 (starting to overfit). That fits a body with many narrow resonances, and it's the part that
makes vibrato come alive: a harmonic moving a few cents crosses them.

Not tried yet: a source per string (the library doesn't say which string each note was played on),
or a source that changes with pitch along the string. Either could close some of the gap between
4.0 dB and the 3.1 dB floor.

## Rebuilding notes (`tools/spike.py`)

Seven notes from C2 to F#5 (C4 at p, mf and f), each rebuilt and compared with its recording over
0-3 s by the perceptual distance (`tools/perceptual.py`, ported from the piano: attack 0-80 ms, early
80-500 ms, sustain 0.5-3 s). Every model variant uses the recording's own level envelope (smoothed
over 100 ms), so they test the timbre, not a player.

| Variant | score | attack | early | sustain |
|---|---|---|---|---|
| analysed harmonics + residual (check) | 0.0 | 0.0 | 0.0 | 0.0 |
| harmonics alone, no residual | 1.3 | 2.4 | 0.2 | 0.2 |
| **model**: measured swell for 0.3 s, then a fixed spectrum (its own), steady pitch, shaped noise | 3.2 | 3.6 | 2.3 | 3.0 |
| **+ onset**: the first 0.3 s of the residual as recorded | **2.5** | 2.9 | 2.2 | 3.0 |
| + onset, with the recording's pitch wander | 2.4 | 1.6 | 2.1 | 3.0 |
| + onset, the other bow's spectrum (yardstick) | 3.6 | 2.9 | 3.0 | 5.3 |
| + onset, **source × body** for a note it hasn't seen | **7.0** | 2.9 | 6.8 | 12.4 |
| + onset, the neighbour's spectrum, by harmonic number | 13.0 | 2.9 | 13.4 | 25.6 |
| the other bow's recording, whole (another performance) | 16.7 | 25.0 | 16.0 | 10.6 |
| the neighbour's recording transposed (a sampler) | 26.9 | 30.1 | 28.5 | 27.6 |

Medians over the 7 notes (%). What it says:

- **The model is close.** With its own spectrum, a rebuilt note is nearer its recording (2.5 %) than
  the same note's other bow (3.6 %) is. The recorded onset helps the attack (3.6 → 2.9) and the early
  sound; the steady noise costs about 3 % of the sustain, which pitch-synchronous noise should reduce.
- **The onset should keep its pitch.** With the recording's pitch movement in the onset, the attack
  goes 2.9 → 1.6: a bow's catch glides into the note. The engine will play the onset's pitch track
  and settle to a steady pitch (or the player's vibrato) after it.
- **Between the sampled notes, source × body halves the error** of transposing a neighbour (7.0 against
  13.0; better on 6 of 7 notes, A4 the exception at 6.5 against 5.4). It is still twice the yardstick,
  mostly in the sustain: the next work on the fit is there.
- The whole-recording references (16.7 and 26.9) are another performance, with their own envelope and
  onset; they show how far apart two real takes are, not timbre alone.
- The residual matters most high up: F#5 without it is 6.0 %, the rest 0.5-2.1 %.

`spike.py` writes a WAV per note (recording, + onset, + onset body, + onset neighbour, sampler, 0.6 s
apart). The spectrograms show no clicks or artifacts.

## What this decides for Phase 1

- Keep the architecture: harmonics with a source × body spectrum, a recorded onset of 0.3 s per
  measured note and dynamic (its residual, its harmonics' swell and its pitch track), shaped noise.
- The body at 1/24 octave from 55 Hz to 12 kHz is 190 numbers; the source is 4 × 120. The onsets
  dominate the data: 0.3 s × 136 files × 16 bits is about 3.5 MB (one bow per note and dynamic halves
  it), as the piano's strikes are.
- The release comes from the staccatos' decay; the sustains have none.
- Next measurements: a source per string and along the string (to close the gap to the yardstick),
  pitch-synchronous bow noise, the release, and the dynamics as a continuous axis (the source's
  change from p to f, which the player's bow will move through).
