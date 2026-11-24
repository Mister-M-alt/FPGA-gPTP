#!/bin/bash
# sample.sh TREES_DIR OUT RUNS...: every 10 s until every RUN has an rc file, log for each run the
# number of live Vengine_sim processes whose working directory is in its tree, with their CPU lists.
set -u
D=$1; O=$2; shift 2
while :; do
  done_all=1
  for r in "$@"; do [ -f "$D/../runs/$r/rc" ] || done_all=0; done
  ts=$(date +%s)
  for r in "$@"; do
    n=0; cpus=
    for p in $(pgrep -x Vengine_sim); do
      cwd=$(readlink "/proc/$p/cwd" 2>/dev/null) || continue
      case "$cwd" in "$D/$r/"*) n=$((n+1)); cpus="$cpus $(taskset -pc "$p" 2>/dev/null | sed 's/.*: //')";; esac
    done
    echo "$ts $r sims=$n cpus=[${cpus# }]"
  done >> "$O"
  [ $done_all = 1 ] && break
  sleep 10
done
