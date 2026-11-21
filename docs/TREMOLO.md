# Tremolo: what was tried

The tremolo took ten rounds of listening before one sounded bowed to the owner. This is the record:
what each round was, what the owner heard, and what was measured on the way, so the next attempt
(the violin's tremolo, or a better cello one) starts from here. The engine as built is in
docs/MODEL.md (Tremolo); the prototypes were offline Python renders (Strings' own renders analysed and
resynthesised, or recordings cut up), heard as listening files, not built into the synth. The owner
asked for that: listening files are much faster to iterate on than engine changes and full checks.

## What the owner chose (round 10, "B")

Each stroke is one of bigcat's staccato takes, **bowed the way the stroke goes** (its round robins
alternate bows), from where its stroke starts, crossfading into the next at each change, **lined up at
half a cycle of the fundamental** (a bow change turns the string's motion over), in **a solo player's
rhythm** (measured: lengths vary 12-18 %, a long stroke followed by a short one), each stroke's level
its own (±1.8 dB rms). "Let's go with B for now."

## The rounds

| # | What | The owner |
|---|---|---|
| 1 | A judgment: a 10 dB dip over a fifth of every stroke, a 9 dB noise burst at each change | "Cool but not really like it's being bowed. A real tremolo is smoother": mostly two slightly distinct sounds, one per bow direction; the change itself very brief and not strong |
| 2 | Two bow directions (the down-bow 0.15 of a dynamic layer heavier, the up-bow lighter), a 10 ms change dipping 4 dB with 4 dB more noise | "Went too far"; the difference between strokes should be larger |
| 3 | Nine variants: larger bow-weight differences between directions, other change shapes | None an improvement |
| 4 | Measured from VSCO 2 CE's cello tremolos (below): each stroke a rounded swell 9 dB deep, its length and size drifting, slower when soft | "The first two strokes sound OK, then it degenerates into a machine" |
| 5 | Strings' tone (an arco render's harmonics) with VSCO's per-harmonic level movement replayed onto it (A); the same smoothed to 20 Hz (B) | A: "a big improvement", but "a bit of a warbly, watery effect". B: not clearly better than A |
| 6 | The same with a solo cellist's movement (the Philharmonia's tremolos, below) | "Didn't improve much" |
| 7 | From the literature: each change turns the waveform over (the old motion dying in 8 ms, the new building in 16); then with the bow's speed (weaker and brighter near each change); then each stroke a little different | "All very mechanical" |
| 8 | Recorded strokes (the owner's idea): one solo stroke repeated, its polarity flipped every other time; all of them in random order; VSCO's strokes; bigcat's staccato starts; VSCO's recording itself | Led to: mix VSCO's strokes with bigcat's |
| 9 | bigcat's staccato starts, now in the solo player's rhythm; then mixed with VSCO strokes (a third, a half), VSCO filtered to bigcat's long-term spectrum | The mix "isn't really working" (two instruments) |
| 10 | On the humanized bigcat strokes, one idea each: (B) each stroke from a take bowed that way; (C) a VSCO stroke under each, 14 dB down; (D) each stroke given a VSCO stroke's overtone shape; (E) each stroke a little harder or softer bowed (bigcat's measured f-mf difference) | **B** |

## What was measured

- **VSCO 2 CE's "Cello Section" tremolos** (CC0; 25 files, `Strings/Cello Section/trem/`, names an
  octave low): played by three cellists (its Freesound metadata), though one of them can sound like
  a solo. Its harmonics' movement holds only 22-46 % in its three strongest shared patterns, against
  about 70 % in bigcat's solo sustains: the players' chorus. That is the likely "watery" in rounds 5
  and 9.
- **The Philharmonia Orchestra's free cello tremolos** (one player; MP3 phrases, 12-23 s; their
  licence lets nothing of them ship, so they were **measured only**): three phrases hold a note long
  enough (D#4 2.3 s, G2 4.9 s, C#3 2.3 s). Shared patterns 47-82 %. **Rhythm**: 12-13.5 strokes a
  second (75-83 ms median), lengths 12-18 % sd, lag-1 correlation of lengths −0.15 to −0.36 (a long
  stroke, then a short: the changes jitter around a beat), one bow 8-9 % longer than the other on two
  of the three notes, the beat drifting 4-7 % over five strokes, each stroke's peak 1.4-2.2 dB apart.
  Each change dips 6-10 dB (40 Hz envelope). The engine's rhythm is built from these
  (`tools/measure_trem.py` compares).
- **A bow change turns the string's motion over**: the Helmholtz corner circulates the other way, so
  the sawtooth comes back upside down. Every harmonic flips sign, so the 2nd harmonic's phase against
  the fundamental's (a2·conj(a1)²) jumps by half a cycle at each change, and the 3rd's doesn't. On the
  solo D#4: the 2nd harmonic sits in two states half a cycle apart (0.56 against 0.09 for one), the
  3rd in one (0.67). The same reading sorts recordings by bow direction: bigcat's staccato round robins
  alternate bows (244 of 270 takes by their order; the rest read by this test).
- **My early prototypes' strokes varied 3.5 %**: the player's vary 12-18 %. Regular timing is part of
  "mechanical" (rounds 4 and 7), but the recorded strokes in regular time (round 8) weren't chosen
  either.

## The literature

- Demoucron (KTH 2008 thesis; Vienna Talk 2010, "The violinist's bestiary"): bow velocity and force
  measured in tremolo at the tip; tremolo simulated with a slightly varying sine of bow velocity. Short
  strokes (tremolo, sautillé, spiccato) are ballistic, well-practised and reproducible; their
  parameters are fitted by a few sines.
- Schoonderwaldt (JASA 2009): the spectral centroid rises with bow force and falls with bow velocity.
- Guettler & Askenfelt: listeners accept at most about 50 ms of pre-Helmholtz transient at a start;
  players stop the bow faster than they start it again, to change quickly and inaudibly.
- Percival's Artifastring (open source): a physical model driven by Demoucron-like bow patterns.

## Lessons

- **Levels alone sound mechanical or watery.** Every version that moved the harmonics' levels (rounds
  1-7) was heard so, even when the movement was a recording's own. A bow change is a change of the
  waveform (it turns over), not of its level.
- **Measure what a source is before using it**: VSCO's "section" chorus came along with its movement.
- **Strokes as recorded, bowed the right way, in a human rhythm** were what worked. The direction
  mattered (B over A): a stroke flipped to stand in for the other bow isn't the other bow.
- **Two instruments don't blend by EQ**: VSCO's room and section stayed audible under bigcat's
  close-miked solo.

## Not done (open)

- C, D and E as additions to B (a quiet second source, overtone variety, harder/softer strokes): heard
  once each, alone.
- Tremolo slower than 6 strokes a second: the grains are 0.2 s (a longer stroke would need longer
  grains, 1.2 MB more per 0.1 s).
- Only the takes of one note (the nearest) play: neighbours a minor third away would add variety at
  the cost of their formants.
- The violin (Phase 5): VSCO's solo violin has tremolo recordings; measure them as above (shared
  patterns, rhythm, the 2nd harmonic's flips) before building from them.
- A physical model of the stroke (Demoucron's bow patterns into a bowed-string model) as the
  waveguide experiment's test case.
