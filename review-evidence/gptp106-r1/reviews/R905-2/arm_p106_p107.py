"""Run the merged engine arm's own main() over the #106 and #107 controls only.

Usage (from tb/verilator/engine of an extraction of the reviewed head):
    PYTHONUNBUFFERED=1 python3 <path>/arm_p106_p107.py <jobs>
The positive control, staging, build and grading are mutants.py's, unchanged.
"""
import sys

sys.path.insert(0, ".")
import mutants  # noqa: E402
from p106_mutants import P106_MUTATIONS  # noqa: E402
from p107_mutants import P107_MUTATIONS  # noqa: E402

sel = [*P106_MUTATIONS, *P107_MUTATIONS]
assert all(m in mutants.MUTATIONS for m in sel), "a #106/#107 control is not in the merged table"
print(f"#106/#107 controls: {len(sel)} of the merged table's {len(mutants.MUTATIONS)}", flush=True)
mutants.MUTATIONS = sel
sys.exit(mutants.main(["--jobs", sys.argv[1]]))
