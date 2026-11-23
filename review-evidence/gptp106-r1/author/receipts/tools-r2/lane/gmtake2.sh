#!/bin/bash
# gmtake2.sh <log dir> <label> <milan_dp dir>: build (obj_gmstep_take) and run the gmstep leg with --takeovers there
L=$1; lab=$2; D=$3
cd "$D" || exit 1
t0=$(date +%s)
make gmstep-build GMSTEP_MDIR=obj_gmstep_take > $L/gmstep-$lab-build.log 2>&1 || { echo "gmstep-$lab build rc=$?" >> $L/parent.summary; exit 1; }
./obj_gmstep_take/Vmilan_dp_gmstep obj_gmstep_take/aemi.bin 0 --takeovers > $L/p-gmstep-$lab.log 2>&1
echo "gmstep-$lab rc=$? $(( $(date +%s) - t0 ))s" >> $L/parent.summary
