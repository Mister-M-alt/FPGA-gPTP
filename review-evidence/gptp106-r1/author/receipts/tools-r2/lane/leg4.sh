#!/bin/bash
# sequential processor gates in a gate worktree; one rc line per gate
G=$1; L=$2
cd $G || exit 1
run() { local name=$1; shift; local t0=$(date +%s); "$@" > $L/$name.log 2>&1; local rc=$?; echo "$name rc=$rc $(( $(date +%s) - t0 ))s" >> $L/leg4.summary; }
: > $L/leg4.summary
run contract make contract
run ucpu make -C tb/verilator/ucpu
run parser make -C tb/verilator/parser
run engine-run make -C tb/verilator/engine run
run gaskets make -C tb/verilator/gaskets
run tsngen make -C tb/tsngen
run bench make -C bench/arty test
run lint make lint
run docs make docs
echo DONE >> $L/leg4.summary
