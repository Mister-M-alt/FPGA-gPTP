#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""#102: running mutants at once must not change a mutation arm's answer.

usage: mutation_jobs_test.py <driver> [--out DIR]

Runs one mutation arm twice, with `--jobs 1` and with `--jobs 4`, and
compares what the two runs print byte for byte: every verdict line, every
named failure line, their order and the tally, on stdout and on stderr,
and the two exit statuses. Both runs are real: every mutant is planted,
built and graded in each.

Equal output is not enough on its own, because two runs that both abort
early also agree. So each run must also print exactly one verdict line
(`[PASS] ` or `[FAIL] `) per entry - the control and each of the driver's
`MUTATIONS` - and end with a tally of that many checks.

The two runs go at once, on 1 + 4 workers, since neither answer depends on
time. The serial run still takes as long as the arm did before #102, so
`make all` leaves this test out; the arm's own Makefile names it.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutation_verdict import TALLY  # noqa: E402

#: the two --jobs values compared, as #102 names them
JOBS = (1, 4)
VERDICT_PREFIXES = ("[PASS] ", "[FAIL] ")


def entries_of(driver: Path) -> int:
    """The verdicts a full run prints: the control and each mutant."""
    spec = importlib.util.spec_from_file_location("arm_under_test", driver)
    arm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arm)
    return 1 + len(arm.MUTATIONS)


def run(driver: Path, jobs: int) -> tuple[int, bytes, bytes, float]:
    """(rc, stdout, stderr, wall seconds) of one run of the driver."""
    start = time.monotonic()
    out = subprocess.run([sys.executable, str(driver), "--jobs", str(jobs)],
                         cwd=str(driver.parent), capture_output=True)
    return out.returncode, out.stdout, out.stderr, time.monotonic() - start


def verdict_lines(stdout: bytes) -> list[bytes]:
    """The lines of `stdout` that give one entry's verdict."""
    return [line for line in stdout.splitlines()
            if line.startswith(tuple(p.encode() for p in VERDICT_PREFIXES))]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("driver", type=Path, help="the arm's mutants.py")
    parser.add_argument("--out", type=Path,
                        help="also write each run's stdout and stderr here")
    args = parser.parse_args(argv)
    driver = args.driver.resolve()
    want = entries_of(driver)

    with ThreadPoolExecutor(max_workers=len(JOBS)) as pool:
        runs = dict(zip(JOBS, pool.map(lambda j: run(driver, j), JOBS)))

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        for jobs, (_, stdout, stderr, _) in runs.items():
            (args.out / f"jobs{jobs}.stdout").write_bytes(stdout)
            (args.out / f"jobs{jobs}.stderr").write_bytes(stderr)

    (rc1, out1, err1, wall1), (rc4, out4, err4, wall4) = runs[1], runs[4]
    for jobs, (rc, stdout, _, wall) in runs.items():
        print(f"INFO --jobs {jobs}: exit {rc}, {len(stdout)} bytes, sha256 "
              f"{hashlib.sha256(stdout).hexdigest()}, "
              f"{len(verdict_lines(stdout))} verdicts, {wall:.0f} s")

    checks: list[tuple[bool, str]] = [
        (rc1 == rc4, f"the exit statuses agree ({rc1} and {rc4})"),
        (verdict_lines(out1) == verdict_lines(out4),
         "the verdict lists agree byte for byte"),
        (out1 == out4, "stdout agrees byte for byte"),
        (err1 == err4, "stderr agrees byte for byte"),
    ]
    for jobs, (_, stdout, _, _) in runs.items():
        count = len(verdict_lines(stdout))
        tallies = list(TALLY.finditer(stdout.decode("utf-8", "replace")))
        total = int(tallies[-1].group(1)) if tallies else None
        checks.append((count == want,
                       f"--jobs {jobs} prints {want} verdict lines (got {count})"))
        checks.append((total == want,
                       f"--jobs {jobs} tallies {want} checks (got {total})"))

    for ok, what in checks:
        print(f"{'PASS' if ok else 'FAIL'} {what}")
    if out1 != out4:
        sys.stdout.writelines(difflib.unified_diff(
            out1.decode("utf-8", "replace").splitlines(keepends=True),
            out4.decode("utf-8", "replace").splitlines(keepends=True),
            "--jobs 1", "--jobs 4"))
    failed = sum(not ok for ok, _ in checks)
    print(f"{len(checks)} checks: {len(checks) - failed} PASS, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
