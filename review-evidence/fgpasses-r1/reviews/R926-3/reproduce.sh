#!/bin/sh
# Usage: sh reproduce.sh CHECKOUT PACKET
set -eu
checkout=$1
packet=$2
mkdir -p "$packet/scratch" "$packet/receipts"
python3 "$packet/fetch_public.py" "$packet"
cd "$checkout"
export TMPDIR="$packet/scratch" PYTHONDONTWRITEBYTECODE=1
set +e
make -j16 docs > "$packet/receipts/docs.log" 2>&1
result=$?
printf '%s\n' "$result" > "$packet/receipts/docs.rc"
set -e
test "$result" -eq 0
python3 "$packet/verify_review.py" "$checkout" "$packet" > "$packet/receipts/verification.log" 2>&1
printf '0\n' > "$packet/receipts/verification.rc"
