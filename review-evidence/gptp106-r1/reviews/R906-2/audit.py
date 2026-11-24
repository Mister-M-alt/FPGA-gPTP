#!/usr/bin/env python3
"""Verify checkout bytes, executable modes, index and gitlinks against HEAD."""
import hashlib
from pathlib import Path
import stat
import subprocess
import sys

repo = Path(sys.argv[1]).resolve()

def git(*args):
    return subprocess.check_output(["git", "-C", str(repo), *args])

head = git("rev-parse", "HEAD").decode().strip()
tree = git("rev-parse", "HEAD^{tree}").decode().strip()
assert head == "331e27de137a1d4f7acd4f3f2cc7e373b6e8e869"
assert tree == "7b579e33a97ff4f2bec8c0064f0f73c862bbb135"
count = links = 0
for row in git("ls-tree", "-rz", "HEAD").split(b"\0"):
    if not row:
        continue
    metadata, name = row.split(b"\t")
    mode, kind, oid = metadata.decode().split()
    path = repo / name.decode()
    if mode == "160000":
        links += 1
        continue
    assert kind == "blob"
    assert path.read_bytes() == git("cat-file", "blob", oid), name
    actual = "100755" if path.stat().st_mode & stat.S_IXUSR else "100644"
    assert mode == actual, name
    count += 1
assert git("write-tree").decode().strip() == tree
assert not git("status", "--porcelain=v1", "--untracked-files=all")
assert links == 0
print(f"PASS HEAD {head}\nPASS tree {tree}")
print(f"PASS all {count} tracked blob bytes and executable modes match HEAD")
print("PASS index tree equals HEAD tree; clean tracked and untracked status")
print("PASS required nested gitlinks: zero; parent pin is assessed only through public receipts")
index = git("rev-parse", "--git-path", "index").decode().strip()
index_path = Path(index) if Path(index).is_absolute() else repo / index
print("Index file SHA256 " + hashlib.sha256(index_path.read_bytes()).hexdigest())
