#!/usr/bin/env python3
"""Fetch and extract only the pinned public evidence packet into scratch/."""
import io
from pathlib import Path
import subprocess
import sys
import tarfile

repo=Path(sys.argv[1]).resolve()
sha='90fd6083843178d81423c1e2ade23a95b5dc5d63'
def git(*args):
    return subprocess.check_output(['rtk','proxy','git',*args],cwd=repo)
try:
    git('cat-file','-e',sha)
except subprocess.CalledProcessError:
    git('fetch','--no-tags','https://github.com/Mister-M-alt/FPGA-gPTP.git',sha)
scratch=Path(__file__).resolve().parent/'scratch'
scratch.mkdir(exist_ok=True)
with tarfile.open(fileobj=io.BytesIO(git('archive',sha,'review-evidence/gptp109-r1'))) as archive:
    archive.extractall(scratch,filter='data')
print('Pinned public evidence extracted; no checkout or index change.')
