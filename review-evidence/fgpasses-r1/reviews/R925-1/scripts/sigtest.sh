#!/bin/bash
# sigtest.sh WORK: with the HEAD tree WORK/par from stubtest.sh and every pass hanging, start
# `make run` in its own process group, wait until four passes live, send SIGNAL to TARGET
# (make | group | recipe-shell), then report make's status (make is the background child itself: setsid execs it) and the passes still alive 3 s later.
set -u
W=$1; E=$W/par/tb/verilator/engine
live() { local n=0 p; for p in $(pgrep -x sleep); do case "$(readlink /proc/$p/cwd 2>/dev/null)" in "$W/par/"*) n=$((n+1));; esac; done; echo $n; }
for case in "TERM make" "INT group" "INT recipe-shell" "TERM recipe-shell" "HUP group"; do
  set -- $case; sig=$1; tgt=$2
  ( cd "$E" && STUB_PLAN="engine=hang seedrun=hang syncseedrun=hang p1run=hang" exec setsid make -j1 VERILATOR=true run > "$W/sig.$sig.$tgt.log" 2>&1 ) &
  bg=$!
  for i in $(seq 50); do [ "$(live)" = 4 ] && break; sleep 0.2; done
  before=$(live); mk=$bg; sh=$(pgrep -P "$mk" -x sh | head -1); [ -n "$sh" ] || sh=$(pgrep -P "$mk" | head -1)
  case $tgt in make) kill -s "$sig" "$mk";; group) kill -s "$sig" -- "-$mk";; recipe-shell) kill -s "$sig" "$sh";; esac
  wait $bg; rc=$?; sleep 3
  echo "$sig to $tgt: passes alive before=$before, make rc=$rc, passes alive 3 s after=$(live); make said: $(grep -E '^make: \*\*\*' "$W/sig.$sig.$tgt.log" | tr '\n' ' ')"
  for p in $(pgrep -x sleep); do case "$(readlink /proc/$p/cwd 2>/dev/null)" in "$W/par/"*) kill "$p";; esac; done
done
