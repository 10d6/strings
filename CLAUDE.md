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
  `tools/noise_adjust.json` and `tools/flicker_adjust.json` → `tools/make_header.py`); never edit it by hand. A note is the recorded
  onset (0.4 s, the nearest measured note transposed) crossfading at 0.30-0.40 s into a harmonic bank
  (to 16 kHz) started in phase with it (`handDb`/`handPh` at 0.35 s), then source × body plus the
  measured notes' own corrections (fading over 3 semitones), the bow's measured movement (pitch, level,
  the harmonics in their recording's own three patterns plus an independent rest), octave-band bow noise pulsing at the string's period, and a release from
  the staccatos.
- **After any change to the sound** run and report: `tools/measure.py` (3.8 % median today; timbre
  2.8; other bow 20.1), `tools/handoff.py` (the render's extra dip at the hand-off: median 0.3 dB),
  `tools/life.py --render` (the movement's statistics against the recordings: docs/MODEL.md's table),
  `--check`, and `stress.py` (`--keys 36-84`, `--mode overlap`, the full range, and extremes), and
  browser speed (`bench-web.cjs tests/four-strings.json`: 3.5× today). After changing the analysis or
  the engine's noise or movement, recalibrate (`calibrate_noise.py`, `calibrate_life.py`, then `calibrate_flicker.py`:
  docs/MODEL.md).
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
- **Presets are settings a player might use**, not the controls' ends (those sounded weird); Body near 0
  is a sawtooth (the bare Helmholtz motion), and a sine LFO vibrato sounds synthy until Phase 3's.
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
