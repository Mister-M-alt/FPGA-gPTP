#!/usr/bin/env python3
"""Summarize completed reviewer executions and hash publishable packet files."""
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parent
receipts = root / "receipts"
results = json.loads((receipts / "local-results.json").read_text())
assert results["head-engine"] == 0
assert results["base-with-head-harness"] == 1
assert results["docs-contract"] == 0
assert all(results[f"p106-{i}-all-named-checks-caught"] for i in range(2))
lines = []
for name in ["head-engine", "base-with-head-harness", "p106-0", "p106-1"]:
    text = (receipts / (name + ".log")).read_text()
    tally = re.findall(r"^\d+ checks: \d+ PASS, \d+ FAIL$", text, re.M)
    assert len(tally) == 1, name
    lines.append(name + ": " + tally[0])
    lines.extend(line for line in text.splitlines() if line.startswith("FAIL "))
    lines.append("")
(receipts / "execution-summary.txt").write_text("\n".join(lines) + "\n")
report = (root / "REPORT.md").read_text()
assert "SKELETON" not in report and "LOCAL_RESULTS_PENDING" not in report
assert report.startswith("[R906] NEGATIVE - exact head a728cc3ce9d0342aa596c8170fecf1284c0b604c\n")
assert report.rstrip().endswith("R906-1 FINISHED")
manifest = []
for path in sorted(root.rglob("*")):
    relative = path.relative_to(root)
    if not path.is_file() or relative.parts[0] == "scratch" or path.name == "MANIFEST.sha256":
        continue
    if "__pycache__" in relative.parts:
        continue
    manifest.append(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + relative.as_posix())
(root / "MANIFEST.sha256").write_text("\n".join(manifest) + "\n")
print("Sealed", len(manifest), "publishable files; scratch excluded")
