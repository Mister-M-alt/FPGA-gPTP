#!/bin/bash
# the parent's milan_dp gptp then gptp-lat legs, in the scratch parent
L=$1; cd $VALIDATION_STORAGE/scratch/gptp106-parent || exit 1
for leg in gptp gptp-lat; do
  t0=$(date +%s); make -C tb/verilator/milan_dp $leg > $L/p-milan_dp-$leg.log 2>&1; echo "milan_dp-$leg rc=$? $(( $(date +%s) - t0 ))s" >> $L/parent.summary
done
