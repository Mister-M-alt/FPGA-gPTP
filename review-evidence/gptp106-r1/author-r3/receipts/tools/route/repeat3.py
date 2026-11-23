"""repeat3.py: repeatability of the controlled comparison. (1) Each round-3 shipping route's synthesis against round
2's route of the same side and shape, from the same inputs (route-inputs.txt): both synthesis utilisation reports, row
for row. (2) Each round-3 ExtraTimingOpt comparison, placed from round 3's synthesis checkpoint, against round 2's
ExtraTimingOpt route, which synthesised and placed in one run: routed utilisation, every signoff corner, the routed
hierarchy row for row. (3) The synthesised images, base against head: the cells whose synthesised LUTs moved by 40 or
more, so the synthesis-stage difference every placement directive starts from is shown."""
import sys
from pathlib import Path

B = Path("/data-2/milan/tmp/gptp106-a831")
sys.path.insert(0, str(B / "base/syn/ooc"))
import pp_resource_gate as gate  # noqa: E402
from pp_baseline_rank import hierarchy  # noqa: E402


def rows(p: Path) -> list[str]:
    return [l for l in p.read_text(errors="replace").splitlines() if l.startswith("|") and not
            any(h in l for h in ("Date", "Command", "Host", "Tool Version"))]


print("# repeat3: repeatability of the route comparison")
print("\n## (1) synthesis, round 2 against round 3 (same inputs; synth.maxThreads 1)")
for side in ("base", "head"):
    for shape in ("1x1", "8x8"):
        a, b = B / f"route-{side}-{shape}/split/gateware", B / f"r3-{side}-{shape}/split/gateware"
        for f in ("alinx_ax7101_utilization_synth.rpt", "alinx_ax7101_utilization_hierarchical_synth.rpt"):
            ra, rb = rows(a / f), rows(b / f)
            print(f"{side} {shape} {f}: {'identical' if ra == rb else 'DIFFERENT'}, {len(rb)} table rows")
        u = gate.utilization((b / "alinx_ax7101_utilization_synth.rpt").read_text(), "ooc")
        print(f"    synthesised: LUT={u['LUT']} FF={u['FF']} RAMB36={u['RAMB36']} RAMB18={u['RAMB18']} DSP={u['DSP']}")
print("\n## (2) placement, round 3's ExtraTimingOpt comparison against round 2's ExtraTimingOpt route")
for side in ("base", "head"):
    for shape in ("1x1", "8x8"):
        a, b = B / f"route-{side}-{shape}/split/gateware", B / f"r3-{side}-{shape}-eto"
        if not (b / "route.rc").exists() or (b / "route.rc").read_text().strip() != "0":
            print(f"{side} {shape}: round 3's comparison not complete")
            continue
        ua = gate.utilization((a / "baseline_utilization.rpt").read_text(), "route")
        ub = gate.utilization((b / "baseline_utilization.rpt").read_text(), "route")
        ca = gate.corners(a, (a / "baseline_integrated.tcl").read_text(), gate.timing((a / "baseline_timing.rpt").read_text()))
        cb = gate.corners(b, (b / "baseline_implementation.tcl").read_text(), gate.timing((b / "baseline_timing.rpt").read_text()))
        ha, hb = hierarchy(a / "baseline_hierarchy.rpt"), hierarchy(b / "baseline_hierarchy.rpt")
        print(f"{side} {shape}: routed utilisation {'identical' if ua == ub else 'DIFFERENT'}; corners "
              f"{'identical' if ca == cb else 'DIFFERENT'}; hierarchy {'identical' if ha == hb else 'DIFFERENT'} "
              f"({len(hb)} rows)")
        if ua != ub or ca != cb:
            print(f"    round 2 {ua} {ca}\n    round 3 {ub} {cb}")
        if ha != hb:
            moved = sorted((k for k in set(ha) | set(hb) if ha.get(k) != hb.get(k)),
                           key=lambda k: -abs(hb.get(k, {}).get('LUT', 0) - ha.get(k, {}).get('LUT', 0)))
            for k in moved[:12]:
                print(f"    {k}: LUT {ha.get(k, {}).get('LUT')} -> {hb.get(k, {}).get('LUT')}")
print("\n## (3) the synthesised images, base against head (round 3; each directive's placement starts here)")
for shape in ("1x1", "8x8"):
    hb = hierarchy(B / f"r3-base-{shape}/split/gateware/alinx_ax7101_utilization_hierarchical_synth.rpt")
    hh = hierarchy(B / f"r3-head-{shape}/split/gateware/alinx_ax7101_utilization_hierarchical_synth.rpt")
    t = "alinx_ax7101"
    print(f"### {shape}: image LUT {hb[t]['LUT']} -> {hh[t]['LUT']} ({hh[t]['LUT'] - hb[t]['LUT']:+d}), "
          f"FF {hb[t]['FF']} -> {hh[t]['FF']} ({hh[t]['FF'] - hb[t]['FF']:+d}), RAMB36 {hh[t]['RAMB36'] - hb[t]['RAMB36']:+d}, "
          f"RAMB18 {hh[t]['RAMB18'] - hb[t]['RAMB18']:+d}, DSP {hh[t]['DSP'] - hb[t]['DSP']:+d}")
    print("Vivado's rows whose LUTs moved by 40 or more (rows nest: a cell's row includes its children's):")
    keys = sorted(set(hb) | set(hh), key=lambda k: -abs(hh.get(k, {"LUT": 0})["LUT"] - hb.get(k, {"LUT": 0})["LUT"]))
    for k in keys:
        dl = hh.get(k, {"LUT": 0})["LUT"] - hb.get(k, {"LUT": 0})["LUT"]
        if abs(dl) >= 40 and k != t:
            print(f"  {dl:+6d}  {hb.get(k, {'LUT': 0})['LUT']:>6} -> {hh.get(k, {'LUT': 0})['LUT']:<6} {k.replace('/@own', ' (own)')}")
