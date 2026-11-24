# Receipts: FPGA-gPTP #109, round 2 ([A836])

- Head: 74830c2 on `109-negative-delay-clamp`. The previous head was 8e4889b; the base is `main` 1213ac5b.
- Local only, not pushed.
- All files are plain text. Scratch paths are rewritten to `<SCRATCH>`, `<PARENT_SCRATCH>` and `<VERILATOR_PREFIX>`.
- Every run used Verilator 5.050, through the pinned wrapper, in `git archive` extractions. The lane checkout was never built in.

| File | What it shows |
|---|---|
| `repro_1213ac5b.txt` | F1. The committed harness against the 1213ac5b ROM image (md5 a9fd0a0f6586a04bc2f2ef19422a8017). At 8e4889b's harness: 2296 checks, 2265 PASS, 31 FAIL. At the head's harness: 2302 checks, 2271 PASS, 31 FAIL. Both lists are identical, all 31 lines are prefixed `#109 `, and 7 of them are "its offset uses the delay exactly" (got 0xb). It also explains the earlier 24. |
| `engine_suite.txt` | The engine suite at 74830c2, four passes: 2302, 2302, 2302 and 61, 0 FAIL, rc 0. It includes the INFO lines for the most negative and most positive wire delays. |
| `arm_p109_controls.txt` | The nine #109 controls at 74830c2: the unmutated control passes and 9/9 are caught. The ninth, "the verdict reads D - 801 from bit 31" (S1), fails both checks it names. The scratch driver is included. |
| `arm_wholerun.txt` | The 12 existing arm entries whose named checks include a whole-run grade, which runs after the new trial, at 74830c2: the unmutated control passes and 12/12 are caught. |
| `repo_gates.txt` | `make docs`, `make contract` and `make lint` at 74830c2, all rc 0 (F2: source evidence 20 exact). It also has the diff stat (no generator, RTL or ROM change) and the parent submodule-scanning ratchets with the gitlink staged at 74830c2. |

The round-1 receipts (`../../round1/receipts/`) still cover what this round did not re-run. These are OOC synthesis, the ucpu, parser, gaskets, tsngen and bench gates, the full arm at 8e4889b (175/175), the parent simulation gates and `clauses.txt`.

Scratch (not copied): `$VALIDATION_STORAGE/gptp109-a836/r2` holds the logs, the extractions and the driver.
