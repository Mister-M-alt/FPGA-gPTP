#!/usr/bin/env bash
# This round's plants against copies of the engine directory, each running the full passes_test.py.
# Usage: plants.sh CLONE WORKDIR   (runs all plants at once; each writes WORKDIR/NAME.log, NAME.rc, NAME.patch)
# A name ending in -c0 runs under `ulimit -c 0` (soft and hard core limit 0).
set -u
clone=$1; work=$2; rm -rf "$work"; mkdir -p "$work"
plant() {  # name, old, new: one replacement applied to pass_run.py
  local name=$1 old=$2 new=$3 d=$work/$1 pre=":"
  case $name in *-c0) pre="ulimit -c 0";; esac
  mkdir -p "$d"; cp "$clone/tb/verilator/engine/"{Makefile,pass_run.py,passes_test.py} "$d/"
  python3 - "$d/pass_run.py" "$old" "$new" <<'PY'
import sys
p, old, new = sys.argv[1:]
s = open(p).read(); assert s.count(old) == 1, old; open(p, "w").write(s.replace(old, new))
PY
  (cd "$d" && diff -u "$clone/tb/verilator/engine/pass_run.py" pass_run.py > "$work/$name.patch"
   bash -c "$pre; python3 passes_test.py" > "$work/$name.log" 2>&1; echo "rc=$?" > "$work/$name.rc")
}
PR='        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_DUMPABLE, 0, 0, 0, 0)
'
SOFT='        soft = 1 if hard == resource.RLIM_INFINITY or hard >= 1 else 0
'
plant no-prctl "$PR" '' &
plant no-prctl-c0 "$PR" '' &
plant soft0-keep-prctl "$SOFT" '        soft = 0
' &
plant soft0-keep-prctl-c0 "$SOFT" '        soft = 0
' &
plant prior-reraise "$SOFT$( printf '        resource.setrlimit(resource.RLIMIT_CORE, (soft, hard))\n')
$PR" '        resource.setrlimit(resource.RLIMIT_CORE, (0, hard))
' &
wait
for n in no-prctl no-prctl-c0 soft0-keep-prctl soft0-keep-prctl-c0 prior-reraise; do
  echo "== $n $(cat $work/$n.rc) PASS=$(grep -c '^\[PASS\]' $work/$n.log) $(grep 'engine passes test' $work/$n.log)"
  grep '^\[FAIL\]' $work/$n.log | cut -c1-170
done
