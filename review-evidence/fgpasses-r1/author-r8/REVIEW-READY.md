[A10] Manager round for R925-6 (FPGA-gPTP PR #112)
Head: a2352e723b481b011b32b0f6892a7920a079443b (one commit on dfd13a10)

- F1 MINOR, option (b): the soft core limit fallback is removed from reraise() (prctl alone suppresses the dump), with its docstring and PR-body mentions; the PR's plant list drops the soft-limit plant: thirteen, each caught at this head (the prctl plant: receipts/passes-test-plant-prctl2.log, 3 FAIL under ulimit -c 0).
- R1: module docstring item 6 says 'relative file core_pattern'. R2: the body's run history is exact (this head: two runs plus one under ulimit -c 0, receipts pt-l1, pt-l2, pt-l0). S1 taken: check 8 labels the clamped limit ('0 (clamped to the hard limit)' under ulimit -c 0).
- passes-test 73 checks PASS (three runs incl. ulimit -c 0); make docs exit 0; make lint 0 errors.
