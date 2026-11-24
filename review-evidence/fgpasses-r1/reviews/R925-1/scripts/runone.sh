#!/bin/bash
# runone.sh TREE CPUS OUTDIR: `make -j1 run` in TREE's engine suite pinned to CPUS; log, rc, time.
set -u
T=$1; C=$2; O=$3
mkdir -p "$O"; rm -f "$O/rc"
cd "$T/tb/verilator/engine" || { echo 99 > "$O/rc"; exit 99; }
export CCACHE_DIR=${CCACHE_DIR:?}
taskset -c "$C" /usr/bin/time -f "%e wall %U user %S sys" -o "$O/time" \
  make -j1 VERILATOR=$VALIDATION_TOOLS/pinned-verilator-5.050/verilator run > "$O/log" 2>&1
echo $? > "$O/rc"
