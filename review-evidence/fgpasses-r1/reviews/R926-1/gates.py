#!/usr/bin/env python3
"""Run focused review gates, joined in the foreground; never run full banks.

Usage: gates.py CHECKOUT PACKET PINNED_SIMULATOR
"""
import concurrent.futures
import os
from pathlib import Path
import subprocess
import sys

root, packet, simulator = map(lambda s:Path(s).resolve(), sys.argv[1:])
out = packet/'receipts'
out.mkdir(exist_ok=True)
env = os.environ.copy()
env['PATH'] = str(simulator.parent)+os.pathsep+env['PATH']
env['PYTHONDONTWRITEBYTECODE']='1'
env['LC_ALL']='C'
for name in ('MAKEFLAGS','MFLAGS','MAKELEVEL','GNUMAKEFLAGS'):
    env.pop(name, None)
identity = subprocess.run([str(simulator),'--version'],stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT,env=env,check=True)
assert b'5.050' in identity.stdout
(out/'simulator-identity.log').write_bytes(identity.stdout)
def gate(name, cmd):
    result = subprocess.run(cmd,cwd=root,env=env,stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,timeout=300)
    log = result.stdout.replace(str(root).encode(),b'<CHECKOUT>')
    (out/(name+'.log')).write_bytes(log)
    (out/(name+'.rc')).write_text(str(result.returncode)+'\n')
    return name, result.returncode
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    pending = [pool.submit(gate,'focused-gates',['make','-j16','docs','contract','lint']),
               pool.submit(gate,'mutation-order',['make','-j16','--no-print-directory','-C',
                           'tb/verilator/engine','mutants-order-test'])]
    results = [f.result() for f in pending]
for name,code in results:
    print(name, 'rc='+str(code))
assert all(code==0 for _,code in results)
