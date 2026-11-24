#!/usr/bin/env python3
"""Run independent focused checks concurrently, keeping all children joined."""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys

repo = Path(sys.argv[1]).resolve()
packet = Path(__file__).resolve().parent
scratch = packet / 'scratch'
env = dict(os.environ, TMPDIR=str(scratch), PATH='$VALIDATION_TOOLS/pinned-verilator-5.050:' + os.environ['PATH'])
env.pop('MAKEFLAGS', None)
env.pop('MAKELEVEL', None)
jobs = {
    'passes-1': ['make', '-j16', '-C', 'tb/verilator/engine', 'passes-test'],
    'passes-2': ['make', '-j16', '-C', 'tb/verilator/engine', 'passes-test'],
    'docs-lint': ['make', '-j16', 'docs', 'lint'],
}
def run(item):
    name, command = item
    with (packet / (name + '.log')).open('w') as log:
        result = subprocess.run(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=550)
    (packet / (name + '.rc')).write_text(str(result.returncode) + '\n')
    return name, result.returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(run, jobs.items()))
print(results)
sys.exit(any(rc for _, rc in results))
