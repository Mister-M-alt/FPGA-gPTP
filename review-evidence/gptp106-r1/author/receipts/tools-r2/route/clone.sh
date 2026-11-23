#!/usr/bin/env bash
# clone.sh <name> <commit>: a clean clone of the scratch parent at <commit>, every submodule from the scratch
# parent's own module repositories (no network)
set -euo pipefail
B=/data-2/milan/tmp/gptp106-a831; P=$VALIDATION_STORAGE/scratch/gptp106-parent; n=$1; c=$2
rm -rf "$B/$n"; git clone -q "$P" "$B/$n"; cd "$B/$n"; git checkout -q "$c"
for s in external third_party/verilog-axis protocol-processor gptp-processor third_party/lwSRP third_party/tsn-c-stack; do
  git config "submodule.$s.url" "$P/.git/modules/$s"
done
git -c protocol.file.allow=always submodule update -q --init
echo "$n $(git rev-parse HEAD)"; git submodule status | cut -c1-60
