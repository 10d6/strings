#!/usr/bin/env python3
"""Every measure in one command, against the saved baseline.

    python3 -I tools/regress.py <bigcat checkout> build-rel/strings_render            # ~5 min on 2 cores
    python3 -I tools/regress.py <bigcat checkout> build-rel/strings_render --only arco,pizz
    python3 -I tools/regress.py <bigcat checkout> build-rel/strings_render --update   # a change meant to move them

Runs measure.py, handoff.py, life.py --render, measure_pizz.py, measure_stacc.py and measure_trem.py
(two at a time), reads each one's summary lines and compares them with tools/baseline.json. A number
outside its tolerance fails; the exit code is the number of failures. Renders are deterministic, so
on one machine the numbers repeat exactly; the tolerances allow for another compiler or platform and
are well under what the owner would hear. A PR that moves a number on purpose runs --update and
commits the baseline with the change (the diff shows what moved).

Tools render dry (common.DRY), as every comparison with the recordings does. Use a Release build:
the default build is several times slower.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
BASELINE = os.path.join(HERE, "baseline.json")
NUM = r"([-+]?\d+(?:\.\d+)?)"

# name: (command after the interpreter, {metric: (regex with one group, tolerance)})
# Tolerances are absolute, in the metric's own unit (% of the perceptual distance, dB, cents, ...).
SUITES = {
    "arco": (["measure.py", "{root}", "{tool}"], {
        "distance %": (r"^\s+raw\s+" + NUM, 0.3),
        "distance attack %": (r"^\s+raw\s+\S+\s+" + NUM, 0.3),
        "distance early %": (r"^\s+raw\s+\S+\s+\S+\s+" + NUM, 0.3),
        "distance sustain %": (r"^\s+raw\s+\S+\s+\S+\s+\S+\s+" + NUM, 0.5),
        "timbre %": (r"^\s+timbre\s+" + NUM, 0.3),
        "other bow %": (r"^\s+other_bow\s+" + NUM, 0.3),
        "evenness max step dB": (r"level step between semitones max " + NUM, 0.3),
        "evenness median step dB": (r"level step between semitones max \S+ dB \(median " + NUM, 0.2),
    }),
    "handoff": (["handoff.py", "{root}", "{tool}"], {
        "extra dip median dB": (r"extra dip median " + NUM, 0.2),
        "extra dip worst dB": (r"extra dip median \S+, worst " + NUM, 0.8),
    }),
    "life": (["life.py", "{root}", "--render", "{tool}"], {
        "pitch rms c": (r"(?s)^renders:.*?pitch\s+rms " + NUM, 0.1),
        "level rms dB": (r"(?s)^renders:.*?level\s+rms " + NUM, 0.1),
        "harmonics rms dB": (r"(?s)^renders:.*?harmonics rms " + NUM, 0.1),
        "harmonics correlation": (r"(?s)^renders:.*?correlation between them " + NUM, 0.05),
        "patterns top-3 %": (r"(?s)^renders:.*?the strongest three " + NUM, 3.0),
    }),
    "pizz": (["measure_pizz.py", "{root}", "{tool}"], {
        "distance %": (r"^\s+score\s+" + NUM, 0.3),
        "other take %": (r"^\s+other\s+" + NUM, 0.3),
        "hand-off median dB": (r"hand-off: .*median " + NUM, 0.3),
    }),
    "stacc": (["measure_stacc.py", "{root}", "{tool}"], {
        "distance %": (r"^\s+render\s+" + NUM, 0.5),
        "other take %": (r"^\s+other take\s+" + NUM, 0.3),
        "bow-off ms": (r"bow off, render minus recording: median " + NUM, 3.0),
        "peak dB": (r"bow off, .*level " + NUM, 0.3),
    }),
    "trem": (["measure_trem.py", "{tool}"], {
        "strokes/s": (r"^median: " + NUM, 0.3),
        "lengths sd %": (r"^median: .*lengths sd " + NUM, 1.0),
        "lag-1": (r"^median: .*lag-1 " + NUM, 0.06),
        "dip dB": (r"^median: .*dip " + NUM, 0.5),
        "rms vs held dB": (r"^median: .*held note " + NUM, 0.3),
    }),
}


def run(name, root, tool, logdir):
    cmd, _ = SUITES[name]
    argv = [sys.executable, "-I", os.path.join(HERE, cmd[0])] + [a.format(root=root, tool=tool) for a in cmd[1:]]
    t = time.time()
    p = subprocess.run(argv, capture_output=True, text=True)
    out = p.stdout + p.stderr
    if logdir:
        with open(os.path.join(logdir, name + ".log"), "w") as f:
            f.write(out)
    return name, p.returncode, out, time.time() - t


def parse(name, out):
    vals = {}
    for metric, (rx, _) in SUITES[name][1].items():
        m = re.search(rx, out, re.M)
        vals[metric] = float(m.group(1)) if m else None
    return vals


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", help="the bigcat checkout")
    ap.add_argument("tool", help="strings_render (a Release build)")
    ap.add_argument("--only", help="comma-separated suites: " + ",".join(SUITES))
    ap.add_argument("--update", action="store_true", help="write the results as the new baseline")
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--logs", help="a folder for each tool's full output")
    a = ap.parse_args()
    names = a.only.split(",") if a.only else list(SUITES)
    for n in names:
        if n not in SUITES:
            sys.exit("unknown suite %r (have %s)" % (n, ", ".join(SUITES)))
    root, tool = os.path.abspath(a.root), os.path.abspath(a.tool)
    if a.logs:
        os.makedirs(a.logs, exist_ok=True)
    base = json.load(open(BASELINE)) if os.path.exists(BASELINE) else {}

    results, fails = {}, 0
    # the longest first, so two jobs finish together
    order = sorted(names, key=lambda n: ["arco", "life", "pizz", "stacc", "handoff", "trem"].index(n))
    with ThreadPoolExecutor(a.jobs) as ex:
        for name, code, out, secs in ex.map(lambda n: run(n, root, tool, a.logs), order):
            vals = parse(name, out)
            results[name] = vals
            print("%s (%.0f s)%s" % (name, secs, "" if code == 0 else "  EXIT %d" % code))
            if code != 0:
                fails += 1
                print("   " + "\n   ".join(out.strip().splitlines()[-8:]))
            for metric, v in vals.items():
                tol = SUITES[name][1][metric][1]
                b = base.get(name, {}).get(metric)
                if v is None:
                    fails += 1
                    status, note = "FAIL", "not found in the output"
                elif b is None:
                    status, note = "new ", ""
                elif abs(v - b) > tol + 1e-9:
                    fails += 1
                    status, note = "FAIL", "baseline %g, ±%g" % (b, tol)
                else:
                    status, note = "ok  ", "baseline %g" % b if v != b else ""
                print("  %s %-26s %8s  %s" % (status, metric, "-" if v is None else "%g" % v, note))

    if a.update:
        if any(v is None for r in results.values() for v in r.values()):
            sys.exit("not updating: a number wasn't found")
        base.update(results)
        with open(BASELINE, "w") as f:
            json.dump(base, f, indent=1, sort_keys=True)
            f.write("\n")
        print("baseline updated: " + ", ".join(results))
        return 0
    print("\n%s: %d failure(s)" % ("FAIL" if fails else "OK", fails))
    return fails


if __name__ == "__main__":
    sys.exit(main())
