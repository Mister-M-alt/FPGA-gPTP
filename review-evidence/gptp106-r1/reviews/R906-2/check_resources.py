#!/usr/bin/env python3
"""Independently parse the published routed reports; no build is run."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "scratch/review-evidence/gptp106-r1/author-r3/receipts/routes"
FIELDS = {"LUT": "Slice LUTs", "FF": "Slice Registers", "SLICE": "Slice", "BRAM": "Block RAM Tile", "RAMB36": "RAMB36/FIFO*", "RAMB18": "RAMB18", "DSP": "DSPs"}

def utilization(path):
    rows = {}
    for line in path.read_text().splitlines():
        if not line.startswith("|"):
            continue
        cols = [s.strip() for s in line.split("|")[1:-1]]
        if len(cols) == 6:
            try:
                rows[cols[0]] = (float(cols[1]), float(cols[4]))
            except ValueError:
                pass
    return {k: rows[v] for k, v in FIELDS.items()}

def hierarchy(path):
    rows, stack = {}, []
    for line in path.read_text().splitlines():
        cols = line.split("|")[1:-1]
        if len(cols) != 10 or not cols[2].strip().isdigit():
            continue
        name = cols[0].strip()
        depth = (len(cols[0]) - len(cols[0].lstrip()) - 1) // 2
        if name.startswith("("):
            key = "/".join(stack[:depth]) + "/@own"
        else:
            stack = stack[:depth] + [name]
            key = "/".join(stack)
        rows[key] = tuple(int(cols[i]) for i in (2, 6, 7, 8, 9))
    pieces = {k: v for k, v in rows.items() if k.endswith("/@own") or not any(j.startswith(k + "/") for j in rows)}
    totals = tuple(sum(v[i] for v in pieces.values()) for i in range(5))
    top = next(v for k, v in rows.items() if "/" not in k)
    assert totals[1:] == top[1:]
    return rows, pieces, totals[0] - top[0]

sets = {}
for shape in ("1x1", "8x8"):
    for side in ("base", "head"):
        routes = []
        for directive in ("eppo", "aslh", "eto"):
            path = BASE / f"{shape}-{side}-{directive}"
            util = utilization(path / "baseline_utilization.rpt")
            assert all(used <= available for used, available in util.values())
            sections = (path / "timing-summaries.txt").read_text().split("== ")
            corners = {}
            for section in sections:
                match = re.match(r".*_signoff_(.*?)_timing.rpt", section)
                if not match:
                    continue
                numeric = [line.split() for line in section.splitlines() if re.match(r"\s+-?\d+\.\d+\s+-?\d+\.\d+", line)]
                assert len(numeric) == 1
                row = numeric[0]
                assert all(float(row[i]) == 0 for i in (1, 2, 5, 6, 9, 10))
                corners[match[1]] = (float(row[0]), float(row[4]))
            assert set(corners) == {"Slow_0C", "Slow_85C", "Fast_0C", "Fast_85C"}
            route_text = (path / "alinx_ax7101_route_status.rpt").read_text()
            assert re.search(r"nets with routing errors\.*\s*:\s*0\s*:", route_text)
            routable = re.search(r"# of routable nets\.*\s*:\s*(\d+)", route_text)[1]
            routed = re.search(r"# of fully routed nets\.*\s*:\s*(\d+)", route_text)[1]
            assert routable == routed
            wns = min(v[0] for v in corners.values())
            whs = min(v[1] for v in corners.values())
            floor = wns >= .030 and whs >= 0
            routes.append((wns, directive, util, path, whs))
            print(f"PASS {shape} {side} {directive}: LUT {util['LUT'][0]:g}, WNS {wns:+.3f}, WHS {whs:+.3f}, floor {floor}, fit and routing clean; corners {corners}")
        picked = max(routes, key=lambda x: x[0])
        assert picked[0] >= .030 and picked[4] >= 0
        sets[shape, side] = picked
        print(f"SELECT {shape} {side} {picked[1]}")

for shape, expected in (("1x1", -322), ("8x8", 455)):
    base, head = sets[shape, "base"], sets[shape, "head"]
    change = {k: head[2][k][0] - base[2][k][0] for k in FIELDS}
    assert change["LUT"] == expected
    print(f"DELTA {shape} {change}")
    br, bp, bo = hierarchy(base[3] / "baseline_hierarchy.rpt")
    hr, hp, ho = hierarchy(head[3] / "baseline_hierarchy.rpt")
    assert set(bp) == set(hp)
    pieces_delta = sum(hp[k][0] - bp[k][0] for k in bp)
    assert pieces_delta - (ho - bo) == expected
    assert all(hp[k][2:] == bp[k][2:] for k in bp)
    print(f"PARTITION {shape}: {len(bp)} disjoint pieces, LUT change {pieces_delta:+}, shared sites {bo}->{ho}, reconciled {expected:+}; all piece RAMB/DSP unchanged")
    for suffix in ("/u_engine", "/u_edit/@own", "/csr", "/g_gptp_plane.u_gptp_shadow/@own", "/milan_datapath/@own"):
        keys = [k for k in br if k.endswith(suffix)]
        assert len(keys) == 1
        key = keys[0]
        deltas = tuple(hr[key][i] - br[key][i] for i in range(5))
        print(f"CELL {shape} {suffix}: {br[key]} -> {hr[key]}, delta {deltas}")
        if suffix == "/u_engine":
            assert deltas[0] == (-80 if shape == "1x1" else -74)
print("COMPLETE: all 12 routes, 48 corners, both qualifying images and resource partitions checked")
