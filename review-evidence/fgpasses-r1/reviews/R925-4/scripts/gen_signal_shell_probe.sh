#!/usr/bin/env bash
# Probe: an image generator killed by SIGSEGV, replayed by pass_run.py, against the serial recipe line,
# under the host's /bin/sh (which execs the line) and under an emulated shell that forks it (exit 128+n).
# Also runs passes_test.py's check-7 shape (crafted gen_signal record vs a shell recipe line) under the
# forking shell. Usage: gen_signal_shell_probe.sh CLONE WORKDIR
set -u
clone=$1; work=$2
rm -rf "$work"; mkdir -p "$work"; cd "$work" || exit 2
cat > forksh <<'SH'
#!/usr/bin/bash
# a /bin/sh that forks its -c command and reports a signal death as 128+n
[ "$1" = -c ] && shift
/usr/bin/bash -c "$1"
exit $?
SH
chmod +x forksh
cat > segv.py <<'PY'
import os, signal, sys
print("gen: about to die", file=sys.stderr)
os.kill(os.getpid(), signal.SIGSEGV)
PY
for sh in host fork; do
  d=$work/$sh; mkdir -p $d/obj_dir/engine-passes; cd $d || exit 2
  touch obj_dir/engine-passes/build.ok
  sed "s#\"/bin/sh\"#\"$( [ $sh = fork ] && echo $work/forksh || echo /bin/sh )\"#g" "$clone/tb/verilator/engine/pass_run.py" > pass_run.py
  shellset=$( [ $sh = fork ] && echo "SHELL := $work/forksh" || echo "" )
  printf '%s\nserial:\n\t@python3 %s/segv.py -o seedrun/x >/dev/null\n' "$shellset" "$work" > Makefile.serial
  printf '%s\nproduct:\n\t@python3 pass_run.py run 1 --mkdir seedrun --gen %s --shell true\n\t@python3 pass_run.py replay-gen 1\n' \
    "$shellset" "'python3 $work/segv.py -o seedrun/x'" > Makefile.product
  printf '%s\ncheck7:\n\t@python3 -c '"'"'import os; os.kill(os.getpid(), 11)'"'"'\n' "$shellset" > Makefile.check7
  ( ulimit -c 0; make --no-print-directory -f Makefile.serial > serial.out 2> serial.err; echo $? > serial.rc )
  rm -rf obj_dir/engine-passes/1.*; ( ulimit -c 0; make --no-print-directory -f Makefile.product > product.out 2> product.err; echo $? > product.rc )
  cp obj_dir/engine-passes/1.json product.record.json
  ( ulimit -c 0; make --no-print-directory -f Makefile.check7 > check7.out 2> check7.err; echo $? > check7.rc )
  printf '{"gen_signal": 11, "gen_core": false}' > obj_dir/engine-passes/1.json
  printf 'crafted:\n\t@python3 pass_run.py replay-gen 1\n' > Makefile.crafted
  ( ulimit -c 0; make --no-print-directory -f Makefile.crafted > crafted.out 2> crafted.err; echo $? > crafted.rc )
  echo "== shell=$sh"
  echo "record: $(cat product.record.json)"
  for f in serial product check7 crafted; do echo "$f rc=$(cat $f.rc) stderr=$(tr '\n' '|' < $f.err)"; done
  a=$(sed 's/Makefile[.a-z0-9]*:[0-9]*: [a-z0-9]*/MK/' serial.err); b=$(sed 's/Makefile[.a-z0-9]*:[0-9]*: [a-z0-9]*/MK/' product.err)
  [ "$a" = "$b" ] && [ "$(cat serial.rc)" = "$(cat product.rc)" ] && echo "product == serial: YES" || echo "product == serial: NO"
  a=$(sed 's/Makefile[.a-z0-9]*:[0-9]*: [a-z0-9]*/MK/' check7.err); b=$(sed 's/Makefile[.a-z0-9]*:[0-9]*: [a-z0-9]*/MK/' crafted.err)
  [ "$a" = "$b" ] && [ "$(cat check7.rc)" = "$(cat crafted.rc)" ] && echo "check-7 shape passes: YES" || echo "check-7 shape passes: NO"
  cd "$work"
done
