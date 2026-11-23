#!/usr/bin/env python3
"""Re-run reviewer probes of r905_mutslice.py and print every FAIL line.

Usage: r905_probe_out.py ARM_DIR WORK_DIR CLEAN_EXE NAME_SUBSTRING...

Each probe whose name contains a given substring is staged by the arm's own
stage()/generate_image() (generator probes reuse CLEAN_EXE, RTL probes are
built), run through the arm's run_harness(), and reported with the verdict
and every FAIL line of both passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import r905_mutslice as ms  # noqa: E402


def main() -> int:
    arm, work, clean = (Path(a).resolve() for a in sys.argv[1:4])
    want = sys.argv[4:]
    m = ms.load(arm)
    for name, fname, pat, repl, breaks in ms.probes(m):
        if not any(w in name for w in want):
            continue
        tag = "out_" + "".join(c if c.isalnum() else "_" for c in name)
        src = m.stage(work, tag, (fname, m.edits_of(pat, repl)))
        run = work / f"run_{tag}"
        assert m.generate_image(src, run), name
        exe = clean if fname == m.GENERATOR else m.build(src, work, tag)
        rc, out = m.run_harness(exe, run)
        fails = [ln for ln in out.splitlines() if ln.startswith("FAIL ")]
        print(f"== {name}: verdict {m.verdict(rc, out)}, rc {rc},"
              f" {len(fails)} FAIL lines")
        for ln in fails:
            print(ln)
        tally = [ln for ln in out.splitlines() if " checks: " in ln]
        print(tally[-1] if tally else "no tally")
    return 0


if __name__ == "__main__":
    sys.exit(main())
