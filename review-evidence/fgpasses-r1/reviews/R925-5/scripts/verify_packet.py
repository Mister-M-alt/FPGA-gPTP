#!/usr/bin/env python3
"""Verify a published review-evidence tree against its MANIFEST.json (file, published_sha256), report unlisted files.

usage: verify_packet.py ROOT
"""
import hashlib, json, os, sys
root = sys.argv[1]
entries = json.load(open(os.path.join(root, "MANIFEST.json")))
ok, bad, missing = 0, [], []
for e in entries:
    path = os.path.join(root, e["file"])
    if not os.path.exists(path):
        missing.append(e["file"]); continue
    if hashlib.sha256(open(path, "rb").read()).hexdigest() == e["published_sha256"]:
        ok += 1
    else:
        bad.append(e["file"])
listed = {e["file"] for e in entries}
unlisted = sorted(os.path.relpath(os.path.join(d, f), root) for d, _, fs in os.walk(root) for f in fs
                  if os.path.relpath(os.path.join(d, f), root) not in listed | {"MANIFEST.json"})
print(f"entries {len(entries)} ok {ok} bad {len(bad)} missing {len(missing)} unlisted {len(unlisted)}")
for e in entries:
    if e["file"].startswith(("author-r5/", "author-r6/")):
        print(e["published_sha256"], e["file"])
sys.exit(1 if bad or missing else 0)
