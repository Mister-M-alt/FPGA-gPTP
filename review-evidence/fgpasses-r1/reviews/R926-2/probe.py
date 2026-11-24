#!/usr/bin/env python3
"""Focused, disposable budget and planted-echo checks. Usage: probe.py CHECKOUT PACKET"""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

repo, packet = map(lambda p: Path(p).resolve(), sys.argv[1:])
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("passes", repo / "tb/verilator/engine/passes_test.py")
test = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test)
scratch = Path(tempfile.mkdtemp(prefix="independent-probe-", dir=packet / "scratch"))
trees = test.tree(scratch)
bad = test.budget(trees, scratch)
for path in sorted(scratch.glob("budget*.jsonl")):
    (packet / "receipts" / path.name).write_bytes(path.read_bytes())
mk = trees["parallel"] / "Makefile"
original = mk.read_text()
needle = '$(if $(findstring s,$(firstword -$(MAKEFLAGS))),,--banner ./obj_dir/Vengine_sim)'
assert original.count(needle) == 1
mk.write_text(original.replace(needle, '--banner ./obj_dir/Vengine_sim'))
test.PLANS = {"clean": {}}
caught = test.transcripts(trees, scratch)
print(f"PLANTED ECHO DEFECT: {caught} failing comparisons; expected 1")
mk.write_text(original)
assert bad == 0 and caught == 1
for n in range(4):
    done = test.make(trees["parallel"], ["-j4"], {str(n): {"unreadable": 1}}, scratch / f"unreadable{n}.jsonl")
    assert done.returncode == 2 and f"engine pass {n}: its transcript could not be printed" in done.stderr
    assert all(f"pass {later}:" not in done.stdout for later in range(n + 1, 4))
    print(f"Unreadable transcript {n}: status 2, diagnostic present, later output suppressed")
done = test.make(trees["parallel"], ["-j4", "-i"], {"1": {"exit": 1}}, scratch / "ignore-errors.jsonl")
for suffix, content in (("stdout", done.stdout), ("stderr", done.stderr), ("rc", str(done.returncode) + "\n")):
    (packet / "receipts" / f"ignore-errors.{suffix}").write_text(content)
assert done.returncode == 0 and "pass 3: 12 checks: 12 PASS" in done.stdout and "(ignored)" in done.stderr
print("With -i, pass 1 failure is ignored; passes 2 and 3 print and make returns 0")
print("Independent budget and mutation probes: PASS")
