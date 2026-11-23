#!/usr/bin/env bash
# chain3.sh <side> <shape> [full]: one side's routes of one shape, one Vivado run at a time through vivado-slot.sh:
# with "full", the shipping route (ExtraPostPlacementOpt) first; then the AltSpreadLogic_high and ExtraTimingOpt
# comparisons, each written by comp3.py from the shipping route's script and synthesis checkpoint.
set -u
B=/data-2/milan/tmp/gptp106-a831; n=$1; s=$2; SLOT=<home-path>/milan-fpga-management/2026-09-23/vivado-slot.sh
G=$B/r3-$n-$s/split/gateware
if [ "${3:-}" = full ]; then
  $SLOT $B/tools3/run3.sh $G baseline_integrated.tcl > $B/r3-$n-$s/slot.log 2>&1
  echo "$n $s EPPO rc=$(cat $G/route.rc 2>/dev/null) $(cat $G/route.start) .. $(cat $G/route.end 2>/dev/null)"
fi
[ "$(cat $G/route.rc 2>/dev/null)" = 0 ] || { echo "$n $s: the shipping route did not complete"; exit 1; }
for tag in aslh eto; do
  case $tag in aslh) d=AltSpreadLogic_high;; eto) d=ExtraTimingOpt;; esac
  C=$B/r3-$n-$s-$tag
  (cd $B/tmp && python3 -I $B/tools3/comp3.py $G $d $C) || exit 2
  $SLOT $B/tools3/run3.sh $C baseline_implementation.tcl > $C.slot.log 2>&1
  echo "$n $s $tag rc=$(cat $C/route.rc 2>/dev/null) $(cat $C/route.start) .. $(cat $C/route.end 2>/dev/null)"
done
