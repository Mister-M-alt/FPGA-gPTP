#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""#102, #104: neither concurrency nor ccache may change a mutation arm's answer.

usage: mutation_jobs_test.py <driver> [--out DIR]

Runs one mutation arm six times, at `--jobs 1` and at `--jobs 8`, each with
ccache off (`OBJCACHE=`), cold and warm, and compares what every run prints
with what the first, `--jobs 1` with ccache off, printed, byte for byte:
every verdict line, every named failure line, their order and the tally, on
stdout and on stderr, and the exit status. Every run is real: every mutant
is planted, built and graded in each.

Equal output is not enough on its own, because runs that all abort early
also agree. So each run must also print exactly one verdict line
(`[PASS] ` or `[FAIL] `) per entry - the control and each of the driver's
`MUTATIONS` - and end with a tally of that many checks. Each cache must
also be what its run is called. An off run's cache directory stays empty.
A cold run starts from an empty cache and compiles into it. A warm run
starts from a copy of the cache the `--jobs 8` cold run left, and takes
every compilation from it although every build runs in new temporary
directories, so build paths do not defeat the cache.

The runs share the host. The `--jobs 1` runs off and cold start at once,
beside the `--jobs 8` cold run; once that ends, the `--jobs 1` warm run
starts, and the other two `--jobs 8` runs follow one after the other. So
at most 3 + 8 mutants run at once. The serial runs take as long as the
whole arm did before #102, so `make all` leaves this test out and runs
`mutation_order_test.py` instead; the arm's own Makefile names both.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mutation_verdict import TALLY  # noqa: E402

#: (name, --jobs, cache) of each run, the reference first; the cache is
#: "off", "cold" (an empty cache) or "warm" (WARM_FROM's cache, copied)
RUNS = (
    ("jobs1-off", 1, "off"),
    ("jobs8-off", 8, "off"),
    ("jobs1-cold", 1, "cold"),
    ("jobs8-cold", 8, "cold"),
    ("jobs1-warm", 1, "warm"),
    ("jobs8-warm", 8, "warm"),
)
#: the cold run whose cache each warm run starts from
WARM_FROM = "jobs8-cold"
VERDICT_PREFIXES = ("[PASS] ", "[FAIL] ")
#: ccache's counters of compilations it answered from the cache, and not
HITS = ("direct_cache_hit", "preprocessed_cache_hit")
MISSES = ("cache_miss",)

#: what one run returned: (rc, stdout, stderr, wall seconds)
Run = tuple[int, bytes, bytes, float]


def entries_of(driver: Path) -> int:
    """The verdicts a full run prints: the control and each mutant."""
    spec = importlib.util.spec_from_file_location("arm_under_test", driver)
    arm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arm)
    return 1 + len(arm.MUTATIONS)


def run_env(cache: str, cache_dir: Path) -> dict[str, str]:
    """This environment, with only the run's own ccache settings.

    Every CCACHE_* variable of the caller's is dropped, so the runs differ
    in nothing but OBJCACHE and their own cache directory; the driver
    applies its own defaults to the rest.
    """
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("CCACHE_") and k != "OBJCACHE"}
    env["OBJCACHE"] = "" if cache == "off" else "ccache"
    env["CCACHE_DIR"] = str(cache_dir)
    return env


def run(driver: Path, jobs: int, env: dict[str, str]) -> Run:
    """(rc, stdout, stderr, wall seconds) of one run of the driver."""
    start = time.monotonic()
    out = subprocess.run([sys.executable, str(driver), "--jobs", str(jobs)],
                         cwd=str(driver.parent), env=env, capture_output=True)
    return out.returncode, out.stdout, out.stderr, time.monotonic() - start


def ccache(cache_dir: Path, *args: str) -> str:
    """ccache's own output for `args` on the cache in `cache_dir`."""
    return subprocess.run(["ccache", *args], env={**os.environ, "CCACHE_DIR": str(cache_dir)},
                          capture_output=True, text=True, check=True).stdout


def counters(cache_dir: Path) -> dict[str, int]:
    """ccache's nonzero counters for the cache in `cache_dir`."""
    stats = {}
    for line in ccache(cache_dir, "--print-stats").splitlines():
        key, _, value = line.partition("\t")
        if value.isdigit() and int(value) and not key.endswith("_timestamp"):
            stats[key] = int(value)
    return stats


def count(stats: dict[str, int], keys: tuple[str, ...]) -> int:
    """The sum of `stats` over `keys`."""
    return sum(stats.get(key, 0) for key in keys)


def verdict_lines(stdout: bytes) -> list[bytes]:
    """The lines of `stdout` that give one entry's verdict."""
    return [line for line in stdout.splitlines()
            if line.startswith(tuple(p.encode() for p in VERDICT_PREFIXES))]


def run_all(driver: Path, caches: dict[str, Path]) -> dict[str, Run]:
    """Every one of `RUNS`, scheduled as the module docstring says."""
    spec = {name: (jobs, cache) for name, jobs, cache in RUNS}
    runs: dict[str, Run] = {}

    def go(name: str) -> None:
        """Run `name` on its own cache directory and keep what it returned."""
        jobs, cache = spec[name]
        runs[name] = run(driver, jobs, run_env(cache, caches[name]))

    with ThreadPoolExecutor(max_workers=3) as pool:
        serial = [pool.submit(go, "jobs1-off"), pool.submit(go, "jobs1-cold")]
        go(WARM_FROM)
        for name in ("jobs1-warm", "jobs8-warm"):
            shutil.copytree(caches[WARM_FROM], caches[name])
            ccache(caches[name], "--zero-stats")
        serial.append(pool.submit(go, "jobs1-warm"))
        go("jobs8-warm")
        go("jobs8-off")
        for future in serial:
            future.result()
    return {name: runs[name] for name, _, _ in RUNS}


def cache_checks(caches: dict[str, Path]) -> list[tuple[bool, str]]:
    """Each cache is what its run is called: off, cold or warm."""
    checks: list[tuple[bool, str]] = []
    stats = {name: counters(caches[name]) for name, _, cache in RUNS if cache != "off"}
    compiled = count(stats[WARM_FROM], HITS + MISSES)
    for name, _, cache in RUNS:
        if cache == "off":
            left = sorted(caches[name].rglob("*"))
            checks.append((not left, f"{name}: ccache wrote nothing ({len(left)} files)"))
            continue
        print(f"INFO {name}: ccache " + ", ".join(f"{k} {v}" for k, v in sorted(stats[name].items())))
        hits, misses = count(stats[name], HITS), count(stats[name], MISSES)
        if cache == "cold":
            checks.append((0 < misses and hits + misses == compiled,
                           f"{name}: {compiled} compilations, {misses} into the empty cache "
                           f"(got {hits + misses}, {misses})"))
        else:
            checks.append((misses == 0 and hits == compiled > 0,
                           f"{name}: all {compiled} compilations from the warm cache "
                           f"(got {hits} hits, {misses} misses)"))
    return checks


def main(argv: list[str] | None = None) -> int:
    """Run the arm as `RUNS` lists and compare; 0 when every check holds."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("driver", type=Path, help="the arm's mutants.py")
    parser.add_argument("--out", type=Path,
                        help="also write each run's stdout and stderr here")
    args = parser.parse_args(argv)
    driver = args.driver.resolve()
    want = entries_of(driver)
    if shutil.which("ccache") is None:
        print("FAIL ccache is not on PATH, so no run can use a cache")
        return 1

    with tempfile.TemporaryDirectory(prefix="mutation-jobs-") as td:
        caches = {name: Path(td) / name for name, _, _ in RUNS}
        for name, _, cache in RUNS:
            if cache != "warm":
                caches[name].mkdir()
        runs = run_all(driver, caches)
        checks = cache_checks(caches)

    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        for name, (_, stdout, stderr, _) in runs.items():
            (args.out / f"{name}.stdout").write_bytes(stdout)
            (args.out / f"{name}.stderr").write_bytes(stderr)

    ref_name = RUNS[0][0]
    ref_rc, ref_out, ref_err, _ = runs[ref_name]
    for name, (rc, stdout, _, wall) in runs.items():
        print(f"INFO {name}: exit {rc}, {len(stdout)} bytes, sha256 "
              f"{hashlib.sha256(stdout).hexdigest()}, "
              f"{len(verdict_lines(stdout))} verdicts, {wall:.0f} s")
    for name, (rc, stdout, stderr, _) in runs.items():
        if name != ref_name:
            checks += [
                (rc == ref_rc, f"{name}: the exit status is {ref_name}'s ({rc} and {ref_rc})"),
                (verdict_lines(stdout) == verdict_lines(ref_out),
                 f"{name}: the verdict list is {ref_name}'s, byte for byte"),
                (stdout == ref_out, f"{name}: stdout is {ref_name}'s, byte for byte"),
                (stderr == ref_err, f"{name}: stderr is {ref_name}'s, byte for byte"),
            ]
        lines = len(verdict_lines(stdout))
        tallies = list(TALLY.finditer(stdout.decode("utf-8", "replace")))
        total = int(tallies[-1].group(1)) if tallies else None
        checks += [(lines == want, f"{name}: prints {want} verdict lines (got {lines})"),
                   (total == want, f"{name}: tallies {want} checks (got {total})")]

    for ok, what in checks:
        print(f"{'PASS' if ok else 'FAIL'} {what}")
    for name, (_, stdout, _, _) in runs.items():
        if stdout != ref_out:
            sys.stdout.writelines(difflib.unified_diff(
                ref_out.decode("utf-8", "replace").splitlines(keepends=True),
                stdout.decode("utf-8", "replace").splitlines(keepends=True),
                ref_name, name))
    failed = sum(not ok for ok, _ in checks)
    print(f"{len(checks)} checks: {len(checks) - failed} PASS, {failed} FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
