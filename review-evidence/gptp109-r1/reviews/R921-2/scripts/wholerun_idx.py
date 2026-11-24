#!/usr/bin/env python3
"""Reviewer check: list the full-arm indices whose named checks include one
of the whole-run grades (graded after phase 64), and confirm that no other
check of the suite is graded after the #109 phases. Usage: wholerun_idx.py ENGINE_DIR"""
import re, sys
from pathlib import Path
eng = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(eng))
import mutants
src = (eng / "sim_main.cpp").read_text(encoding="utf-8")
# the check names the three whole-run grade functions emit
names = set()
for fn in ("hold_every_committed_path_coherent", "keep_sync_ok_in_every_master_cycle",
           "end_every_peer_path_with_thisclock"):
    m = re.search(r"void %s\(\) \{(.*?)\n  \}\n" % fn, src, re.S)
    body = m.group(1)
    for s in re.findall(r'expect\(\s*"([^"]+)"', body):
        names.add(s)
print("whole-run check names:", sorted(names))
idx = []
for i, (name, _f, _p, _r, breaks) in enumerate(mutants.MUTATIONS):
    parts = [b.strip() for b in breaks.split("|")]
    if any(p in names for p in parts):
        idx.append(i)
print("entries", len(mutants.MUTATIONS), "whole-run idx", ",".join(map(str, idx)), "count", len(idx))
