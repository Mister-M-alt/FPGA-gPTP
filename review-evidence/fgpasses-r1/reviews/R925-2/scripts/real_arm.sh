#!/bin/sh
# usage: real_arm.sh REPO REV DEST JOBS LOGDIR
# Extracts REV of REPO into DEST and runs `make -jJOBS -C tb/verilator/engine run` with the
# pinned Verilator, sampling the number of simulator processes every 0.2 s.
set -u
repo=$1 rev=$2 dest=$3 jobs=$4 logs=$5
mkdir -p "$dest" "$logs"
git -C "$repo" archive "$rev" | tar -x -C "$dest"
echo "$rev" > "$logs/rev"
( while :; do n=$(pgrep -f -c "^\.\./obj_dir/Vengine_sim|^\./obj_dir/Vengine_sim" 2>/dev/null); \
   n2=$(for p in $(pgrep -x Vengine_sim 2>/dev/null); do d=$(readlink /proc/$p/cwd 2>/dev/null); case "$d" in "$dest"/*) echo x;; esac; done | wc -l); \
   echo "$(date +%s.%N) $n2"; sleep 0.2; done ) > "$logs/samples" 2>/dev/null &
sampler=$!
start=$(date +%s.%N)
env MAKEFLAGS= CCACHE_DIR="$logs/../ccache" make -j"$jobs" -C "$dest/tb/verilator/engine" run \
  VERILATOR=$VALIDATION_TOOLS/pinned-verilator-5.050/verilator > "$logs/log" 2>&1
rc=$?
end=$(date +%s.%N)
kill $sampler 2>/dev/null
echo "$start $end" > "$logs/time"
awk '{if($2>m)m=$2} END{print "peak simulators in this tree at once:", m+0}' "$logs/samples" > "$logs/peak"
echo $rc > "$logs/rc"
