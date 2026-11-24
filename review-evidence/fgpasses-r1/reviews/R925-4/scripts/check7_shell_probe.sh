#!/usr/bin/env bash
# Run passes_test.py's own check 7 (gen_signal) from copies, under the host /bin/sh and under an emulated /bin/sh
# that forks its -c command (exit 128+n) unless the command is `exec ...`, as written and with the reference line
# prefixed by `exec`. Only the serial (reference) Makefile names the emulated shell: make runs the replay form's
# metachar-free line directly, without any shell, as it does on a real host (a SHELL other than /bin/sh would
# disable that and route both forms through the shell). The replay Makefile gets a comment line in place of the
# SHELL line, so make's recipe line numbers match.
# Usage: check7_shell_probe.sh CLONE WORKDIR
set -u
clone=$1; work=$2; rm -rf "$work"; mkdir -p "$work"
printf '#!/usr/bin/bash\n[ "$1" = -c ] && shift\ncase $1 in exec\\ *) exec /usr/bin/bash -c "$1";; esac\n/usr/bin/bash -c "$1"\nexit $?\n' > "$work/forksh"; chmod +x "$work/forksh"
for variant in as-written exec-reference; do
  for sh in host fork; do
    d=$work/$variant-$sh; mkdir -p "$d"
    cp "$clone/tb/verilator/engine/pass_run.py" "$d/"
    cp "$clone/tb/verilator/engine/passes_test.py" "$d/"
    shellline=""; [ $sh = fork ] && shellline="SHELL := $work/forksh\\n"
    python3 - "$d/passes_test.py" "$variant" "$shellline" <<'PY'
import sys
p, variant, shell = sys.argv[1:]
s = open(p).read()
old = '(d / "Makefile").write_text(f"all:\\n\\t@{line}\\n")'
assert old in s
s = s.replace(old, '(d / "Makefile").write_text(("' + shell + '" if form == "serial" else "#\\n" if "' + shell + '" else "") + f"all:\\n\\t@{line}\\n")')
if variant == "exec-reference":
    old = 'else f"python3 -c \'import os; os.kill(os.getpid(), {int(signum)})\'")'
    assert old in s
    s = s.replace(old, 'else f"exec python3 -c \'import os; os.kill(os.getpid(), {int(signum)})\'")')
open(p, "w").write(s)
PY
    out=$(cd "$d" && python3 -c "
import sys, tempfile; from pathlib import Path
sys.path.insert(0, '.'); import passes_test as t
with tempfile.TemporaryDirectory() as s: print('bad =', t.gen_signal({}, Path(s)))" 2>&1)
    echo "== $variant, /bin/sh $sh"; echo "$out"
  done
done
