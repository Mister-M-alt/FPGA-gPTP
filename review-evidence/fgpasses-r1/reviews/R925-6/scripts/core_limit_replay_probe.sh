#!/usr/bin/env bash
# Under a soft core limit of 1 (which suppresses a piped core dump; a limit of 0 does not), compare make's report
# of a recipe line whose process dies of SIGSEGV with pass_run.py's run + replay of the same death.
# Usage: core_limit_replay_probe.sh CLONE WORKDIR
set -u
clone=$1; work=$2; rm -rf "$work"; mkdir -p "$work/obj_dir/engine-passes"; cd "$work" || exit 2
touch obj_dir/engine-passes/build.ok; cp "$clone/tb/verilator/engine/pass_run.py" .
printf 'import os, signal\nos.kill(os.getpid(), signal.SIGSEGV)\n' > segv.py
printf 'serial:\n\t@python3 segv.py\n' > Makefile.serial
printf 'parallel:\n\t@python3 pass_run.py run 0 -- python3 segv.py\n\t@python3 pass_run.py replay 0\n' > Makefile.parallel
echo "core_pattern: $(cut -c1-40 /proc/sys/kernel/core_pattern)"
lim_exec() { python3 -c "import os, resource, sys; resource.setrlimit(resource.RLIMIT_CORE, (int(sys.argv[1]), resource.getrlimit(resource.RLIMIT_CORE)[1])); os.execvp(sys.argv[2], sys.argv[2:])" "$@"; }
for lim in 0 1 1048576; do
  s=$( (lim_exec $lim make --no-print-directory -f Makefile.serial 2>&1) | sed 's/Makefile[.a-z]*:[0-9]*: [a-z]*/MK/')
  rm -f obj_dir/engine-passes/0.*
  p=$( (lim_exec $lim make --no-print-directory -f Makefile.parallel 2>&1) | sed 's/Makefile[.a-z]*:[0-9]*: [a-z]*/MK/')
  echo "soft limit $lim bytes: record $(cat obj_dir/engine-passes/0.json)"
  echo "  serial:   $s"; echo "  replayed: $p"; [ "$s" = "$p" ] && echo "  SAME" || echo "  DIFFER"
done
