"""Recompute the criterion-2 figures from the author's published summary.txt. usage: python3 -I figures.py SUMMARY"""
import sys
rows = {}
for line in open(sys.argv[1]):
    f = line.split()
    if len(f) == 7 and f[-1].startswith("rc="):
        rows[f[0]] = {"cpu": float(f[3]), "cyc": float(f[4][:-1]), "ins": float(f[5][:-1])}
pct = lambda a, b: 100 * (a / b - 1)
for head, base in (("c-head-j4", "c-base-j4"), ("r-head-j4", "r-base-j4"), ("r-head-j4-b", "r-base-j4"), ("c-head-j1", "c-base-j1")):
    h, b = rows[head], rows[base]
    print(f"{head} vs {base}: instructions {pct(h['ins'], b['ins']):+.3f} %  CPU {pct(h['cpu'], b['cpu']):+.3f} %  cycles {pct(h['cyc'], b['cyc']):+.2f} %")
