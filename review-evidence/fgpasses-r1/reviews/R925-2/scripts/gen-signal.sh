#!/bin/sh
# usage: gen-signal.sh WORKDIR
# How a generator line that dies of SIGSEGV ends: as the serial recipe ran it (make, with its own
# `>/dev/null`), and as pass_run.py runs it (/bin/sh -c GEN with stdout discarded by the caller), then the
# exit status a replay gets from sys.exit(that returncode).
set -u
mkdir -p "$1" && cd "$1" || exit 1
ulimit -c 0
echo "/bin/sh is: $(readlink /bin/sh || echo /bin/sh)"
printf 'all:\n\t@python3 -c "import os,signal;os.kill(os.getpid(),signal.SIGSEGV)" >/dev/null\n' > Makefile
echo "serial-form line under make: $(make 2>&1 | tail -1)"
rc=$(python3 -I -c '
import subprocess
g = "python3 -c \"import os,signal;os.kill(os.getpid(),signal.SIGSEGV)\""
print(subprocess.run(["/bin/sh", "-c", g], stdout=subprocess.DEVNULL).returncode)')
echo "pass_run.py-form returncode: $rc"
python3 -I -c "import sys; sys.exit($rc)"; echo "replay-gen exit status for that record: $?"
