#!/usr/bin/env python3
"""Focused review: one engine pass on head/base and two #106 controls.

All disposable files stay under packet/scratch. No checkout file is edited.
Usage: python3 reproduce.py --repo REPO --verilator EXECUTABLE --jobs 2
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile

HEAD = "a728cc3ce9d0342aa596c8170fecf1284c0b604c"
BASE = "1616fc8f062fbf58c35ad31674b5b233207bbdb8"
PACKET = Path(__file__).resolve().parent
RECEIPTS = PACKET / "receipts"
SCRATCH = PACKET / "scratch"


def command(argv, cwd, name):
    with (RECEIPTS / (name + ".log")).open("w") as log:
        result = subprocess.run(argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    (RECEIPTS / (name + ".rc")).write_text(str(result.returncode) + "\n")
    return result.returncode


def stage(repo, ref, name):
    target = SCRATCH / name
    target.mkdir(parents=True, exist_ok=True)
    data = subprocess.check_output(["git", "archive", ref], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(target, filter="data")
    return target


def build(tree, executable, name):
    work = tree / "tb/verilator/engine"
    sources = ["ucpu/gptp_ucpu_pkg.sv", "ucpu/KL_gptp_ucpu.sv",
               "wire/KL_gptp_rx_parser.sv", "wire/KL_gptp_tx_slot.sv",
               "common/KL_gptp_timer.sv", "top/KL_gptp_engine.sv"]
    argv = [executable, "--cc", "--exe", "--build", "-j", "8",
            "--top-module", "KL_gptp_engine", "-Wall", "-Wno-fatal",
            "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL", "-Wno-WIDTHEXPAND",
            "-Wno-WIDTHTRUNC", "-Wno-UNUSEDPARAM",
            '-GUCODE_HEX_P="gptp_ucode.hex"', "-GCLK_HZ_P=2000000",
            "-CFLAGS", "-std=c++17 -O2 -Wall -Wextra",
            *[str(tree / "hdl" / s) for s in sources], "sim_main.cpp",
            "-o", "Vreview"]
    assert command(argv, work, name + "-build") == 0
    return work / "obj_dir/Vreview"


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--verilator", required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    assert 1 <= args.jobs <= 2
    RECEIPTS.mkdir(exist_ok=True)
    SCRATCH.mkdir(exist_ok=True)
    version = subprocess.check_output([args.verilator, "--version"], text=True)
    assert "Verilator 5.050 " in version
    (RECEIPTS / "compiler-identity.txt").write_text(version + "sha256 " +
        hashlib.sha256(Path(args.verilator).read_bytes()).hexdigest() + "\n")
    head = stage(args.repo, HEAD, "head-engine")
    base = stage(args.repo, BASE, "base-engine")
    harness = head / "tb/verilator/engine/sim_main.cpp"
    (base / "tb/verilator/engine/sim_main.cpp").write_bytes(harness.read_bytes())
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        docs = pool.submit(command, ["make", "-j16", "docs", "contract"],
                           head, "docs-contract")
        head_build = pool.submit(build, head, args.verilator, "head")
        exe = head_build.result()
        head_run = pool.submit(command, [str(exe)], exe.parent.parent, "head-engine")
        base_exe = pool.submit(build, base, args.verilator, "base").result()
        base_run = pool.submit(command, [str(base_exe)], base_exe.parent.parent,
                               "base-with-head-harness")
        results = {"docs-contract": docs.result(), "head-engine": head_run.result(),
                   "base-with-head-harness": base_run.result()}
    # The two ROM-only #106 mutations use the exact-head model and harness.
    import sys
    sys.path.insert(0, str(head / "tb/verilator/engine"))
    from p106_mutants import P106_MUTATIONS
    futures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for i, mutation in enumerate(P106_MUTATIONS):
            name, filename, patterns, replacement, checks = mutation
            edits = patterns if replacement is None else [(patterns, replacement)]
            text = (head / "hdl" / filename).read_text()
            for old, new in edits:
                assert text.count(old) == 1
                text = text.replace(old, new)
            work = SCRATCH / ("p106-control-" + str(i))
            work.mkdir(exist_ok=True)
            generator = work / "generator.py"
            generator.write_text(text)
            assert command([sys.executable, str(generator), "--clk-hz", "2000000",
                            "--cease-ms", "3000", "-o", "gptp_ucode.hex"],
                           work, "p106-" + str(i) + "-generate") == 0
            futures.append((i, checks, pool.submit(command, [str(exe)], work,
                                                  "p106-" + str(i))))
        for i, checks, future in futures:
            rc = future.result()
            log = (RECEIPTS / ("p106-" + str(i) + ".log")).read_text()
            failed = [line for line in log.splitlines() if line.startswith("FAIL ")]
            caught = rc == 1 and all(any(check in line for line in failed)
                                     for check in checks.split(" | "))
            results["p106-" + str(i) + "-all-named-checks-caught"] = caught
    (RECEIPTS / "local-results.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
    assert results["head-engine"] == 0
    assert results["docs-contract"] == 0
    assert results["base-with-head-harness"] == 1
    assert all(results["p106-" + str(i) + "-all-named-checks-caught"] for i in range(2))


if __name__ == "__main__":
    main()
