#!/usr/bin/env python3
"""Verify every tracked byte, executable mode, index entry and gitlink.

Usage: verify_checkout.py CHECKOUT PACKET
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

root, packet = map(Path, sys.argv[1:])
def git(*args):
    return subprocess.check_output(['git',*args],cwd=root)
head = git('rev-parse','HEAD').decode().strip()
tree = git('rev-parse','HEAD^{tree}').decode().strip()
assert head == 'bbda770befae8748c1139c4e843c5874c5330048'
assert tree == 'f4ea8ea4b503f8680d571c14394eb7235650ee77'
items = git('ls-tree','-rz','HEAD').split(b'\0')
files = []
links = []
for item in filter(None,items):
    meta, rawpath = item.split(b'\t',1)
    mode, kind, oid = meta.decode().split()
    path = os.fsdecode(rawpath)
    if mode == '160000':
        actual = subprocess.check_output(['git','rev-parse','HEAD'],cwd=root/path).decode().strip()
        assert actual == oid
        links.append({'path':path,'oid':oid})
        continue
    f = root/path
    if mode == '120000':
        assert f.is_symlink()
        data = os.fsencode(os.readlink(f))
    else:
        assert f.is_file() and not f.is_symlink()
        assert bool(f.stat().st_mode & 0o111) == (mode == '100755'), path
        data = f.read_bytes()
    actual = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    assert actual == oid, path
    files.append({'path':path,'mode':mode,'blob':oid})
index = git('ls-files','-s')
assert index == (packet/'receipts/index-before.txt').read_bytes()
assert git('write-tree').decode().strip() == tree
assert not git('status','--porcelain=v1','--untracked-files=all')
result = {'head':head,'tree':tree,'tracked_files_checked':len(files),
          'worktree_bytes_and_modes':'EXACT','index':'EXACT',
          'index_sha256':hashlib.sha256(index).hexdigest(),
          'gitlinks':links,'status':'CLEAN',
          'note':'No tracked source was edited. All probe copies remain under packet scratch.'}
(packet/'receipts/checkout-integrity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
