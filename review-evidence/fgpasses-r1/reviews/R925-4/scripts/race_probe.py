#!/usr/bin/env python3
"""Deterministic probes for pass_run.py's two signal-race fixes.

usage: race_probe.py PASS_RUN.py WORKDIR ITERATIONS

late-stop: a pass running a simulator that ends at once (`true`) gets one SIGUSR1 (the fail-fast stop) every
  millisecond from the moment its pid file exists until it exits, so stops land in its exit and interpreter
  shutdown; it must still exit 0 and write its record, never die of SIGUSR1. (An unthrottled flood instead makes
  Python's handler re-enter itself until RecursionError, which is not a delivery pass_run.py can see: stop_later
  sends a pass at most three stops.)
early-signal: SIGTERM reaches the pass inside subprocess.Popen, after the simulator is forked but before the pass
  has registered it; the simulator (a unique sleep of about 30 s) must still be stopped and the pass die of SIGTERM within 10 s.
"""
import json, os, signal, subprocess, sys, time
from pathlib import Path

tool, work, iterations = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), int(sys.argv[3])

def fresh(name):
    d = work / name
    subprocess.run(["rm", "-rf", str(d)], check=True)
    (d / "obj_dir" / "engine-passes").mkdir(parents=True)
    (d / "obj_dir" / "engine-passes" / "build.ok").touch()
    return d

late = {"exit0+record": 0, "other": []}
for i in range(iterations):
    d = fresh("late")
    proc = subprocess.Popen([sys.executable, str(tool), "run", "3", "--", "true"], cwd=d)
    pidfile = d / "obj_dir" / "engine-passes" / "3.pid"
    while proc.poll() is None:
        if pidfile.exists():
            try:
                os.kill(proc.pid, signal.SIGUSR1)
            except OSError:
                pass
            time.sleep(0.001)
    rc = proc.wait()
    rec = (d / "obj_dir" / "engine-passes" / "3.json")
    if rc == 0 and rec.exists() and json.loads(rec.read_text()).get("exit") == 0:
        late["exit0+record"] += 1
    else:
        late["other"].append(rc)

probe = r'''
import os, runpy, signal, subprocess, sys, time
real = subprocess.Popen
class Early(real):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        os.kill(os.getpid(), signal.SIGTERM)  # arrives before the pass has registered this child
        time.sleep(0.01)
subprocess.Popen = Early
sys.argv = [TOOL, "run", "0", "--", "sleep", SIMSECS]
runpy.run_path(TOOL, run_name="__main__")
'''.replace("TOOL", repr(str(tool)))
simsecs = f"30.{os.getpid()}"  # unique, so the cleanup below never touches another probe's simulator
probe = probe.replace("SIMSECS", repr(simsecs))
early = {"died TERM <10s": 0, "other": []}
for i in range(max(1, iterations // 10)):
    d = fresh("early")
    t = time.monotonic()
    try:
        rc = subprocess.run([sys.executable, "-c", probe], cwd=d, timeout=10).returncode
    except subprocess.TimeoutExpired:
        rc = "hung >10s"
    subprocess.run(["pkill", "-x", "-f", f"sleep {simsecs}"])
    if rc == -signal.SIGTERM:
        early["died TERM <10s"] += 1
    else:
        early["other"].append(rc)
    early.setdefault("max_s", 0)
    early["max_s"] = max(early["max_s"], round(time.monotonic() - t, 2))

print(f"{tool}: late-stop {late}; early-signal {early}")
