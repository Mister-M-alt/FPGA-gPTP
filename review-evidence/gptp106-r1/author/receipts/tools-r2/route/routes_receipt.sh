#!/bin/bash
# routes_receipt.sh: signoff per corner and placed utilization for head and base at 1x1/1if and 8x8/1if, and the deltas
B=/data-2/milan/tmp/gptp106-a831
echo "# routes: AX7101 split image (the shipping default since #960), one interface, ExtraTimingOpt placement (the route-1x1 record's selected directive), integrated flow (synthesis AreaOptimized_high, opt ExploreArea, single-thread synthesis), Vivado 2026.1, xc7a100t-fgg484-2"
echo "base = parent 854bd72367 (gptp-processor 1616fc8f); head = parent 2cf4b61406 (854bd72367 with gptp-processor a728cc3)"
for s in 1x1 8x8; do for n in head base; do g=$B/route-$n-$s/split/gateware
  echo; echo "## $s $n: route rc=$(cat $g/route.rc 2>/dev/null) ($(cat $g/route.start 2>/dev/null) .. $(cat $g/route.end 2>/dev/null))"
  grep -h "gptp ucode image\|^head " $B/prep-$n-$s.log | cut -c1-160
  python3 -I $B/tools/signoff.py $g 2>&1 | grep -v "ruling floors"
  grep -E "routing errors|fully routed" $g/alinx_ax7101_route_status.rpt 2>/dev/null | sed 's/  */ /g'
  $B/tools/util.sh $g
done
  echo; echo "## $s head - base"
  python3 - "$B/tools/util.sh" "$B/route-head-$s/split/gateware" "$B/route-base-$s/split/gateware" <<'PY'
import subprocess, sys
def u(g):
    out = subprocess.run([sys.argv[1], g], capture_output=True, text=True).stdout.split()
    return {k: float(v) for k, v in (x.split("=") for x in out) if v}
h, b = u(sys.argv[2]), u(sys.argv[3])
print("  ".join(f"{k} {h[k]-b[k]:+g}" for k in h if k in b))
PY
done
