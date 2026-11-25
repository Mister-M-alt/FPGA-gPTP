#!/usr/bin/env python3
"""Probe F1/F2: replay a {signal: SIGSEGV, core: false} record through pass_run.py at several caller
core limits and report the kernel's core-dumped bit, against an exec'd non-dumpable and a dumpable
reference.  usage: probe_nocore.py PASS_RUN SCRATCH"""
import json, os, resource, signal, subprocess, sys
from pathlib import Path

INF = resource.RLIM_INFINITY
tool, scratch = Path(sys.argv[1]).resolve(), Path(sys.argv[2])
limits = {"(0,0)": (0, 0), "(0,inf)": (0, INF), "(1,inf)": (1, INF), "(inf,inf)": (INF, INF)}
segv = int(signal.SIGSEGV)
forms = {
    "replay": [sys.executable, str(tool), "replay", "0"],
    "nondumpable": [sys.executable, "-c", f"import ctypes,os; ctypes.CDLL(None).prctl(4,0,0,0,0); os.kill(os.getpid(),{segv})"],
    "dumpable": [sys.executable, "-c", f"import os; os.kill(os.getpid(),{segv})"],
}
hard0 = resource.getrlimit(resource.RLIMIT_CORE)[1]
print(f"core_pattern={Path('/proc/sys/kernel/core_pattern').read_text().strip()!r} caller_hard={'inf' if hard0 == INF else hard0}")
bad = 0
for name, lim in limits.items():
    if hard0 != INF and (lim[1] == INF or lim[0] == INF):
        print(f"{name}: SKIP (hard limit {hard0} cannot be raised)"); continue
    row = {}
    for form, argv in forms.items():
        d = scratch / f"{form}-{name.strip('()').replace(',', '_')}"
        st = d / "obj_dir" / "engine-passes"; st.mkdir(parents=True, exist_ok=True)
        (st / "build.ok").touch(); (st / "0.log").write_bytes(b"")
        (st / "0.json").write_text(json.dumps({"signal": segv, "core": False}))
        pid = os.fork()
        if pid == 0:
            os.chdir(d); resource.setrlimit(resource.RLIMIT_CORE, lim)
            os.execv(argv[0], argv)
        _, status = os.waitpid(pid, 0)
        row[form] = (os.WTERMSIG(status) if os.WIFSIGNALED(status) else None, bool(os.WCOREDUMP(status)))
        # make's own report at the same limit
        (d / "Makefile").write_text("all:\n\t@" + " ".join(f"'{a}'" for a in argv) + "\n")
        r = subprocess.run(["make", "--no-print-directory"], cwd=d, capture_output=True, text=True,
                           env={**os.environ, "MAKEFLAGS": ""},
                           preexec_fn=lambda lim=lim: resource.setrlimit(resource.RLIMIT_CORE, lim))
        row[form + "_make"] = r.stderr.strip()
    ok = row["replay"] == row["nondumpable"] == (segv, False) and row["replay_make"] == row["nondumpable_make"]
    bad += not ok
    print(f"{name}: {'PASS' if ok else 'FAIL'} replay={row['replay']} nondumpable={row['nondumpable']} "
          f"dumpable={row['dumpable']} | make: {row['replay_make']!r} / {row['nondumpable_make']!r} / {row['dumpable_make']!r}")
print("probe:", "PASS" if not bad else f"{bad} FAIL")
sys.exit(1 if bad else 0)
