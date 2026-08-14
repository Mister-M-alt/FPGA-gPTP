#!/bin/sh
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
# Build the Arty first-light bench into bench/arty/work/.
#   ./build.sh [--mac 0x02A1B2C3D4E5]
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
