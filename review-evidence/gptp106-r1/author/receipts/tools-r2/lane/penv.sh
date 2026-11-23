#!/bin/bash
# the parent's simulation environment, as round 1's parentleg.sh sets it, then "$@"
V=$VALIDATION_TOOLS/pinned-verilator-5.050
export VERILATOR=$V/verilator TMPDIR=$VALIDATION_STORAGE/gptp106-a831/tmp PYTHONHASHSEED=0
export PATH=<home-path>/litex-milan/venv/bin:$V:$VALIDATION_TOOLS/sv2v-v0.0.12:$VALIDATION_STORAGE/scratch/a662/make43/bin:/usr/local/bin:/usr/bin:/bin
export MAKEFLAGS="-j8 --no-print-directory"
mkdir -p $TMPDIR
exec "$@"
