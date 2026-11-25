#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""#111: `make run`'s scheduled passes against the serial recipe, with stub tools.

usage: passes_test.py

Copies this Makefile and pass_run.py into a scratch tree, beside a reference
Makefile whose `run` is the serial recipe the passes replaced, and runs both
with a stub Verilator, a stub image generator and a stub simulator. Each stub
pass prints to standard output and standard error and ends as a plan says.
The checks:

1. The transcript and the exit status equal the serial recipe's, byte for
   byte apart from the recipe line numbers in make's own messages, for a clean
   run, a failing pass at each position, two failing passes, a pass killed by
   SIGSEGV, SIGABRT and SIGKILL, a failing image generator, an image
   generator killed by SIGSEGV and a failing build; each with no option, -s,
   -i and -k at -j4, and again at -j1 with no option. Standard output and
   standard error are compared apart, with only the tree's own path and
   make's recipe line numbers masked. The clean -j4 run must have finished
   its passes out of order, or the ordering was not exercised.
2. The job budget: at most one pass at a time at -j1, two at -j2, four at
   -j4 (and four reached), and under a parent make at -j3 whose two other
   targets hold job slots, at most three jobs at once in all.
3. Fail fast: when pass 1 fails, passes 2 and 3 are stopped at -j4 and never
   start at -j1.
4. INT, TERM, QUIT and HUP to make's process group, and TERM to make alone,
   leave no stub simulator running.
5. A pass's kept transcript that cannot be read back fails the run with a
   diagnostic, after the passes before it and with nothing after it.
6. A replayed signal death is re-raised from obj_dir/engine-passes/, so a
   file core_pattern never replaces the simulator's core.
7. An image generator whose shell died of a signal (a shell that execs the
   line, as dash does) ends as the serial line did: make reports the signal
   for SIGSEGV and SIGKILL. A crafted record stands in for the run, so the
   check holds on any host's /bin/sh. The reference line execs its process,
   so it dies of the signal itself whether the shell forks or not.
8. A replayed signal death that did not dump core ends as a non-dumpable
   serial death does, under caller core limits of 0 and of 1, on a piped
   core_pattern too.
Nothing is built or simulated; it takes about 90 seconds.
"""

from __future__ import annotations

import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
START = "# #111: the four passes are independent"
END = "# #111: the serial order, the budget"
SERIAL = """run: gptp_ucode.hex
\t$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vengine_sim
\t./obj_dir/Vengine_sim
\t@mkdir -p seedrun
\t@python3 $(GEN) $(GENARGS) --seq-seed 0x200000 -o seedrun/gptp_ucode.hex >/dev/null
\t@echo "-- again, with the request counter seeded above 16 bits --"
\t@cd seedrun && ../obj_dir/Vengine_sim
\t@mkdir -p syncseedrun
\t@python3 $(GEN) $(GENARGS) --sync-seq-seed 0x10000 -o syncseedrun/gptp_ucode.hex >/dev/null
\t@echo "-- again, with the Sync counter seeded above 16 bits --"
\t@cd syncseedrun && ../obj_dir/Vengine_sim
\t@mkdir -p p1run
\t@python3 $(GEN) $(GENARGS) --p1 255 --clock-accuracy 0xFE -o p1run/gptp_ucode.hex >/dev/null
\t@echo "-- the self publication again, not grandmaster-capable (priority1 255), clockAccuracy 0xFE --"
\t@cd p1run && ../obj_dir/Vengine_sim +not-gm-capable

"""
SIM = r'''#!/usr/bin/env python3
import fcntl, json, os, signal, sys, time
plan = json.loads(os.environ["STUB_PLAN"])
n = {"engine": 0, "seedrun": 1, "syncseedrun": 2, "p1run": 3}[os.path.basename(os.getcwd())]
assert (n == 3) == ("+not-gm-capable" in sys.argv[1:])
me = plan.get(str(n), {})
def event(what):
    with open(os.environ["STUB_EVENTS"], "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps({"what": what, "job": f"pass{n}", "pid": os.getpid(), "t": time.monotonic()}) + "\n")
def die(signum, _frame):
    event("end")
    signal.signal(signum, signal.SIG_DFL)
    os.kill(os.getpid(), signum)
for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGQUIT, signal.SIGHUP):
    signal.signal(signum, die)
event("start")
print(f"pass {n}: first line", flush=True)
print(f"pass {n}: a note on standard error", file=sys.stderr, flush=True)
time.sleep(me.get("sleep", 0.3 - 0.07 * n))
if me.get("unreadable"):
    os.chmod(f"{'.' if n == 0 else '..'}/obj_dir/engine-passes/{n}.log", 0)
print(f"pass {n}: 12 checks: {12 - bool(me.get('exit'))} PASS, {int(bool(me.get('exit')))} FAIL", flush=True)
event("end")
if "signal" in me:
    signal.signal(me["signal"], signal.SIG_DFL)
    os.kill(os.getpid(), me["signal"])
sys.exit(me.get("exit", 0))
'''
VERILATOR = r'''#!/usr/bin/env python3
import json, os, shutil, sys
print("stub verilator: Vengine_sim from", len(sys.argv) - 1, "arguments")
if json.loads(os.environ["STUB_PLAN"]).get("build"):
    print("%Error: stub verilator: a planted build failure", file=sys.stderr)
    sys.exit(1)
os.makedirs("obj_dir", exist_ok=True)
shutil.copy(os.environ["STUB_SIM"], "obj_dir/Vengine_sim")
os.chmod("obj_dir/Vengine_sim", 0o755)
'''
GEN = r'''import json, os, signal, sys
out = sys.argv[sys.argv.index("-o") + 1]
if json.loads(os.environ["STUB_PLAN"]).get("gensig") == os.path.dirname(out):
    os.kill(os.getpid(), signal.SIGSEGV)
if json.loads(os.environ["STUB_PLAN"]).get("gen") == os.path.dirname(out):
    print(f"gen_gptp_ucode: a planted refusal for {out}", file=sys.stderr)
    sys.exit(1)
print("image written", out)
open(out, "w").write("0\n")
'''
HOG = r'''import fcntl, json, os, sys, time
def event(what):
    with open(os.environ["STUB_EVENTS"], "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps({"what": what, "job": sys.argv[1], "pid": os.getpid(), "t": time.monotonic()}) + "\n")
event("start"); time.sleep(float(sys.argv[2])); event("end")
'''
TOP = """.PHONY: all engine hog1 hog2
all: engine hog1 hog2
engine:
\t+$(MAKE) --no-print-directory -C engine run
hog1 hog2:
\tpython3 ../stub/hog.py $@ 1.5
"""
PLANS = {
    "clean": {},
    "pass 0 fails": {"0": {"exit": 1}},
    "pass 1 fails": {"1": {"exit": 1}},
    "pass 3 fails": {"3": {"exit": 1}},
    "passes 1 and 2 fail": {"1": {"exit": 3}, "2": {"exit": 7}},
    "pass 2 SIGSEGV": {"2": {"signal": signal.SIGSEGV}},
    "pass 1 SIGABRT": {"1": {"signal": signal.SIGABRT}},
    "pass 3 SIGKILL": {"3": {"signal": signal.SIGKILL}},
    "pass 2 image refused": {"gen": "syncseedrun"},
    "pass 1 image generator SIGSEGV": {"gensig": "seedrun"},
    "build fails": {"build": 1},
}
LINE = re.compile(r"(make(?:\[\d+\])?: (?:\*\*\* )?\[)[^\]:]+:\d+: run\]")


def norm(text: str, engine: Path) -> str:
    """Only host text differs: the tree's own path (the build's -I$(CURDIR)) and make's recipe line numbers."""
    return LINE.sub(r"\1MK: run]", text.replace(str(engine), "<engine>"))


def tree(scratch: Path) -> dict[str, Path]:
    """Scratch engines: `serial` with the serial recipe, `parallel` with this one; shared stubs."""
    stub = scratch / "stub"
    stub.mkdir()
    for name, text in (("sim.py", SIM), ("verilator.py", VERILATOR), ("gen.py", GEN), ("hog.py", HOG)):
        (stub / name).write_text(text)
    (stub / "verilator.py").chmod(0o755)
    real = (HERE / "Makefile").read_text()
    assert real.count(START) == 1 and real.count(END) == 1, "the Makefile's #111 anchors moved"
    serial = real[:real.index(START)] + SERIAL + real[real.index(END):]
    trees = {}
    for name, text in (("serial", serial), ("parallel", real)):
        engine = scratch / name / "engine"
        engine.mkdir(parents=True)
        (engine / "Makefile").write_text(text)
        shutil.copy(HERE / "pass_run.py", engine)
        trees[name] = engine
    (scratch / "parallel" / "Makefile").write_text(TOP)
    return trees


def make(engine: Path, flags: list[str], plan: dict, events: Path, stdout: int | None = None,
         directory: Path | None = None, target: str = "run") -> subprocess.CompletedProcess:
    """One make run with the stubs; its captured streams and status."""
    stub = engine.parents[1] / "stub"
    env = {**os.environ, "STUB_PLAN": json.dumps(plan), "STUB_EVENTS": str(events),
           "STUB_SIM": str(stub / "sim.py"), "MAKEFLAGS": ""}
    env.pop("MAKELEVEL", None)
    args = ["make", *flags, target, "VERILATOR=../../stub/verilator.py", "GEN=../../stub/gen.py"]
    subprocess.run(["make", "-s", "clean"], cwd=engine, check=True, env=env)
    return subprocess.run(args, cwd=directory or engine, env=env, text=True, preexec_fn=no_cores, timeout=120,
                          stdout=subprocess.PIPE if stdout is None else stdout, stderr=subprocess.PIPE)


def no_cores() -> None:
    """No core files, INT and QUIT at their defaults, as from a terminal."""
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGQUIT, signal.SIG_DFL)


def read(events: Path) -> list[dict]:
    return [json.loads(line) for line in events.read_text().splitlines()] if events.exists() else []


def peak(events: list[dict]) -> int:
    """The most jobs running at once."""
    live, most = 0, 0
    for event in sorted(events, key=lambda e: (e["t"], e["what"] == "start")):
        live += 1 if event["what"] == "start" else -1
        most = max(most, live)
    return most


def transcripts(trees: dict[str, Path], scratch: Path) -> int:
    """Check 1: the scheduled run prints and ends as the serial recipe did."""
    bad = 0
    for plan_name, plan in PLANS.items():
        for mode in ([], ["-s"], ["-i"], ["-k"]):
            for jobs in (["-j4"], ["-j1"]) if not mode else (["-j4"],):
                events = scratch / "events.jsonl"
                events.unlink(missing_ok=True)
                want = make(trees["serial"], [*jobs, *mode], plan, events)
                events.unlink(missing_ok=True)
                got = make(trees["parallel"], [*jobs, *mode], plan, events)
                same = (got.returncode == want.returncode
                        and norm(got.stdout, trees["parallel"]) == norm(want.stdout, trees["serial"])
                        and norm(got.stderr, trees["parallel"]) == norm(want.stderr, trees["serial"]))
                label = f"{plan_name}, make {' '.join(jobs + mode)}"
                if not same:
                    bad += 1
                    print(f"[FAIL] {label}: rc {got.returncode} vs serial {want.returncode}\n"
                          f"--- serial stdout\n{want.stdout}--- stdout\n{got.stdout}"
                          f"--- serial stderr\n{want.stderr}--- stderr\n{got.stderr}")
                else:
                    print(f"[PASS] {label}: the serial transcript and status (rc {got.returncode})")
                if plan_name == "clean" and jobs == ["-j4"] and not mode:
                    ends = [e["job"] for e in read(events) if e["what"] == "end"]
                    ordered = ends == sorted(ends)
                    bad += ordered
                    print(f"[{'FAIL' if ordered else 'PASS'}] the clean -j4 passes finished out of order: {ends}")
    return bad


def budget(trees: dict[str, Path], scratch: Path) -> int:
    """Check 2: never more jobs than the caller allowed."""
    bad = 0
    slow = {str(n): {"sleep": 0.6} for n in range(4)}
    for jobs, limit, reach in (("-j1", 1, 1), ("-j2", 2, 2), ("-j4", 4, 4)):
        events = scratch / f"budget{jobs}.jsonl"
        done = make(trees["parallel"], [jobs], slow, events)
        most = peak(read(events))
        ok = done.returncode == 0 and most <= limit and most >= reach
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] make {jobs} run: at most {most} passes at once (budget {limit})")
    events = scratch / "budget-recursive.jsonl"
    done = make(trees["parallel"], ["-j3"], slow, events, directory=trees["parallel"].parent, target="all")
    jobs = read(events)
    most = peak(jobs)
    hogs = {e["job"] for e in jobs if e["job"].startswith("hog")}
    passes = {e["job"] for e in jobs if e["job"].startswith("pass")}
    ok = done.returncode == 0 and most == 3 and hogs == {"hog1", "hog2"} and len(passes) == 4
    bad += not ok
    print(f"[{'PASS' if ok else 'FAIL'}] a parent make -j3 with two other jobs: {len(passes)} passes ran, "
          f"at most {most} jobs at once in all (budget 3, reached)")
    return bad


def fail_fast(trees: dict[str, Path], scratch: Path) -> int:
    """Check 3: the first failing pass stops the later ones."""
    bad = 0
    plan = {"0": {"sleep": 0.2}, "1": {"exit": 1, "sleep": 0.1}, "2": {"sleep": 30}, "3": {"sleep": 30}}
    for jobs in ("-j4", "-j1"):
        events = scratch / f"fast{jobs}.jsonl"
        began = time.monotonic()
        done = make(trees["parallel"], [jobs], plan, events)
        took = time.monotonic() - began
        started = sorted({e["job"] for e in read(events) if e["what"] == "start"})
        ended = sorted({e["job"] for e in read(events) if e["what"] == "end"})
        expect = ["pass0", "pass1", "pass2", "pass3"] if jobs == "-j4" else ["pass0", "pass1"]
        ok = done.returncode == 2 and took < 15 and started == expect and ended == expect
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] make {jobs}: pass 1 fails and the run ends in {took:.1f} s; "
              f"passes started {started}, all ended")
    return bad


def signals(trees: dict[str, Path], scratch: Path) -> int:
    """Check 4: an interrupt leaves no simulator running."""
    bad = 0
    plan = {str(n): {"sleep": 60} for n in range(4)}
    for signum, group in ((signal.SIGINT, True), (signal.SIGTERM, True), (signal.SIGQUIT, True),
                          (signal.SIGHUP, True), (signal.SIGTERM, False)):
        events = scratch / f"signal{signum}{group}.jsonl"
        engine = trees["parallel"]
        env = {**os.environ, "STUB_PLAN": json.dumps(plan), "STUB_EVENTS": str(events),
               "STUB_SIM": str(engine.parents[1] / "stub" / "sim.py"), "MAKEFLAGS": ""}
        subprocess.run(["make", "-s", "clean"], cwd=engine, check=True, env=env)
        proc = subprocess.Popen(["make", "-j4", "run", "VERILATOR=../../stub/verilator.py", "GEN=../../stub/gen.py"],
                                cwd=engine, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                preexec_fn=no_cores, start_new_session=True)
        deadline = time.monotonic() + 30
        while sum(e["what"] == "start" for e in read(events)) < 4 and time.monotonic() < deadline:
            time.sleep(0.05)
        (os.killpg if group else os.kill)(proc.pid, signum)
        try:
            rc = proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            rc = None
        time.sleep(0.2)
        pids = {e["pid"] for e in read(events) if e["what"] == "start"}
        alive = [pid for pid in pids if subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode == 0]
        ok = rc not in (None, 0) and len(pids) == 4 and not alive
        bad += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {signal.Signals(signum).name} to make's "
              f"{'process group' if group else 'own process'}: make ended ({rc}), {len(alive)} simulators left")
    return bad


def unprintable(trees: dict[str, Path], scratch: Path) -> int:
    """Check 5: a transcript that cannot be printed fails the run, after the passes before it."""
    done = make(trees["parallel"], ["-j4"], {"1": {"unreadable": 1}}, scratch / "unreadable.jsonl")
    ok = (done.returncode == 2 and "engine pass 1: its transcript could not be printed" in done.stderr
          and "pass 0: 12 checks: 12 PASS" in done.stdout and "pass 2:" not in done.stdout)
    print(f"[{'PASS' if ok else 'FAIL'}] pass 1's kept transcript made unreadable: rc {done.returncode}, "
          f"pass 0 printed, the diagnostic {'printed' if ok else 'missing'}, nothing after it")
    return not ok


def replay_cwd(trees: dict[str, Path], scratch: Path) -> int:
    """Check 6: a replayed signal death is re-raised from obj_dir/engine-passes/, so a relative file core_pattern
    keeps the simulator's core."""
    state = scratch / "cwd" / "obj_dir" / "engine-passes"
    state.mkdir(parents=True)
    (state / "0.json").write_text(json.dumps({"signal": int(signal.SIGSEGV), "core": True}))
    (state / "0.log").write_bytes(b"")
    (state / "build.ok").touch()
    seen = scratch / "cwd" / "seen"
    # pass_run's own replay, with os.kill recording where the death would be re-raised instead of dying there
    probe = ("import os, runpy, sys\n"
             "def kill(pid, signum):\n"
             f"    open({str(seen)!r}, 'w').write(os.getcwd())\n"
             "    os._exit(0)\n"
             "os.kill = kill\n"
             "sys.argv = ['pass_run.py', 'replay', '0']\n"
             f"runpy.run_path({str(Path(__file__).resolve().parent / 'pass_run.py')!r}, run_name='__main__')\n")
    subprocess.run([sys.executable, "-c", probe], cwd=state.parent.parent,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
    where = seen.read_text() if seen.exists() else None
    ok = where == str(state.resolve())
    print(f"[{'PASS' if ok else 'FAIL'}] a replayed signal death is re-raised from {where}")
    return not ok


def gen_signal(trees: dict[str, Path], scratch: Path) -> int:
    """Check 7: an image generator whose shell died of a signal (a shell that execs, as dash does) ends as the serial
    line did: make reports the signal, not 128+n. A crafted record stands in for the run on any host's shell."""
    bad = 0
    tool = Path(__file__).resolve().parent / "pass_run.py"
    for signum in (signal.SIGSEGV, signal.SIGKILL):
        runs = {}
        for form in ("replay", "serial"):
            d = scratch / f"gensig-{form}-{int(signum)}"
            state = d / "obj_dir" / "engine-passes"
            state.mkdir(parents=True)
            (state / "build.ok").touch()
            (state / "1.json").write_text(json.dumps({"gen_signal": int(signum), "gen_core": False}))
            line = (f"python3 {tool} replay-gen 1" if form == "replay"
                    else f"exec python3 -c 'import ctypes, os; ctypes.CDLL(None).prctl(4, 0, 0, 0, 0); "
                         f"os.kill(os.getpid(), {int(signum)})'")  # no core, as the record says
            (d / "Makefile").write_text(f"all:\n\t@{line}\n")
            runs[form] = subprocess.run(["make", "--no-print-directory"], cwd=d, capture_output=True, text=True,
                                        preexec_fn=no_cores, env={**os.environ, "MAKEFLAGS": ""})
        same = (runs["replay"].returncode == runs["serial"].returncode
                and runs["replay"].stderr == runs["serial"].stderr)
        bad += not same
        name = signal.Signals(signum).name
        print(f"[{'PASS' if same else 'FAIL'}] an image generator killed by {name} replays as the serial line "
              f"ended: {runs['replay'].stderr.strip()!r} vs {runs['serial'].stderr.strip()!r}")
    return bad


def no_core_replay(trees: dict[str, Path], scratch: Path) -> int:
    """Check 8: a replayed signal death recorded without a core ends as a non-dumpable serial death does, under a
    caller core limit of (0, 0) and of (1, unlimited hard), whatever the host's core_pattern."""
    bad = 0
    tool = Path(__file__).resolve().parent / "pass_run.py"
    die = (f"exec python3 -c 'import ctypes, os; ctypes.CDLL(None).prctl(4, 0, 0, 0, 0); "
           f"os.kill(os.getpid(), {int(signal.SIGSEGV)})'")
    for limit in ((0, 0), (1, resource.RLIM_INFINITY)):
        def caller(limit=limit) -> None:
            hard = resource.getrlimit(resource.RLIMIT_CORE)[1]
            unlimited = limit[1] == resource.RLIM_INFINITY
            want = (min(1, hard), hard) if unlimited and hard != resource.RLIM_INFINITY else limit
            resource.setrlimit(resource.RLIMIT_CORE, want)
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGQUIT, signal.SIG_DFL)
        runs = {}
        for form in ("replay", "serial"):
            d = scratch / f"nocore-{form}-{limit[0]}"
            state = d / "obj_dir" / "engine-passes"
            state.mkdir(parents=True)
            (state / "build.ok").touch()
            (state / "0.json").write_text(json.dumps({"signal": int(signal.SIGSEGV), "core": False}))
            (state / "0.log").write_bytes(b"")
            line = f"python3 {tool} replay 0" if form == "replay" else die
            (d / "Makefile").write_text(f"all:\n\t@{line}\n")
            runs[form] = subprocess.run(["make", "--no-print-directory"], cwd=d, capture_output=True, text=True,
                                        preexec_fn=caller, env={**os.environ, "MAKEFLAGS": ""})
        same = runs["replay"].returncode == runs["serial"].returncode and runs["replay"].stderr == runs["serial"].stderr
        bad += not same
        print(f"[{'PASS' if same else 'FAIL'}] a no-core signal death replays as a non-dumpable one at core limit "
              f"{limit[0]}: {runs['replay'].stderr.strip()!r} vs {runs['serial'].stderr.strip()!r}")
    return bad


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="engine-passes-test-") as name:
        scratch = Path(name)
        trees = tree(scratch)
        bad = sum(check(trees, scratch) for check in (transcripts, budget, fail_fast, signals, unprintable,
                                               replay_cwd, gen_signal, no_core_replay))
    print(f"engine passes test: {'PASS' if not bad else f'{bad} FAIL'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
