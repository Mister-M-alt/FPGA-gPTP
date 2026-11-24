#!/bin/sh
# usage: my_plants.sh ENGINE_DIR WORK OUTDIR
# Reviewer-written planted defects (independent of the author's driver). Each copies the three files
# into WORK/<name>, applies one edit with python (anchor must occur once), runs passes_test.py there.
set -u
eng=$1 work=$2 out=$3
mkdir -p "$work" "$out"
plant() { name=$1 file=$2 old=$3 new=$4
  d="$work/$name"; rm -rf "$d"; mkdir -p "$d"; cp "$eng/Makefile" "$eng/pass_run.py" "$eng/passes_test.py" "$d/"
  python3 -I - "$d/$file" "$old" "$new" <<'PY' || { echo "BAD-ANCHOR $name" > "$out/$name.verdict"; return; }
import sys
p,o,n=sys.argv[1:4]; o=o.replace("\\t","\t").replace("\\n","\n"); n=n.replace("\\t","\t").replace("\\n","\n")
s=open(p).read(); assert s.count(o)==1, s.count(o); open(p,"w").write(s.replace(o,n))
PY
  ( cd "$d" && python3 -I passes_test.py > "$out/$name.log" 2>&1; echo $? > "$out/$name.rc" ) 
  rc=$(cat "$out/$name.rc"); fails=$(grep -c '^\[FAIL\]' "$out/$name.log")
  if [ "$rc" != 0 ]; then v=CAUGHT; else v=MISSED; fi
  echo "$v rc=$rc failing_checks=$fails" > "$out/$name.verdict"
}
plant budget-forced-j4 Makefile 'PASSES = engine-pass0' 'MAKEFLAGS += -j4\nPASSES = engine-pass0' &
plant notparallel Makefile 'PASSES = engine-pass0' '.NOTPARALLEL:\nPASSES = engine-pass0' &
plant signal-as-exit1 pass_run.py '        if record["signal"] != signal.SIGKILL:' '        return 1\n        if record["signal"] != signal.SIGKILL:' &
plant k-replay-prints pass_run.py '    """Pass N'"'"'s banner, what it printed, then its own ending."""\n    if not ignoring and failed_before(n):' '    """Pass N'"'"'s banner, what it printed, then its own ending."""\n    if not ignoring and failed_before(n) and False:' &
plant core-always-off pass_run.py '        if not record.get("core"):' '        if True:' &
plant core-never-off pass_run.py '        if not record.get("core"):' '        if False:' &
plant late-start-not-stopped pass_run.py '            if record.get("stopped"):\n                signal_all' '            if False:\n                signal_all' &
plant gen-status-ignored pass_run.py '    return record.get("gen", 0)' '    return 0' &
wait
