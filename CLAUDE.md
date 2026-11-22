# Strings — notes for Claude

Strings is a synth built on synthkit (the `synthkit/` submodule, pinned).
The owner plays it and gives feedback; Claude writes the code and opens PRs.
The owner tests via the PR's GitHub Pages preview, and installs the plugin zips
from CI at milestones.

## Ground rules

1. **`synthkit/API.md` is the contract.** Work in this repo needs only that
   page plus this repo. Don't read synthkit's source to build the synth; if
   the page is missing something, note it and fix the doc in a synthkit PR.
2. **Don't edit `synthkit/` here.** Kit changes go to the synthkit repo; this
   repo then moves the submodule to the new commit in its own PR.
3. **Real-time safety** (API.md §4a): no allocation, locks, I/O or exceptions
   in `start`, `release`, `render`, `processGlobal`, `processEvents`, `tune`,
   `allocateVoice`. Allocate in `prepare`. No `throw`/`catch` anywhere.
4. **Stable identifiers.** Parameter IDs, `synth.json` `id`, `pluginCode`,
   `vendorCode` and `bundleId` never change once released. Patches store real
   units.
5. **Verify by rendering** before every PR: `--check` passes, and listen to
   (or look at) the renders when the change is audible.
6. Escape hatches and custom state (API.md §4, §5a) are the way to do unusual
   things. A feature moves into the kit when a second synth needs it.
7. **Porting a browser sketch?** Use the Web Audio blocks (`sk::wa`, API.md
   §8a), which match the browser's nodes sample for sample, and compare the
   port's renders with the sketch's. Input from the page that isn't a
   parameter is a message (§9b); a look of the synth's own is `ui/page.js`
   (§9a), with `ui/style.css` for styling either page.

## This synth

- A modelled cello and violin in one synth (an Instrument choice), measured from recordings the
  way `10d6/piano` is: the sustain is modelled, only the onset is recorded audio. `docs/PLAN.md` is
  the plan and its phases; `docs/SOURCES.md` the recordings and their licenses (keep attribution for
  any recorded audio that ships).
- **Picking up the work**: `docs/PLAN.md` has where it stands, what the owner has decided, what's left
  (Phase 4 next: calibration and a `v0.1` release; then the violin, a waveguide experiment),
  and the steps for starting a new session (the recordings to clone, the check that the workspace
  reproduces today's numbers).
- The piano repo is the reference for technique: its `docs/MODEL.md` and `docs/TESTING.md`, the
  perceptual distance (`tools/measure/perceptual.py`), the recorded strike, the free-string bank,
  Touch Point, the reverb. Port what fits rather than reinventing it, and say where it came from.
- **Phase 0** (`docs/PHASE0.md`; `tools/inventory.py`, `tools/bodyfit.py`, `tools/spike.py`): the
  bigcat cello's names are an octave low (`common.NAME_OCTAVE_OFFSET`); its sustains start at the attack
  and are cut mid-bow (the release comes from the staccatos); no vibrato. Source × body predicts an unseen
  note at 4.0 dB per harmonic (neighbour 7.6, other bow 3.1); rebuilt notes are 2.5 % from their
  recordings (other bow's spectrum 3.6, source × body for an unseen note 7.0, neighbour 13.0). Compare
  spectra with the envelope and onset shared: whole other takes measure a different performance.
- **The engine** (`docs/MODEL.md`): `src/CelloData.h` is generated (`tools/analyze.py` →
  `tools/cello.json` + `tools/cello_onsets.npz`, with `tools/life_adjust.json`,
  `tools/noise_adjust.json`, `tools/flicker_adjust.json` and `tools/finebody_stats.json` → `tools/make_header.py`); never edit it by hand. A note is the recorded
  onset (0.4 s, the nearest measured note transposed) crossfading at 0.30-0.40 s into a harmonic bank
  (to 16 kHz) started in phase with it (`handDb`/`handPh` at 0.35 s), then source × body plus the
  measured notes' own corrections (fading over 3 semitones), the bow's measured movement (pitch, level,
  the harmonics in their recording's own three patterns plus an independent rest), the body's fine
  detail read every step (narrow resonances: what makes vibrato sound like one), octave-band bow noise
  pulsing at the string's period, and a release from the staccatos. With Bowing at Alternate (default) every other bow starts from the cell's
  up-bow take (`tools/upbow.py` → `src/UpbowData.h`; `processEvents` turns the bow once a block, records
  `noteUp`; after a change, `tools/measure_upbow.py`: 9.9 % against the up-bow recordings; their attacks are levelled
  to the down-bow's + 1 dB, the owner heard them spiky). Phase 3a added continuous
  dynamics (Velocity or Controller), vibrato, legato slurs and One Note Each (docs/MODEL.md: Playing);
  3d a room (synthkit's `dsp::Reverb`, the piano's, API.md §8b), Hall at 25 % by default, sympathetic
  open strings (a bank driven by the dry sound; the voices report their string, `stopMask`), Body Size
  and a wolf (off by default); 3c Bow Position and the Mute (judgments: the source moves along the
  measured dynamics, not the corrections).
- **After any change to the sound** run `tools/regress.py ../bigcat build-rel/strings_render` (every
  measure below at once against `tools/baseline.json`, about 5 minutes on two cores; a change that
  moves a number on purpose runs `--update` and commits the baseline with it, so the diff shows what
  moved), then the checks it doesn't cover. The measures it runs: `tools/measure.py` (4.2 % median today; timbre
  3.0; other bow 20.1; `--at-recorded-pitch` 3.5, timbre 2.7: the recordings are 3.8 cents rms off
  equal temperament, which the fine detail hears; it plays Even Notes off, each note at its recording's level), `tools/handoff.py` (the render's extra dip at the hand-off: median 0.2 dB),
  `tools/life.py --render` (the movement's statistics against the recordings: docs/MODEL.md's table),
  `--check`, and `stress.py` (`--keys 36-84`, `--mode overlap`, the full range, extremes, and the modes:
  `voiceMode=1`, `voiceMode=2 glide=…`, `play.strings=1`, `play.dynMode=1`, and each
  `play.articulation=1…5`; Release 400 % needs `--tail 20`), and browser speed (`bench-web.cjs tests/four-strings.json`: 2.6-3.0× today with the room, 4.9× dry; a four-string tremolo 3.9×). The page is 17.0 MB. After changing the analysis or
  the engine's noise or movement, recalibrate (`calibrate_noise.py`, `calibrate_life.py`, then `calibrate_flicker.py`:
  docs/MODEL.md).
- **Articulations** (3b, docs/MODEL.md: Pizzicato, Strokes, Tremolo, Harmonics): `play.articulation`
  (Arco, Pizzicato, Staccato, Spiccato, Tremolo, Harmonics: appended as they came, so patches keep their
  indices) and keyswitches (C1 D1 E1 F1 G1 A1 in that order of the keys: Arco, Staccato, Spiccato,
  Pizzicato, Tremolo, Harmonics), swallowed in `processEvents`, which records each key's articulation
  and round robin (`noteArt`, `noteRR`) for `start` to read (no parameters there). Plucked notes run
  `pizzRun`, every bowed one `arcoRun` (strokes through `setupStroke` and `bowOff`; tremolo through
  `tremStroke`/`tremSample`, the release by `tremEnd`; harmonics through `hNode` in `place`); a string played again with another
  articulation switches at the restart. Strokes are their own data (`tools/staccato.py` →
  `src/StaccData.h`, the tremolo's strokes too; after a change, `tools/measure_stacc.py`: 23.4 % today, other takes 26.5,
  and `tools/measure_trem.py`: 11.6 strokes/s, lengths 12.9 % sd, lag-1 −0.26, dips 8.2 dB, rms +0.1 dB on a held note), the
  harmonics' finger `src/TouchData.h` (`tools/touch.py`); never edit them by hand. Lessons: smooth a level
  in power, not dB (zero padding read as 0 dB: every take's "peak" at its first sample); compare a take
  only as long as its file runs (some end mid-ring); a stroke's own per-harmonic release made its tail
  right, but never let it be slower than the pooled one (half-second fits of a low fundamental ring on:
  stress found it); a long stroke must fade as its take did until its bow-off; notes started together
  share a tremolo's rhythm (one bow). **Tremolo** (docs/TREMOLO.md: ten rounds of listening): every
  version that moved the model's levels (dips, swells, a recording's own per-harmonic movement) sounded
  mechanical or watery; what the owner chose is recorded strokes (bigcat's staccato starts) bowed the
  way each stroke goes (a bow change turns the string's motion over: the 2nd harmonic's phase against
  the fundamental's flips, which sorts takes by direction), lined up at half a cycle, in a solo
  player's measured rhythm (lengths 12-18 % sd, a long stroke then a short). Iterate on it with
  listening files (offline prototypes), not engine changes: the owner asked for that. VSCO's "Cello
  Section" is three players (its chorus came along); the Philharmonia's tremolos can be measured, never
  shipped. Adding a parameter reshuffles the check's random patches: a new warning
  there may be an old bug (one found a plucked note at +718 dB: the mode rotation's series, past a wide
  bend; to see a hot patch, make the kit's check save it in a local, uncommitted edit). Pizzicato is its own data (`tools/pizz.py` → `src/PizzData.h` via
  `tools/make_pizz_header.py`; never edit by hand): the pluck as recorded (0.22 s, hand-off 0.15-0.21 s),
  then each harmonic's 1-2 measured modes. After a change to it run `tools/measure_pizz.py` (8.0 %
  median today, another take 16.8; hand-off 1.0 dB) as well as the arco checks (which must not move).
  Pizzicato lessons: weight a mode fit by the *note's* level, not the harmonic's own (its noisy tail took over);
  bound every mode by its recording (each take rings into the noise: modes fitted to noise never
  decayed, and D#3 rang on 15-30 dB over its recording above 1 kHz); move each harmonic to its own peak
  (a free string's partials sit off the series; a stiff-string line fitted worse); the early "pitch
  glide" is modes beating (the same in every round robin), not tension; hand over late enough that the
  pluck's own ring is in the recording (at 0.06-0.10 s the modes were 2-7 dB short). Velocity is v²,
  the library's own mapping (25 dB from 127 to 30: wider than the bow's p-f, for the owner's ears).
- **The harmonics move in patterns** (docs/MODEL.md): each recording's strongest three principal
  components hold 70 % of its harmonics' movement. Moving each harmonic independently, at the right
  size and spectrum, sounded weird to the owner (Still Bow, no movement, sounded good): check the
  structure (`life.py`'s patterns line), not only the size. The level moves below 2 Hz only (a
  judgment: the recordings' 2-16 Hz level movement, played alone, was heard as random volume jitter).
  The harmonics' movement is sized per cell by how bands move (`calibrate_flicker.py`): per-harmonic dB
  readings overstate weak harmonics, and at their size C3's highs fluttered at 15-20 Hz (the owner heard
  it on low notes only). With the movement on, check the spectrum between the harmonics too: too-fast
  modulation shows there as noise (the patterns' 16-64 Hz octaves did, 14-25 dB on C3).
- **The fit counts weak harmonics** (`bodyfit.WEAK`): left out, it predicted the top 8-21 dB too loud.
- **The body's fine detail** (`tools/finebody.py`, docs/MODEL.md): its size is measured (the 8 takes of
  a note share a slope of 0.17-0.42 dB per cent; corrections 3.3 dB rms), its shape is a judgment (a
  fixed curve with those statistics). It moves energy between the harmonics and keeps the level, at
  once, every step: riding on the harmonics' 30 ms follow, a slur bumped the level 4 dB. Measured
  notes keep their own (`corr − fine`).
- **Calibrations average random paths**: one path's slow movement varies ~25 %; a calibration on one
  render a cell chases it (`calibrate_flicker.py` renders four; the kit seeds a note by its place in
  the stream, so silent notes before it give another path).
- **Harmonics added mid-note** (a pitch falling past kFMax / K: a slur, a vibrato on the boundary)
  must turn at their own rotation from that step: `place()` runs before `setRotation()`. A stale
  rotation from an earlier note blew one harmonic up to +30 dB (tests/chords-four-strings.json).
- **Sympathetic strings' coupling is a judgment** (docs/MODEL.md): the staccatos' late ring
  (`tools/sympathy.py`) would take a coupling at which held notes ring as loud as themselves, and the
  recordings already hold their own ring (more than K 0.55 moved the distance). Don't "calibrate" it
  to `calibrate_sympathy.py`; it reports the gap.
- **Compare with recordings dry**: the tools render with `common.DRY` (`space.room` 0); a new tool
  that renders must too. Scenarios' silent windows allow for the hall's ring-out (RT60 2.2 s).
- **Start-up** matters in the browser (the test wants voices 0.5 s after a click): work out anything
  the voices share once in the synth (`wanderStats`), not per voice.
- **Owner's ears on 3a**: vibrato convincing; slurs needed a dip and the vibrato starting again (Slur);
  notes were uneven in a phrase (the recordings' levels, ±3 dB rms: Even Notes); F#4 mf's onset take
  bounced (`tools/onset_choice.py` swaps such takes); the tone is edgy, which is the close-miked
  recordings (the renders match their balance), so Bow Weight tilts it along the measured dynamics.
- **Presets are settings a player might use**, not the controls' ends (those sounded weird); Body near 0
  is a sawtooth (the bare Helmholtz motion). Init has no vibrato (the recordings have none).
- **The movement can't be judged by the distance**: a random path doesn't follow the recording's own
  (two renders of the same note are 1.2-1.3 % apart; with the first version's movement, 2.8). Judge it by `tools/life.py`'s statistics, and the
  distance's signed differences for bias.
- **Block-size independence**: everything not per sample runs on the voice's own 32-sample step
  (`kGrid`, counted in the note's time), never per render call; the kit checks blocks of 1-4096.
- Lessons: anything stepped per `render` call must scale by its length (the kit checks blocks of 1
  sample: a per-call decay made notes end 32× faster); a key let go before the hand-off must still hand
  over (from the decayed level); a harmonic's movement needs a steep top (a band-pass skirt's
  sidebands, or gains changed in steps, bury the noise between the harmonics and hide its pulse); band
  noises need their own noise each (from one, neighbours cancel where they overlap); harmonics stop at
  `kFMax`, and anything above it is measured as noise (at 12 kHz the top band played 8-15 dB of hiss);
  measurements that read biased (the residual on low notes, the slowest movement) need calibrating
  render against recording, not correcting by hand; time with a Release build (the default isn't).
- Speed: low notes cost most (160 harmonics). The browser's expf/logf are slow (use `fastExp`,
  `fastLog2`); normal draws cost a log, a cosine and a root (use uniform: the filters make it Gaussian);
  SIMD and four partial sums in the bank didn't help.
- Analysis tools read the recordings from a path given on the command line; run them with
  `python3 -I` from outside the data directory.
- Measure first, then model; where something can't be measured from these libraries (Bow Position,
  sul ponticello, legato transitions), say it's a judgment.

## Fresh workspace

A new session starts without the toolchains. Install them first (Ubuntu; the
same script CI uses):

```
git submodule update --init
synthkit/tools/ci/deps.sh native && synthkit/tools/ci/deps.sh web && synthkit/tools/ci/deps.sh plugin
```

Playwright/Chromium for the browser test: usually preinstalled (try
`NODE_PATH=$(npm root -g)`), else `npm install --no-save playwright@1.48.2 &&
npx playwright install --with-deps chromium`. synthkit's CLAUDE.md has more
(pluginval, a local JUCE checkout).

## Commands

```
cmake -S . -B build -G Ninja && cmake --build build
./build/strings_render --check . --out build/renders
./build/strings_render tests/chord.json --out x.wav
./build/strings_render --params
python3 synthkit/tools/stress.py build/strings_render 300   # random playing: every note must stop (API.md §10)

# browser page (API.md §11)
cmake -S . -B build-web -G Ninja -DCMAKE_TOOLCHAIN_FILE=synthkit/cmake/wasm32-wasi.cmake && cmake --build build-web
node synthkit/web/test/browser-test.cjs build-web/web/strings.html build-web/test tests/chord.json
node synthkit/web/test/bench-web.cjs build-web/web/strings.html tests/chord.json   # browser speed

# plugins (API.md §12)
cmake -S . -B build-plugin -G Ninja -DSYNTHKIT_PLUGIN=ON -DSYNTHKIT_WEB_UI_DIR=$PWD/build-web/web && cmake --build build-plugin
```

## CI

Every PR: native checks, the browser page (Chromium test + browser-vs-native
comparison), a Pages preview linked on the PR, and plugin builds for Windows,
macOS and Linux (plugin check, pluginval, auval) with a zip per OS. A `v*` tag
publishes a release. The steps live in `synthkit/tools/ci/`.
