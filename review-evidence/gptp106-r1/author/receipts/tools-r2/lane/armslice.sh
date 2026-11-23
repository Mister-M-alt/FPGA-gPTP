#!/bin/bash
# armslice.sh <a:b> [--clean]: the engine mutation arm's controls a..b-1 at the gate worktree, through the arm's own
# run_mutant() (mutslice.py); the log goes to logs-a728cc3/arm-<a>.log
S=$VALIDATION_STORAGE/gptp106-a831; r=$1; shift
cd $S/gate-a728cc3/tb/verilator/engine || exit 1
python3 $S/tools/mutslice.py . --range "$r" "$@" > $S/logs-a728cc3/arm-${r%%:*}.log 2>&1
echo "arm $r rc=$? $(grep -a '^SLICE' $S/logs-a728cc3/arm-${r%%:*}.log)" >> $S/logs-a728cc3/arm.summary
