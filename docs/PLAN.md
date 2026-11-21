# Plan

A modelled cello and violin in one synth, measured from recordings the way `10d6/piano` is.
Recorded audio is kept only for the onset (the bow's catch, its scratch and noise). Everything that
sustains is a model, so it can be played continuously, varied and taken past what a real instrument
does.

**One synth, two instruments.** An **Instrument** choice (Cello, Violin) selects the measured data
set, and both share the engine, the controls and the page. Each instrument's data is a few MB of
generated header, as the piano's is, so carrying both costs nothing at run time. If the browser page
grows past what loads comfortably, split them into two builds of the same source.

## Sources

`docs/SOURCES.md` lists the recordings, their licenses and what each is used for. In short:

- Cello: **Karoryfer × bigcat Cello** (CC0, primary) and **University of Iowa MIS cello**
  (unrestricted; dry, every note, pp/mf/ff per string).
- Violin: **VSCO 2 CE Solo Violin** (CC0, primary) and **Iowa MIS violin**.

## Where it stands (2026-11-20)

The cello is playable and was judged by ear at every step (Phases 0-3, PRs #1-#11, all merged). 3b's
articulations are built: pizzicato (PR #10, merged), then staccato, spiccato, tremolo and harmonics
(PR #12, for the owner's ears). Next: Phase 4, calibration and a `v0.1` release.
`docs/MODEL.md` is the reference for how everything works and why; `CLAUDE.md` has the rules, the
lessons and the checks to run.

- **The note**: the recorded onset (0.4 s) handing over to a harmonic bank: source × body plus the
  measured notes' own corrections and the body's fine detail; the bow's measured movement; bow noise
  pulsing at the string's period; the release from the staccatos.
- **Playing** (3a): Dynamics From Velocity or Controller (CC 1 and 11); vibrato; Legato and Mono with
  Glide; Slur (a dip and the vibrato starting again); One Note Each (four strings); Even Notes; Bow
  Weight.
- **Pizzicato** (3b, first part): the pluck as recorded, then each harmonic's measured modes ringing
  down (`tools/pizz.py`); Articulation (Arco, Pizzicato) and keyswitches C1, F1. 8.0 % from its
  recordings (another take of the same note: 16.8 %).
- **Bow colour** (3c): Bow Position (sul tasto … sul ponticello), the Mute.
- **Body and room** (3d): a room (synthkit's `dsp::Reverb`, the piano's); sympathetic open strings;
  Body Size; a wolf.
- **Numbers today**: 4.2 % median from the recordings (timbre 3.0; 3.5 and 2.7 at their own pitch);
  hand-off 0.2 dB; browser 2.6× realtime on four low notes with the room. 25 presets.

**What the owner has said** (the decisions that stand): one synth with an Instrument choice; the
browser page is for quick testing, so no big quality trade-offs for its speed; Still Bow (no
movement) sounded good and every movement since was judged against it; the level moves below 2 Hz
only; vibrato is convincing; slurs needed the dip and the vibrato restarting; the notes needed
evening out; the recordings' tone is edgy (close-miked), which Bow Weight, Bow Position and the room
answer. The owner tests each PR on its Pages preview and installs plugin zips at milestones.

## What's left

### 3b: articulations (done, PR #12 for the owner's ears)

bigcat has more for this than the first plan assumed (`docs/PHASE0.md`): **pizzicato** (13 notes × 4
round robins, 0.75-7 s, decaying 12-45 dB/s), **staccato** (the 17 notes × 4 dynamics × 4 round
robins, 0.5-2 s, ending in the free decay), a **harmonic slide** per string, and 17 **knocks**. So
most of 3b can be measured.

- **Done (PR #10)**: the Articulation choice (Arco, Pizzicato so far; the others are appended as they
  come, so patches keep their indices), keyswitches C1 Arco and F1 Pizzicato, and pizzicato
  (docs/MODEL.md: Pizzicato). The owner chose: pizzicato first in its own PR, the rest in a second;
  keyswitches from C1 on white keys (D1 Staccato, E1 Spiccato, G1 Tremolo, A1 Harmonics are kept for
  them). Not a modulation destination: voices read it as they start, through `processEvents`. Left
  from the pizzicato: above C5 (C5's pluck transposed), a pluck position, the recordings' louder open
  strings.
- **Done (PR #12)**: staccato (measured: each take's own stroke, bow-off and release; 23.5 % from its
  recordings, another take 26.1), spiccato (a judgment from the staccatos), tremolo (a judgment;
  notes started together share one bow), natural and artificial harmonics (measured from the slides),
  keyswitches D1, E1, G1, A1, Tremolo Rate; and a fix for a plucked note far from its pitch, which blew
  up (docs/MODEL.md). Not done: col legno (the knocks), the seagull effect between harmonic nodes.
- **Choosing an articulation** (as first planned): an Articulation choice (Arco, Staccato, Spiccato, Pizzicato,
  Tremolo, Harmonics), modulatable, and **keyswitches** (low keys below the cello's range, swallowed
  in `processEvents`, which moves the choice with `ctx.setParam`: API.md §4a; check the page's
  keyboard shows them). A voice reads it at its start; changing it during a note affects the next.
- **Pizzicato** (measured; done, as planned here except as docs/MODEL.md says): decaying modes, as the piano's partials. A tool like `analyze.py` for the
  pizzicato files: per note, each harmonic's initial level and decay rate, fitted as a pluck source ×
  the same body (the body fit is shared), plus a recorded pluck onset (about 50-100 ms, the finger's
  snap, as the arco onset is kept) handing over to decaying harmonics in phase (the same `handDb` /
  `handPh` machinery). Velocity sets the pluck's strength (the four round robins span no dynamics:
  check, and if they don't, velocity scales level and brightness by a judgment). The fine detail and
  sympathetic strings apply as they are; vibrato on a plucked note is possible (left hand). Pluck
  position as Bow Position's comb (a judgment).
- **Staccato** (measured): the bow leaves after the stroke whatever the key does. The staccato takes'
  first part as the onset (their own, not the sustains'), the model for the rest of the stroke, and
  the release; the stroke's length from the takes (bow off where they fall 6 dB). Their four round
  robins rotate.
- **Spiccato** (judgment, from staccato): bounced, shorter and lighter: the staccato takes at a lighter
  layer, a shorter stroke, more noise at the bounce. VSCO's violin spiccato (Phase 5's data) can size
  it if needed.
- **Tremolo** (judgment; VSCO violin has tremolo to measure rate and shape): rapid bow changes, each a
  small re-bow (the level dipping, the noise bursting, the patterns' movement reset), at a Tremolo
  Rate (about 8-16 strokes a second) with some irregularity; measured or by ear.
- **Natural harmonics** (measured from the slides): a finger lightly at 1/n of a string keeps only its
  partials that are multiples of n (the piano's Touch Point does this for a piano string). A note is
  played as the nearest natural harmonic of an open string (2nd-6th); the source keeps the string's
  multiples of n with the slides' measured spectra (fewer, flute-like partials), the body as always.
  The slides sweep continuously, so they also give the touch's own sound between nodes.
- **Knocks / col legno** (optional): the knocks are short enough to play as recorded.
- Check, as every phase: the measures in `CLAUDE.md`, renders looked at and listened to, demos for the
  owner, presets that a player would use.

### 4: calibration and listening

- **Leave one note out** (Phase 0's test, now on the engine): rebuild the header without a measured
  note and measure the render of that note against its recording, for every note: how well the model
  plays the notes between the measured ones (where most notes are).
- **Blind listening**: a page (or a set of files) pairing renders with recordings at random, for the
  owner to tell apart and to rate; the distance and `life.py` say where to look, the owner's ears
  decide.
- **The judgments, revisited by ear**: Even Notes' curve, the sympathetic coupling, Slur's dip, the
  room's default, Bow Position's extremes, the vibrato's string scaling.
- **Known gaps** to look at: the pitch wander reads 1.09 cents rms against the recordings' 1.58; a few
  cells move more than their recordings even with no flicker (C3 f, C2 mf, C5 f, F#2 f: their level's
  own movement); the renders' late release sits higher than the recordings' (−86 against −94 dB 0.3 s
  after a staccato is 36 dB down); the staccatos' late sympathetic ring isn't reproduced (a model of a
  note's string coupled to its open neighbour might); speed in the browser (2.6×).
- **A milestone release**: tag `v0.1` (CI makes a release from the plugin zips) for the owner to try in
  Ableton (VST3, Windows: the main target) and GarageBand (AU).

### 5: violin

- **Inventory** VSCO 2 CE's solo violin (CC0) as Phase 0 did the cello: notes, layers, round robins,
  articulations, tuning, room. It has vibrato, which changes the analysis:
  - the sustain's spectrum: average over whole vibrato cycles;
  - the bow's movement: separate the vibrato (a band around 5-7 Hz, and its harmonics) from the wander;
  - the body's fine detail can be **measured** here, not just its statistics: the vibrato sweeps each
    harmonic across ±20 cents of the body, which the cello's 1-2 cent wander couldn't resolve;
  - the onset needs a take or a moment before the vibrato starts, or the hand-off has to meet it.
- **Generalise the tools** by instrument (open strings G3 D4 A4 E5, the note range, the layer names,
  the data path), and the header (`ViolinData.h` beside `CelloData.h`); the engine reads the chosen
  instrument's tables (a pointer per voice, set at its start). Each instrument's calibrations
  (`*_adjust.json`) are its own.
- **The Instrument choice** (Cello, Violin) selects the data; the controls stay; presets per instrument.
  If the browser page gets too large with both, build the two separately from the same source.
- Iowa MIS (anechoic, every note, per string) can fill gaps if it's attached by hand: the workspace
  can't reach it.

### 6: experiment

A waveguide bow-friction engine (a string as two delay lines and a friction curve at the bow) as a
second model, judged on the same distance and by ear against this one. It could give what this
can't measure: real Helmholtz motion breaking up (overpressure, flautando), legato transitions,
double-slip. An experiment: kept only if it wins somewhere.

### Other threads

- **Piano onto the kit's reverb**: 10d6/piano still has its own `src/Reverb.h`; it can move to
  synthkit's `dsp::Reverb` (the same algorithm; renders within 0.03 dB) in a piano PR.
- bigcat's sfz programs include "legato" maps, which look like crossfades of sustains rather than
  recorded transitions: check before assuming legato can be measured.

## Starting a new session

1. Set up the workspace (`CLAUDE.md`: Fresh workspace), and clone the recordings next to the repo:
   `git clone --depth 1 https://github.com/sfzinstruments/karoryfer-bigcat.cello ../bigcat` (267 MB;
   the analysis tools take the path).
2. Build and check: `cmake -S . -B build-rel -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build
   build-rel`, then `./build-rel/strings_render --check . --out /tmp/renders` and `python3 -I
   tools/measure.py ../bigcat build-rel/strings_render` (4.2 %, timbre 3.0): if those match, the
   workspace is right.
3. Read `docs/MODEL.md` for the engine, then start on Phase 4 above, on a branch, with a PR when it's
   ready for the owner's ears.

## The model

A bowed note is driven rather than struck, so the sustain is a different core from the piano's
decaying partials. The rest of the piano's pipeline carries over.

- **Sustain: source × body.** Each harmonic's level is the bowed string's spectrum (set by bow speed
  and pressure) times one fixed body response at that harmonic's frequency. The two are fitted
  separately across every note and dynamic. Vibrato and portamento then sweep the harmonics across
  the body's resonances, as on the real instrument, which is much of why vibrato sounds alive, and
  notes between the sampled ones interpolate without spectral artifacts.
- **Onset: recorded.** Sinusoidal tracking with time-varying frequencies (bow onsets glide in pitch,
  so the piano's fixed notches would leave residue) gives each harmonic's swell. What's left (the
  scratch and noise) is stored, 0.2-0.3 s per measured note and layer, as `PianoStrike.h` is.
- **Bow noise.** Pitch-synchronous noise, measured in bands and played through the body.
- **Release.** The string's own decay and the body's short ring.
- **Pizzicato.** Decaying modes, exactly as the piano's partials.

## Controls (as first proposed; what's built is above and in docs/MODEL.md's Controls)

- **Playing:** Instrument; continuous Dynamics (CC11, mod wheel or aftertouch, with velocity setting
  only the onset); Bow Pressure; Bow Position (sul tasto … sul ponticello, from the comb a bowing
  point puts on the spectrum, as the piano's Strike Point); Sordino.
- **Expression:** vibrato (rate, depth, delay, irregularity); legato with portamento (the kit's
  legato mode); one voice per string (`allocateVoice`) for real double stops.
- **Articulations:** arco, pizzicato, spiccato, tremolo, natural harmonics (the piano's Touch Point).
- **Body:** open strings ringing in sympathy (the piano's free-string bank), wolf tone, body size
  (a morph towards viola- or bass-like colour).
- **Around it:** a room (the piano's `Reverb.h`, which with a second synth needing it is a candidate
  for the kit) and the kit's modulation and arpeggiator.

## Phases

0. **Inventory and spike** (done: `docs/PHASE0.md`; the architecture holds). Download the sources and record what's actually there (rates, layers,
   vibrato or not, release samples, licenses). Analyse and resynthesise one cello note, and A/B it
   against its recording. If that isn't convincing, change the architecture before building on it.
1. **Analysis tools** (done: `docs/MODEL.md`; with a minimal voice that plays the data, so it is checked
   by rendering: 3.0 % from the recordings) (`tools/`, Python, offline): f0 and harmonic tracking that survives vibrato,
   onset residuals, the source × body factorisation, noise bands, onset envelopes, a header
   generator.
2. **Engine v1** (done: `docs/MODEL.md`): a living sustain (the bow's pitch, level and each harmonic's
   own movement, measured from the recordings and calibrated to match them), noise that pulses with
   the string, the body following the pitch, harmonics to 16 kHz, parameters, page, presets.
3. **Playability:** the controls above, in four parts, each a set to judge by ear:
   - **3a, playing** (done; `docs/MODEL.md`: Playing): continuous dynamics, vibrato (with the body's
     fine detail it sweeps through, measured from the bow's wander), legato and portamento, one note
     per string, Slur, Even Notes, Bow Weight.
   - **3b, articulations** (done: docs/MODEL.md): pizzicato, staccato, spiccato, tremolo, natural and
     artificial harmonics.
   - **3c, bow colour** (done): pressure (Bow Weight, in 3a), position (tasto … ponticello), the mute.
   - **3d, body and room** (done): a room (synthkit's reverb, from the piano), sympathetic strings,
     body size, a wolf tone.
4. **Calibration:** a leave-one-note-out test on the engine, blind listening, the judgments revisited,
   a `v0.1` release (What's left, above).
5. **Violin:** the same pipeline on VSCO's violin, with its vibrato taken out (and used: it measures
   the body's fine detail).
6. **Experiment:** a waveguide bow-friction engine as a second model, judged on the same distance.

## Risks and gaps

- The violin will trail the cello: one good library, with vibrato to take out and some room in it.
- Not measurable from these libraries, so judgments (each flagged in `docs/MODEL.md`): Bow Position,
  the mute, legato transitions and Slur, the wolf, Body Size, the sympathetic coupling, Even Notes'
  curve, the room's level, the vibrato (sized from published measurements of cellists).
- The page's keyboard has velocity and a mod wheel, enough to play the dynamics; a bow pad on the
  page (a custom page, API.md §9a) is still an option.
