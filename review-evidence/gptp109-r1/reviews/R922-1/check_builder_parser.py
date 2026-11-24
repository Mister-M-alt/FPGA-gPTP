#!/usr/bin/env python3
"""Execute only the parent's public constant parsers on base and reviewed sources."""
from pathlib import Path
import re
import subprocess
import sys

packet=Path(__file__).resolve().parent
repo=Path(sys.argv[1]).resolve()
ns={'re':re,'ConfigError':ValueError,'_GPTP_ENGINE_PINS_CACHE':{}}
exec(compile((packet/'builder-parser-functions.py').read_text(),
             'builder-parser-functions.py','exec'),ns)
values=[]
for sha in ['1213ac5b9e09b8759ba76cc70c53652b5e108996',
            '8e4889bba462d14d4e5a34068769872510d4775d']:
    source=subprocess.check_output(['rtk','proxy','git','show',
        sha+':hdl/ucode/gen_gptp_ucode.py'],cwd=repo,text=True)
    value=(ns['gptp_engine_port_number'](source),ns['gptp_engine_pins'](source))
    values.append(value)
    print(sha,value)
assert values[0]==values[1]
print('PASS: retiring NPD_LO_C leaves the parent parsed dataset unchanged. Focused function execution only; no builder bank.')
