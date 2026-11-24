#!/usr/bin/env bash
# Reproduce the round's three plants against copies of the engine directory, each running the full passes_test.py.
# Usage: plants.sh CLONE WORKDIR   (runs the three plants at once; each writes WORKDIR/NAME.log and NAME.rc)
set -u
clone=$1; work=$2; rm -rf "$work"; mkdir -p "$work"
plant() {  # name, python replacement (old, new) applied to pass_run.py
  local name=$1 old=$2 new=$3 d=$work/$1
  mkdir -p "$d"; cp "$clone/tb/verilator/engine/"{Makefile,pass_run.py,passes_test.py} "$d/"
  python3 - "$d/pass_run.py" "$old" "$new" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read(); assert s.count(old) == 1, old; open(p, "w").write(s.replace(old, new))
PY
  (cd "$d" && diff -u "$clone/tb/verilator/engine/pass_run.py" pass_run.py > "$work/$name.patch"; python3 passes_test.py > "$work/$name.log" 2>&1; echo "rc=$?" > "$work/$name.rc")
}
plant no-chdir '    os.chdir(STATE)  # a file core_pattern' '    pass  # planted: no chdir; was: a file core_pattern' &
plant no-gen-reraise '    if record.get("gen_signal"):
        reraise(record["gen_signal"], record.get("gen_core", False))
' '' &
plant gen-no-redirect 'gen = subprocess.Popen(["/bin/sh", "-c", generate + " >/dev/null"]' 'gen = subprocess.Popen(["/bin/sh", "-c", generate]' &
wait
for n in no-chdir no-gen-reraise gen-no-redirect; do echo "== $n $(cat $work/$n.rc) $(grep 'engine passes test' $work/$n.log)"; grep '^\[FAIL\]' $work/$n.log | cut -c1-150; done
