#!/usr/bin/env python3
"""Verify actual worktree bytes/modes and index against the required tree."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

repo = Path(sys.argv[1]).resolve()
packet = Path(__file__).resolve().parent
def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo)
head = 'f1b566a881573611637e7bd6ecd257799b8c991c'
tree = 'c4cd0d38763e6d99ad35d8b6dc7e30db6fa38924'
assert git('rev-parse', 'HEAD').decode().strip() == head
assert git('rev-parse', 'HEAD^{tree}').decode().strip() == tree
assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=repo, capture_output=True).returncode == 1
expected = []
links = []
for item in git('ls-tree', '-rz', 'HEAD').split(b'\0'):
    if not item: continue
    meta, path = item.split(b'\t', 1)
    mode, kind, oid = meta.split()
    expected.append(mode + b' ' + oid + b' 0\t' + path)
    if mode == b'160000':
        links.append(path.decode())
        continue
    filename = repo / os.fsdecode(path)
    info = filename.lstat()
    if mode == b'120000':
        assert stat.S_ISLNK(info.st_mode)
        data = os.fsencode(os.readlink(filename))
    else:
        data = filename.read_bytes()
        actual = b'100755' if info.st_mode & 0o111 else b'100644'
        assert actual == mode, path
    actual_hash = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest().encode()
    assert actual_hash == oid, path
actual_index = git('ls-files', '-s', '-z').split(b'\0')
assert sorted(filter(None, actual_index)) == sorted(expected)
assert git('ls-files', '-s') == (packet / 'index-before.txt').read_bytes()
assert not git('status', '--porcelain=v1', '--untracked-files=all')
identity = subprocess.check_output(['$VALIDATION_TOOLS/pinned-verilator-5.050/verilator', '--version'], text=True).strip()
result = dict(head=head, tree=tree, detached=True, tracked_entries=len(expected),
              blob_bytes_and_modes='PASS', index_matches_head_and_initial='PASS',
              clean_status=True, required_gitlinks=links, compiler_identity=identity,
              compiler_launcher_sha256=hashlib.sha256(Path('$VALIDATION_TOOLS/pinned-verilator-5.050/verilator').read_bytes()).hexdigest())
(packet / 'checkout-integrity.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
