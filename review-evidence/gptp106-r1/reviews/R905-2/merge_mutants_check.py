"""Compare the engine MUTATIONS tables of the merge parents and the merge.

Usage: python3 merge_mutants_check.py <tree_base> <tree_branch> <tree_main> <tree_merge>
Each tree is an extraction holding tb/verilator/engine/mutants.py.
"""
import importlib, sys, pathlib

def load(tree):
    d = pathlib.Path(tree, "tb/verilator/engine").resolve()
    for k in [k for k in sys.modules if k.endswith("_mutants") or k == "mutants"]:
        del sys.modules[k]
    sys.path.insert(0, str(d))
    m = importlib.import_module("mutants")
    sys.path.remove(str(d))
    return {tuple(map(str, x)) for x in m.MUTATIONS}, [x[0] for x in m.MUTATIONS]

base, branch, main, merge = (load(t) for t in sys.argv[1:5])
for n, (s, l) in zip(("base", "branch", "main", "merge"), (base, branch, main, merge)):
    print(f"{n}: {len(l)} entries, {len(set(l))} unique names")
B, Br, M, Mg = base[0], branch[0], main[0], merge[0]
br_added, br_removed = Br - B, B - Br
mn_added, mn_removed = M - B, B - M
print("branch adds", len(br_added), "removes", len(br_removed))
print("main adds", len(mn_added), "removes", len(mn_removed))
expect = (B - br_removed - mn_removed) | br_added | mn_added
print("merge == base - removals + both sides' additions:", Mg == expect)
for x in sorted(Mg ^ expect):
    print("  DIFF", "in-merge" if x in Mg else "missing", x[0])
for x in sorted(br_removed): print("  branch removed:", x[0])
for x in sorted(mn_removed): print("  main removed:", x[0])
