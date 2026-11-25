#!/bin/sh
# Plant: remove reraise()'s prctl(PR_SET_DUMPABLE, 0) in a disposable copy of the engine
# suite and run passes-test there.  usage: plant_noprctl.sh CLONE WORKDIR   (run under
# `ulimit -c 0` for the hard-zero case)
set -eu
clone=$1; work=$2
rm -rf "$work"; mkdir -p "$work"
git -C "$clone" archive HEAD tb/verilator/engine | tar -x -C "$work"
f=$work/tb/verilator/engine/pass_run.py
python3 -I - "$f" <<'PY'
import sys; p = sys.argv[1]; s = open(p).read()
old = "        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)\n"
assert s.count(old) == 1, "plant site not found"
open(p, "w").write(s.replace(old, "        pass  # plant: prctl removed\n"))
PY
cd "$work/tb/verilator/engine" && make passes-test
