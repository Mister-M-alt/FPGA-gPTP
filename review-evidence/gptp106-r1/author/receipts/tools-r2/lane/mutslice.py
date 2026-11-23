#!/usr/bin/env python3
"""Run a slice of a suite's own mutation arm, unchanged, in a private work
directory: the arm's MUTATIONS list, selected by index range or by name
substring, each through the arm's own run_mutant().

Usage: mutslice.py ARM_DIR (--range A:B | --grep TEXT) [--clean]
  ARM_DIR  the suite directory holding mutants.py (e.g. tb/verilator/engine)
  --clean  also run the arm's positive control (the unmutated harness)
Prints the arm's own [PASS]/[FAIL] lines and a slice tally.
"""
import importlib.util
import sys
import tempfile
from pathlib import Path


def main() -> int:
    arm = Path(sys.argv[1]).resolve()
    args = sys.argv[2:]
    sys.path.insert(0, str(arm))
    spec = importlib.util.spec_from_file_location("arm_mutants", arm / "mutants.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    muts = list(m.MUTATIONS)
    sel = []
    if "--range" in args:
        a, b = args[args.index("--range") + 1].split(":")
        sel = list(enumerate(muts))[int(a):int(b)]
    if "--grep" in args:
        g = args[args.index("--grep") + 1]
        sel = [(i, mu) for i, mu in enumerate(muts) if g in mu[0]]
    passes = fails = 0
    with tempfile.TemporaryDirectory(prefix="mutslice-",
                                     dir="$VALIDATION_STORAGE/gptp106-a831") as td:
        work = Path(td)
        clean_src = m.stage(work, "clean")
        clean_exe = m.build(clean_src, work, "clean")
        if clean_exe is None:
            print("[FAIL] the unmutated sources did not build")
            return 1
        if "--clean" in args:
            clean_run = work / "run_clean"
            if not m.generate_image(clean_src, clean_run):
                print("[FAIL] the clean image was refused")
                return 1
            answer = m.verdict(*m.run_harness(clean_exe, clean_run))
            print(f"[{'PASS' if answer == 'pass' else 'FAIL'}] control: {answer}")
            passes += answer == "pass"
            fails += answer != "pass"
        for i, mu in sel:
            print(f"-- mutant {i}: {mu[0]}", flush=True)
            if m.run_mutant(work, clean_exe, mu):
                passes += 1
            else:
                fails += 1
    print(f"SLICE {len(sel)} mutants of {len(muts)}: {passes} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
