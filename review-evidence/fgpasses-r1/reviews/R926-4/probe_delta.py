#!/usr/bin/env python3
"""Focused fault controls; no edits to the reviewed checkout."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile

repo = Path(sys.argv[1]).resolve()
packet = Path(__file__).resolve().parent
root = Path(tempfile.mkdtemp(prefix='delta-probes-', dir=packet / 'scratch'))
source = (repo / 'tb/verilator/engine/pass_run.py').read_text()

def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def fixture(name, code):
    directory = root / name
    directory.mkdir()
    for filename in ('Makefile', 'passes_test.py'):
        shutil.copy(repo / 'tb/verilator/engine' / filename, directory)
    (directory / 'pass_run.py').write_text(code)
    return directory

def plan_test(name, code, kind):
    directory = fixture(name, code)
    module = load(directory / 'passes_test.py', name)
    work = directory / 'work'
    work.mkdir()
    trees = module.tree(work)
    if kind == 'gen':
        module.PLANS = {'pass 1 image generator SIGSEGV': {'gensig': 'seedrun'}}
        bad = module.transcripts(trees, work)
    else:
        bad = module.replay_cwd(trees, work)
    print(json.dumps({'probe': name, 'failures': int(bad)}), flush=True)
    return int(bad)

def race_test(name, code, kind):
    directory = fixture(name, code)
    state = directory / 'obj_dir/engine-passes'
    state.mkdir(parents=True)
    (state / 'build.ok').touch()
    child = directory / 'child.py'
    child.write_text('import os, signal, time\nfrom pathlib import Path\n'
                     'def stop(s, f):\n Path("outcome").write_text("signal")\n os._exit(0)\n'
                     'signal.signal(signal.SIGTERM, stop)\nPath("ready").touch()\n'
                     'time.sleep(0.5)\nPath("outcome").write_text("natural")\n')
    runner = '''import importlib.util, os, signal, subprocess, sys, time
from pathlib import Path
s = importlib.util.spec_from_file_location('runner', 'pass_run.py')
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
'''
    if kind == 'gap':
        runner += '''original = subprocess.Popen
def gap(*args, **kwargs):
    p = original(*args, **kwargs)
    deadline = time.monotonic() + 5
    while not Path('ready').exists():
        if time.monotonic() > deadline: raise RuntimeError('child not ready')
        time.sleep(0.001)
    os.kill(os.getpid(), signal.SIGTERM)
    return p
m.subprocess.Popen = gap
m.run(0, None, None, [sys.executable, 'child.py'], False)
'''
    else:
        runner += '''m.run(1, None, None, ['/bin/true'], False)
Path('obj_dir/engine-passes/0.stop').touch()
disposition = signal.getsignal(signal.SIGUSR1)
print('SIGUSR1 ignored after run:', disposition == signal.SIG_IGN, flush=True)
# Model interpreter teardown: custom handlers reset; ignored dispositions survive.
if callable(disposition): signal.signal(signal.SIGUSR1, signal.SIG_DFL)
os.kill(os.getpid(), signal.SIGUSR1)
print('late stop survived', flush=True)
'''
    result = subprocess.run([sys.executable, '-c', runner], cwd=directory, capture_output=True, text=True, timeout=10)
    outcome = (directory / 'outcome').read_text() if (directory / 'outcome').exists() else None
    print(json.dumps({'probe': name, 'rc': result.returncode, 'outcome': outcome,
                      'stdout': result.stdout, 'stderr': result.stderr}), flush=True)
    return result.returncode, outcome

if __name__ == '__main__':
    old_gen = source.replace('generate + " >/dev/null"', 'generate').replace(
        'done.returncode if done.returncode >= 0 else 128 - done.returncode', 'done.returncode')
    no_cwd = '\n'.join(line for line in source.split('\n') if 'os.chdir(STATE)' not in line)
    no_gap = source.replace('            if received:\n                signal_all(child[0].pid, received[0])  # a signal that came before the child was known\n', '')
    no_ignore = source.replace('    signal.signal(signal.SIGUSR1, signal.SIG_IGN)\n', '')
    # These runs are small; each make invocation is bounded at four slots.
    assert plan_test('generator-head', source, 'gen') == 0
    assert plan_test('generator-plant', old_gen, 'gen') == 5
    assert plan_test('cwd-head', source, 'cwd') == 0
    assert plan_test('cwd-plant', no_cwd, 'cwd') == 1
    assert race_test('gap-head', source, 'gap') == (-signal.SIGTERM, 'signal')
    assert race_test('gap-plant', no_gap, 'gap') == (-signal.SIGTERM, 'natural')
    assert race_test('finished-head', source, 'finished')[0] == 0
    assert race_test('finished-plant', no_ignore, 'finished')[0] == -signal.SIGUSR1
    print('focused delta probes: PASS', flush=True)
