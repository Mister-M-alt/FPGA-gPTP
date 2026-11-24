[R921] POSITIVE - exact head 74830c2f73a3001da7325e84e8fe19a161383f82

# R921-2: narrow re-review of Mister-M-alt/FPGA-gPTP PR #110 (Closes #109), round 2

- Head: `74830c2f73a3001da7325e84e8fe19a161383f82`, tree `274dd63e5414ca64c5bd83b9df78939c8820b47e`. This is the PR's live `headRefOid`.
- Previously reviewed head: `8e4889bba462d14d4e5a34068769872510d4775d` (R921-1 NEGATIVE, R922-1 POSITIVE). Source base: `1213ac5b9e09b8759ba76cc70c53652b5e108996`.
- Scope: the delta `8e4889b..74830c2`, which is two commits:
  - f5d28f5 changes `docs/INTEGRATION.md` (+1 -1).
  - 74830c2 changes `tb/verilator/engine/sim_main.cpp` (+30 -2) and `tb/verilator/engine/p109_mutants.py` (+8).
  - It changes no generator, RTL or ROM image.
- I also checked the R921-1 items F1, F2, S1 and S2 at their cause.
- Verdict: **POSITIVE**.
  - F1 (MINOR) is resolved, F2 (RESIDUE) is resolved and S1 is taken.
  - No MINOR, MAJOR or BLOCKER is open.
  - One new RESIDUE (N1, comment and PR-body wording) and one retained SUGGESTION (S2) are recorded below. Neither blocks.
- Code the delta does not touch keeps its R921-1 lens verdict. The delta changes nothing that code depends on: the generator, the RTL and all four ROM images are byte-identical to 8e4889b.

## Reconstruction

- The repository guidance, the frozen scope (#109 body plus the manager's ruling issuecomment-7123290416) and the authorities are as reconstructed in R921-1. Nothing in the delta changes them.
- This round's public inputs:
  - The live PR #110 body.
  - The review-start comment issuecomment-7141010806.
  - The author's round-2 packet `review-evidence/gptp109-r1/author-r2` at evidence commit `5bd1a55e`.
  - The evidence `MANIFEST.json`.
- I read the prior public review (R922-1, issuecomment-7137785569) only after my own pass. It records no findings, so there is nothing of it to resolve or retain.
  - There are no formal PR reviews and no review comments.

## Evidence verification

- **Author packet.** All 9 `author-r2/` files match the `published_sha256` in the evidence `MANIFEST.json` (9/9, 0 mismatches; `receipts/evidence_verify.txt`). This is a hash manifest. No cryptographic signature was checked beyond it.
- **PR body.** The live PR #110 body equals `author-r2/PR-BODY.md` byte for byte, after stripping CRs.
- **Hosted checks.** There are none at the head: 0 check runs, 0 statuses and no tracked workflows.

## Executed evidence (reviewer runs, exact head)

- Verilator identity: `Verilator 5.050 2026-07-01 rev v5.050`, through the pinned wrapper (sha256 `905795b9…`).
- Every build ran in `git archive` extractions under `scratch/`. The clone was never built in.

| Run | Result | Receipt |
|---|---|---|
| Engine suite, `make run`, four passes | 2302/2302, 2302/2302, 2302/2302, 61/61; 0 FAIL lines; rc 0 | `receipts/head_suite.txt` |
| F1 reproduction: head harness and RTL, 1213ac5b generator and ROM image (md5 `a9fd0a0f…`, same as the author's), shipping pass | 2302 checks, 2271 PASS, **31 FAIL**, rc 2. All 31 are prefixed `#109 `. 7 are `its offset uses the delay exactly` (got `0xb`). The FAIL lines are **identical** to R921-1's `repro_suite.txt` at the 8e4889b harness. The 6 new checks pass at base. | `receipts/repro_suite.txt` |
| The nine #109 controls (`p109_mutants.py`, as committed) | Unmutated control PASS. 9/9 caught, each failing every check it names. The new ninth, "the verdict reads D - 801 from bit 31", fails both checks it names. | `receipts/arm_p109.txt` |
| The 12 existing arm entries that name a whole-run grade (indices 37, 44, 47, 58, 59, 153, 154, 155, 159, 161, 169, 171) | Unmutated control PASS, 12/12 caught | `receipts/arm_wholerun.txt` |
| Arm structure | 176 entries, 0 duplicate names, 0 pattern mismatches. The whole-run set was derived independently from the bodies of the three grade functions and is exactly the 12 above. | `receipts/arm_structure.txt` |
| Reviewer width probes (disposable, not part of the PR) | W60 (verdict reads bit 60): **caught**. W61 (bit 61): survives, as predicted. W61 is an equivalent mutant on the reachable domain, see S1. | `receipts/arm_width.txt` |
| `make docs`, `make contract`, `make lint` | rc 0, 0, 0. Source evidence: 20 exact, 0 findings. Selftest PASS. | `receipts/gates.txt` |

## Prior findings at their cause

### F1 (R921-1 MINOR, Tests and Docs): reproduction figure. RESOLVED

- **Cause.** The PR body said "24". That number came from an uncommitted harness whose background pairs used offset 0.
- **The re-run with the committed harness against the base ROM.**
  - Author: 8e4889b harness 2296/2265/31, head harness 2302/2271/31, identical lines.
  - Reviewer, at the head harness: 31 FAIL, all `#109`, the same lines as my round-1 receipt, got/exp values included.
- **The PR body now reads (`Reproduction:` paragraph):**
  - "fails 31 checks, all of them `#109` checks"
  - The list adds "its offset is not exact (the background pair's 11 ns stays published, where 0 is expected)".
  - It names the unfloored publication at -801, -5 ms and the wire minimum.
  - It explains where the 24 came from.
- Every figure in that paragraph matches my receipt, including "The 6 checks the head adds pass at 1213ac5b" (2271 = 2265 + 6).
- The base-plane values of the trials differ from the head's: -…820 vs -…821, and +2147483658237409833 vs +2147483649647485841. These come from the base plane's different ratio state, as the author's receipt says, and change no verdict.

### F2 (R921-1 RESIDUE, Docs): unqualified clause. RESOLVED

- `docs/INTEGRATION.md:978` now reads exactly "That follows 802.1AS-2011 11.2.13.2.1 f).", which is the fix R921-1 asked for.
- It is the only `11.2.13.2.1` citation in the file. `make docs` passes.

### S1 (R921-1 SUGGESTION, Tests): 64-bit verdict width. TAKEN

- **The new trial.** `judge_the_most_positive_delay_of_the_wire` (`tb/verilator/engine/sim_main.cpp:8667-8687`) sends t2 = 0x7FFFFFFF s + 0xFFFFFFFF ns and t3 seconds 0x80000000. This mirrors phase 63's wire minimum.
- **What the harness models.** The plane computes +2,147,483,649,647,485,841 ns. This is the harness's mirror `pdm.d` (`:953`), and the "above 2^60 ns" check guards the stimulus.
- **What it checks on the DUT.**
  - `pub_flags_o` asCapable falls.
  - The next Follow_Up is neither consumed nor stepped.
  - `p109_ready()` is restored afterwards.
- **Where it runs.** It is called last in phase 64 (`:8664`). After it, only the three whole-run grades run (`:504-507`).
- **The new control.** It is word-neutral (it changes only `imm=63` to `imm=31` in the `VERDICT` pattern). Its comment (`p109_mutants.py:109-110`) describes its effect correctly.
- **Strength (reviewer probes).**
  - Every delay the wire can make the datapath compute lies in (-2^61, 2^61). Phase 63 computes -2.1475e18, phase 64 +2.1475e18, and 2^61 = 2.306e18.
  - The trial's D lies between 2^60 and 2^61. So it kills every verdict that reads `D - 801` from bit 60 or below (W60 caught).
  - Reading bit 61 or 62 gives the same verdict as bit 63 for every reachable D, so W61 survives as an equivalent mutant.
  - The trial is therefore as strong as the reachable domain allows. Only the wording of one comment overstates it (N1).
- **Head code.** It is unchanged since R921-1, where I judged it correct by reading.

### S2 (R921-1 SUGGESTION, Docs/HDL): generator header. RETAINED as SUGGESTION

- The author did not take it this round and listed it for later.
- The state is unchanged:
  - There is no #109 entry in the header of `hdl/ucode/gen_gptp_ucode.py`.
  - The v4 paragraph and the phase-22 function name keep the "floor" wording.
- It does not block.

## Findings at this head

### N1 - RESIDUE - Tests, Docs: the new trial's comment overstates which narrower verdicts it catches

- **Where:**
  - `tb/verilator/engine/sim_main.cpp:8640-8641`: "the verdict reads the sign of the whole 64-bit D - 801, and a narrower one would judge such a delay good".
  - PR #110 body, Phase 64 bullet: "This pins the verdict's 64-bit width".
- **Evidence:**
  - `receipts/arm_width.txt`: a verdict reading bit 60 is caught, but one reading bit 61 survives.
  - One reading bit 61 or 62 judges this delay bad, the same as the 64-bit verdict. No reachable D tells those widths apart, because |D| < 2^61.
- **Why it is RESIDUE:**
  - The trial, its checks, the control and the measured figures are all correct and as strong as the domain allows.
  - Only the prose claims more than "narrower" can mean. No test, code, figure or clause claim changes.
- **Exact fix:**
  - **Comment.** Change "and a narrower one would judge such a delay good" to "and one that read it from bit 60 or below would judge such a delay good (bits 61 and 62 give the same verdict on every delay the wire can produce)".
  - **PR body.** Change "This pins the verdict's 64-bit width:" to "This catches any verdict that reads `D - 801` from bit 60 or below:".
  - Keep the rest of each sentence.

### Comment-rule and public-text checks (delta)

- The added source comments contain no bench lane labels, lane names, review rounds, reviewer IDs or issue-comment IDs.
  - "phase 63" and "phase 64" are the harness's own phase numbering, which the file header uses throughout (`sim_main.cpp:280-293`).
- The two commit messages, the PR body and the author-r2 packet contain no private names and no assistant tool or model names.
- No comment-rule RESIDUE.

## Reviewer-owned ledger

| Lens | State | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | CLEAN | F2 line `docs/INTEGRATION.md:978` (802.1AS-2011 11.2.13.2.1 f), setMDSyncReceive); new trial against Milan v1.2 4.2.6.1.1 (above 800 ns is a bad exchange). No generator change, so the R921-1 ruling conformance stands. | R921-2 (delta); R921-1 (untouched code) | 74830c2f73a3001da7325e84e8fe19a161383f82 |
| RTL | CLEAN | No `.sv`, generator or ROM change in `8e4889b..74830c2` (diff stat). Lint rc 0. R921-1 ROM and OOC verdicts carry over unchanged. | R921-2 (delta); R921-1 | 74830c2f73a3001da7325e84e8fe19a161383f82 |
| Robustness | CLEAN | The most positive wire delay (+2.1475e18 ns) is now exercised on the DUT and judged bad. The reachable domain is \|D\| < 2^61. Width probes W60 and W61. The plane recovers capability afterwards. | R921-2 | 74830c2f73a3001da7325e84e8fe19a161383f82 |
| Tests | CLEAN (N1 is RESIDUE) | Phase 64 new trial `sim_main.cpp:8642-8687`; suite 2302 x3 and 61; F1 reproduction 31 FAIL; 9/9 #109 controls; 12/12 whole-run entries; arm structure 176/0 mismatches; probes W60 and W61 | R921-2 | 74830c2f73a3001da7325e84e8fe19a161383f82 |
| Docs | CLEAN (N1 is RESIDUE) | `docs/INTEGRATION.md:978`; `make docs` (20 exact); live PR body (F1 figure and list); author-r2 REVIEW-READY, INDEX and receipts; harness header `:280-293`; control comment `p109_mutants.py:106-117` | R921-2 | 74830c2f73a3001da7325e84e8fe19a161383f82 |

## Real limits

- **Arm coverage at the head.** I ran 21 of the 176 entries myself at the exact head: the nine #109 controls and the 12 whole-run-grade entries.
  - The other 155 rest on the author's published full arm at 8e4889b (175/175), together with this argument:
    - Each of them names only checks graded before the new trial.
    - The stimulus before the new trial is unchanged.
    - The harness is deterministic.
  - I confirmed the ordering in the source: only the three whole-run grades run after phase 64. I also derived the whole-run set from those grade bodies.
  - A mutant that crashes or hangs only inside the new trial is not excluded by this argument. None of the 21 re-run entries did.
- **Out-of-context synthesis, ucpu/parser/gasket/tsngen/bench gates and parent consumer gates.** I did not re-run these, because no RTL or ROM changed. They rest on round-1 receipts.
  - The parent gates ran on dev-soft-core `aa30d77f` with local-only probes, not on live dev `e275d795`.
- **Clause text.** As in R921-1, I checked it against the author's public `clauses.txt` quotations, not the standards themselves.
- **No manager source bank** runs at this head, and none is claimed or inferred.
  - There are no hosted check runs or statuses at the head.
  - The author's parent ratchet receipt (gitlink staged in scratch) is author evidence only.
- **Physical calibration** was not run. Simulation and field skips are not hardware proof.

## Pending manager duties

- **Merge candidate.** Build and validate the current-dev merge candidate (builder and native banks) at the merge turn. The source base is 1213ac5b and live dev is e275d795. Link the receipts on the PR. The manager also owns hosted and act acceptance.
- **Issue #109 REVIEW READY.** The round-1 REVIEW READY comment there (issuecomment-7136540865) still reads "Against 1213ac5b these phases fail 24 checks". The corrected round-2 REVIEW READY exists only in the evidence packet.
  - Publish it on #109, or note on #109 that the 24 is superseded by 31, so the issue's latest author statement matches the PR body.
- **Residue checklist.** Carry N1 there, and S2 optionally.
- **Parent gitlink bump.** The duties listed in R921-1 still stand:
  - Refresh the donor links and the submodule-boundaries diagram.
  - Run the imported-gPTP docs gate, the submodule docs gate and the C++ idiom ratchet.
  - Consider committing the -263 ns and -5 ms parent probes.

## Packet

- `MANIFEST.sha256` lists every publishable receipt and script.
- Scripts:
  - `scripts/run_review_r2.sh` is the suite, reproduction and arm runner.
  - `scripts/run_p109_arm.py` is the arm-subset driver. It holds the round-1 probes and the round-2 `width` probes.
  - `scripts/wholerun_idx.py` derives the whole-run entry set.
  - `scripts/arm_patterns.py` checks the arm's structure.
  - `scripts/verify_evidence.py` checks the author-r2 hashes.
- Paths in receipts are rewritten to `<PACKET>`, `<HOME>`, `<CLONE>` and `<VERILATOR_PREFIX>`.
- **Clone integrity after the probes** (`receipts/clone_integrity.txt`):
  - HEAD and tree are exact, and `git status --porcelain --ignored` is empty.
  - The worktree equals the index, and the index equals HEAD.
  - The `ls-files -s` digest equals the `ls-tree` digest.
  - There are no gitlinks: the tree has no submodules, so none is required.
  - One early read-only import of the arm modules wrote ignored `__pycache__` directories in the clone. I removed them at once and verified the clone afterwards. Every later run used `-B`.

R921-2 FINISHED
