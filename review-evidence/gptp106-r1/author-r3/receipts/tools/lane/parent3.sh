#!/bin/bash
# parent3.sh <A|B|R> <log dir>: the parent's gPTP consumer simulations in the scratch parent (gitlink at the
# processor head under test), each leg's directory cleaned first; chain A: the gptp_* legs and clkvalid, chain B:
# every leg that builds in milan_dp (milan_dp gptp, gptp-lat, milan_dp_gptp, milan_dp_gm_steps); R: the parent's
# Python, SystemVerilog and C++ idiom ratchets
P=$VALIDATION_STORAGE/scratch/gptp106-parent; c=$1; L=$2
V=$VALIDATION_TOOLS/pinned-verilator-5.050
export VERILATOR=$V/verilator TMPDIR=$VALIDATION_STORAGE/gptp106-a831/tmp PYTHONHASHSEED=0
export PATH=<home-path>/litex-milan/venv/bin:$V:$VALIDATION_TOOLS/sv2v-v0.0.12:$VALIDATION_STORAGE/scratch/a662/make43/bin:/usr/local/bin:/usr/bin:/bin
export MAKEFLAGS="-j8 --no-print-directory"
mkdir -p $TMPDIR; cd $P || exit 1
echo "chain $c: parent $(git rev-parse --short=10 HEAD) gptp-processor $(git -C gptp-processor rev-parse --short HEAD) verilator $($VERILATOR --version) $(date -Iseconds)" >> $L/parent.summary
run() { local name=$1; shift; local t0=$(date +%s); "$@" > $L/p-$name.log 2>&1; local rc=$?; echo "$name rc=$rc $(( $(date +%s) - t0 ))s" >> $L/parent.summary; }
clean() { make -C tb/verilator/$1 clean > /dev/null 2>&1; }
case $c in
A) for d in gptp_shadow gptp_plane gptp_txts gptp_tables clkvalid; do clean $d; run $d make -C tb/verilator/$d; done;;
B) clean milan_dp; clean milan_dp_gptp; clean milan_dp_gm_steps
   run milan_dp-gptp make -C tb/verilator/milan_dp gptp
   run milan_dp-gptp-lat make -C tb/verilator/milan_dp gptp-lat
   run milan_dp_gptp make -C tb/verilator/milan_dp_gptp
   run milan_dp_gm_steps make -C tb/verilator/milan_dp_gm_steps;;
R) for x in py sv cpp; do run ratchet-$x python3 scripts/check_${x}_idiom.py; done
   echo "arm module: $(wc -l < gptp-processor/tb/verilator/engine/mutants.py) lines" >> $L/parent.summary;;
esac
echo "chain $c DONE $(date -Iseconds)" >> $L/parent.summary
