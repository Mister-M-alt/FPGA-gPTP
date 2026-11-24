#!/usr/bin/env python3
"""Review #111 runner in disposable copies. Usage: probe.py CHECKOUT PACKET.

Runs the unchanged old/new recipes with the same stand-in executable and real
image generator. Compilation is bypassed; this tests orchestration, not RTL.
Every child is joined before returning. No checkout files are changed.
"""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

BASE = '1213ac5b9e09b8759ba76cc70c53652b5e108996'
HEAD = 'bbda770befae8748c1139c4e843c5874c5330048'
REL = 'tb/verilator/engine/Makefile'

STUB = r'''#!/usr/bin/env python3
import fcntl, hashlib, json, os, pathlib, sys, time
root = pathlib.Path(os.environ['PROBE_ROOT'])
name = pathlib.Path.cwd().name
idx = {'seedrun':1, 'syncseedrun':2, 'p1run':3}.get(name, 0)
def event(kind):
    with (root/'events.jsonl').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps({'kind':kind,'pass':idx,'time_ns':time.monotonic_ns(),
              'image_sha256':hashlib.sha256(pathlib.Path('gptp_ucode.hex').read_bytes()).hexdigest(),
              'args':sys.argv[1:]})+'\n')
        f.flush()
event('start')
time.sleep((4-idx)*0.15)
print('pass %d stdout' % idx, flush=True)
print('pass %d stderr' % idx, file=sys.stderr, flush=True)
codes = json.loads(os.environ.get('PROBE_CODES','[0,0,0,0]'))
print('[FAIL]' if codes[idx] else '[PASS]', 'pass', idx, flush=True)
event('end')
sys.exit(codes[idx])
'''

def main():
    checkout, packet = map(lambda s: Path(s).resolve(), sys.argv[1:])
    scratch = packet/'scratch'/'probes'
    receipts = packet/'receipts'
    scratch.mkdir(parents=True, exist_ok=True)
    receipts.mkdir(exist_ok=True)
    recipes = {label: subprocess.check_output(['git','show',ref+':'+REL], cwd=checkout)
               for label,ref in [('serial',BASE),('parallel',HEAD)]}
    # The fault helper fails a real transcript read without modifying the recipe.
    badcat = scratch/'fault-bin'
    badcat.mkdir(exist_ok=True)
    (badcat/'cat').write_text('#!/bin/sh\ncase "$1" in obj_dir/pass1.out) echo "cat: planted transcript read error" >&2; exit 74;; esac\nexec /bin/cat "$@"\n')
    (badcat/'cat').chmod(0o755)
    def run(label, case, jobs, codes, read_fault=False):
        key = label+'-'+case
        root = scratch/key
        if root.exists():
            shutil.rmtree(root)
        (root/'obj_dir').mkdir(parents=True)
        (root/'Makefile').write_bytes(recipes[label])
        (root/'obj_dir'/'Vengine_sim').write_text(STUB)
        (root/'obj_dir'/'Vengine_sim').chmod(0o755)
        env = os.environ.copy()
        for n in ('MAKEFLAGS','MFLAGS','MAKELEVEL','GNUMAKEFLAGS'):
            env.pop(n, None)
        env.update(PROBE_ROOT=str(root), PROBE_CODES=json.dumps(codes), LC_ALL='C')
        if read_fault:
            env['PATH'] = str(badcat)+os.pathsep+env['PATH']
        cmd = ['make','--no-print-directory','-j'+str(jobs),'run',
               'VERILATOR=true','VFLAGS=','SRCS=','CPP=',
               'GEN='+str(checkout/'hdl/ucode/gen_gptp_ucode.py')]
        result = subprocess.run(cmd, cwd=root, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=45)
        # Remove only checkout path in the generator command for publication.
        log = result.stdout.replace(str(checkout).encode(), b'<CHECKOUT>')
        (receipts/(key+'.log')).write_bytes(log)
        (receipts/(key+'.rc')).write_text(str(result.returncode)+'\n')
        events = [json.loads(x) for x in (root/'events.jsonl').read_text().splitlines()]
        live = peak = 0
        for e in events:
            live += 1 if e['kind']=='start' else -1
            peak = max(peak, live)
        assert live == 0
        (receipts/(key+'.events.json')).write_text(json.dumps(events, indent=2)+'\n')
        # Recipe line location differs; preserve all verdicts, numeric statuses,
        # headings and ordering. No sorting or multiset equality is permitted.
        normalized = re.sub(rb'\[Makefile:\d+: run\]', b'[Makefile:LINE: run]', log)
        return {'case':case,'variant':label,'jobs':jobs,'codes':codes,'rc':result.returncode,
                'peak_passes':peak,'passes_started':[e['pass'] for e in events if e['kind']=='start'],
                'passes_finished':[e['pass'] for e in events if e['kind']=='end'],
                'normalized_sha256':hashlib.sha256(normalized).hexdigest(),
                'recipe_sha256':hashlib.sha256(recipes[label]).hexdigest()}
    cases = [('clean-j1',1,[0,0,0,0],False), ('clean-j2',2,[0,0,0,0],False),
             ('clean-j16',16,[0,0,0,0],False),
             *[('fail'+str(i),16,[3 if k==i else 0 for k in range(4)],False) for i in range(4)],
             ('multi-fail',16,[0,3,7,0],False), ('read-fault',16,[0,0,0,0],True)]
    results = []
    # Each pair has at most five simultaneous pass children; all are awaited.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for case,jobs,codes,fault in cases:
            pending = [pool.submit(run,label,case,jobs,codes,fault) for label in recipes]
            pair = [f.result() for f in pending]
            results.extend(pair)
            a,b = pair
            print(case, 'serial_rc='+str(a['rc']), 'parallel_rc='+str(b['rc']),
                  'serial_peak='+str(a['peak_passes']), 'parallel_peak='+str(b['peak_passes']),
                  'ordered_output_equal='+str(a['normalized_sha256']==b['normalized_sha256']), flush=True)
    (receipts/'probe-results.json').write_text(json.dumps(results, indent=2)+'\n')

if __name__ == '__main__':
    main()
