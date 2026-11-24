#!/usr/bin/env python3
"""Independently grade completed raw replay receipts, without rerunning simulations."""
import json
from pathlib import Path
import re
import sys

p=Path(__file__).resolve().parent
sys.path.insert(0,str(p/'scratch/head/tb/verilator/engine'))
import mutants as m

results=[]
for tag,count in [('shipping',2296),('request-seed',2296),('sync-seed',2296),('p1-255',61)]:
    output=(p/(tag+'.log')).read_text()
    assert (p/(tag+'.rc')).read_text().strip()=='0'
    assert f'{count} checks: {count} PASS, 0 FAIL' in output
    results.append({'task':tag,'checks':count,'failures':0,'rc':0})
for i,(name,_,_,_,breaks) in enumerate(m.P109_MUTATIONS,1):
    tag=f'mutation-{i:02}'
    output=(p/(tag+'.log')).read_text()
    rc=int((p/(tag+'.rc')).read_text())
    lines=[]
    answer=m.named_verdict(m.verdict(rc,output),breaks,output,lines.append)
    assert answer=='caught',(name,answer)
    results.append({'task':tag,'name':name,'rc':rc,'verdict':answer,'witnesses':lines})
output=(p/'base-reproduction.log').read_text()
rc=int((p/'base-reproduction.rc').read_text())
tally=re.search(r'(\d+) checks: (\d+) PASS, (\d+) FAIL',output)
assert rc==1 and tally and int(tally[1])==2296
failed=[x for x in output.splitlines() if x.startswith('FAIL ')]
assert len(failed)==int(tally[3]) and len(failed)>=24
assert all(x.startswith('FAIL #109 ') for x in failed)
for label in ['D -81','D -263','latency constants over-stated by 400 ns','D -800','D -801','D -5000000','the most negative delay of the wire']:
    for suffix in ['asCapable kept','the next Follow_Up is used','the grandmaster stays elected']:
        assert any(f'#109 {label}: {suffix}' in line for line in failed)
assert not any(re.match(r'FAIL #109 D -(3|80):',line) for line in failed)
results.append({'task':'base-reproduction','rc':rc,'checks':2296,
                'passes':int(tally[2]),'failures':int(tally[3]),'fail_lines':failed})
for tag in ['docs','contract']:
    assert (p/(tag+'.rc')).read_text().strip()=='0'
    results.append({'task':tag,'rc':0})
(p/'focused-results.json').write_text(json.dumps(results,indent=2)+'\n')
print('Four clean passes: 2296, 2296, 2296, 61.')
print('Eight #109 controls caught, each through every required named witness.')
print(f'Base image with exact-head harness: {tally[1]} checks, {tally[2]} PASS, {tally[3]} FAIL; all failures belong to #109.')
print('Documentation and interface-contract checks PASS.')
