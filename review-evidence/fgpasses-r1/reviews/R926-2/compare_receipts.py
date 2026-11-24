#!/usr/bin/env python3
"""Strict ordered comparison and timing arithmetic from the verified public receipts."""
import hashlib
import json
import re
import sys
from pathlib import Path

packet = Path(sys.argv[1]).resolve()
root = packet / "scratch/public/author-r2/receipts/gptp"
def norm(path):
    lines = []
    for line in path.read_text().splitlines():
        if line.startswith("- Verilator: Walltime "):
            continue
        line = re.sub(r'-I/[^\s"]*/tb/verilator/engine', '-I<TREE>', line)
        line = re.sub(r'(make: \*\*\* \[Makefile:)\d+(: run\])', r'\1NN\2', line)
        lines.append(line)
    return "\n".join(lines) + "\n"
results = []
for a, b, file in [
    ("c-base-j4", "c-head-j4", "log"),
    ("r-base-j4", "r-head-j4", "log.tail"),
    ("r-base-j4", "r-head-j4-b", "log.tail"),
    ("c-base-j1", "c-head-j1", "log.tail"),
    ("c-base-abort-j4", "c-head-abort-j4", "log.tail"),
]:
    left, right = norm(root / a / file), norm(root / b / file)
    same = left == right
    assert same, (a, b)
    results.append({"base": a, "head": b, "artifact": file, "strict_order_equal": same,
                    "lines": len(left.splitlines()), "sha256": hashlib.sha256(left.encode()).hexdigest()})
    print(f"{a} vs {b}: STRICT ORDER IDENTICAL, {len(left.splitlines())} lines ({file})")
    if file == "log":
        # The raw public log stays in scratch. Retain the complete simulator output and image metadata.
        kept = left.splitlines()
        sim = kept.index("./obj_dir/Vengine_sim")
        transcript = "\n".join(kept[:3] + kept[sim:]) + "\n"
        (packet / "receipts/real-transcript.txt").write_text(transcript)
arms = {}
for name in sorted(p.name for p in root.iterdir() if p.is_dir()):
    value = (root / name / "time").read_text()
    wall, user, system = map(float, re.search(r'([\d.]+) wall ([\d.]+) user ([\d.]+) sys', value).groups())
    rc = int(re.search(r'rc=(\d+)', value).group(1))
    arms[name] = {"wall": wall, "cpu": user + system, "rc": rc}
    print(name, json.dumps(arms[name], sort_keys=True))
for base, head in [("c-base-j4", "c-head-j4"), ("r-base-j4", "r-head-j4"),
                   ("r-base-j4", "r-head-j4-b"), ("c-base-j1", "c-head-j1")]:
    print(f'{base} -> {head}: wall speedup {arms[base]["wall"] / arms[head]["wall"]:.4f}x, '
          f'CPU change {(arms[head]["cpu"] / arms[base]["cpu"] - 1)*100:+.4f}%')
(packet / "receipts/real-evidence-audit.json").write_text(json.dumps({"comparisons": results, "timings": arms}, indent=2) + "\n")
