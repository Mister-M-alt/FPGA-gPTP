#!/usr/bin/env python3
"""Reviewer check: compare the downloaded author-r2 evidence files with the
published_sha256 the evidence MANIFEST.json records for them.
Usage: verify_evidence.py EVIDENCE_DIR (holds MANIFEST.json and the author-r2 files)"""
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
m = json.loads((d / "MANIFEST.json").read_text())
bad = n = 0
for e in m:
    f = e["file"]
    if not f.startswith("author-r2/"):
        continue
    n += 1
    h = hashlib.sha256((d / f[len("author-r2/"):]).read_bytes()).hexdigest()
    ok = h == e["published_sha256"]
    bad += not ok
    print(("OK  " if ok else "BAD ") + f + " " + h)
print(f"author-r2 entries {n}; mismatches {bad}")
