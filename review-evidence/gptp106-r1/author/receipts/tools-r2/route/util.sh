#!/bin/bash
# util.sh <gateware dir>: LUT, FF, slices, BRAM tiles, RAMB36, RAMB18, DSP from the placed design's utilization report
r=$1/alinx_ax7101_utilization_place.rpt
f() { grep -m1 -E "^\| +$1 +\|" "$r" | awk -F'|' '{gsub(/ /,"",$3); print $3}'; }
echo "LUT=$(f 'Slice LUTs\*?') FF=$(f 'Slice Registers') SLICE=$(f 'Slice') BRAM_TILE=$(f 'Block RAM Tile') RAMB36=$(f 'RAMB36/FIFO\*') RAMB18=$(f 'RAMB18') DSP=$(f 'DSPs')"
