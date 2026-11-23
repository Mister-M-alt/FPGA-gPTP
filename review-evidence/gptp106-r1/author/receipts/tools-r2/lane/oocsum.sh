#!/bin/bash
# summarize an OOC work dir: LUT, FF, BRAM, DSP, WNS for ucpu and engine
d=$1
for t in ucpu engine; do
  lut=$(grep -m1 "^| Slice LUTs" $d/${t}_util.rpt | awk -F'|' '{gsub(/ /,"",$3); print $3}')
  ff=$(grep -m1 "^| Slice Registers" $d/${t}_util.rpt | awk -F'|' '{gsub(/ /,"",$3); print $3}')
  bram=$(grep -m1 "^| Block RAM Tile" $d/${t}_util.rpt | awk -F'|' '{gsub(/ /,"",$3); print $3}')
  dsp=$(grep -m1 "^| DSPs" $d/${t}_util.rpt | awk -F'|' '{gsub(/ /,"",$3); print $3}')
  wns=$(grep -A6 "Design Timing Summary" $d/${t}_timing.rpt | awk 'NF>4 && $1 ~ /^-?[0-9.]+$/ {print $1; exit}')
  echo "$t LUT=$lut FF=$ff BRAM=$bram DSP=$dsp WNS=$wns"
done
