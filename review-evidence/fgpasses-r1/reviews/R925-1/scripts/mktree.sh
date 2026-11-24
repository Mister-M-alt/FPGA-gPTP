#!/bin/bash
# mktree.sh CLONE OUT MAKEFILE_REV [PLANT]: export CLONE's HEAD into OUT, take the engine
# Makefile from MAKEFILE_REV (base 1213ac5 = serial recipe, HEAD = parallel recipe), plant PLANT.
set -eu
C=$1; O=$2; R=$3; K=${4:-}
rm -rf "$O"; mkdir -p "$O"
git -C "$C" archive HEAD | tar -x -C "$O"
git -C "$C" show "$R:tb/verilator/engine/Makefile" > "$O/tb/verilator/engine/Makefile"
[ -z "$K" ] || python3 -I "$(dirname "$0")/plant.py" "$O/tb/verilator/engine/sim_main.cpp" "$K"
