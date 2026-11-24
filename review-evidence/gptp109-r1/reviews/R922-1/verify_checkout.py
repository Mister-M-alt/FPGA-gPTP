#!/usr/bin/env python3
"""Verify the reviewed checkout's HEAD, tree, tracked bytes/modes, index and gitlinks."""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys

repo=Path(sys.argv[1]).resolve()
head='8e4889bba462d14d4e5a34068769872510d4775d'
tree='bcd69a8e01ba7856d093579faf0dfbf256e772e4'
def git(*args):
    return subprocess.check_output(['rtk','proxy','git',*args],cwd=repo)
assert git('rev-parse','HEAD').decode().strip()==head
assert git('rev-parse','HEAD^{tree}').decode().strip()==tree
count=0
links=[]
for row in git('ls-tree','-rz',head).split(b'\0'):
    if not row: continue
    meta,path=row.split(b'\t',1)
    mode,kind,oid=meta.decode().split()
    name=os.fsdecode(path)
    if mode=='160000':
        links.append((name,oid))
        continue
    file=repo/name
    data=os.readlink(file).encode() if mode=='120000' else file.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==oid,name
    actual='120000' if file.is_symlink() else ('100755' if file.stat().st_mode & stat.S_IXUSR else '100644')
    assert actual==mode,(name,mode,actual)
    count+=1
assert not links
assert git('diff','--cached','--name-only',head)==b''
assert git('diff','--name-only',head)==b''
assert git('status','--porcelain=v1')==b''
print('HEAD:',head)
print('Tree:',tree)
print('Tracked blob bytes and modes:',count,'PASS')
print('Index equality to HEAD: PASS')
print('Required nested submodule gitlinks: none (PASS)')
print('Working tree and untracked status: clean')
print('No source restoration was necessary: all probes used disposable copies.')
