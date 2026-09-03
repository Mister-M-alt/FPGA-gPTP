#!/bin/sh
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
# Build the Arty first-light bench into bench/arty/work/.
#   ./build.sh [--mac 0x02A1B2C3D4E5]
#
# Rule 13 strict mode is `errexit` only here; the other two thirds are DECLINED
# and this is the record of why, not an oversight.
#   -u          The `.` below sources Vivado's settings64.sh - a vendor script
#               that appends to variables it does not set first, in the shape
#               `LD_LIBRARY_PATH=$XILINX_VIVADO/lib/lnx64.o:$LD_LIBRARY_PATH`.
#               Under nounset that is an unbound variable, and with errexit the
#               build stops there, before the microcode and the bitstream, on a
#               machine where nothing is wrong. Reproduced against a
#               settings64.sh of that shape: `LD_LIBRARY_PATH: unbound
#               variable`, exit 1, nothing built. This script's own expansions
#               are already nounset-clean (`${2:-...}`, `${P1:-248}`); it is
#               the vendor file that is not, and it is not ours to fix.
#   -o pipefail A late addition to POSIX (Issue 8) that not every /bin/sh
#               implements, and with errexit a /bin/sh that rejects the option
#               exits on the `set` line itself. There is no pipeline in this
#               script for it to protect, so the trade is portability for
#               nothing.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
MAC=${2:-0x02A1B2C3D4E5}
VIVADO_SETTINGS=${VIVADO_SETTINGS:-$HOME/Xilinx/2026.1/Vivado/settings64.sh}
. "$VIVADO_SETTINGS"
mkdir -p "$HERE/work"
cd "$HERE/work"
python3 "$HERE/../../hdl/ucode/gen_gptp_ucode.py" -o gptp_ucode.hex --mac "$MAC" --p1 "${P1:-248}"
vivado -mode batch -source "$HERE/build.tcl" -nojournal -log bench_build.log
echo "bitstream: $HERE/work/bench_arty.bit"
echo "load (SRAM):  openFPGALoader -b arty --ftdi-serial <ARTY_SERIAL> bench_arty.bit"
echo "watch:        stty -F /dev/ttyUSBx 115200 raw && cat /dev/ttyUSBx"
