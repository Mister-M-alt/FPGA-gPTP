"""body3.py <gateware dir> ...: the generated top alinx_ax7101.v of each export with both comment forms removed
(// and /* */: the exporter stamps dates in the first and prints its hierarchy tree, whose black-box order is not
stable between runs, in the second) and the clone and export roots written as $CLONE and $GATEWARE: one sha256 per
export, then the comment lines that differ from the first export's after only the roots are normalised."""
import difflib
import hashlib
import re
import sys
from pathlib import Path

first = None
for arg in sys.argv[1:]:
    d = Path(arg).resolve()
    script = (d / "baseline_integrated.tcl").read_text()
    clone = re.search(r"source \{(\S+)/sw/litex/clock_constraints\.tcl\}", script)[1]
    text = (d / "alinx_ax7101.v").read_text().replace(clone, "$CLONE").replace(str(d), "$GATEWARE")
    body = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))
    print(f"{hashlib.sha256(body.encode()).hexdigest()[:16]} body of {d}")
    if first is None:
        first = text
    else:
        for line in difflib.unified_diff(first.splitlines(), text.splitlines(), n=0, lineterm=""):
            if line[:1] in "+-" and not line.startswith(("+++", "---")):
                print(f"    {line[:110]}")
