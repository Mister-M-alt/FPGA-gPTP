#!/usr/bin/env python3
"""Verify only the public author packet relevant to #112, then retain it in scratch."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

repo, packet = map(lambda p: Path(p).resolve(), sys.argv[1:])
commit = "fab17af4fdfd59955b6e8ad671ac127bcb3af403"
prefix = "review-evidence/fgpasses-r1/"
def git(*args):
    return subprocess.check_output(["git", "-C", str(repo), *args])
manifest = json.loads(git("show", f"{commit}:{prefix}MANIFEST.json"))
selected = [e for e in manifest if e["file"].startswith("author-r2/receipts/gptp/") or e["file"] == "author-r2/REPORT.md"]
assert selected
for entry in selected:
    data = git("show", f'{commit}:{prefix}{entry["file"]}')
    digest = hashlib.sha256(data).hexdigest()
    assert digest == entry["published_sha256"], entry["file"]
    dest = packet / "scratch/public" / entry["file"]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    print(f'{digest}  {entry["file"]}  VERIFIED')
headers = git("cat-file", "commit", commit).split(b"\n\n", 1)[0]
print(f"Verified {len(selected)} published manifest entries at {commit}")
print("Commit signature header present:", b"\ngpgsig " in headers)
print("The published manifest supplies SHA-256 integrity, not an independently verified signing identity.")
