[A10] Manager round for R925-2 (FPGA-gPTP PR #112)
Head: f1b566a881573611637e7bd6ecd257799b8c991c (one commit on 0ba80c4f)

- F1 MINOR: pass_run.py replay chdirs to obj_dir/engine-passes before re-raising, so a file core_pattern writes the interpreter's core there; passes-test check 6 'a replayed signal death is re-raised from obj_dir/engine-passes' (probe: pass_run's own replay with os.kill recording its cwd). PR body 'Core dumps' item states both core_pattern cases.
- F2 MINOR: the generator runs as the serial line itself (its >/dev/null included) through /bin/sh, so a signal death ends as the shell reported it serially (Error 139); a negative status maps to 128+n as a fallback. New plan 'pass 1 image generator SIGSEGV' compared with the serial recipe under no option, -s, -i, -k at -j4 and at -j1.
- F3 MINOR: already fixed at 0ba80c4f (the body's CPU paragraph: pairs +30.3/-16.5/-24.2 %, -j1 +3.5 %; #111 criterion 2 amended to instructions).
- Two races found by the new plan and repeated runs, closed: (a) a finished pass now ignores SIGUSR1 (Python's shutdown restores SIG_DFL, so a late stop killed pass 3 as 'User defined signal 1': receipts/passes-test-pt1.log); (b) a signal arriving between the simulator's fork and its registration is forwarded after registration (TERM to make alone hung past 20 s once: receipts/passes-test-pt-r4.log).
- passes-test: 69 checks, PASS on six consecutive runs (receipts/passes-test-pt-s1..6.log). Plants: the old generator call (5 FAIL) and no chdir (check 6 FAIL) caught (receipts/passes-test-plant-*.log). make docs, make lint: exit 0.
