#!/usr/bin/env python3
"""Replay the focused source-head review without modifying the source checkout.

Usage: python3 run_focused.py /path/to/exact-head-clone --jobs 8
All disposable files stay in scratch/ beside this script. No full bank runs.
"""
import argparse
import concurrent.futures
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time

HEAD = '8e4889bba462d14d4e5a34068769872510d4775d'
BASE = '1213ac5b9e09b8759ba76cc70c53652b5e108996'
PACKET = Path(__file__).resolve().parent
SCRATCH = PACKET / 'scratch'
PIN = '$VALIDATION_TOOLS/pinned-verilator-5.050/verilator'

def capture(args, cwd=None):
    return subprocess.check_output(['rtk', 'proxy', *map(str, args)], cwd=cwd)

def logged(name, args, cwd):
    start = time.monotonic()
    with (PACKET / (name + '.log')).open('w') as out:
        out.write('command: ' + ' '.join(map(str, args)) + '\n')
        out.flush()
        rc = subprocess.run(['rtk', 'proxy', *map(str, args)], cwd=cwd,
                            stdout=out, stderr=subprocess.STDOUT).returncode
    (PACKET / (name + '.rc')).write_text(str(rc) + '\n')
    print(f'{name}: rc={rc}, elapsed={time.monotonic()-start:.1f}s', flush=True)
    return rc

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('repo', type=Path)
    ap.add_argument('--jobs', type=int, default=8)
    ap.add_argument('--simulator', default=PIN,
                    help='Path to the required 5.050 simulator')
    args = ap.parse_args()
    assert 1 <= args.jobs <= 16
    repo = args.repo.resolve()
    assert capture(['git', 'rev-parse', 'HEAD'], repo).decode().strip() == HEAD
    SCRATCH.mkdir(exist_ok=True)
    os.environ['TMPDIR'] = str(SCRATCH)
    os.environ['OBJCACHE'] = ''
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    ident = capture([args.simulator, '--version']).decode()
    assert 'Verilator 5.050' in ident
    (PACKET / 'simulator-identity.txt').write_text(ident)
    tree = SCRATCH / 'head'
    tree.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(capture(['git', 'archive', HEAD], repo))) as archive:
        archive.extractall(tree, filter='data')
    engine = tree / 'tb/verilator/engine'
    sys.path.insert(0, str(engine))
    m = importlib.import_module('mutants')
    flags = m.VFLAGS.copy()
    flags.remove('--build')
    at = flags.index('-j')
    del flags[at:at+2]
    obj = SCRATCH / 'obj'
    assert logged('compile-generate', [args.simulator, *flags, '--Mdir', obj,
        '-CFLAGS', f'-std=c++17 -O2 -I{engine} -Wall -Wextra',
        *m.RTL_SOURCES, engine / 'sim_main.cpp', '-o', 'Vreview'], tree/'hdl') == 0
    assert logged('compile', ['make', '-j16', '-C', obj, '-f', 'VKL_gptp_engine.mk'], tree) == 0
    exe = obj / 'Vreview'
    tasks = []
    for tag, extras, plus in [
        ('shipping', [], []),
        ('request-seed', ['--seq-seed','0x200000'], []),
        ('sync-seed', ['--sync-seq-seed','0x10000'], []),
        ('p1-255', list(m.P1_GENARGS), [m.P1_PLUSARG]),
        ('base-reproduction', [], []),
    ]:
        run = SCRATCH / tag
        run.mkdir(exist_ok=True)
        gen = tree/'hdl'/m.GENERATOR
        if tag == 'base-reproduction':
            gen = run / 'base-generator.py'
            gen.write_bytes(capture(['git','show',BASE+':hdl/ucode/gen_gptp_ucode.py'], repo))
        assert logged('generate-'+tag, [sys.executable, gen, *m.GENARGS, *extras,
            '-o', run/'gptp_ucode.hex'], run) == 0
        tasks.append((tag, [exe,*plus], run, None))
    for i, mutation in enumerate(m.P109_MUTATIONS, 1):
        name, fname, pattern, replacement, breaks = mutation
        own = SCRATCH / f'mutation-{i:02}'
        own.mkdir(exist_ok=True)
        src = (tree/'hdl'/fname).read_text()
        for pat, repl in m.edits_of(pattern, replacement):
            assert src.count(pat) == 1
            src = src.replace(pat, repl)
        gen = own / 'generator.py'
        gen.write_text(src)
        assert logged(f'generate-mutation-{i:02}', [sys.executable,gen,*m.GENARGS,
            '-o',own/'gptp_ucode.hex'], own) == 0
        tasks.append((f'mutation-{i:02}', [exe], own, (name, breaks)))
    tasks += [('docs', ['make','-j16','docs'],tree,None),
              ('contract',['make','-j16','contract'],tree,None)]
    def task(spec):
        tag, command, cwd, mutation = spec
        rc = logged(tag,command,cwd)
        output = (PACKET/(tag+'.log')).read_text()
        if mutation:
            name, breaks = mutation
            lines = []
            result = m.named_verdict(m.verdict(rc,output),breaks,output,lines.append)
            assert result == 'caught', (name,result)
            return {'task':tag,'name':name,'rc':rc,'verdict':result,'witnesses':lines}
        if tag == 'base-reproduction':
            # The published historical reproduction had 24 failures with
            # background offset zero. The committed harness uses 11 ns,
            # adding seven exact-offset witnesses when a pair is refused.
            assert rc != 0 and '2296 checks: 2265 PASS, 31 FAIL' in output
        else:
            assert rc == 0, (tag,rc)
        return {'task':tag,'rc':rc,'verdict':'expected result'}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(task,tasks))
    (PACKET/'focused-results.json').write_text(json.dumps(results,indent=2)+'\n')
    print('Focused campaign PASS: four source passes, base reproduction, eight controls, docs and contract.',flush=True)

if __name__ == '__main__':
    main()
