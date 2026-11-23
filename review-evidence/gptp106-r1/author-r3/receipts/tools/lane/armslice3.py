"""armslice3.py <a:b>: the engine mutation arm's own main() (mutants.py, run from its directory) over the slice
MUTATIONS[a:b] of its table, at --jobs 8: the positive control and run_mutant() unchanged, so each slice prints the
verdict lines the whole arm prints for those controls, then its own tally. Run with PYTHONUNBUFFERED=1."""
import sys

sys.path.insert(0, ".")
import mutants  # noqa: E402

a, b = (int(x) for x in sys.argv[1].split(":"))
whole = len(mutants.MUTATIONS)
mutants.MUTATIONS = mutants.MUTATIONS[a:b]
print(f"SLICE {a}:{b} of {whole} controls ({len(mutants.MUTATIONS)} here), --jobs 8", flush=True)
sys.exit(mutants.main(["--jobs", "8"]))
