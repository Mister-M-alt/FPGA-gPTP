#!/bin/bash
# milan_dp_gm_steps: the clean gmstep leg, then its five acceptance controls
L=$1
cd $VALIDATION_STORAGE/scratch/gptp106-parent || exit 1
t0=$(date +%s); make -C tb/verilator/milan_dp_gm_steps > $L/p-milan_dp_gm_steps.log 2>&1; echo "milan_dp_gm_steps rc=$? $(( $(date +%s) - t0 ))s" >> $L/parent.summary
