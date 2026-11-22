#!/usr/bin/env python3
"""The up-bow onsets against their recordings (Bowing: Alternate).

    python3 -I tools/measure_upbow.py <bigcat checkout> build-rel/strings_render     # ~3 min

Per cell with an up-bow take (src/UpbowData.h), the note is played as a second bow (a quiet C6 first,
let go at once, so the bow has turned), and compared with the cell's up-bow sustain over 0-3 s by the
perceptual distance, as tools/measure.py compares the first bow with the down-bow sustain:

  up        the up-bow render against the up-bow recording (raw, as measure.py's raw).
  down      the same note played as a first bow (the down-bow onset) against the up-bow recording:
            what an up-bow sounded like before.
  timbre    both with the recording's level movement applied after the hand-off (measure.py's
            timbre): the sustain plays the cell's down-bow level, which an up-bow take can differ from.
  hand-off  the render's extra dip at the hand-off over the recording's own (tools/handoff.py's dip).

A cell whose up-bow take is a neighbouring dynamic's (tools/upbow.py) is compared with that take's
recording, which is what plays.
"""
import json
import os
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import handoff as H  # noqa: E402
import measure as Me  # noqa: E402
import perceptual as P  # noqa: E402

LEAD = 1.5      # the first, quiet bow, then the note this long after it
EVEN_OFF = {"play.even": 0.0}   # each note at its recording's level, as measure.py plays them


def render_second(tool, midi, vel, tmp):
    ev = [dict(t=0, on=96, vel=1), dict(t=0.03, off=96),
          dict(t=LEAD, on=int(midi), vel=int(vel)), dict(t=LEAD + 3.2, off=int(midi))]
    sc = dict(patch="init", sampleRate=Me.SR, length=LEAD + 3.4, params=dict(C.DRY, **EVEN_OFF), events=ev)
    js, wav = os.path.join(tmp, "u.json"), os.path.join(tmp, "u.wav")
    json.dump(sc, open(js, "w"))
    subprocess.run([tool, js, "--out", wav], check=True, capture_output=True)
    y, sr = sf.read(wav, always_2d=True)
    return y.mean(axis=1)[int(LEAD * sr):] * 10 ** (-Me.TRIM_DB / 20)


def main():
    root, tool = sys.argv[1:3]
    up = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "upbow.json")))
    sus = {(s["midi"], s["dyn"], s["bow"]): s for s in C.sustains(root)}
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in up["cells"]:
            if c["take"] is None:
                continue
            m, d = c["midi"], c["dyn"]
            x, sr = C.load(sus[(m, c["take"], "g")]["path"])
            Nr = P.loudness(x, sr, Me.LEN)
            yu = render_second(tool, m, Me.VEL[d], tmp)
            yd = Me.render(tool, m, Me.VEL[d], tmp, params=EVEN_OFF)
            r = dict(note=C.note_name(m), dyn=d, take=c["take"],
                     up=P.distance(Nr, P.loudness(yu, sr, Me.LEN))["score"],
                     down=P.distance(Nr, P.loudness(yd, sr, Me.LEN))["score"],
                     up_t=P.distance(Nr, P.loudness(Me.envelope_matched(yu, x, sr), sr, Me.LEN))["score"],
                     down_t=P.distance(Nr, P.loudness(Me.envelope_matched(yd, x, sr), sr, Me.LEN))["score"],
                     dip=H.dip(yu[:sr]) - H.dip(x[:sr]))
            rows.append(r)
            print("%-4s %-2s (take %-2s) up %5.1f  down onset %5.1f   timbre: up %5.1f  down %5.1f   "
                  "hand-off extra dip %+.1f dB" % (r["note"], d, r["take"], r["up"], r["down"], r["up_t"],
                                                    r["down_t"], r["dip"]), flush=True)
    med = lambda k: float(np.median([r[k] for r in rows]))  # noqa: E731
    print("\nmedian %%: up-bow render %.1f, down-bow onset %.1f (against the up-bow recordings, %d cells)" % (
        med("up"), med("down"), len(rows)))
    print("timbre (the recording's level movement applied after the hand-off): up-bow %.1f, down-bow onset %.1f" % (
        med("up_t"), med("down_t")))
    print("hand-off: the up-bow render's extra dip median %.1f, worst %.1f dB" % (
        med("dip"), min(r["dip"] for r in rows)))


if __name__ == "__main__":
    main()
