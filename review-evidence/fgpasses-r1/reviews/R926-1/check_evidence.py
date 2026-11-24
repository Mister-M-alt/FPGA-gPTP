#!/usr/bin/env python3
"""Recheck the published #111 measurements with ordered byte comparison.

Usage: check_evidence.py PUBLIC_AUTHOR_DIRECTORY OUTPUT_DIRECTORY
Input files are the unmodified public receipts under receipts/gptp/.
All simulation and image-generation lines are preserved in their original order.
"""
import hashlib
import json
from pathlib import Path
import sys

root, out = map(Path, sys.argv[1:])
out.mkdir(parents=True, exist_ok=True)
result = {'source_commit':'0e37e261d07b7fd332590bfe57ae90ddaad2dc57', 'runs':{}}
normalized = {}
for variant in ('serial','parallel'):
    source = root/'receipts'/'gptp'/variant
    lines = (source/'log').read_text().splitlines()
    # Keep generation output and all text from the simulator command onward.
    # The removed interval contains only compiler/build commands and statistics.
    start = lines.index('./obj_dir/Vengine_sim')
    kept = lines[:3] + lines[start:]
    normalized[variant] = ('\n'.join(kept)+'\n').encode()
    (out/(variant+'-public-normalized.log')).write_bytes(normalized[variant])
    t = (source/'time').read_text().split()
    wall, user, system = [float(t[k]) for k in (0,2,4)]
    result['runs'][variant] = {'wall_s':wall,'user_s':user,'system_s':system,
         'cpu_s':user+system,'exit':t[6], 'kept_lines':len(kept),
         'removed_build_lines':start-3,
         'sha256':hashlib.sha256(normalized[variant]).hexdigest(),
         'tallies':[line for line in kept if ' checks:' in line]}
result['strict_ordered_equal'] = normalized['serial']==normalized['parallel']
result['speedup'] = result['runs']['serial']['wall_s']/result['runs']['parallel']['wall_s']
result['cpu_change_percent'] = 100*(result['runs']['parallel']['cpu_s']/result['runs']['serial']['cpu_s']-1)
result['scope'] = 'Published clean real simulations; failing receipt uses a stand-in executable.'
(out/'public-evidence-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result, indent=2))
assert result['strict_ordered_equal']
