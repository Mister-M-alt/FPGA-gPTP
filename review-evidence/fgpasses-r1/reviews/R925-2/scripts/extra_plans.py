#!/usr/bin/env python3
"""Reviewer probe: more plans and flags than passes_test.py, using its own stubs and comparison.

usage: python3 -I extra_plans.py ENGINE_DIR
Compares the scheduled `run` against the serial recipe (both from passes_test.py's tree()) for
plans and make options passes_test.py does not cover. Prints one PASS/DIFF line per case and, for a DIFF,
a unified diff of the normalised streams.
"""
import difflib, os, signal, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
import passes_test as t

PLANS = {
    "top image (rule-1 prerequisite) refused": {"gen": ""},
    "pass 0 SIGSEGV": {"0": {"signal": signal.SIGSEGV}},
    "pass 0 SIGABRT": {"0": {"signal": signal.SIGABRT}},
    "pass 3 image refused": {"gen": "p1run"},
    "passes 0 and 3 fail": {"0": {"exit": 2}, "3": {"exit": 5}},
    "pass 2 fails first, pass 1 later": {"1": {"exit": 1, "sleep": 0.6}, "2": {"exit": 4, "sleep": 0.0}},
    "clean": {},
}
FLAGS = [["-j4"], ["-j2"], ["-j3"], ["-j4", "-k", "-s"], ["-j4", "-i", "-k"], ["-j4", "-i", "-s"], ["-j1", "-k"],
         ["-j1", "-i"], ["-j4", "--no-print-directory"], ["-j4", "-w"], ["-j4", "-Otarget"], ["-j4", "-Oline"]]

def main():
    bad = 0
    with tempfile.TemporaryDirectory(prefix="r925-extra-") as name:
        scratch = Path(name)
        trees = t.tree(scratch)
        for plan_name, plan in PLANS.items():
            for flags in FLAGS:
                ev = scratch / "e.jsonl"
                want = t.make(trees["serial"], flags, plan, ev)
                got = t.make(trees["parallel"], flags, plan, ev)
                ws = [t.norm(want.stdout, trees["serial"]), t.norm(want.stderr, trees["serial"])]
                gs = [t.norm(got.stdout, trees["parallel"]), t.norm(got.stderr, trees["parallel"])]
                same = want.returncode == got.returncode and ws == gs
                bad += not same
                print(f"[{'PASS' if same else 'DIFF'}] {plan_name}, make {' '.join(flags)}: rc {got.returncode} vs serial {want.returncode}")
                if not same:
                    for label, a, b in (("stdout", ws[0], gs[0]), ("stderr", ws[1], gs[1])):
                        for line in difflib.unified_diff(a.splitlines(), b.splitlines(), f"serial {label}", f"scheduled {label}", lineterm="", n=1):
                            print("    " + line)
    print(f"extra plans: {bad} differing cases")
    return 0

if __name__ == "__main__":
    sys.exit(main())
