#!/usr/bin/env python3
"""Split a routes receipt's base->head LUT moves into changed and untouched RTL.

Usage: r905_route_split.py ROUTES_TXT

ROUTES_TXT is the author's receipts/routes.txt (same directive, base and
head). This change edits RTL only inside the engine cell (u_engine: its
top module and its ROM image); every other cell is RTL this change does not
touch. Prints the totals per image, the engine cell's move, the 8x8 list of
largest moves, and what the untouched cells move by in total.
"""
import re
import sys

text = open(sys.argv[1], encoding="utf-8").read()
for img in ("1x1", "8x8"):
    m = re.search(rf"## {img} head - base\n(LUT \S+\s+FF \S+\s+SLICE \S+)", text)
    print(f"{img} image, head - base: {m.group(1)}")
    sec = text.split(f"### {img}\n", 1)[1].split("\n#", 1)[0]
    for line in sec.splitlines():
        if line.startswith(("u_engine ", "g_gptp_plane.u_gptp_shadow ",
                            "(g_gptp_plane.u_gptp_shadow)", "u_timer",
                            "u_txslot", "u_ucpu", "(u_engine)")):
            print(f"  {img} {' '.join(line.split()[:5])}")
moves = re.findall(r"^\s+([+-]\d+) (\S+) \((\d+) -> (\d+)\)", text, re.M)
print("8x8 largest moves (|LUT| >= 80):")
for d, cell, a, b in moves:
    print(f"  {cell:44s} {a:>6} -> {b:>6} ({d})")
edit = next(int(d) for d, c, *_ in moves if c == "u_edit")
csr = next(int(d) for d, c, *_ in moves if c == "csr")
eng = next(int(d) for d, c, *_ in moves if c == "u_engine")
top = next(int(d) for d, c, *_ in moves if c == "alinx_ax7101")
print(f"u_edit + csr = {edit:+d} {csr:+d} = {edit + csr:+d} LUT")
print(f"image {top:+d} LUT = engine cell {eng:+d} (changed RTL)"
      f" + {top - eng:+d} in cells whose RTL is unchanged")
print(f"of which u_edit + csr {edit + csr:+d}, other untouched cells"
      f" {top - eng - edit - csr:+d}")
