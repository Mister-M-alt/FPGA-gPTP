#!/usr/bin/env python3
"""norm.py LOG: print LOG with only host text removed: the verilator build command line and the
compiler/ccache/includer lines it runs (they hold this tree's absolute path and the CPU count),
make's directory chatter, and Verilator's build statistics lines. Nothing else is touched."""
import re, sys
DROP = re.compile(r'^(/\S*verilator --cc |\s*(g\+\+|ccache) |python3 \S*verilator_includer |rm \S+deplist|echo "" > '
                  r'|make\[\d+\]: (Entering|Leaving|Nothing)|- V e r i l a t i o n|- Verilator: |ar -rcs |\S*verilator_)')
for line in open(sys.argv[1], errors="replace").read().splitlines():
    if not DROP.search(line):
        print(line)
