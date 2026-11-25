#!/usr/bin/env bash
# Plants against copies of the engine directory, each running the full passes_test.py at once.
# Usage: plants.sh CLONE WORKDIR RECEIPTS   (each writes RECEIPTS/plant-NAME.{patch,log,rc})
set -u
clone=$1; work=$2; rec=$3; rm -rf "$work"; mkdir -p "$work" "$rec"
plant() {  # name, file, old, new: one exact replacement in a copy of FILE
  local name=$1 file=$2 old=$3 new=$4 d=$work/$1
  mkdir -p "$d"; cp "$clone/tb/verilator/engine/"{Makefile,pass_run.py,passes_test.py} "$d/"
  python3 - "$d/$file" "$old" "$new" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read(); assert s.count(old) == 1, old; open(p, "w").write(s.replace(old, new))
PY
  (cd "$d" && diff -u "$clone/tb/verilator/engine/$file" "$file" > "$rec/plant-$name.patch"
   TMPDIR="$d" python3 passes_test.py > "$rec/plant-$name.log" 2>&1; echo "rc=$?" > "$rec/plant-$name.rc")
}
plant no-gen-reraise pass_run.py '    if record.get("gen_signal"):
        reraise(record["gen_signal"], record.get("gen_core", False))
' '' &
plant limit-zero pass_run.py '(1 if hard == resource.RLIM_INFINITY or hard >= 1 else 0, hard)' '(0, hard)' &
plant no-chdir pass_run.py '    os.chdir(STATE)  # a relative' '    pass  # planted: no chdir; was: a relative' &
plant no-gen-record pass_run.py '            record.update(gen_signal=os.WTERMSIG(status), gen_core=os.WCOREDUMP(status))' '            pass  # planted: no gen_signal record' &
plant gen-no-redirect pass_run.py 'gen = subprocess.Popen(["/bin/sh", "-c", generate + " >/dev/null"]' 'gen = subprocess.Popen(["/bin/sh", "-c", generate]' &
wait
for n in no-gen-reraise limit-zero no-chdir no-gen-record gen-no-redirect; do
  echo "== $n $(cat $rec/plant-$n.rc) $(grep 'engine passes test' $rec/plant-$n.log)"; grep '^\[FAIL\]' $rec/plant-$n.log | cut -c1-170
done
