#!/bin/sh
# Reviewer gate runner for FPGA-gPTP PR #110 (#109) at an exact head.
# Usage: run_review_gates.sh CLONE PACKET VERILATOR_WRAPPER
#   CLONE    a clean checkout of the reviewed repository (never written)
#   PACKET   output directory; disposable trees go under PACKET/scratch
#   VERILATOR_WRAPPER  the pinned Verilator 5.050 entry point
# Every tree is extracted with `git archive`, so the clone is never built in.
# The long jobs start detached with their own log and rc file; wait on the
# rc files in the foreground.
set -eu
CLONE=$1; PACKET=$2; VW=$3
HEAD_SHA=8e4889bba462d14d4e5a34068769872510d4775d
BASE_SHA=1213ac5b9e09b8759ba76cc70c53652b5e108996
S=$PACKET/scratch; L=$S/logs
mkdir -p "$S/bin" "$S/head" "$S/base" "$S/repro" "$L"
[ -e "$S/bin/verilator" ] || ln -s "$VW" "$S/bin/verilator"
export PATH="$S/bin:$PATH"
verilator --version
git -C "$CLONE" archive "$HEAD_SHA" | tar -x -C "$S/head"
git -C "$CLONE" archive "$HEAD_SHA" | tar -x -C "$S/repro"
git -C "$CLONE" archive "$BASE_SHA" | tar -x -C "$S/base"
# reproduction: the head harness and RTL with the base generator (base ROM)
cp "$S/base/hdl/ucode/gen_gptp_ucode.py" "$S/repro/hdl/ucode/gen_gptp_ucode.py"

# 1) engine suite at the head (four passes) and the reproduction
( cd "$S/head/tb/verilator/engine" && nohup sh -c \
  "make run VERILATOR=verilator > $L/head_suite.log 2>&1; echo \$? > $L/head_suite.rc" \
  >/dev/null 2>&1 & )
( cd "$S/repro/tb/verilator/engine" && nohup sh -c \
  "make run VERILATOR=verilator > $L/repro_suite.log 2>&1; echo \$? > $L/repro_suite.rc" \
  >/dev/null 2>&1 & )

# 2) light gates at the head (foreground)
( cd "$S/head" && make docs > "$L/docs.log" 2>&1; echo "docs_rc=$?";
  make contract > "$L/contract.log" 2>&1; echo "contract_rc=$?";
  make lint > "$L/lint.log" 2>&1; echo "lint_rc=$?" ) | tee "$L/gates.rc"

# 3) ROM images: regenerate each tracked image and compare
G=$S/head/hdl/ucode/gen_gptp_ucode.py; R=$S/regen; mkdir -p "$R"
python3 "$G" --clk-hz 2000000 --cease-ms 3000 -o "$R/engine.hex"
python3 "$G" -o "$R/default.hex"
python3 "$G" --clk-hz 2000000 -o "$R/tsngen.hex"
python3 "$G" --clk-hz 2000000 --cease-ms 3000 --seq-seed 0x200000 -o "$R/seed.hex"
( cd "$S/head" && sha256sum tb/verilator/engine/gptp_ucode.hex \
  tb/verilator/ucpu/gptp_ucode.hex syn/ooc/work/gptp_ucode.hex tb/tsngen/gptp_ucode.hex )
( cd "$R" && sha256sum engine.hex default.hex tsngen.hex )

# 4) mutation arm subsets (see run_p109_arm.py); TMPDIR keeps staging local
A=$(dirname "$0")/run_p109_arm.py
for spec in "p109 9" "probes 5"; do
  set -- $spec; mkdir -p "$S/tmp_$1"
  ( cd "$S/head/tb/verilator/engine" && TMPDIR="$S/tmp_$1" nohup sh -c \
    "python3 $A . $1 --jobs $2 > $L/arm_$1.log 2>&1; echo \$? > $L/arm_$1.rc" \
    >/dev/null 2>&1 & )
done
echo "started; wait for $L/*.rc"
