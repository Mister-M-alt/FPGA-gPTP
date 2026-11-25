#!/bin/bash
# Emulates a /bin/sh that execs a one-command -c line instead of forking it (the behaviour of dash 0.5.11+),
# for make's SHELL and pass_run.py's /bin/sh alike, on every plan of passes_test.py's check 1.
# usage: exec-sh-probe.sh CLONE WORKDIR RECEIPTS [no-gen-record]
#   no-gen-record additionally deletes run()'s gen_signal record (a plant), to show that half is load-bearing here.
set -u
CLONE=$1; W=$2; R=$3; MODE=${4:-head}; D=$W/e1-$MODE
rm -rf "$D" "$D.tmp"; mkdir -p "$W" "$R"; cp -r "$CLONE/tb/verilator/engine" "$D"; mkdir -p "$D.tmp"; X="$D/xsh"
cat >"$X" <<'SH'
#!/bin/bash
if [ "$1" = -c ] && [[ "$2" != *"&&"* && "$2" != *";"* && "$2" != *"|"* && "$2" != *'$('* ]]; then
  read -r first _ <<<"$2"
  if [ "$(type -t -- "$first")" = file ]; then exec /bin/bash -c "exec $2"; fi
fi
exec /bin/bash "$@"
SH
chmod +x "$X"
sed -i "s|\"/bin/sh\"|\"$X\"|g" "$D/pass_run.py"
python3 - "$D/passes_test.py" "$X" "$D/pass_run.py" "$MODE" <<'PY'
import re, sys
p, x, pr, mode = sys.argv[1:]; t = open(p).read()
old = '"GEN=../../stub/gen.py"]'; assert t.count(old) >= 1
t = t.replace(old, f'"GEN=../../stub/gen.py", "SHELL={x}"]')
t, k = re.subn(r"for check in \(transcripts,[^)]*\)\)", "for check in (transcripts,))", t); assert k == 1
open(p, "w").write(t)
if mode == "no-gen-record":
    s = open(pr).read()
    old = "record.update(gen_signal=os.WTERMSIG(status), gen_core=os.WCOREDUMP(status))"
    assert s.count(old) == 1; open(pr, "w").write(s.replace(old, "pass  # planted"))
PY
( cd "$D" && TMPDIR="$D.tmp" python3 passes_test.py >"$R/e1-exec-sh-$MODE.log" 2>&1; echo "rc=$?" >"$R/e1-exec-sh-$MODE.rc" )
echo "== exec-ing /bin/sh, $MODE: $(cat "$R/e1-exec-sh-$MODE.rc")"; grep '^\[' "$R/e1-exec-sh-$MODE.log" | cut -c1-150
grep 'engine passes test' "$R/e1-exec-sh-$MODE.log"
