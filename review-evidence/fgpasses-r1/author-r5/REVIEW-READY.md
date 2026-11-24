[A10] Manager round for R925-3 (FPGA-gPTP PR #112)
Head: dcf1caef6966221fda86684bf6406fe3134a0b11 (one commit on f1b566a8)

- F1 MINOR: the generator runs under Popen + waitpid; a shell that forked reports 128+n (kept as the exit status); a shell that died of the signal itself (one that execs the line, e.g. dash) is recorded as gen_signal/gen_core and replay-gen re-raises it through the same reraise() the simulator uses (core limit from the record, re-raised from obj_dir/engine-passes). No 128+n synthesis remains. Comment corrected.
- New check 7 (both forms, SIGSEGV and SIGKILL): a crafted record of a generator signal death, replayed under make, gives the same stderr and rc as a recipe line that dies of the signal (receipts/passes-test-pt-g1.log: 'Segmentation fault (core dumped)' and 'Killed' on both sides). Plant: the re-raise removed -> both check-7 cases FAIL (receipts/passes-test-plant-gensig.log).
- F2 MINOR: body -j1 CPU figure +3.6 %.
- R1 RESIDUE: body opening lists the five commits and the head; Measured heading names its base/head. R2 RESIDUE: passes_test.py docstring lists checks 6 and 7 and the generator SIGSEGV plan.
- passes-test: 71 checks, PASS on three runs (pt-g1..3). make docs exit 0; make lint 0 errors.
