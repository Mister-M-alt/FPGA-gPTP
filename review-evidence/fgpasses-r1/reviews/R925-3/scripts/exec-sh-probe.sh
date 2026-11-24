#!/bin/bash
# Emulates a /bin/sh that execs a one-command -c line instead of forking it (the behaviour of dash 0.5.11+),
# for make's SHELL and pass_run.py's /bin/sh alike, on the generator plans of passes_test.py's check 1.
# usage: exec-sh-probe.sh CLONE PACKET
set -u
CLONE=$1; PACKET=$2; D=$PACKET/scratch/mut/e1-exec-sh; R=$PACKET/receipts/mutants
rm -rf "$D" "$D.tmp"; cp -r "$CLONE/tb/verilator/engine" "$D"; mkdir -p "$D.tmp" "$R"; X="$D/xsh"
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
python3 - "$D/passes_test.py" "$X" <<'PY'
import sys
p, x = sys.argv[1], sys.argv[2]; t = open(p).read()
t = t.replace('"GEN=../../stub/gen.py"]', f'"GEN=../../stub/gen.py", "SHELL={x}"]')
t = t.replace('for check in (transcripts, budget, fail_fast, signals, unprintable, replay_cwd)', 'for check in (transcripts,)')
keep = ('"clean"', '"pass 2 image refused"', '"pass 1 image generator SIGSEGV"', '"pass 2 SIGSEGV"')
out, inplans = [], False
for l in t.split("\n"):
    if l.startswith("PLANS = {"): inplans = True; out.append(l); continue
    if inplans and l.startswith("}"): inplans = False
    if inplans and not any(l.strip().startswith(k) for k in keep): continue
    out.append(l)
open(p, "w").write("\n".join(out))
PY
( cd "$D" && TMPDIR="$D.tmp" python3 passes_test.py >"$R/e1-exec-sh.log" 2>&1; echo "rc=$?" >"$R/e1-exec-sh.rc" )
cat "$R/e1-exec-sh.rc"; grep '^\[' "$R/e1-exec-sh.log" | cut -c1-120
