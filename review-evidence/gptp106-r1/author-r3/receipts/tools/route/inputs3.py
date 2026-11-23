"""inputs3.py <shipping gateware dir> [...]: each design input of a shipping route the way the parent's resource
gate digests it (syn/ooc/pp_resource_gate.py inputs(): every read or sourced file, include header, generic and memory
image of the script, the exporter's comment dates and absolute roots normalised), one line per input, then the gate's
own digest of the whole set under --placement full-split."""
import hashlib
import re
import sys
from pathlib import Path

for arg in sys.argv[1:]:
    d = Path(arg).resolve()
    script = (d / "baseline_integrated.tcl").read_text()
    root = Path(re.search(r"source \{(\S+)/sw/litex/clock_constraints\.tcl\}", script)[1])
    sys.path.insert(0, str(root / "syn/ooc"))
    import pp_resource_gate as gate  # noqa: E402
    files, roots = gate.located(d, script, "full-split")
    print(f"## {d}")
    for path in files:
        data = path.read_bytes()
        if str(path).startswith(roots[0] + "/"):
            text = re.sub(r"//[^\n]*", "", data.decode(errors="replace"))
            for index, r in enumerate(roots):
                text = text.replace(r, f"$ROOT{index}")
            data = text.encode()
        rel = str(path).replace(str(root) + "/", "<clone>/").replace(str(d) + "/", "<gateware>/")
        print(f"file {hashlib.sha256(data).hexdigest()[:16]} {rel}")
    for generic in gate.GENERICS.findall(script):
        print("generic " + re.sub(r'"[^"]*/([^/"]+)"', r'"\1"', generic))
    images = gate.strict((d / "baseline_images.json").read_text())
    for image in sorted(images, key=lambda row: Path(row["path"]).name):
        print(f"image {image['sha256'][:16]} {Path(image['path']).name}")
    print(f"inputs_sha256 {gate.inputs(d, script, 'full-split')}")
    sys.path.pop(0)
    del sys.modules["pp_resource_gate"]
