"""routes3.py: round 3's controlled base/head route comparison (#818 route sets), read with the parent's own
resource-gate parsers (syn/ooc/pp_resource_gate.py: utilization(), timing(), corners(), routing(), best();
pp_baseline_rank.hierarchy()).

For each shape and side: the shipping route at ExtraPostPlacementOpt (r3-<side>-<shape>/split/gateware) and its two
comparisons opened from its synthesis checkpoint (r3-<side>-<shape>-aslh, -eto). Each route's routed utilisation
(baseline_utilization.rpt, the figures the gate records) and placed utilisation, worst-corner WNS/WHS and every signoff
corner, route status; the floors of the route-1x1 baseline endpoint; the route best() selects; whether it meets the
floors at every corner. Then per shape the selected (qualifying) head against the selected base: totals, and the routed
hierarchy as a partition of disjoint pieces (every leaf cell and the own logic of every cell with children), so the
pieces' changes sum exactly to the total change and no nested cell is counted twice."""
import json
import sys
from pathlib import Path

B = Path("/data-2/milan/tmp/gptp106-a831")
sys.path.insert(0, str(B / "base/syn/ooc"))
import pp_resource_gate as gate  # noqa: E402
from pp_baseline_rank import hierarchy  # noqa: E402

FIG = ("LUT", "FF", "SLICE", "BRAM_TILE", "RAMB36", "RAMB18", "DSP")
SHORT = {"ExtraPostPlacementOpt": "EPPO", "AltSpreadLogic_high": "ASLH", "ExtraTimingOpt": "ETO"}
policy = json.loads((B / "base/syn/ooc/pp_resource_baseline.json").read_text())["endpoints"]["route-1x1"]
floor = policy["floor"]


def route(d: Path, script: str) -> dict:
    own = (d / script).read_text()
    routed = gate.utilization((d / "baseline_utilization.rpt").read_text(), "route")
    placed = gate.utilization((d / "alinx_ax7101_utilization_place.rpt").read_text(), "route")
    summary = gate.timing((d / "baseline_timing.rpt").read_text())
    corners = gate.corners(d, own, summary)
    problems = gate.routing(d, "route")
    directive = gate.PLACE.search(own)[1]
    ok = not problems and all(c["WNS_ns"] >= floor["WNS_ns"] and c["WHS_ns"] >= floor["WHS_ns"]
                              for c in corners.values())
    return {"dir": d, "directive": directive, "routed": routed, "placed": placed, "summary": summary,
            "corners": corners, "problems": problems, "floor_ok": ok,
            "record": {"figures": {"WNS_ns": summary["WNS_ns"]}}}


def partition(rows: dict) -> tuple[dict, dict]:
    """Disjoint pieces as Vivado reports them: every leaf cell's row and every parent's parenthesised own row (a parent
    without one has no logic of its own), and the overlap: what the pieces count beyond the image. FF, RAMB and DSP
    pieces sum exactly; a physical LUT holding LUTs of two cells is counted in each, so the LUT overlap is the shared
    LUT sites, and the image's LUTs are the pieces' less the overlap."""
    names = [k for k in rows if not k.endswith("/@own")]
    out = {}
    for k in names:
        kids = [c for c in names if c.startswith(k + "/") and c.count("/") == k.count("/") + 1]
        if not kids:
            out[k] = rows[k]
        elif k + "/@own" in rows:
            out[k + " (own)"] = rows[k + "/@own"]
    top = rows[[k for k in names if "/" not in k][0]]
    overlap = {f: sum(v[f] for v in out.values()) - top[f] for f in top}
    assert all(overlap[f] == 0 for f in ("FF", "RAMB36", "RAMB18", "DSP")), overlap
    return out, overlap


def fmt(x: float) -> str:
    return f"{x:g}" if isinstance(x, float) else f"{x}"


sets = {}
for shape in ("1x1", "8x8"):
    for side in ("base", "head"):
        s = B / f"r3-{side}-{shape}"
        rs = [route(s / "split/gateware", "baseline_integrated.tcl")]
        for tag, directive in (("aslh", "AltSpreadLogic_high"), ("eto", "ExtraTimingOpt")):
            c = B / f"r3-{side}-{shape}-{tag}"
            assert gate.bound(c.resolve(), (s / "split/gateware").resolve(),
                              (s / "split/gateware/baseline_integrated.tcl").read_text())
            rs.append(route(c, "baseline_implementation.tcl"))
        assert sorted(r["directive"] for r in rs) == sorted(gate.DIRECTIVES)
        sets[shape, side] = rs

print("# routes3: the #818 route sets, base 1616fc8f and head, both shapes")
print(f"floors (pp_resource_baseline.json route-1x1): WNS >= {floor['WNS_ns']:+.3f} ns, WHS >= {floor['WHS_ns']:+.3f} ns"
      " at every signoff corner")
print("figures: routed = baseline_utilization.rpt (the gate's record); placed = alinx_ax7101_utilization_place.rpt")
picked = {}
for (shape, side), rs in sets.items():
    print(f"\n## {shape} {side}")
    for r in rs:
        c = r["corners"]
        cs = "  ".join(f"{k} {v['WNS_ns']:+.3f}/{v['WHS_ns']:+.3f}" for k, v in c.items())
        print(f"{SHORT[r['directive']]:<5} {r['directive']:<22} {cs}  route status {'clean' if not r['problems'] else r['problems']}"
              f"  floors {'met' if r['floor_ok'] else 'NOT met'}")
        print("      routed " + " ".join(f"{f}={fmt(r['routed'][f])}" for f in FIG)
              + "   placed " + " ".join(f"{f}={fmt(r['placed'][f])}" for f in FIG))
    best = gate.best(rs)
    meeting = [r for r in rs if r["floor_ok"]]
    best_meeting = gate.best(meeting) if meeting else None
    print(f"best() selects {best['directive']} (worst-corner WNS {best['summary']['WNS_ns']:+.3f} ns); "
          f"it {'meets' if best['floor_ok'] else 'does NOT meet'} the floors at every corner")
    if best_meeting is not best:
        print(f"  best of the routes meeting the floors: {best_meeting['directive'] if best_meeting else 'none'}")
    picked[shape, side] = best if best["floor_ok"] else best_meeting

print("\n# qualifying head against qualifying base")
for shape in ("1x1", "8x8"):
    b, h = picked[shape, "base"], picked[shape, "head"]
    print(f"\n## {shape}: base {b['directive']}, head {h['directive']}")
    for kind in ("routed", "placed"):
        print(f"{kind}: " + "  ".join(f"{f} {fmt(b[kind][f])} -> {fmt(h[kind][f])} ({h[kind][f] - b[kind][f]:+g})" for f in FIG))
    grow = [f for f in ("LUT", "FF", "BRAM_TILE", "RAMB36", "RAMB18") if h["routed"][f] > b["routed"][f]]
    print("rule (LUT/FF/BRAM of the qualifying head <= the qualifying base's, routed): "
          + ("MET" if not grow else "NOT MET: " + ", ".join(f"{f} {h['routed'][f] - b['routed'][f]:+g}" for f in grow)))
    for r in sets[shape, "head"]:
        g = [f for f in ("LUT", "FF", "BRAM_TILE", "RAMB36", "RAMB18") if r["routed"][f] > b["routed"][f]]
        print(f"  head {SHORT[r['directive']]:<5} floors {'met' if r['floor_ok'] else 'NOT met'}; against the qualifying base: "
              + ("no growth" if not g else ", ".join(f"{f} {r['routed'][f] - b['routed'][f]:+g}" for f in g)))
    pb, ob = partition(hierarchy(b["dir"] / "baseline_hierarchy.rpt"))
    ph, oh = partition(hierarchy(h["dir"] / "baseline_hierarchy.rpt"))
    keys = sorted(set(pb) | set(ph))
    zero = {f: 0 for f in next(iter(pb.values()))}
    d = {k: {f: ph.get(k, zero)[f] - pb.get(k, zero)[f] for f in zero} for k in keys}
    total = {f: sum(v[f] for v in d.values()) for f in zero}
    print(f"routed hierarchy (baseline_hierarchy.rpt) as {len(keys)} disjoint pieces (base {len(pb)}, head {len(ph)}): "
          f"every leaf cell and every parent's own row")
    print(f"  FF, RAMB36, RAMB18 and DSP pieces sum exactly to the image; LUT pieces count a LUT site shared by two "
          f"cells in each: shared sites base {ob['LUT']}, head {oh['LUT']}")
    print(f"  pieces' changes: LUT {total['LUT']:+d}, less the shared sites' change {oh['LUT'] - ob['LUT']:+d}, "
          f"= the image's {total['LUT'] - (oh['LUT'] - ob['LUT']):+d}; FF {total['FF']:+d}, RAMB36 {total['RAMB36']:+d}, "
          f"RAMB18 {total['RAMB18']:+d}, DSP {total['DSP']:+d}")
    big = sorted((k for k in keys if abs(d[k]["LUT"]) >= 40), key=lambda k: -abs(d[k]["LUT"]))
    rest = {f: sum(d[k][f] for k in keys if k not in big) for f in zero}
    print("pieces whose LUTs moved by 40 or more (base -> head LUT; FF change):")
    for k in big:
        print(f"  {d[k]['LUT']:+6d}  {pb.get(k, zero)['LUT']:>6} -> {ph.get(k, zero)['LUT']:<6} FF {d[k]['FF']:+5d}  {k}")
    print(f"  {rest['LUT']:+6d}  every other piece ({len(keys) - len(big)}), FF {rest['FF']:+d}")
    print(f"  {-(oh['LUT'] - ob['LUT']):+6d}  less the shared LUT sites' change ({ob['LUT']} -> {oh['LUT']})")
    rows_b = hierarchy(b["dir"] / "baseline_hierarchy.rpt")
    rows_h = hierarchy(h["dir"] / "baseline_hierarchy.rpt")
    plane = "alinx_ax7101/milan_datapath/g_gptp_plane.u_gptp_shadow"
    for label, cell in (("the gPTP plane", plane),
                        ("  its engine, the only cell whose RTL or microcode image this change touches", plane + "/u_engine")):
        ks = [k for k in keys if k == cell or k.startswith(cell + "/") or k == cell + " (own)"]
        rb, rh = rows_b[cell], rows_h[cell]
        print(f"{label} ({cell.split('/')[-1]}), Vivado's row: LUT {rb['LUT']} -> {rh['LUT']} ({rh['LUT'] - rb['LUT']:+d}), "
              f"FF {rh['FF'] - rb['FF']:+d}, RAMB36 {rh['RAMB36'] - rb['RAMB36']:+d}, RAMB18 {rh['RAMB18'] - rb['RAMB18']:+d}, "
              f"DSP {rh['DSP'] - rb['DSP']:+d}; the sum of its {len(ks)} pieces: LUT {sum(d[k]['LUT'] for k in ks):+d}")
    outside = [k for k in keys if not (k.startswith(plane + "/") or k == plane + " (own)")]
    print(f"every piece outside the gPTP plane: LUT {sum(d[k]['LUT'] for k in outside):+d}, "
          f"FF {sum(d[k]['FF'] for k in outside):+d}")
    print("depth 1, Vivado's rows (each top-level cell with everything inside it; nested rows are not added):")
    firsts = sorted({k for k in set(rows_b) | set(rows_h) if k.count("/") == 1})
    for k in firsts:
        lb, lh = rows_b.get(k, zero)["LUT"], rows_h.get(k, zero)["LUT"]
        fb, fh = rows_b.get(k, zero)["FF"], rows_h.get(k, zero)["FF"]
        if lb != lh or fb != fh:
            print(f"  LUT {lh - lb:+6d} ({lb} -> {lh})  FF {fh - fb:+5d}  {k.replace('/@own', ' (own)')}")
