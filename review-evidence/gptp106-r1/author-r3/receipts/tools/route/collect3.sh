#!/bin/bash
# collect3.sh <receipts dir>: per round-3 route, the reports the comparison reads (routed utilisation, routed hierarchy,
# placed utilisation, route status, and the Design Timing Summary of the summary and of each signoff corner), the
# Vivado host header line dropped; plus each run's start, end and slot line
B=/data-2/milan/tmp/gptp106-a831; R=$1/routes; mkdir -p $R
for s in 1x1 8x8; do for n in base head; do for t in eppo aslh eto; do
  case $t in eppo) d=$B/r3-$n-$s/split/gateware; slot=$B/r3-$n-$s/slot.log;; *) d=$B/r3-$n-$s-$t; slot=$B/r3-$n-$s-$t.slot.log;; esac
  o=$R/$s-$n-$t; mkdir -p $o
  for f in baseline_utilization.rpt baseline_hierarchy.rpt alinx_ax7101_utilization_place.rpt alinx_ax7101_route_status.rpt; do
    grep -v "^| Host " $d/$f > $o/$f
  done
  { for f in baseline_timing.rpt alinx_ax7101_signoff_Slow_85C_timing.rpt alinx_ax7101_signoff_Slow_0C_timing.rpt \
             alinx_ax7101_signoff_Fast_85C_timing.rpt alinx_ax7101_signoff_Fast_0C_timing.rpt; do
      echo "== $f"; awk '/\| Design Timing Summary/{p=1} p{print; if (++n > 12) exit}' $d/$f; done; } > $o/timing-summaries.txt
  { echo "start $(cat $d/route.start) end $(cat $d/route.end) rc $(cat $d/route.rc)"; cat $slot; grep -m1 "place_design -directive" $d/baseline_*.tcl; } > $o/run.txt
done; done; done
du -sh $R
