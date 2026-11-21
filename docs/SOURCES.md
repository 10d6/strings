# Recordings

The model is measured from these. They are not in the repo: download them next to it
(`docs/PHASE0.md` has the commands). Recorded audio that ships in the build (the onsets) must stay attributed here,
in the README and in the plugin/release notes.

| Source | Instrument | License | Used for |
|---|---|---|---|
| [Karoryfer × bigcat Cello](https://github.com/sfzinstruments/karoryfer-bigcat.cello) (Karoryfer Samples and bigcat instruments; cellist Kamila Borowiak) | cello | CC0 1.0 | **Primary cello.** 479 close-miked mono 24-bit / 44.1 kHz files: bowed sustains (C2-C6 every minor third, p/mp/mf/f, down and up bow), staccato, pizzicato, harmonic slides and knocks; **no vibrato**. `docs/PHASE0.md` has the inventory. The sustains and staccatos are the bowed notes' (`src/CelloData.h`), the pizzicato the plucked notes' (`src/PizzData.h`, each pluck's first 0.22 s shipping as recorded), the staccato two takes per note and dynamic (`src/StaccData.h`, up to 0.31 s each shipping as recorded), the tremolo all four (the other two as 0.2 s grains, shipping as recorded), the harmonics the four harmonic slides (`src/TouchData.h`, measured, none shipping). |
| [University of Iowa MIS](https://theremin.music.uiowa.edu/MIScello2012.html) (Lawrence Fritts) | cello, violin | free, without restrictions | **Secondary, not yet used.** Anechoic, every chromatic note, pp / mf / ff, per string, arco and pizzicato. Not reachable from the workspace (no GitHub mirror): attach by hand if a source per string needs it. |
| [VSCO 2 Community Edition](https://github.com/sgossner/VSCO-2-CE) (Versilian Studios, Sam Gossner) | violin, cello section | CC0 1.0 (with a request that the samples not be sold) | **Primary violin.** Solo violin arco with vibrato, pizzicato, spiccato, tremolo. Some room in the recordings; vibrato has to be taken out in analysis. Its **Cello Section** tremolos (three players) were measured and prototyped for the cello's tremolo; nothing of them is used or ships (docs/TREMOLO.md). |
| [Philharmonia Orchestra sound samples](https://philharmonia.co.uk/resources/sound-samples/) (a GitHub copy: skratchdot/philharmonia-samples) | cello | free; must not be sold or made available as samples or a sampler instrument | **Measured only, nothing ships.** One player's cello tremolo phrases (MP3): the tremolo's rhythm is built from their statistics (docs/TREMOLO.md). |

## Considered and not used

- **Philharmonia Orchestra samples** as a source of sound: may not be made available as samples or a
  sampler instrument; MP3 only (their cello tremolos are measured: above).
- **Sonatina Symphonic Orchestra:** CC Sampling Plus 1.0 (restrictions on reuse).
- **Lewis E. Pyle Violin (Decent Samples):** download behind an email form; license not confirmed.
- **VCSL (Versilian):** no solo violin or cello (bowed psaltery only).
- **Karoryfer Vengeful / Merciful strings:** commercial.
