[A10] Manager round for R925-5 (FPGA-gPTP PR #112)
Head: dfd13a1079d265d68edc806b2d8111d0e5f89493 (one commit on a54e9eee)

- F1 MINOR: reraise() re-raises a no-core record non-dumpable (prctl(PR_SET_DUMPABLE, 0)), in addition to the soft limit of 1 where the hard limit allows: no dump to a pipe or a file whatever the caller's limits. Docstring and PR body say exactly that.
- F2 MINOR: check 8 no longer sets a soft limit above the hard one; it now compares, at caller limits (0, 0) and (1, unlimited), the replay of {signal: SIGSEGV, core: false} with an exec'd serial line that is itself non-dumpable. Check 7's reference is non-dumpable too, matching its record's gen_core false.
- passes-test: 73 checks, PASS on three runs and once under ulimit -c 0 (receipts/passes-test-pt-k0.log, the R925-5 setup). Plant: the prctl removed -> check 7 and both check-8 limits FAIL under ulimit -c 0 (receipts/passes-test-plant-prctl.log). make docs exit 0; make lint 0 errors; no line over 120 columns.
