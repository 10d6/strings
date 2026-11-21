# Strings

A modelled cello and violin built on [synthkit](https://github.com/10d6/synthkit). It runs in the
browser and as a VST3 / AU plugin.

It is measured from recordings of real instruments, as [Piano](https://github.com/10d6/piano) is:
the sustain is a model (so it can be bowed continuously, with vibrato, legato and bow controls), and
only each note's onset is recorded sound. Work in progress: [`docs/PLAN.md`](docs/PLAN.md) has the
plan, [`docs/MODEL.md`](docs/MODEL.md) how the cello is modelled today, and
[`docs/SOURCES.md`](docs/SOURCES.md) the recordings and their licenses.

Today it plays the cello, C2-C6. Each note starts as its recording and hands over to the model,
which sustains as long as the key is held and moves as a bowed note does (its pitch, level and each
harmonic wandering, the bow noise pulsing with the string, all measured from the recordings). It
plays:
- **Dynamics:** by velocity (p to f), or from the mod wheel or expression pedal, moving during a note.
- **Vibrato:** it sweeps the harmonics through the body's narrow resonances.
- **Legato:** slurs and portamento.
- **Strings:** one note per string, as on the cello.
- **A room** around it (Hall by default; Room, Chamber, Cathedral, Plate), the same reverb as Piano's.
- **The instrument:** open strings ringing along, the body's size, and a wolf note if you want one.
- **Bow colour:** bow position (sul tasto to sul ponticello) and a mute.
- **Articulations:** arco; pizzicato (the pluck as recorded, then each harmonic's beating modes);
  staccato (each note's own recorded strokes, the bow leaving as it did); spiccato (bounced); tremolo
  (the recorded strokes, each bowed the way it goes, in a player's rhythm around Tremolo Rate; one bow
  across a double stop); natural and artificial harmonics (measured from the
  harmonic slides). Choose them with Articulation or the keyswitches C1 Arco, D1 Staccato, E1 Spiccato,
  F1 Pizzicato, G1 Tremolo, A1 Harmonics.

The Bow and Tone panels change how much it moves, how much of the body is in the tone, and the bow
noise; the presets show the range. Col legno is still to come.

## The recordings

The model data (`src/CelloData.h`) is measured from the **Karoryfer x bigcat cello** by Karoryfer
Samples and bigcat instruments, played by Kamila Borowiak
([CC0](https://github.com/sfzinstruments/karoryfer-bigcat.cello)). It also holds each measured
note's first 0.4 s as recorded, its pizzicato (`src/PizzData.h`) each pluck's first 0.22 s, and its staccato (`src/StaccData.h`) two takes per note and dynamic, up to 0.31 s each. To measure again:

```
git clone --depth 1 https://github.com/sfzinstruments/karoryfer-bigcat.cello ../bigcat   # 267 MB
python3 -I tools/analyze.py ../bigcat tools/cello.json tools/cello_onsets.npz           # ~5 min
python3 -I tools/finebody.py ../bigcat --stats tools/finebody_stats.json                # the body's fine detail
python3 -I tools/make_header.py tools/cello.json tools/cello_onsets.npz src/CelloData.h
# build, then check against the recordings:
python3 -I tools/measure.py ../bigcat build/strings_render      # every note and dynamic (~2.5 min)
python3 -I tools/handoff.py ../bigcat build/strings_render      # the onset's hand-off to the model
python3 -I tools/life.py ../bigcat --render build/strings_render # how notes move, against the recordings
# the pizzicato (src/PizzData.h):
python3 -I tools/pizz.py ../bigcat tools/pizz.json tools/pizz_onsets.npz                        # ~10 min
python3 -I tools/make_pizz_header.py tools/pizz.json tools/pizz_onsets.npz src/PizzData.h
python3 -I tools/measure_pizz.py ../bigcat build/strings_render  # every plucked take against its recording
# the staccato and spiccato (src/StaccData.h), the harmonics (src/TouchData.h):
python3 -I tools/staccato.py ../bigcat tools/stacc.json tools/stacc_onsets.npz
python3 -I tools/make_stacc_header.py tools/stacc.json tools/stacc_onsets.npz src/StaccData.h
python3 -I tools/measure_stacc.py ../bigcat build/strings_render # every kept staccato take against its recording
python3 -I tools/touch.py ../bigcat src/TouchData.h
```

The noise and the movement are calibrated against the recordings (`tools/calibrate_noise.py`,
`tools/calibrate_life.py`, `tools/calibrate_flicker.py`; `docs/MODEL.md` has when and how).

(needs `pip install numpy scipy soundfile matplotlib`)

## Playing it

- **In the browser:** every PR gets a preview link (posted on the PR), and
  `main` is at the repo's GitHub Pages site. This needs GitHub Pages turned
  on once: Settings → Pages → Deploy from a branch → `gh-pages` / root.
- **In your DAW:** each PR's CI run has a **plugin-windows**, **plugin-macos**
  and **plugin-linux** download (under *Checks → CI → Summary → Artifacts*).
  Unzip it and follow `INSTALL.md` inside. Tagging a version (`v0.2.0`)
  publishes them as a release.

## Building

```
git clone --recursive <this repo>
cmake -S . -B build && cmake --build build
./build/strings_render --check . --out renders     # every check; WAVs into renders/
```

The browser page and the plugins are built the same way as in synthkit: see
[`synthkit/API.md`](synthkit/API.md) §11–12.

## Layout

| | |
|---|---|
| `synth.json` | identity (name, IDs, plugin codes) and kit features |
| `src/` | the sound engine (`Synth.cpp`) and the measured data (`CelloData.h`, `PizzData.h`, `StaccData.h`, `TouchData.h`, generated) |
| `docs/` | the plan, how it's modelled, the recordings, Phase 0's experiments |
| `tools/` | measuring the recordings, generating the header, comparing renders with the recordings |
| `presets/` | factory presets (`init.json` is what a new instance starts on) |
| `tests/` | render scenarios checked in CI |
| `ui/layout.json` | the panel layout (and `ui/custom.js` for custom widgets, `ui/style.css` for styles, or `ui/page.js` for a page of the synth's own: API.md §9a) |
| `synthkit/` | the kit, as a pinned submodule |
