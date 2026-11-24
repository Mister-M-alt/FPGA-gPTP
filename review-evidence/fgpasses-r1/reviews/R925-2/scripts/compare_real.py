#!/usr/bin/env python3
"""Reviewer probe: compare real-harness `make run` logs after removing only host text.

usage: python3 -I compare_real.py LOG_A LOG_B
Removed: Verilator's report lines ('- V e r i l a t i o n', '- Verilator'), compiler/ccache lines
(containing 'g++' or 'ccache'), the verilator command line ('verilator --cc'), sub-make
directory lines ('make[N]: Entering/Leaving'), and each tree's own path (masked).
make's recipe line numbers in '[Makefile:NN: run]' are masked. Prints IDENTICAL or a diff,
the line count and the SHA-256 of the normalised text.
"""
import difflib, hashlib, re, sys
def norm(path):
    out = []
    text = open(path, errors="surrogateescape").read()
    m = re.search(r"Entering directory '([^']*)/tb/verilator/engine'", text)
    root = m.group(1) if m else None
    for line in text.splitlines():
        if (line.startswith("- V e r i l a t i o n") or line.startswith("- Verilator") or "g++" in line
                or "ccache" in line or "verilator --cc" in line or re.match(r"make\[\d+\]: (Entering|Leaving)", line)):
            continue
        if root:
            line = line.replace(root, "<tree>")
        line = re.sub(r"\[Makefile:\d+: run\]", "[Makefile:NN: run]", line)
        out.append(line)
    return out
a, b = norm(sys.argv[1]), norm(sys.argv[2])
if a == b:
    print(f"IDENTICAL ({len(a)} normalised lines, sha256 {hashlib.sha256(chr(10).join(a).encode()).hexdigest()})")
else:
    print(f"DIFFER ({len(a)} vs {len(b)} lines)")
    for l in difflib.unified_diff(a, b, sys.argv[1], sys.argv[2], lineterm="", n=1):
        print(l)
