#!/usr/bin/env python3
"""Verify the detached checkout, index entries, every tracked byte/mode and gitlinks."""
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

repo = Path(sys.argv[1]).resolve()
expected_head = "661e4c3a45904d2d8f3e061c67103a945651d9ff"
expected_tree = "97405b32d95b1b4397f77052d0faef868da20c2e"
def git(*args):
    return subprocess.check_output(["git", "-C", str(repo), *args])
assert git("rev-parse", "HEAD").decode().strip() == expected_head
assert git("rev-parse", "HEAD^{tree}").decode().strip() == expected_tree
assert subprocess.run(["git", "-C", str(repo), "symbolic-ref", "-q", "HEAD"], capture_output=True).returncode == 1
expected = {}
gitlinks = {}
for entry in git("ls-tree", "-rz", "HEAD").split(b"\0"):
    if not entry:
        continue
    header, raw_path = entry.split(b"\t", 1)
    mode, kind, oid = header.decode().split()
    path = os.fsdecode(raw_path)
    expected[path] = (mode, oid)
    if mode == "160000":
        gitlinks[path] = oid
        continue
    target = repo / path
    if mode == "120000":
        assert target.is_symlink()
        data = os.fsencode(os.readlink(target))
    else:
        assert target.is_file() and not target.is_symlink()
        data = target.read_bytes()
        actual_mode = "100755" if target.stat().st_mode & 0o111 else "100644"
        assert actual_mode == mode, path
    assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == oid, path
indexed = {}
for entry in git("ls-files", "--stage", "-z").split(b"\0"):
    if not entry:
        continue
    header, path = entry.split(b"\t", 1)
    mode, oid, stage = header.decode().split()
    assert stage == "0"
    indexed[os.fsdecode(path)] = (mode, oid)
assert indexed == expected
status = git("status", "--porcelain=v1", "--untracked-files=all").decode()
assert not status, status
assert not gitlinks, "This exact repository tree is expected to have no gitlinks"
print(json.dumps({"head": expected_head, "tree": expected_tree, "detached": True,
                  "tracked_entries": len(expected), "all_tracked_bytes_and_modes_match": True,
                  "index_entries_match_tree": True, "gitlinks": gitlinks, "clean_status": True}, indent=2))
