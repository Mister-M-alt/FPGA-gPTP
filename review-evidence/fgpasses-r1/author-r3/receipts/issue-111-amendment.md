[A10] Acceptance amendment, criterion 2: the CPU metric. I made this change as the issue's author, in response to R926-2-F1 on #112.

**Problem.** "CPU stays within a few percent" was meant to say that running the passes at once adds no work. CPU seconds can't show that on the shared build host. Hyperthread siblings are busy there, so the same instructions cost a different number of cycles each run. The base also runs on one core while the head runs on four.

Round 4's receipts show the spread. Total CPU went −24 %, −17 % and +30 % across three `-j4` pairs, all at identical instruction counts. Run to run, that noise swamps any bound of a few percent.

**Criterion 2 now reads:**

2. Wall time falls by the measured amount. The work does not grow, measured as retired user instructions (`perf stat -e instructions:u`) over the whole suite. At matching flags (`-j1` and `-j4`), the head stays within +1 % of the serial recipe. CPU seconds and cycles are still recorded and published for every pair, favourable and unfavourable, but they are not the gate.

**Measured against the new criterion** (#112 round 4, `review-evidence/fgpasses-r1/author-r2/receipts/gptp/summary.txt`), base 1213ac5 against head 661e4c3:
- `-j4`: 7.518 T against 7.540 T instructions, +0.29 %.
- `-j1`: 7.518 T against 7.521 T, +0.04 %.
- Every transcript is identical to the serial run.
