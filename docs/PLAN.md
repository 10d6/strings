# Plan

A modelled cello and violin in one synth, measured from recordings the way `10d6/piano` is.
Recorded audio is kept only for the onset (the bow's catch, its scratch and noise). Everything that
sustains is a model, so it can be played continuously, varied and taken past what a real instrument
does.

**One synth, two instruments.** An **Instrument** choice (Cello, Violin) selects the measured data
set, and both share the engine, the controls and the page. Each instrument's data is a few MB of
generated header, as the piano's is. Whether the browser page carries both or is built twice from
the same source is decided at the start of Phase 5 (the page is 15.5 MB with the cello alone).

## Sources

`docs/SOURCES.md` lists the recordings, their licenses and what each is used for. In short:

- Cello: **Karoryfer × bigcat Cello** (CC0, primary) and **University of Iowa MIS cello**
  (unrestricted; dry, every note, pp/mf/ff per string; not reachable from the workspace).
- Violin: **VSCO 2 CE Solo Violin** (CC0, primary) and **Iowa MIS violin**.
- Research: [`10d6/instrument-research`](https://github.com/10d6/instrument-research): a knowledge base
  on bowed strings (physics, body, articulations, recording; claims tagged by how sure they are) and
  CC0 measurements from VSCO 2 CE (a solo violin's body response, its vibrato, tremolo statistics),
  with the scripts that made them. Cite it by section (`KB §11.2`) where a judgment leans on it.

## Where it stands (2026-11-21)

The cello is complete through Phase 3 and was judged by ear at every step (PRs #1-#12, all merged).
`docs/MODEL.md` is the reference for how everything works and why; `CLAUDE.md` has the rules, the
lessons and the checks to run.

- **The note**: the recorded onset (0.4 s) handing over to a harmonic bank: source × body plus the
  measured notes' own corrections and the body's fine detail; the bow's measured movement; bow noise
  pulsing at the string's period; the release from the staccatos.
- **Playing** (3a): Dynamics From Velocity or Controller; vibrato; Legato and Mono with Glide; Slur;
  One Note Each; Even Notes; Bow Weight. **Articulations** (3b): arco, pizzicato, staccato, spiccato,
  tremolo, natural and artificial harmonics, with keyswitches C1-A1. **Bow colour** (3c): Bow
  Position, the Mute. **Body and room** (3d): a room, sympathetic open strings, Body Size, a wolf.
- **Numbers today**: 4.2 % median from the recordings (timbre 3.0; 3.5 and 2.7 at their own pitch);
  hand-off 0.2 dB; pizzicato 8.0 %; staccato 23.4 %; browser 2.6× realtime on four low notes with the
  room. 25 presets.

**What the owner has said** (the decisions that stand): one synth with an Instrument choice; the
browser page is for quick testing, so no big quality trade-offs for its speed; Still Bow (no
movement) sounded good and every movement since was judged against it; the level moves below 2 Hz
only; vibrato is convincing; slurs needed the dip and the vibrato restarting; the notes needed
evening out; the recordings' tone is edgy (close-miked), which Bow Weight, Bow Position and the room
answer; tremolo is recorded strokes in a player's rhythm (docs/TREMOLO.md), iterated with listening
files rather than engine changes. The owner tests each PR on its Pages preview and installs plugin
zips at milestones.

## What's left

### 4: playing it, then calibrating (in this order)

Playing comes before calibration: the cello is complete enough to use, and what a player meets in a
DAW should decide where calibration effort goes.

**Progress (2026-11-21)**: 1 done (#14); 2 waiting on the owner (the session can't push tags: tag
`v0.1` on `1b17203`, main after #12); 3: up-bow onsets done (#15), the node notch and the room's feed
as listening files for the owner (the room's feed: the room is 12 dB under the dry sound, so feeding
it darker moves the balance under 0.1 dB, and a gently farther mic moves the 1-2.5 kHz edge 0.4 dB;
not worth an engine change unless the owner hears otherwise), the dynamic range a question for the
owner; 4 done (#16: left out, a note plays 29 % from its recording against 2.9 measured and 40 for a
transposed neighbour; its onset is the largest part). Next: 5, listening in phrases, with the onset
between the notes as the first thing to listen for.

1. **A regression check** (`tools/regress.py`): runs every measure (`measure.py`, `handoff.py`,
   `life.py --render`, `measure_pizz.py`, `measure_stacc.py`, `measure_trem.py`) and compares their
   summary numbers with `tools/baseline.json`, within tolerances. One command after any change to the
   sound, and the check that a fresh workspace reproduces today's numbers. A change that moves a number
   on purpose updates the baseline in the same PR.
2. **`v0.1`, tagged now**: the cello as it is, for the owner in Ableton (VST3, Windows: the main
   target) and GarageBand (AU). What to listen for: CPU with several instances, automation and MIDI
   mapping, saving and reloading, the presets, repeated notes, phrases. That feedback sets the
   priorities of everything below.
3. **What a player hears first** (small PRs, each for the owner's ears):
   - **Up-bow onsets.** Only the down-bow onsets ship, so a repeated note plays the same attack every
     time. bigcat has every note and dynamic bowed both ways: alternate them (as the staccato already
     does), at the cost of the page's size (measure it first).
   - **The dynamic range.** The recordings' p to f is 13 dB (median; 4-19 by note); measured violin
     crescendos span 27-31 dB and pp-ff about 37-40 (KB §11.5, Demoucron). Ask the owner whether f
     should stand further from p, and if so offer a range control (extrapolating along the measured
     dynamics, as Bow Weight does).
   - **Bow Position's node notch.** The engine weakens the partials with a node at the bowing point
     (`kPosNodeFloor`); in bowing, unlike plucking, they are not removed (KB §1.1, tagged from memory):
     the bowing point shows as ripples instead. A/B with and without the notch.
   - **The room's feed.** The room is fed the dry close-miked sound; a room hears an instrument's
     power response over all directions, smoother and darker above 1 kHz (KB §12.3e). A gentle
     high-frequency tilt on the send (and later perhaps a Mic Distance control) answers the edge where
     it comes from.
   - **Col legno** (optional): the 17 knocks are short enough to play as recorded.
4. **Leave one note out** (Phase 0's test, now on the engine): rebuild the header without a measured
   note and measure the render of that note against its recording, for every note: how well the model
   plays the notes between the measured ones (where most notes are).
5. **Listening in phrases.** The single held notes are where the model is closest (4.2 %); slurs, bow
   changes, vibrato and repeated notes are where it isn't, and the recordings have none of them. Render
   phrases for the owner (and any reference cello, for listening only); revisit the judgments (Even
   Notes' curve, the sympathetic coupling, Slur's dip, the room's default, Bow Position's extremes, the
   vibrato's string scaling) where the listening points, not all of them.
6. **Known gaps, if they're heard**: the pitch wander reads 1.09 cents rms against the recordings' 1.58;
   a few cells move more than their recordings (C3 f, C2 mf, C5 f, F#2 f); the renders' late release
   sits higher than the recordings' (−86 against −94 dB 0.3 s after a staccato is 36 dB down: likely
   under the room); the staccatos' late sympathetic ring. Browser speed (2.6×) only if the page stops
   being usable for testing.
7. **`v0.2`** with what came of 3-6.

Ideas from the research to try once the above is done, each a judgment for the owner's ears:
decorrelated stereo (a second fine-detail curve for the right channel, so vibrato moves differently
in each ear: KB §5.5, §8.4; about one multiply-add per harmonic); a wolf that beats per harmonic and is
worst at light bowing (KB §5.4); release types (bow lift, bow stopped on the string, finger lifted:
KB §11.2); a held note re-bowed by turning the waveform over (what tremolo found a bow change is) in
place of Mono's fade and new onset; tremolo's down/up level difference and a rate that rises with the
dynamic (KB §11.2: cello section 11.2 soft, 12.7 loud), after checking what the recorded strokes
already carry; spiccato's contact time as a control (60-100 ms measured; under 20 ms sounds like col
legno, over 140 ms thrown: KB §11.5).

### 5: violin

1. **A spike first, as Phase 0 was** (go / no-go): analyse one or two of VSCO 2 CE's solo violin notes,
   take the vibrato out, resynthesise, A/B against the recordings. The violin is harder than the
   cello in three ways:
   - **Vibrato is narrow**: 6-33 cents peak to peak, median 16 (about ±8), 4.5-5.3 Hz
     (instrument-research `data/articulation_measurements/`, leaving out G3 and A6 f). It still
     sweeps each harmonic across the body further than the cello's 1-2 cent wander, so the body's
     fine detail can be measured, but over about ±8 cents, not ±20.
   - **Vibrato from the first moment**: the samples have no still start to hand over from, so the
     hand-off has to meet a vibrating note (the onset recording moving in pitch, the bank following it).
   - **A room in the recordings**: the body fit takes it in.
   instrument-research's `tools/fetch_vsco.sh` (only the string folders) and `body_response.py` (the
   same source × body factorisation, 4.1 dB per harmonic on held-out notes; it assumes a 1/n source and
   bakes in the library's microphones and room) make the spike cheap; use its response to check this
   repo's fit, not as shipped data.
2. **Decide the page**: one page with both instruments, or two builds of the same source.
3. **Generalise the tools** by instrument (open strings G3 D4 A4 E5, the note range, the layer names,
   the data path), and the header (`ViolinData.h` beside `CelloData.h`); the engine reads the chosen
   instrument's tables (a pointer per voice, set at its start). Each instrument's calibrations
   (`*_adjust.json`) are its own.
4. **The pipeline on the violin**: inventory (notes, layers, round robins, articulations, tuning);
   the sustain's spectrum averaged over whole vibrato cycles; the bow's movement with the vibrato (5-7
   Hz and its harmonics) separated from the wander; onsets, pizzicato, strokes, tremolo (measure its
   tremolos as docs/TREMOLO.md did: shared patterns, rhythm, the 2nd harmonic's flips).
5. **The Instrument choice** (Cello, Violin) selects the data; the controls stay; presets per instrument.

### 6: experiment (time-boxed, offline)

A waveguide bow-friction model (a string as two delay lines and a friction curve at the bow) for
what this engine can't measure: bow changes, attacks, slurs, flautando, overpressure. Judged by ear on
those, not by the distance (a model not fitted to bigcat's spectra will lose there, and that isn't what
it's for). instrument-research's KB §10 (a minimal waveguide with defaults) is the starting point, with
§2.1 (measured cello strings and their damping), §6.4 (oversampling: f_s ≥ 20·f0/β at the junction),
§7.3 (keeping the bow inside its playable window) and §11.5 (measured bow gestures). An offline
prototype first, which can run alongside Phase 5; if it wins somewhere, the likely shape is a hybrid:
the waveguide for transitions inside this engine.

### Other threads

- **Piano onto the kit's reverb**: 10d6/piano still has its own `src/Reverb.h`; it can move to
  synthkit's `dsp::Reverb` (the same algorithm; renders within 0.03 dB) in a piano PR.
- bigcat's sfz programs include "legato" maps, which look like crossfades of sustains rather than
  recorded transitions: check before assuming legato can be measured.
- Left from 3b (docs/MODEL.md: What isn't modelled): pizzicato above C5 (C5's pluck transposed), a
  pluck position, the recordings' louder open strings under a pluck; tremolo slower than 6 strokes a
  second; the seagull effect between harmonic nodes.

## Starting a new session

1. Set up the workspace (`CLAUDE.md`: Fresh workspace), and clone the recordings next to the repo:
   `git clone --depth 1 https://github.com/sfzinstruments/karoryfer-bigcat.cello ../bigcat` (267 MB;
   the analysis tools take the path).
2. Build and check: `cmake -S . -B build-rel -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build
   build-rel`, then `./build-rel/strings_render --check . --out /tmp/renders` and `python3 -I
   tools/regress.py ../bigcat build-rel/strings_render` (once it exists; until then `tools/measure.py`:
   4.2 %, timbre 3.0): if those match, the workspace is right.
3. Read `docs/MODEL.md` for the engine, then pick up Phase 4 above where it stands, on a branch, with a
   PR when it's ready for the owner's ears.

## The model

A bowed note is driven rather than struck, so the sustain is a different core from the piano's
decaying partials. The rest of the piano's pipeline carries over. `docs/MODEL.md` has it in full.

- **Sustain: source × body.** Each harmonic's level is the bowed string's spectrum (set by bow speed
  and pressure) times one fixed body response at that harmonic's frequency, fitted separately across
  every note and dynamic. Vibrato and portamento sweep the harmonics across the body's resonances, as
  on the real instrument.
- **Onset: recorded**, handing over to the model in phase.
- **Bow noise**: pitch-synchronous noise, measured in bands.
- **Release**: the string's own decay, from the staccatos.
- **Pizzicato**: the pluck recorded, then decaying modes, as the piano's partials.

## Phases

0. **Inventory and spike** (done: `docs/PHASE0.md`).
1. **Analysis tools** (done: `docs/MODEL.md`).
2. **Engine v1** (done): a living sustain, noise that pulses with the string, harmonics to 16 kHz.
3. **Playability** (done): 3a playing, 3b articulations, 3c bow colour, 3d body and room.
4. **Playing it, then calibrating**: regression check, `v0.1`, what a player hears first, leave one
   note out, listening in phrases, known gaps, `v0.2`.
5. **Violin**: a spike first, then the same pipeline on VSCO's violin.
6. **Experiment**: a waveguide model for transitions, offline and time-boxed, judged by ear.

## Risks and gaps

- The violin will trail the cello: one good library, with vibrato from the start, a narrow vibrato to
  measure the body with, and some room in it.
- Not measurable from these libraries, so judgments (each flagged in `docs/MODEL.md`): Bow Position,
  the mute, legato transitions and Slur, the wolf, Body Size, the sympathetic coupling, Even Notes'
  curve, the room's level, the vibrato (sized from published measurements of cellists), spiccato.
- Statistics measured from recordings that can't ship (the Philharmonia's tremolos, for the tremolo's
  rhythm) are facts, not audio; where a CC0 measurement agrees (instrument-research's VSCO tremolo
  statistics), cite it beside them.
- The page's keyboard has velocity and a mod wheel, enough to play the dynamics; a bow pad on the
  page (a custom page, API.md §9a) is still an option.
