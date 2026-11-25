#!/usr/bin/env bash
# End to end: an image generator killed by SIGSEGV, through `pass_run.py run --gen` + `replay-gen`, against the
# serial recipe line `python3 GEN ... >/dev/null`, with make's SHELL and pass_run.py's /bin/sh the same shell:
# the host /bin/sh, an emulated shell that forks its -c command (exit 128+n), and one that execs it (dies of the
# signal itself, as dash 0.5.11+ does). Prints the record and both endings. Usage: gen_signal_shell_probe.sh CLONE WORKDIR
set -u
clone=$1; work=$2; rm -rf "$work"; mkdir -p "$work"; cd "$work" || exit 2
printf '#!/usr/bin/bash\n[ "$1" = -c ] && shift\n/usr/bin/bash -c "$1"\nexit $?\n' > forksh
printf '#!/usr/bin/bash\n[ "$1" = -c ] && shift\nexec /usr/bin/bash -c "exec $1"\n' > execsh
chmod +x forksh execsh
printf 'import os, signal, sys\nprint("gen: about to die", file=sys.stderr)\nos.kill(os.getpid(), signal.SIGSEGV)\n' > segv.py
for sh in host fork exec; do
  case $sh in host) S=/bin/sh;; fork) S=$work/forksh;; exec) S=$work/execsh;; esac
  d=$work/$sh; mkdir -p $d/obj_dir/engine-passes; cd $d || exit 2
  touch obj_dir/engine-passes/build.ok
  sed "s#\"/bin/sh\"#\"$S\"#g" "$clone/tb/verilator/engine/pass_run.py" > pass_run.py
  # the same number of lines before each recipe line, so make's line numbers match
  printf 'SHELL := %s\nserial:\n\t@python3 %s/segv.py -o seedrun/x >/dev/null\n' "$S" "$work" > Makefile.serial
  printf 'SHELL := %s\nproduct:\n\t@python3 pass_run.py replay-gen 1\n' "$S" > Makefile.product
  ( ulimit -S -c 0; make --no-print-directory -f Makefile.serial > serial.out 2> serial.err; echo $? > serial.rc )
  ( ulimit -S -c 0; python3 pass_run.py run 1 --mkdir seedrun --gen "python3 $work/segv.py -o seedrun/x" --shell true )
  cp obj_dir/engine-passes/1.json record.json
  ( ulimit -S -c 0; make --no-print-directory -f Makefile.product > product.out 2> product.err; echo $? > product.rc )
  echo "== /bin/sh: $sh"
  echo "record: $(cat record.json)"
  for f in serial product; do echo "$f rc=$(cat $f.rc) stderr=$(sed "s#$work#W#g" $f.err | tr '\n' '|')"; done
  a=$(sed 's/Makefile[.a-z0-9]*:[0-9]*: [a-z0-9]*/MK/' serial.err); b=$(sed 's/Makefile[.a-z0-9]*:[0-9]*: [a-z0-9]*/MK/' product.err)
  [ "$a" = "$b" ] && [ "$(cat serial.rc)" = "$(cat product.rc)" ] && echo "product == serial: YES" || echo "product == serial: NO"
  cd "$work"
done
