#!/usr/bin/env python3
"""Reviewer check: count the full engine arm's entries and confirm every
pattern of every entry appears exactly once in its target file (the arm's
own precondition), without building anything. Usage: arm_patterns.py ENGINE_DIR"""
import sys
from pathlib import Path
eng = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(eng))
import mutants
bad = 0
names = [m[0] for m in mutants.MUTATIONS]
for name, fname, pat, rep, breaks in mutants.MUTATIONS:
    src = (mutants.HDL / fname).read_text(encoding="utf-8")
    for p, _ in mutants.edits_of(pat, rep):
        c = src.count(p)
        if c != 1:
            bad += 1
            print(f"MISMATCH {name!r}: {c}")
print(f"entries {len(names)}; duplicate names {len(names)-len(set(names))}; pattern mismatches {bad}")
