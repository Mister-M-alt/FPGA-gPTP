[A10] Manager round for R926-2 (FPGA-gPTP PR #112)
Head: 0ba80c4f1a7e506a9bc727f162582bfc6212f771 (one docs commit on 661e4c3a)

- F1 MAJOR: issue #111 criterion 2 amended publicly by its author (https://github.com/Mister-M-alt/FPGA-gPTP/issues/111#issuecomment-7145509264; issue body edited): work = retired user instructions within +1% at matching flags; CPU seconds recorded, not the gate. Round 4's receipts (author-r2/receipts/gptp/summary.txt): -j4 +0.29%, -j1 +0.04%. PR body Measured section updated.
- F2 MINOR: docs/TEST_DEVELOPER.md takes the reviewer's exact sentences (the 10-word gate dropped 'in order', the reviewer's own text).
- Gates: make docs PASS (receipts/docs-gate.txt); no code change (receipts/diff.txt).
