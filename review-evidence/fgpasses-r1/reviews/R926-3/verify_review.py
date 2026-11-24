#!/usr/bin/env python3
"""Read-only review verification. Usage: verify_review.py CHECKOUT PACKET"""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

repo, packet = map(lambda p: Path(p).resolve(), sys.argv[1:])
out = packet / 'receipts'
pub = packet / 'scratch/public'
head = '0ba80c4f1a7e506a9bc727f162582bfc6212f771'
prior = '661e4c3a45904d2d8f3e061c67103a945651d9ff'
base = '1213ac5b9e09b8759ba76cc70c53652b5e108996'
def git(*args):
    return subprocess.check_output(['git', *args], cwd=repo)
def save(name, data):
    (out / name).write_text(json.dumps(data, indent=2) + '\n')

# Compare actual blob bytes and modes, not just timestamp-based status.
assert git('rev-parse', 'HEAD').decode().strip() == head
assert git('rev-parse', 'HEAD^{tree}').decode().strip() == '2d30c9a8563b133c5c14bbb9cb761b5ae6382952'
assert subprocess.run(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=repo, capture_output=True).returncode == 1
entries = []
links = []
expected_index = []
for entry in git('ls-tree', '-rz', 'HEAD').split(b'\0'):
    if not entry:
        continue
    meta, path = entry.split(b'\t', 1)
    mode, kind, oid = meta.decode().split()
    name = os.fsdecode(path)
    expected_index.append(f'{mode} {oid} 0\t{name}')
    if mode == '160000':
        links.append({'path': name, 'commit': oid})
        continue
    file = repo / name
    actual = os.readlink(file).encode() if mode == '120000' else file.read_bytes()
    assert actual == git('cat-file', 'blob', oid), name
    if mode != '120000':
        executable = bool(file.stat().st_mode & 0o111)
        assert executable == (mode == '100755'), name
    entries.append({'path': name, 'mode': mode, 'blob': oid})
assert git('ls-files', '--stage', '-z').decode().split('\0')[:-1] == expected_index
assert not links, 'This repository is expected to have zero gitlinks'
assert not git('status', '--porcelain=v1')
delta = git('diff', '--name-only', prior, head).decode().splitlines()
assert delta == ['docs/TEST_DEVELOPER.md'], delta
save('checkout.json', {'head': head, 'tree': git('rev-parse', 'HEAD^{tree}').decode().strip(),
     'detached': True, 'delta_files': delta, 'gitlinks': links, 'index_equals_tree': True,
     'tracked_bytes_and_modes': entries, 'clean_status': True})
(out / 'delta.patch').write_bytes(git('diff', prior, head))
(out / 'history.txt').write_bytes(git('log', '--format=%H %s', base + '..' + head))

# Verify selected published bytes against both the archive tree and its manifest.
manifest = {x['file']: x['published_sha256'] for x in json.loads((pub / 'MANIFEST.json').read_text())}
audited = []
for item in json.loads((pub / 'selected-tree.json').read_text()):
    raw = (pub / item['path']).read_bytes()
    sha256 = hashlib.sha256(raw).hexdigest()
    oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    assert oid == item['sha'], item['path']
    assert len(raw) == item['size'], item['path']
    if item['path'] != 'MANIFEST.json':
        assert sha256 == manifest[item['path']], item['path']
    audited.append({'path': item['path'], 'sha256': sha256, 'git_blob': oid,
                    'manifest_match': item['path'] != 'MANIFEST.json'})
save('packet-integrity.json', audited)

gptp = pub / 'author-r2/receipts/gptp'
arms = {}
for arm in sorted(gptp.iterdir()):
    if not arm.is_dir():
        continue
    counters = {r[2]: int(r[0]) for r in csv.reader((arm / 'perf').read_text().splitlines()) if len(r) > 2 and r[2] in ('instructions:u', 'cycles:u')}
    timing = (arm / 'time').read_text()
    m = re.search(r'([\d.]+) wall ([\d.]+) user ([\d.]+) sys', timing)
    wall, user, system = map(float, m.groups())
    rc = int(re.search(r'rc=(\d+)', timing)[1])
    commit = (arm / 'head').read_text().strip()
    assert commit == (base if '-base-' in arm.name else prior)
    assert rc == (2 if 'abort' in arm.name else 0)
    arms[arm.name] = dict(head=commit, wall=wall, user=user, system=system, cpu=user+system, rc=rc, **counters)
pairs = []
for a, b in [('c-base-j4', 'c-head-j4'), ('r-base-j4', 'r-head-j4'), ('r-base-j4', 'r-head-j4-b'), ('c-base-j1', 'c-head-j1'), ('c-base-abort-j4', 'c-head-abort-j4')]:
    left, right = arms[a], arms[b]
    instr = (right['instructions:u'] / left['instructions:u'] - 1) * 100
    assert instr <= 1
    pairs.append(dict(base=a, head=b, instructions_percent=instr,
        cpu_percent=(right['cpu']/left['cpu']-1)*100,
        wall_speedup=left['wall']/right['wall'], instruction_gate_pass=True))
save('measurement-audit.json', {'arms': arms, 'pairs': pairs})

# Ordered spot-check: normalize checkout include paths and compiler timing only.
def normalized_log(arm):
    text = (gptp / arm / 'log').read_text()
    text = re.sub(r'-I/data-2/milan/tmp/cicd-a839/r4/gp/[^ /]+/tb/verilator/engine', '-I<engine>', text)
    return [line for line in text.splitlines() if not line.startswith('- Verilator: Walltime')]
left = normalized_log('c-base-j4')
right = normalized_log('c-head-j4')
assert left == right
save('transcript-spotcheck.json', {'pair': ['c-base-j4', 'c-head-j4'],
     'ordered_equal': True, 'retained_lines': len(left),
     'normalization': 'checkout include path and one compiler timing-statistics line only'})
assert (gptp / 'passes_test-661e4c3.txt').read_text().count('[PASS]') == 63

# F2: verify the prior independent raw receipt, then reproduce the one behavior
# changed in the guide against both the serial oracle and current scheduler.
old = pub / 'reviews/R926-2/receipts'
assert (old / 'ignore-errors.rc').read_text().strip() == '0'
assert 'Error 1 (ignored)' in (old / 'ignore-errors.stderr').read_text()
for n in (2, 3):
    assert f'pass {n}: 12 checks: 12 PASS, 0 FAIL' in (old / 'ignore-errors.stdout').read_text()
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('pass_checks', repo / 'tb/verilator/engine/passes_test.py')
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)
probe_results = []
with tempfile.TemporaryDirectory(prefix='ignore-errors-', dir=packet / 'scratch') as tmp:
    scratch = Path(tmp)
    trees = checks.tree(scratch)
    for flags, label in [(['-j4', '-i'], 'ignore-errors'), (['-j4'], 'ordinary-failure')]:
        results = {}
        for which in ('serial', 'parallel'):
            result = checks.make(trees[which], flags, {'1': {'exit': 1}}, scratch / (which + label + '.events'))
            if which == 'parallel':
                (out / (label + '.raw.stdout')).write_text(result.stdout)
                (out / (label + '.raw.stderr')).write_text(result.stderr)
            stdout = checks.norm(result.stdout, trees[which])
            stderr = checks.norm(result.stderr, trees[which])
            results[which] = (result.returncode, stdout, stderr)
        assert results['serial'] == results['parallel']
        rc, stdout, stderr = results['parallel']
        assert rc == (0 if label == 'ignore-errors' else 2)
        for n in (2, 3):
            assert (f'pass {n}: 12 checks:' in stdout) == (label == 'ignore-errors')
        assert ('(ignored)' in stderr) == (label == 'ignore-errors')
        for ext, value in [('stdout', stdout), ('stderr', stderr), ('rc', str(rc) + '\n')]:
            (out / (label + '.' + ext)).write_text(value)
        probe_results.append({'case': label, 'rc': rc, 'serial_equal': True})
save('focused-probe.json', probe_results)
assert not git('status', '--porcelain=v1')
print(f'PASS: {len(entries)} tracked files; index, bytes, modes and zero gitlinks; documentation-only delta')
print(f'PASS: {len(audited)} archive blobs; {len(audited)-1} manifest matches')
for pair in pairs:
    print(f"{pair['base']} -> {pair['head']}: instructions {pair['instructions_percent']:+.6f}%; CPU {pair['cpu_percent']:+.6f}%; wall {pair['wall_speedup']:.6f}x")
print('PASS: ignored and ordinary failures match serial; current documentation describes both')
