#!/bin/sh
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
# Runs both OOC measurements into syn/ooc/work/. Needs Vivado 2026.1.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
VIVADO_SETTINGS=${VIVADO_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}
. "$VIVADO_SETTINGS"
mkdir -p "$HERE/work"
cd "$HERE/work"
python3 "$HERE/../../hdl/ucode/gen_gptp_ucode.py" -o gptp_ucode.hex
vivado -mode batch -source "$HERE/ucpu_ooc.tcl"   -nojournal -log ucpu_ooc.log
vivado -mode batch -source "$HERE/engine_ooc.tcl" -nojournal -log engine_ooc.log
echo "==== ucpu ===="
grep -A2 "Slice LUTs\|Block RAM Tile\|DSPs" ucpu_util.rpt | head -20
echo "==== engine ===="
grep -A2 "Slice LUTs\|Block RAM Tile\|DSPs" engine_util.rpt | head -20
