#!/bin/bash
# gptp_shadow: the standard gate (lifecycle, run, mutants), then the -100 ppm loop variant
L=$1; P=$VALIDATION_STORAGE/scratch/gptp106-parent/tb/verilator/gptp_shadow
cd $P || exit 1
t0=$(date +%s); make > $L/p-gptp_shadow.log 2>&1; echo "gptp_shadow rc=$? $(( $(date +%s) - t0 ))s" >> $L/parent.summary
cmd=$(make -n run 2>/dev/null | grep -- '--cc --exe' | sed 's/--build/--Mdir obj_m100 --build/; s/-o Vgptp_shadow_sim/-CFLAGS -DP107_MASTER_SIGN=-1 -o Vgptp_shadow_sim/')
t0=$(date +%s); { eval "$cmd" && ./obj_m100/Vgptp_shadow_sim; } > $L/p-gptp_shadow-m100.log 2>&1; echo "gptp_shadow-m100 rc=$? $(( $(date +%s) - t0 ))s" >> $L/parent.summary
