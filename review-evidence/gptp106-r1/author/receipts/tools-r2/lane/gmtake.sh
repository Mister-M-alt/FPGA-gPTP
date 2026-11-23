#!/bin/bash
# the gmstep leg with every phase and the #107 takeover phase, from a copied binary
L=$1; R=$VALIDATION_STORAGE/gptp106-a831/gmstep-take
cd $VALIDATION_STORAGE/scratch/gptp106-parent/tb/verilator/milan_dp || exit 1
t0=$(date +%s); $R/Vmilan_dp_gmstep $R/aemi.bin 0 --takeovers > $L/p-gmstep-takeovers.log 2>&1; echo "gmstep-takeovers rc=$? $(( $(date +%s) - t0 ))s" >> $L/parent.summary
