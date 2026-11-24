[A10] Manager round for R925-4 (FPGA-gPTP PR #112)
Head: a54e9eee922cb632364e864b2bce6aaf06c9c6ea (one commit on dcf1caef)

- F1 MINOR: check 7's reference line is 'exec python3 -c ...', so it dies of the signal itself whether /bin/sh forks or execs; the docstring and PR claims now say so.
- F2 MINOR: reraise() lowers the soft core limit to 1 (or 0 where the hard limit is 0), which suppresses a dump on a piped and on a file core_pattern. New check 8: a crafted {signal: SIGSEGV, core: false} record replayed under a one-byte caller limit vs an exec'd serial line under the same limit: identical ('Segmentation fault', no '(core dumped)'). Plant: limit 0 -> check 8 FAILS (receipts/passes-test-plant-nocore.log).
- R1-R4 residues: exact fixes (matrix wording, 'about 90 seconds', obj_dir/engine-passes/ + relative core_pattern, source comment). R5: body states six runs at f1b566a, three at dcf1cae, four at this head. R6: tools/logcmp4.py is round 4's comparison tool (round 3's logcmp.py masks plus that round's clone paths); it removes only host text.
- S1 taken: a finished pass's pid file is removed. S4 taken: no line over 120 columns in either file.
- passes-test: 72 checks, PASS on four runs (pt-i1..i4). make docs exit 0; make lint 0 errors.
