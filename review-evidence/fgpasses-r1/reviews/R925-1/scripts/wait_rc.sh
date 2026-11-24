#!/bin/bash
# wait_rc.sh SECONDS DIR...: wait up to SECONDS for every DIR/rc to exist; report which remain.
set -u
end=$(( $(date +%s) + $1 )); shift
while :; do
  left=; for d in "$@"; do [ -f "$d/rc" ] || left="$left $(basename "$d")"; done
  [ -z "$left" ] && { echo "all done"; exit 0; }
  [ "$(date +%s)" -ge "$end" ] && { echo "still running:$left"; exit 1; }
  sleep 15
done
