#!/bin/bash
# campaign.sh CLONE PACKET: the probe campaign as run. Seven disposable trees from CLONE's HEAD,
# each with the engine Makefile of base 1213ac5 (serial, S-*) or of HEAD (parallel, P-*), clean or
# with one planted defect (plant.py), each running `make -j1 run` pinned to its own CPUs (16 in all),
# all at once, with sample.sh recording how many simulators each tree has live. Then compare.sh.
set -u
C=$1; P=$2; S=$P/scripts; B=1213ac5b9e09b8759ba76cc70c53652b5e108996
mkdir -p "$P/scratch/trees" "$P/scratch/runs" "$P/scratch/ccache"; export CCACHE_DIR=$P/scratch/ccache
while read -r name rev plant cpus; do
  [ "$plant" = - ] && plant=; [ "$rev" = base ] && rev=$B
  "$S/mktree.sh" "$C" "$P/scratch/trees/$name" "$rev" $plant
  setsid nohup "$S/runone.sh" "$P/scratch/trees/$name" "$cpus" "$P/scratch/runs/$name" >/dev/null 2>&1 </dev/null &
done <<'RUNS'
S-clean base - 64
P-clean HEAD - 65-68
P1cpu-clean HEAD - 69
S-fail base fail-seedrun 70
P-fail HEAD fail-seedrun 71-74
S-abort base abort-sync 75
P-abort HEAD abort-sync 76-79
RUNS
setsid nohup "$S/sample.sh" "$P/scratch/trees" "$P/scratch/runs/samples.log" S-clean P-clean P1cpu-clean S-fail P-fail S-abort P-abort >/dev/null 2>&1 </dev/null &
"$S/wait_rc.sh" 7000 "$P"/scratch/runs/{S,P,P1cpu}-clean "$P"/scratch/runs/{S,P}-fail "$P"/scratch/runs/{S,P}-abort
for pr in "S-clean P-clean" "S-clean P1cpu-clean" "S-fail P-fail" "S-abort P-abort"; do "$S/compare.sh" "$P/scratch/runs" $pr; done
