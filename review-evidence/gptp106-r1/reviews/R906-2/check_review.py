#!/usr/bin/env python3
"""Read-only review probes. Usage: python3 check_review.py REPOSITORY.

All disposable extractions live beside this script under scratch/.
Requires the published evidence commit and the reviewed history in REPOSITORY.
"""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
REPO = Path(sys.argv[1]).resolve()
HEAD = "331e27de137a1d4f7acd4f3f2cc7e373b6e8e869"
EVIDENCE = "2c2ba060bc802cef25ccb95767d657d4e3c6b260"
PREFIX = "review-evidence/gptp106-r1/"
sys.dont_write_bytecode = True

def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args])

def check(ok, text):
    print(("PASS " if ok else "FAIL ") + text, flush=True)
    if not ok:
        raise AssertionError(text)

def load(path):
    spec = importlib.util.spec_from_file_location("review_subject", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def extract(ref, dest):
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(git("archive", ref))) as archive:
        archive.extractall(dest, filter="data")

def table(ref):
    dest = ROOT / "scratch" / ("source-" + ref)
    extract(ref, dest)
    driver = dest / "tb/verilator/engine/mutants.py"
    code = "import runpy,json; d=runpy.run_path(" + repr(str(driver)) + "); print(json.dumps([d[\"MUTATIONS\"],d[\"P100_MUTATIONS\"]]))"
    tables = json.loads(subprocess.check_output([sys.executable, "-B", "-c", code]))
    return tables[0], tables[1], dest

check(git("rev-parse", "HEAD").decode().strip() == HEAD, "exact head")
check(git("rev-parse", "HEAD^{tree}").decode().strip() == "7b579e33a97ff4f2bec8c0064f0f73c862bbb135", "exact tree")
check(git("rev-parse", "HEAD:hdl") == git("rev-parse", "a728cc3:hdl"), "unchanged hdl tree since preceding review")
check(not git("diff", "a728cc3", HEAD, "--", "*.hex"), "unchanged committed images since preceding review")

manifest = json.loads(git("show", EVIDENCE + ":" + PREFIX + "MANIFEST.json"))
counts = {}
for entry in manifest:
    name = entry["file"]
    if not name.startswith(("author/", "author-r3/")):
        continue
    raw = git("show", EVIDENCE + ":" + PREFIX + name)
    check(hashlib.sha256(raw).hexdigest() == entry["published_sha256"], "published digest " + name)
    counts[name.split("/")[0]] = counts.get(name.split("/")[0], 0) + 1
print("Verified publication counts " + json.dumps(counts, sort_keys=True))
commit = git("cat-file", "commit", EVIDENCE)
print("Publication commit signature present: " + str(b"\ngpgsig " in commit))

old, old100, _ = table("a728cc3")
main, main100, _ = table("7cfd6a0")
head, head100, work = table(HEAD)
check(old == head, "all 167 predecessor mutation tuples retained byte-for-byte, including order and named checks")
mainmap = {m[0]: m for m in main}
headmap = {m[0]: m for m in head}
check(all(m[0] in headmap and m == headmap[m[0]] for m in main if m not in main100), "all main controls outside the previously reviewed #100 retargeting retained exactly")
check(head100 == old100, "#100 retargeting unchanged from predecessor, including renamed and combined word-3 controls")
print(f"Mutation counts: main {len(main)}, predecessor {len(old)}, head {len(head)}; #100 main {len(main100)}, head {len(head100)}")
check(len(head) == 167 and len(headmap) == 167, "167 unique mutation names")

arm = load(work / "tb/verilator/engine/mutants.py")
checks = 0
for m in arm.P106_MUTATIONS + arm.P107_MUTATIONS:
    wants = m[4].split(" | ")
    full = "".join("FAIL " + w + "\n" for w in wants)
    check(arm.named_verdict("caught", m[4], full, lambda _: None) == "caught", "all-named control accepts complete evidence: " + m[0])
    for omit in range(len(wants)):
        partial = "".join("FAIL " + w + "\n" for i, w in enumerate(wants) if i != omit)
        check(arm.named_verdict("caught", m[4], partial, lambda _: None) != "caught", "all-named control rejects missing check: " + wants[omit])
        checks += 1
print("Named-check omissions rejected: " + str(checks))

receipts = ROOT / "scratch" / PREFIX / "author-r3/receipts"
gate = (receipts / "gates-331e27d.txt").read_text()
reported = re.findall(r'^\[PASS\] mutant caught: (.*?) - breaks "(.*)"$', gate.split("## verdict counts over both halves")[0], re.M)
check(reported == [(m[0], m[4]) for m in head], "published split-arm receipts cover exact table and named checks once, in order")
check(gate.count("[PASS] the unmutated engine still passes the harness") == 2, "both split-arm receipts have positive controls")

gen = load(work / "hdl/ucode/gen_gptp_ucode.py")
b = gen.LOCAL_CLOCK_PPM_C * 1e-6
fast = ((1 + b) / (1 - b) - 1) * 1e6
slow = ((1 - b) / (1 + b) - 1) * 1e6
print(f"Corners: {fast:+.6f}, {slow:+.6f} ppm")
doc = (REPO / "docs/INTEGRATION.md").read_text()
for hz in (50_000_000, 100_000_000, 125_000_000, 2_000_000):
    clamp = gen.ppm_addend(gen.RATE_PPM_C, hz)
    envelope = clamp * hz / (2**24 * 1000)
    gap = fast - envelope
    seconds = gen.STEP_LOCKED_NS_C / (gap * 1000)
    check(f"{envelope:.6f}" in doc and f"{gap:.6f}" in doc and f"{seconds:,.0f}" in doc, f"documented envelope at {hz} Hz: {envelope:.6f} ppm, gap {gap:.6f} ppm, interval {seconds:,.0f} s")
    check(abs(slow) < envelope < fast, "slow corner inside, fast corner outside")

env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(ROOT / "scratch"))
order = subprocess.run([sys.executable, "-B", str(work / "tb/mutation_order_test.py"), str(work / "tb/verilator/engine/mutants.py")], env=env, capture_output=True, text=True)
(ROOT / "order-check.txt").write_text(order.stdout + order.stderr + f"\nexit_status={order.returncode}\n")
check(order.returncode == 0, "merged ordering check passes at jobs 1 and 8")
print("COMPLETE")
