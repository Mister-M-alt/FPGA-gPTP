#!/bin/bash
# Stand-in for obj_dir/Vengine_sim. STUB_PLAN holds "dir=action" words, action one of:
#   N (exit N), sigNAME (kill itself with NAME), hang (sleep 600), slowN (sleep N, exit 0).
# Writes to stdout and stderr alternately so an interleaving change would show.
d=$(basename "$PWD"); a=0
for w in ${STUB_PLAN:-}; do [ "${w%%=*}" = "$d" ] && a=${w#*=}; done
echo "stub out 1 in $d args[$*]"; echo "stub err 1 in $d" >&2; echo "stub out 2 in $d"
case $a in
  sig*) kill -s "${a#sig}" $$ ;;
  hang) exec sleep 600 ;;
  slow*) sleep "${a#slow}"; echo "stub $d done"; exit 0 ;;
  *) [ "$a" = 0 ] && echo "1 checks: 1 PASS, 0 FAIL" || echo "FAIL stub in $d"; exit "$a" ;;
esac
