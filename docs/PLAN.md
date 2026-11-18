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

## Controls (proposed)

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
3. **Playability:** the controls above.
4. **Calibration:** the piano's perceptual distance, a leave-one-note-out test, blind listening.
5. **Violin:** the same pipeline on its data.
6. **Experiment:** a waveguide bow-friction engine as a second model, judged on the same distance.

## Risks and gaps

- The samples haven't been opened yet: bigcat's layer count and release samples are unknown until
  Phase 0. If it's thin on dynamics, Iowa's pp/mf/ff fill that axis.
- The violin will trail the cello: one good library, with vibrato to take out.
- Not measurable from these libraries, so judgments: Bow Position, sul ponticello and tasto,
  legato transitions.
- Kit gap: the page's keyboard has no velocity or expression, which a bowed instrument needs more
  than a piano. Plan: a bow pad on the page, and the gap filed with synthkit.
