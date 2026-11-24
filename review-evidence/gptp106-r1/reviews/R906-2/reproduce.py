#!/usr/bin/env python3
"""Usage: python3 reproduce.py REPOSITORY. Runs focused foreground probes only."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile

root = Path(__file__).resolve().parent
repo = Path(sys.argv[1]).resolve()
scratch = root / "scratch"
scratch.mkdir(exist_ok=True)
evidence = "2c2ba060bc802cef25ccb95767d657d4e3c6b260"
prefix = "review-evidence/gptp106-r1/"
archive = subprocess.check_output(["git", "-C", str(repo), "archive", evidence,
                                   prefix + "author", prefix + "author-r3", prefix + "MANIFEST.json"])
with tarfile.open(fileobj=io.BytesIO(archive)) as source:
    source.extractall(scratch, filter="data")
env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(scratch))

def run(name, argv, cwd=None):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    text = (result.stdout + result.stderr).replace(str(root), "$PACKET").replace(str(repo), "$SOURCE")
    (root / (name + ".txt")).write_text(text)
    (root / (name + ".rc")).write_text(str(result.returncode) + "\n")
    print(f"{name}: exit {result.returncode}", flush=True)
    if result.returncode:
        raise SystemExit(result.returncode)

run("structural-checks", [sys.executable, "-B", str(root / "check_review.py"), str(repo)])
run("resource-checks", [sys.executable, "-B", str(root / "check_resources.py")])
source = scratch / "source-331e27de137a1d4f7acd4f3f2cc7e373b6e8e869"
run("docs-contract", ["make", "-j16", "docs", "contract"], source)
run("integrity", [sys.executable, "-B", str(root / "audit.py"), str(repo)])
