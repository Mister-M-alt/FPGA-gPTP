#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""#104: a fast check, inside `make all`, that a mutation arm prints in list order.

usage: mutation_order_test.py <driver>

`mutation_jobs_test.py` runs the whole arm six times and takes hours, so
`make all` leaves it out. This check runs the arm's own `main` in this
process, at `--jobs 1` and at `--jobs 8`, with its build, its ROM images
and its harness run replaced by stubs. Each entry sleeps a seeded
pseudo-random time, so the entries finish out of list order, and then
returns output that fails every check the entry names, which the arm reads
as caught. Everything else is the arm's own code: staging, the pattern
check, the verdict rules, the per-entry directories, the ordering and the
tally.

Both runs must print the same bytes: one `[PASS] ` line per entry, in list
order, and a tally of that many checks. No two entries may share a run
directory, and at `--jobs 8` the entries must really have finished out of
list order, or the check proved nothing. Nothing is built or simulated.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import random
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

#: the two --jobs values compared
JOBS = (1, 8)
#: the longest stub delay, in seconds
MAX_DELAY_S = 0.02
#: the delays' seed, so a failure reproduces
SEED = 104


def load(driver: Path) -> ModuleType:
    """The arm under test, imported from its own file."""
    spec = importlib.util.spec_from_file_location("arm_under_test", driver)
    arm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arm)
    return arm


def tag_of(name: str) -> str:
    """A mutant's directory tag, as the arm derives it from its name."""
    return "".join(c if c.isalnum() else "_" for c in name)


class Stubs:
    """The arm's build, ROM images and harness run, replaced.

    `rundirs` records every directory a harness run was handed, and
    `finished` the order in which the entries' runs returned.
    """

    def __init__(self, arm: ModuleType) -> None:
        self.breaks = {tag_of(m[0]): m[4] for m in arm.MUTATIONS}
        rng = random.Random(SEED)
        self.delay = {tag: rng.uniform(0, MAX_DELAY_S) for tag in self.breaks}
        self.lock = threading.Lock()
        self.rundirs: list[Path] = []
        self.finished: list[str] = []
        arm.build = self.build
        arm.generate_image = self.generate_image
        arm.run_harness = self.run_harness

    def build(self, srcdir: Path, work: Path, tag: str) -> Path:
        """The executable path a real build would return, unbuilt."""
        return work / f"obj_{tag}" / f"Vengine_{tag}"

    def generate_image(self, srcdir: Path, rundir: Path) -> bool:
        """No image is written; the stub harness reads none."""
        return True

    def run_harness(self, exe: Path, rundir: Path) -> tuple[int, str]:
        """The control passes; a mutant fails each check its entry names."""
        tag = rundir.name.removeprefix("run_")
        with self.lock:
            self.rundirs.append(rundir)
        if tag == "clean":
            return 0, "1 checks: 1 PASS, 0 FAIL\n"
        time.sleep(self.delay[tag])
        with self.lock:
            self.finished.append(tag)
        wants = self.breaks[tag].split(" | ")
        fails = "".join(f"FAIL {want}\n" for want in wants)
        return 1, f"{fails}{len(wants)} checks: 0 PASS, {len(wants)} FAIL\n"


def main(argv: list[str] | None = None) -> int:
    """Run the arm at each of `JOBS` under the stubs; 0 when every check holds."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("driver", type=Path, help="the arm's mutants.py")
    args = parser.parse_args(argv)
    arm = load(args.driver.resolve())
    entries = 1 + len(arm.MUTATIONS)
    expected = ["[PASS] the unmutated engine still passes the harness"] + [
        f"[PASS] mutant caught: {m[0]} - breaks \"{m[4]}\"" for m in arm.MUTATIONS]
    in_order = [tag_of(m[0]) for m in arm.MUTATIONS]

    checks: list[tuple[bool, str]] = []
    outs: dict[int, str] = {}
    for jobs in JOBS:
        stubs = Stubs(arm)
        buf = io.StringIO()
        start = time.monotonic()
        with contextlib.redirect_stdout(buf):
            rc = arm.main(["--jobs", str(jobs)])
        outs[jobs] = buf.getvalue()
        verdicts = [line for line in outs[jobs].splitlines()
                    if line.startswith(("[PASS] ", "[FAIL] "))]
        print(f"INFO --jobs {jobs}: exit {rc}, {len(outs[jobs])} bytes, "
              f"{len(verdicts)} verdicts, {time.monotonic() - start:.1f} s")
        checks += [
            (rc == 0, f"--jobs {jobs} exits 0 (got {rc})"),
            (verdicts == expected,
             f"--jobs {jobs} prints {entries} [PASS] lines in list order"),
            (outs[jobs].endswith(f"\n{entries} checks: {entries} PASS, 0 FAIL\n"),
             f"--jobs {jobs} tallies {entries} checks"),
            (len(set(stubs.rundirs)) == len(stubs.rundirs) == entries,
             f"--jobs {jobs} gives each of the {entries} entries its own run "
             f"directory (got {len(set(stubs.rundirs))})"),
        ]
        if jobs > 1:
            checks.append((stubs.finished != in_order,
                           f"--jobs {jobs}: the entries finished out of list order"))
    checks.append((outs[JOBS[0]] == outs[JOBS[1]],
                   f"--jobs {JOBS[0]} and --jobs {JOBS[1]} print the same bytes"))

    for ok, what in checks:
        print(f"{'PASS' if ok else 'FAIL'} {what}")
    failed = sum(not ok for ok, _ in checks)
    print(f"{len(checks)} checks: {len(checks) - failed} PASS, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
