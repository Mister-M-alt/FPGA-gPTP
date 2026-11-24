#!/bin/sh
# Reviewer runner, FPGA-gPTP PR #110 (#109) round 2, at an exact head.
# Usage: run_review_r2.sh CLONE PACKET VERILATOR_WRAPPER
#   CLONE    a clean checkout of the reviewed repository (never written)
#   PACKET   output directory; disposable trees go under PACKET/scratch
#   VERILATOR_WRAPPER  the pinned Verilator 5.050 entry point
# Trees are extracted with `git archive`, so the clone is never built in.
# Long jobs start detached, each with its own log and rc file; the caller
# waits on the rc files in the foreground.
set -eu
CLONE=$1; PACKET=$2; VW=$3
HEAD_SHA=74830c2f73a3001da7325e84e8fe19a161383f82
BASE_SHA=1213ac5b9e09b8759ba76cc70c53652b5e108996
S=$PACKET/scratch; L=$S/logs; A=$PACKET/scripts/run_p109_arm.py
export PYTHONDONTWRITEBYTECODE=1
mkdir -p "$S/bin" "$S/head" "$S/base" "$S/repro" "$S/armp" "$S/armw" "$L"
[ -e "$S/bin/verilator" ] || ln -s "$VW" "$S/bin/verilator"
export PATH="$S/bin:$PATH"
verilator --version
for d in head repro armp armw; do git -C "$CLONE" archive "$HEAD_SHA" | tar -x -C "$S/$d"; done
git -C "$CLONE" archive "$BASE_SHA" | tar -x -C "$S/base"
# reproduction: the head harness and RTL with the base generator and ROM image
cp "$S/base/hdl/ucode/gen_gptp_ucode.py" "$S/repro/hdl/ucode/gen_gptp_ucode.py"
cp "$S/base/tb/verilator/engine/gptp_ucode.hex" "$S/repro/tb/verilator/engine/gptp_ucode.hex"
md5sum "$S/repro/tb/verilator/engine/gptp_ucode.hex"
start() { # name dir command...
  n=$1; d=$2; shift 2
  ( cd "$d" && nohup sh -c "$* > $L/$n.log 2>&1; echo \$? > $L/$n.rc" >/dev/null 2>&1 & )
}
start head_suite  "$S/head/tb/verilator/engine"  make run VERILATOR=verilator
start repro_suite "$S/repro/tb/verilator/engine" make run VERILATOR=verilator
mkdir -p "$S/tmp_p" "$S/tmp_w"
start arm_p109 "$S/armp/tb/verilator/engine" env TMPDIR="$S/tmp_p" python3 -B $A . p109 --jobs 9
start arm_wholerun "$S/armw/tb/verilator/engine" env TMPDIR="$S/tmp_w" \
  python3 -B $A . idx:37,44,47,58,59,153,154,155,159,161,169,171 --jobs 4
echo "started; wait for $L/*.rc"
