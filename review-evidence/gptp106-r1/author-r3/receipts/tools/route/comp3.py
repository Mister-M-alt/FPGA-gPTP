"""comp3.py <shipping gateware dir> <directive> <output dir>: write a comparison route for another placement
directive the way the parent's recipe does (docs/testing/PP_SHADOW_BASELINE_RECIPE.md, integrated measurements;
#818): the shipping script's thread setting, the shipping route's synthesis checkpoint opened, then every command of
the shipping script after '# Add pre-optimize commands' with only the placement directive changed. The constraint
file is copied beside it, as the recipe does. The script is then checked with the gate's own bound()
(syn/ooc/pp_resource_gate.py), which accepts only the script the recipe writes from that shipping route."""
import shutil
import sys
from pathlib import Path

shipping, directive, out = Path(sys.argv[1]).resolve(), sys.argv[2], Path(sys.argv[3])
clone = Path(sys.argv[4]) if len(sys.argv) > 4 else None
script = (shipping / "baseline_integrated.tcl").read_text()
gate_dir = Path([l for l in script.splitlines() if l.startswith("source {") and "clock_constraints.tcl" in l][0]
                .split("{")[1].split("}")[0]).parents[2] / "syn/ooc"
sys.path.insert(0, str(gate_dir))
import pp_resource_gate as gate  # noqa: E402

threads = gate.THREADS.findall(script)
shipped = f"place_design -directive {gate.DIRECTIVES[0]}"
_, marker, tail = script.partition(gate.TAIL)
assert len(threads) == 1 and marker and script.count(shipped) == 1 and shipped in tail, "not a shipping route"
assert directive in gate.DIRECTIVES[1:], directive
if out.exists():
    sys.exit(f"refusing: {out} exists (each measurement in a fresh directory)")
out.mkdir(parents=True)
shutil.copy2(shipping / "alinx_ax7101.xdc", out)
text = f"{threads[0]}\nopen_checkpoint {{{shipping / gate.CHECKPOINT}}}\n" + tail.replace(
    shipped, f"place_design -directive {directive}")
(out / gate.COMPARISON).write_text(text)
bound = gate.bound(out.resolve(), shipping, script)
assert bound == script.replace(shipped, f"place_design -directive {directive}")
print(f"{out}: {gate.COMPARISON} written; the gate's bound() accepts it as the {directive} comparison of {shipping}")
