#!/bin/bash
# stubtest.sh CLONE WORK: run the engine `run` recipe from base 1213ac5 (serial) and from HEAD
# (parallel) with a stub harness (VERILATOR=true, stub_sim.sh as obj_dir/Vengine_sim), for each plan;
# print each transcript's make status, and whether the transcripts are byte-identical once the
# make recipe-location in make's own error line is masked. STUB_MAKEFLAGS adds make options (e.g. -s).
set -u
C=$1; W=$2; S=$(cd "$(dirname "$0")" && pwd)
for v in ser:1213ac5b9e09b8759ba76cc70c53652b5e108996 par:HEAD; do
  t=$W/${v%%:*}; "$S/mktree.sh" "$C" "$t" "${v#*:}"
  mkdir -p "$t/tb/verilator/engine/obj_dir"; cp "$S/stub_sim.sh" "$t/tb/verilator/engine/obj_dir/Vengine_sim"
done
n=0
while IFS= read -r plan; do
  n=$((n+1))
  for k in ser par; do
    ( cd "$W/$k/tb/verilator/engine" && STUB_PLAN=$plan make ${STUB_MAKEFLAGS:-} -j1 VERILATOR=true run > "$W/$k.$n.log" 2>&1; echo "make-rc=$?" >> "$W/$k.$n.log" )
  done
  m() { sed -E 's/^make: \*\*\* \[Makefile:[0-9]+: run\]/make: *** [Makefile:<L>: run]/; /^true --cc /d' "$1"; }
  if cmp -s <(m "$W/ser.$n.log") <(m "$W/par.$n.log"); then r=IDENTICAL; else r=DIFFER; fi
  echo "== plan $n [$plan]: $r; serial: $(grep -E '^make: \*\*\*|make-rc' "$W/ser.$n.log" | tr '\n' ' ')| parallel: $(grep -E '^make: \*\*\*|make-rc' "$W/par.$n.log" | tr '\n' ' ')"
  [ $r = IDENTICAL ] || diff <(m "$W/ser.$n.log") <(m "$W/par.$n.log") | sed 's/^/   /'
done <<'PLANS'
engine=0
engine=1
seedrun=3
seedrun=3 syncseedrun=5
p1run=7
engine=2 p1run=9
seedrun=sigSEGV
syncseedrun=sigABRT
p1run=sigKILL
PLANS
