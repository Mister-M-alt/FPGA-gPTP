#!/usr/bin/env bash
# run3.sh <directory> <tcl>: one Vivado batch run of <tcl> in <directory> (a shipping route's
# baseline_integrated.tcl or a comparison's baseline_implementation.tcl); writes route.start, route.rc, route.end.
# Run inside vivado-slot.sh.
set -u
d=$1; t=$2
source <home-path>/Xilinx/2026.1/Vivado/settings64.sh
cd "$d" || exit 3
[ -e route.start ] && { echo "refusing: $d already ran (each measurement in a fresh directory)"; exit 5; }
date -Iseconds > route.start
vivado -mode batch -source "$t" -nojournal -log baseline.log > vivado.out 2>&1
echo $? > route.rc
date -Iseconds > route.end
echo "$d rc=$(cat route.rc)"
