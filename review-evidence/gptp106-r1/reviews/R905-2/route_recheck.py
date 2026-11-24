"""Independent re-read of the published #818 route reports (author-r3 receipts).

Usage: python3 -I route_recheck.py <receipts/routes dir>
Prints, per route: image LUT/FF/slices/BRAM tiles/DSP (baseline_utilization.rpt),
WNS/WHS and failing endpoints at each signoff corner, routing errors, the
best() pick per side/shape under WNS >= +0.030 and WHS >= 0 at every corner,
and for each shape the qualifying head vs base hierarchy split into disjoint
pieces (leaf rows and "(own)" rows) of baseline_hierarchy.rpt.
"""
import re, sys, pathlib
R = pathlib.Path(sys.argv[1])
FLOOR_WNS, FLOOR_WHS = 0.030, 0.0

def util(p):
    t = p.read_text()
    def g(label):
        m = re.search(r"^\|\s*" + re.escape(label) + r"\s*\|\s*([\d.]+)\s*\|", t, re.M)
        return float(m.group(1))
    return dict(LUT=g("Slice LUTs"), FF=g("Slice Registers"), SLICE=g("Slice"),
                BRAM=g("Block RAM Tile"), DSP=g("DSPs"))

def timing(p):
    out = {}
    for blk in p.read_text().split("== ")[1:]:
        name = blk.splitlines()[0].strip()
        m = re.search(r"-------\s*\n\s*([-\d.]+)\s+([-\d.]+)\s+(\d+)\s+\d+\s+([-\d.]+)\s+([-\d.]+)\s+(\d+)", blk)
        out[name] = (float(m.group(1)), float(m.group(4)), int(m.group(3)), int(m.group(6)))
    return out

def hier(p):
    rows, stack = {}, []
    for line in p.read_text().splitlines():
        if not line.startswith("|   ") and not line.startswith("| alinx"):
            continue
        cells = line.split("|")
        inst = cells[1]
        depth = (len(inst) - len(inst.lstrip(" ")) - 1) // 2
        name = inst.strip()
        nums = [c.strip() for c in cells[3:11]]
        try:
            lut, ff = int(nums[0]), int(nums[4])
        except ValueError:
            continue
        stack[depth:] = [name]
        rows["/".join(stack)] = (lut, ff, depth)
    # disjoint pieces: rows with no child rows
    paths = list(rows)
    pieces = {}
    for i, q in enumerate(paths):
        has_child = any(r.startswith(q + "/") for r in paths)
        if not has_child:
            pieces[q] = rows[q][:2]
    return rows, pieces

res = {}
for d in sorted(R.iterdir()):
    if d.name == "prep":
        continue
    u = util(d / "baseline_utilization.rpt")
    tm = timing(d / "timing-summaries.txt")
    corners = {k: v for k, v in tm.items() if "signoff" in k}
    rs = (d / "alinx_ax7101_route_status.rpt").read_text()
    rerr = int(re.search(r"routing errors\.*\s*:\s*(\d+)", rs).group(1))
    wns = min(v[0] for v in corners.values()); whs = min(v[1] for v in corners.values())
    fail = sum(v[2] + v[3] for v in corners.values())
    ok = wns >= FLOOR_WNS and whs >= FLOOR_WHS and fail == 0 and rerr == 0
    res[d.name] = (u, wns, whs, ok, d)
    print(f"{d.name:14s} LUT {u['LUT']:.0f} FF {u['FF']:.0f} SLICE {u['SLICE']:.0f} BRAM {u['BRAM']} DSP {u['DSP']:.0f} "
          f"worst WNS {wns:+.3f} WHS {whs:+.3f} corners={len(corners)} failing={fail} route_err={rerr} floors={'met' if ok else 'NOT met'}")
for shape in ("1x1", "8x8"):
    best = {}
    for side in ("base", "head"):
        c = [(v[1], k) for k, v in res.items() if k.startswith(f"{shape}-{side}-") and v[3]]
        best[side] = max(c)[1]
    b, h = res[best["base"]], res[best["head"]]
    print(f"\n{shape}: best base {best['base']} best head {best['head']}: " +
          " ".join(f"{k} {h[0][k]-b[0][k]:+g}" for k in ("LUT", "FF", "SLICE", "BRAM", "DSP")))
    for k, v in res.items():
        if k.startswith(f"{shape}-head-"):
            print(f"   {k} vs qualifying base: LUT {v[0]['LUT']-b[0]['LUT']:+.0f}")
    rb, pb = hier(b[4] / "baseline_hierarchy.rpt"); rh, ph = hier(h[4] / "baseline_hierarchy.rpt")
    assert set(pb) == set(ph), "piece sets differ"
    dl = {q: ph[q][0] - pb[q][0] for q in pb}; df = {q: ph[q][1] - pb[q][1] for q in pb}
    top_b, top_h = rb["alinx_ax7101"], rh["alinx_ax7101"]
    print(f"   pieces {len(pb)}; sum LUT change {sum(dl.values()):+d} (image {top_h[0]-top_b[0]:+d}); sum FF change {sum(df.values()):+d} (image {top_h[1]-top_b[1]:+d})")
    for q in sorted(pb, key=lambda q: -abs(dl[q]))[:8]:
        print(f"   LUT {dl[q]:+6d} FF {df[q]:+4d}  {q}")
    ffm = [q for q in pb if df[q] != 0]
    print(f"   FF moves in {len(ffm)} pieces; largest:", sorted(((df[q], q) for q in ffm), key=lambda x: abs(x[0]))[-1])
    for key in [k for k in rb if k.endswith("/u_engine")]:
        print(f"   engine row {key}: LUT {rh[key][0]-rb[key][0]:+d} FF {rh[key][1]-rb[key][1]:+d}")
