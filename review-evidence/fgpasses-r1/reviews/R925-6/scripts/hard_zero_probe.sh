#!/usr/bin/env bash
# A non-dumpable process (prctl PR_SET_DUMPABLE 0) dies of SIGSEGV: serially make reports no core. Compare that with
# `pass_run.py run` + `replay` of the same death under caller core limits (soft,hard) = (0,0) as from `ulimit -c 0`,
# (0,unlimited) and (1,unlimited); for the head's pass_run.py and for a copy with the head's prctl line removed.
# Usage: hard_zero_probe.sh CLONE WORKDIR
set -u
clone=$1; work=$2; rm -rf "$work"; mkdir -p "$work"; cd "$work" || exit 2
echo "core_pattern: $(cut -c1-40 /proc/sys/kernel/core_pattern)"
printf 'import ctypes, os, signal\nctypes.CDLL(None).prctl(4, 0, 0, 0, 0)\nos.kill(os.getpid(), signal.SIGSEGV)\n' > nodump.py
mkdir head no-prctl; cp "$clone/tb/verilator/engine/pass_run.py" head/; cp "$clone/tb/verilator/engine/pass_run.py" no-prctl/
python3 - no-prctl/pass_run.py <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
old = "        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)\n"
assert s.count(old) == 1
open(p, "w").write(s.replace(old, ""))
PY
lim_exec() { python3 -c "import os, resource, sys; resource.setrlimit(resource.RLIMIT_CORE, (int(sys.argv[1]), int(sys.argv[2]))); os.execvp(sys.argv[3], sys.argv[3:])" "$@"; }
for v in head no-prctl; do
  cd "$work/$v"; mkdir -p obj_dir/engine-passes; touch obj_dir/engine-passes/build.ok
  printf 'serial:\n\t@python3 ../nodump.py\n' > Makefile.serial
  printf 'parallel:\n\t@python3 pass_run.py run 0 -- python3 ../nodump.py\n\t@python3 pass_run.py replay 0\n' > Makefile.parallel
  for lim in "0 0" "0 -1" "1 -1"; do
    s=$( (lim_exec $lim make --no-print-directory -f Makefile.serial 2>&1) | sed 's/Makefile[.a-z]*:[0-9]*: [a-z]*/MK/')
    rm -f obj_dir/engine-passes/0.*
    p=$( (lim_exec $lim make --no-print-directory -f Makefile.parallel 2>&1) | sed 's/Makefile[.a-z]*:[0-9]*: [a-z]*/MK/')
    echo "$v, limit (soft,hard)=($lim): record $(cat obj_dir/engine-passes/0.json)"
    echo "  serial:   $s"; echo "  replayed: $p"; [ "$s" = "$p" ] && echo "  SAME" || echo "  DIFFER"
  done
done
