#!/bin/bash
# Disposable mutation and shell-emulation probes of the #111 delta, each in its own copy of tb/verilator/engine.
# usage: mutants.sh CLONE PACKET
set -u
CLONE=$1; PACKET=$2; S=$PACKET/scratch/mut; R=$PACKET/receipts/mutants
rm -rf "$S"; mkdir -p "$S" "$R"
mk() { rm -rf "$S/$1"; cp -r "$CLONE/tb/verilator/engine" "$S/$1"; mkdir -p "$S/$1.tmp"; }
probe() { ( cd "$S/$1" && TMPDIR="$S/$1.tmp" python3 passes_test.py >"$R/$1.log" 2>&1; echo "rc=$?" >"$R/$1.rc" ) & }
# M1: the generator line without its serial redirection (the code before the delta)
mk m1-no-redirect; sed -i 's| + " >/dev/null"||' "$S/m1-no-redirect/pass_run.py"
# M2: a shell signal death recorded as the raw negative return code
mk m2-raw-returncode; sed -i 's|record\["gen"\] = done.returncode if done.returncode >= 0 else 128 - done.returncode|record["gen"] = done.returncode|' "$S/m2-raw-returncode/pass_run.py"
# M3: replay re-raises without moving to obj_dir/engine-passes
mk m3-no-chdir; sed -i '/os.chdir(STATE)/d' "$S/m3-no-chdir/pass_run.py"
# M4: SIGUSR1 left at its handler after the pass ends
mk m4-no-usr1-ignore; sed -i '/signal.signal(signal.SIGUSR1, signal.SIG_IGN)/d' "$S/m4-no-usr1-ignore/pass_run.py"
# M5: a signal received before the child was known is not forwarded to it
mk m5-no-early-forward; sed -i '/signal_all(child\[0\].pid, received\[0\])/d;/            if received:$/d' "$S/m5-no-early-forward/pass_run.py"
# E1: a /bin/sh that execs a one-command -c line (as dash 0.5.11+ does), for make and pass_run alike; generator plans only
mk e1-exec-sh; X="$S/e1-exec-sh/xsh"
printf '%s\n' '#!/bin/bash' 'if [ "$1" = -c ] && [[ "$2" != *"&&"* && "$2" != *";"* && "$2" != *"|"* ]]; then exec /bin/bash -c "exec $2"; fi' 'exec /bin/bash "$@"' >"$X"; chmod +x "$X"
sed -i "s|\"/bin/sh\"|\"$X\"|g" "$S/e1-exec-sh/pass_run.py"
python3 - "$S/e1-exec-sh/passes_test.py" "$X" <<'PY'
import sys
p, x = sys.argv[1], sys.argv[2]; t = open(p).read()
t = t.replace('"GEN=../../stub/gen.py"]', f'"GEN=../../stub/gen.py", "SHELL={x}"]')
t = t.replace('for check in (transcripts, budget, fail_fast, signals, unprintable, replay_cwd)', 'for check in (transcripts,)')
import re
keep = ('"clean"', '"pass 2 image refused"', '"pass 1 image generator SIGSEGV"')
lines = t.split("\n"); out = []; inplans = False
for l in lines:
    if l.startswith("PLANS = {"): inplans = True; out.append(l); continue
    if inplans and l.startswith("}"): inplans = False
    if inplans and not any(l.strip().startswith(k) for k in keep): continue
    out.append(l)
open(p, "w").write("\n".join(out))
PY
probe m1-no-redirect; probe m2-raw-returncode; probe m3-no-chdir; probe m4-no-usr1-ignore; probe m5-no-early-forward; probe e1-exec-sh
wait
for f in "$R"/*.rc; do echo "$(basename "$f" .rc) $(cat "$f") $(grep -c '^\[FAIL\]' "${f%.rc}.log") FAIL"; done
