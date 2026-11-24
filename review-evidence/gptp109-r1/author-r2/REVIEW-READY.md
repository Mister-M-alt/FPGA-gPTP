# [A836] FPGA-gPTP #109, round 2: REVIEW READY (delta from 8e4889b)

- Repository: Mister-M-alt/FPGA-gPTP, PR #110. Branch `109-negative-delay-clamp`, base `main` 1213ac5b.
- Head: 74830c2 (`74830c2f73a3001da7325e84e8fe19a161383f82`). Local only; origin still has 8e4889b.
- Replies to R921-1 (NEGATIVE: F1 MINOR, F2 RESIDUE, S1, S2) and R922-1 (POSITIVE).
- PR body: `PR-BODY.md` (full replacement). Receipts: `receipts/INDEX.md`.

## New commits on 8e4889b

- f5d28f5 Name the edition of the setMDSyncReceive clause the link delay section cites (802.1AS-2011 11.2.13.2.1 f))
- 74830c2 Judge the most positive link delay the wire can make the plane compute a bad exchange, and control the verdict's 64-bit width (#109)

`git diff --stat 8e4889b..74830c2`: `docs/INTEGRATION.md` 2 +-, `tb/verilator/engine/p109_mutants.py` +8, `tb/verilator/engine/sim_main.cpp` +30 -2.
No generator, RTL or ROM image changes.

## Findings

| Finding | What was done | Evidence |
|---|---|---|
| F1 MINOR: the reproduction figure "24" came from an earlier harness | Re-ran the reproduction with the committed harness against the 1213ac5b ROM (image md5 a9fd0a0f…, unchanged RTL). 8e4889b harness: 2296 checks, 2265 PASS, **31 FAIL**, all prefixed `#109 `. This matches R921-1's `repro_suite.txt` line for line, got/exp values included. Head harness: 2302 checks, 2271 PASS, the same 31 FAIL lines. The PR body's figure and list are corrected: 31, with "its offset is not exact" added and the unfloored publication at -801, -5 ms and the wire minimum named. It also says where the 24 came from. | `receipts/repro_1213ac5b.txt` |
| F2 RESIDUE: `docs/INTEGRATION.md:978` cited no edition | The line now reads exactly "That follows 802.1AS-2011 11.2.13.2.1 f)." `make docs` passes (source evidence 20 exact). | f5d28f5; `receipts/repo_gates.txt` |
| S1: no trial pins the verdict's 64-bit width | Taken. Phase 64 adds "#109 the most positive delay of the wire", a `PD_WIRE` exchange with t2 at 0x7FFFFFFF s plus 2^32 - 1 ns and t3 seconds 0x80000000. The plane computes +2,147,483,649,647,485,841 ns. Checks: the plane computes above 2^60 ns, asCapable falls, the next Follow_Up is not used, then capable again. That is 6 new checks per pass. A ninth control, "the verdict reads D - 801 from bit 31" (R921-1's probe R5), is caught by both named checks. | 74830c2; `receipts/engine_suite.txt`, `receipts/arm_p109_controls.txt` |
| S2: generator header has no #109 entry; v4 paragraph and the phase-22 function name keep the old wording | Not taken (not in this round's brief). It would be a comment and identifier change only, with no ROM effect. Listed for a later round or the residue checklist. | — |

## Re-run at the head 74830c2

- Engine suite, all four passes: 2302/2302, 2302/2302, 2302/2302, 61/61. rc 0.
- The nine #109 controls: unmutated control PASS, 9/9 caught, each failing every check it names.
- The 12 existing arm entries that name a whole-run grade (`#82 every commit naming thisClock…`, `#84 …`, `#85 …`): unmutated control PASS, 12/12 caught.
  - The new trial runs before those grades, so only these entries could change verdict.
- `make docs`, `make contract`, `make lint`: rc 0.
- Parent (scratch, gitlink staged at 74830c2): C++ idiom, hygiene, Python idiom, TODO ownership, naming, fail-fast and test-evidence ratchets pass.

## Not re-run at the head (stated in the PR body)

- The other 155 arm entries (175/175 at 8e4889b).
  - They name only checks graded before the new trial. The harness is deterministic and has no host deadline: every wait is bounded in DUT cycles.
  - The stimulus before the new trial is unchanged, so their verdicts cannot change, except through a crash inside the new trial. None was seen in the 21 entries re-run.
- OOC synthesis, the ucpu, parser, gaskets, tsngen and bench gates, and the parent simulation gates.
  - All ran at 8e4889b. The ROM and RTL are byte-identical since then, and none of these reads the changed files.
