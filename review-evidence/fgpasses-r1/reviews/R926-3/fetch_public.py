#!/usr/bin/env python3
"""Populate disposable published-evidence inputs. Usage: fetch_public.py PACKET"""
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

packet = Path(sys.argv[1]).resolve()
selected = (packet / 'receipts/selected-tree.json').read_bytes()
destination = packet / 'scratch/public'
destination.mkdir(parents=True, exist_ok=True)
(destination / 'selected-tree.json').write_bytes(selected)
prefix = ('https://raw.githubusercontent.com/Mister-M-alt/FPGA-gPTP/'
          '4fb9a5ee3369635112520f1f9db91393003b39b8/review-evidence/fgpasses-r1/')
for item in json.loads(selected):
    target = destination / item['path']
    if target.exists():
        data = target.read_bytes()
    else:
        with urllib.request.urlopen(prefix + item['path'], timeout=60) as response:
            data = response.read()
    digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
    assert digest == item['sha'] and len(data) == item['size'], item['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
print('PASS: selected published blobs downloaded and matched to the pinned archive tree')
