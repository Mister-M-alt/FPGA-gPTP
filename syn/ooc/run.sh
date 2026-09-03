#!/bin/sh
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
# Runs both OOC measurements into syn/ooc/work/. Needs Vivado 2026.1.
#
# Rule 13 strict mode is `errexit` only here; the other two thirds are DECLINED
# and this is the record of why, not an oversight.
#   -u          The `.` below sources Vivado's settings64.sh - a vendor script
#               that appends to variables it does not set first, in the shape
#               `LD_LIBRARY_PATH=$XILINX_VIVADO/lib/lnx64.o:$LD_LIBRARY_PATH`.
#               Under nounset that is an unbound variable, and with errexit the
#               run stops there, before either synthesis. Reproduced against a
#               settings64.sh of that shape: `LD_LIBRARY_PATH: unbound
#               variable`, exit 1, no reports.
#   -o pipefail The two report readers at the bottom are `grep ... | head -20`,
#               and pipefail breaks both. A report with no matching line makes
#               grep exit 1, which with errexit ends the run after the ucpu
#               heading and never prints the engine numbers; a report with more
#               than twenty matching lines makes `head` close the pipe, and
#               grep dies of SIGPIPE for exit 141 on a run where both
#               syntheses succeeded. Both reproduced with a stub vivado.
#               `-o pipefail` is also a late addition to POSIX (Issue 8) that
#               not every /bin/sh implements.
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
