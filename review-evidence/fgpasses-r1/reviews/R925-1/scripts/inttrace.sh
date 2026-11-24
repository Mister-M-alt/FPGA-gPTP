#!/bin/bash
# inttrace.sh WORK SIG [shell|group]: in WORK/par (stub harness, every pass hanging), run the recipe shell traced
# (-x), send SIG to TARGET (recipe shell alone, or make's whole process group as a terminal does)
# once four passes live, and show what the shell did. make starts with INT and QUIT at their defaults,
# as from an interactive terminal; a background launch would leave them ignored and the trap inert.
set -u
W=$1; S=$2; T=${3:-shell}; E=$W/par/tb/verilator/engine; L=$W/inttrace.$S.$T.log
live() { local n=0 p; for p in $(pgrep -x sleep); do case "$(readlink /proc/$p/cwd 2>/dev/null)" in "$W/par/"*) n=$((n+1));; esac; done; echo $n; }
cd "$E"
STUB_PLAN="engine=hang seedrun=hang syncseedrun=hang p1run=hang" setsid python3 -I -c 'import os, signal, sys; signal.signal(signal.SIGINT, signal.SIG_DFL); signal.signal(signal.SIGQUIT, signal.SIG_DFL); os.execvp(sys.argv[1], sys.argv[1:])' make -j1 VERILATOR=true .SHELLFLAGS=-xc run > "$L" 2>&1 &
mk=$!
for i in $(seq 200); do [ "$(live)" = 4 ] && break; sleep 0.2; done
sh=$(pgrep -P "$mk" -x sh)
echo "live=$(live) make=$mk recipe-shell=$sh"
echo "recipe shell $(grep -E 'SigIgn|SigCgt' /proc/$sh/status | tr '\n' ' ')"
for p in $(pgrep -P "$sh"); do echo "pass pid $p $(grep SigIgn /proc/$p/status)"; done
if [ "$T" = group ]; then kill -s "$S" -- "-$mk"; else kill -s "$S" "$sh"; fi; wait "$mk"; echo "make rc=$?"; sleep 2; echo "live after=$(live)"
grep -nE '^\+|^make: \*\*\*' "$L" | tail -12
for p in $(pgrep -x sleep); do case "$(readlink /proc/$p/cwd 2>/dev/null)" in "$W/par/"*) kill "$p";; esac; done
