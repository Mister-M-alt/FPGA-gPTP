#!/usr/bin/env python3
"""Verify exact checkout/index bytes and modes, public receipt hashes, ROMs.

Usage: python3 audit.py REPO > receipts/audit.log
The public packet must have been archived into scratch/public first.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve()
HEAD = "a728cc3ce9d0342aa596c8170fecf1284c0b604c"
TREE = "d99b9b065b9acebdae5d39519023b785e249222c"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=REPO)


assert git("rev-parse", "HEAD").decode().strip() == HEAD
assert git("rev-parse", "HEAD^{tree}").decode().strip() == TREE
expected = {}
links = []
for row in git("ls-tree", "-rz", "HEAD").split(b"\0"):
    if not row:
        continue
    meta, rawpath = row.split(b"\t", 1)
    mode, kind, oid = meta.decode().split()
    name = os.fsdecode(rawpath)
    expected[name] = (mode, oid)
    if mode == "160000":
        links.append((name, oid))
        continue
    path = REPO / name
    data = os.fsencode(os.readlink(path)) if mode == "120000" else path.read_bytes()
    digest = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert digest == oid, name
    actual_mode = "120000" if path.is_symlink() else (
        "100755" if path.stat().st_mode & 0o111 else "100644")
    assert actual_mode == mode, name
index = {}
for row in git("ls-files", "--stage", "-z").split(b"\0"):
    if not row:
        continue
    meta, name = row.split(b"\t", 1)
    mode, oid, stage = meta.decode().split()
    assert stage == "0"
    index[os.fsdecode(name)] = (mode, oid)
assert index == expected
assert not git("status", "--porcelain=v1", "--untracked-files=all")
print("HEAD", HEAD, "TREE", TREE)
print("PASS tracked blob bytes, executable/symlink modes and index:", len(expected))
print("Required nested gitlinks:", json.dumps(links))
print("PASS clean status; source repository has no nested submodules")
print("mutants.py lines:", len((REPO / "tb/verilator/engine/mutants.py").read_text().splitlines()))
function_maps = []
for revision in ["1616fc8f062fbf58c35ad31674b5b233207bbdb8", HEAD]:
    module = ast.parse(git("show", revision + ":hdl/ucode/gen_gptp_ucode.py"))
    functions = {}
    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            if (node.body and isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)):
                node.body = node.body[1:]
            functions[node.name] = ast.dump(node, include_attributes=False)
    function_maps.append(functions)
changed = sorted(name for name in function_maps[0]
                 if function_maps[0][name] != function_maps[1].get(name))
assert changed == ["prog_become", "prog_self"], changed
print("PASS generator semantic function delta (docstrings excluded):", changed)
public = ROOT / "scratch/public/review-evidence/gptp106-r1"
entries = json.loads((public / "MANIFEST.json").read_text())
for entry in entries:
    digest = hashlib.sha256((public / entry["file"]).read_bytes()).hexdigest()
    assert digest == entry["published_sha256"], entry["file"]
print("PASS published evidence manifest:", len(entries), "files at 42e140e6768105b5b53231367046800f630b834e")
out = ROOT / "scratch/rom-audit"
out.mkdir(exist_ok=True)
generator = REPO / "hdl/ucode/gen_gptp_ucode.py"
recipes = [
    ("tb/verilator/engine/gptp_ucode.hex", ["--clk-hz", "2000000", "--cease-ms", "3000"]),
    ("tb/tsngen/gptp_ucode.hex", ["--clk-hz", "2000000"]),
    ("tb/verilator/ucpu/gptp_ucode.hex", []),
    ("syn/ooc/work/gptp_ucode.hex", []),
]
for i, (name, options) in enumerate(recipes):
    result = subprocess.run([sys.executable, str(generator), *options, "-o", str(out / str(i))],
                            capture_output=True, text=True, check=True)
    assert (out / str(i)).read_bytes() == (REPO / name).read_bytes(), name
    print("PASS regenerated", name, hashlib.sha256((out / str(i)).read_bytes()).hexdigest())
    print(result.stdout.replace(str(out / str(i)), name).strip())
