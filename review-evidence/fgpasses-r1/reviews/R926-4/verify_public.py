#!/usr/bin/env python3
"""Recheck public receipt hashes; downloaded inputs remain unpublished scratch."""
import hashlib
import json
from pathlib import Path
import urllib.request

packet = Path(__file__).resolve().parent
commit = '0e29af3b936ba1f7e36cd4dfdb0501adc2bf50f2'
prefix = f'https://raw.githubusercontent.com/Mister-M-alt/FPGA-gPTP/{commit}/review-evidence/fgpasses-r1/'
for row in json.loads((packet / 'public-manifest-selected.json').read_text()):
    with urllib.request.urlopen(prefix + row['file'], timeout=60) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    assert digest == row['published_sha256'], row['file']
    print('PASS', row['file'], digest)
