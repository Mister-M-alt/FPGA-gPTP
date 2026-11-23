#!/usr/bin/env bash
# route.sh <name> <shape>: the integrated route (synthesis, ExtraTimingOpt placement, route, signoff corners) in the
# exported gateware dir; writes route.rc, route.start, route.end. Run inside vivado-slot.sh.
set -u
B=/data-2/milan/tmp/gptp106-a831; g=$B/route-$1-$2/split/gateware
source <home-path>/Xilinx/2026.1/Vivado/settings64.sh
cd "$g" || exit 3
date -Iseconds > route.start
vivado -mode batch -source baseline_integrated.tcl -nojournal -log baseline.log > vivado.out 2>&1
echo $? > route.rc
date -Iseconds > route.end
echo "$1 $2 rc=$(cat route.rc)"
