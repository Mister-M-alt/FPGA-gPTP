#!/bin/bash
# compare.sh RUNS SERIAL PARALLEL: compare two run directories' transcripts after norm.py (host
# text only), first exactly, then with make's recipe location masked; print both make statuses.
set -u
R=$1; S=$2; Q=$3; N=$(dirname "$0")/norm.py
a=$(mktemp); b=$(mktemp)
python3 -I "$N" "$R/$S/log" > "$a"; python3 -I "$N" "$R/$Q/log" > "$b"
m() { sed -E 's/^make: \*\*\* \[Makefile:[0-9]+: run\]/make: *** [Makefile:<L>: run]/' "$1"; }
if cmp -s "$a" "$b"; then x=IDENTICAL; else x=DIFFER; fi
if cmp -s <(m "$a") <(m "$b"); then y=IDENTICAL; else y=DIFFER; fi
echo "$S vs $Q: $(wc -l < "$a") vs $(wc -l < "$b") normalised lines; exact $x; with make's recipe line number masked $y"
echo "  $S: make rc=$(cat "$R/$S/rc"); $(grep -E '^make: \*\*\*' "$a" || echo 'no make error line'); $(grep wall "$R/$S/time")"
echo "  $Q: make rc=$(cat "$R/$Q/rc"); $(grep -E '^make: \*\*\*' "$b" || echo 'no make error line'); $(grep wall "$R/$Q/time")"
diff <(m "$a") <(m "$b") | head -20 | sed 's/^/  | /'
rm -f "$a" "$b"
