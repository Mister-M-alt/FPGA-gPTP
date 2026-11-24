"""Own -i / no-option receipt for docs/TEST_DEVELOPER.md's fail-fast sentences: the head's run against the serial
recipe with stub tools, passes 1 and 2 failing. usage: python3 ignore_errors.py ENGINE_DIR_COPY"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import passes_test as pt
with tempfile.TemporaryDirectory(prefix="ign-", dir=sys.argv[2]) as name:
    scratch = Path(name); trees = pt.tree(scratch)
    plan = {"1": {"exit": 1}, "2": {"exit": 1}}
    for flags in (["-j4"], ["-j4", "-i"], ["-j1", "-i"]):
        for side in ("serial", "parallel"):
            ev = scratch / "ev.jsonl"; ev.unlink(missing_ok=True)
            r = pt.make(trees[side], flags, plan, ev)
            starts = sorted({e["job"] for e in pt.read(ev) if e["what"] == "start"})
            print(f"=== {side} make {' '.join(flags)}: rc {r.returncode}; passes started {starts}")
            print("stdout:", *[l for l in r.stdout.splitlines() if l.startswith(("pass", "--"))], sep="\n  ")
            print("stderr:", *[l for l in pt.norm(r.stderr, trees[side]).splitlines() if "note" not in l], sep="\n  ")
