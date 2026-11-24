[R905] POSITIVE - exact head 331e27de137a1d4f7acd4f3f2cc7e373b6e8e869

# R905-2 delta review: Mister-M-alt/FPGA-gPTP PR #108 (issues #106, #107), round 3

- Exact head `331e27de137a1d4f7acd4f3f2cc7e373b6e8e869`, tree `7b579e33a97ff4f2bec8c0064f0f73c862bbb135`. Source base `1616fc8f062fbf58c35ad31674b5b233207bbdb8`.
- Delta reviewed: `a728cc3c..331e27de`. That is two branch commits, `884c755` (docs and test text) and `309292f` (one docs sentence), plus the merge `331e27d` of main `7cfd6a0` (#102, #104).
- **Verdict: POSITIVE.** No BLOCKER, MAJOR or MINOR finding is open. There are two RESIDUE items and five SUGGESTIONs below.
- Both named prior MINORs are fixed exactly at their cause: R905-1-F1 (the follow range against the B.1.1 corner) and R906-1-F2 (phase-61 duration).
- The merge keeps both sides' mutants. `hdl/` and `syn/` are byte-identical to the round-2 head.
- The controlled route comparison re-derives from the raw published reports, figure for figure.
- R906-1-F1 was resolved by the owner's decision of 2026-11-24 and is not raised again. The PR body records the exception and its figures truthfully.

## 1. Reconstruction (order followed)

1. AGENTS.md / CONTRIBUTING.md: none tracked in this repository. Then the repository README and `docs/README.md`, which sets the truth order: RTL and generated microcode, then tests, then current guides, then history.
2. Issue #106: body plus comments `7097266371`, `7109217025` and `7115686067`. Issue #107: body plus the ruling `7101407241`, which sets D1 = C, D2 = no servo change, D3 = no grading change, and A1 as a harness setup step.
3. PR #108: body at the head, the review-start comments, and the owner decision `issuecomment-7121892317`.
4. Authorities, as frozen by the issues and the ruling:
   - IEEE 802.1AS-2011 Figures 10-13 and 10-15;
   - Milan v1.2 4.2.6.2.3 and Table 4.2;
   - IEEE 802.1AS-2020 10.1.2.1, 10.2.4.14, 10.2.8.2.1 j)-l), 11.4.4.3.9 and B.1.1.
5. `git diff 1616fc8f..331e27de`, the history, and the round-3 delta with each merge side separately.
6. Public evidence at `2c2ba060` `review-evidence/gptp106-r1/author-r3`: HANDOFF-r3, REVIEW-READY, STOP-NOTE, PR-BODY and receipts, read by section.
7. Prior public findings (R905-1, R906-1), read only after my own pass over the delta. They are resolved in section 3.
8. Not read: the `reviews/` directory of the evidence tree and any other reviewer's round-2 report.

## 2. What the delta changes, and what it does not

| Part | Change | Evidence |
|---|---|---|
| `hdl/`, `syn/` | None. The `hdl` tree is `e0d11b2f` at `a728cc3`, `309292f` and `331e27d` alike. | `git rev-parse <rev>:hdl`; `git diff --quiet a728cc3 331e27d -- hdl syn` |
| Generated microcode | The four tracked images regenerate byte-identical at the head. The default and ucpu images come from the 100 MHz default; the engine image from `--clk-hz 2000000 --cease-ms 3000`; the tsngen image from `--clk-hz 2000000`. ROM 1,013 of 1,024 words. | This review's regeneration (cmp) |
| `sim_main.cpp` (branch side) | Comments only, plus a function rename and one check rename: `#107 B.1.1 range: runs from a capable master` becomes `#107 follow: runs from a capable master`. No mutant names the old or the new string, and the check count stays at 2,199. | `git diff a728cc3 309292f -- tb` |
| `p107_mutants.py` | Docstring only. | Same diff |
| `docs/INTEGRATION.md`, `docs/TEST_DEVELOPER.md` | The F1 text fix, the S1 and S2 suggestions, and main's #104 test-guide section. | Diffs |
| Merge | `mutants.py` is main's file plus exactly the branch's 7 added and 5 removed lines. `path_mutants.py`, the engine `Makefile` and `mutation_{jobs,order}_test.py` are main's bytes. `sim_main.cpp` and the `p10x` tables are the branch's bytes. | `git diff 7cfd6a0 331e27d`, `git diff 309292f 331e27d` |

There is no behaviour change beyond round 2's reviewed fixes (the #106 first Announce at once; the #107 mastership on this oscillator). The only other changes are the review fixes.

## 3. Prior findings at this head

| ID | Severity | Status at 331e27d | Evidence |
|---|---|---|---|
| R905-1-F1 | MINOR | **RESOLVED** (see below) | Section 3.1 |
| R906-1-F2 | MINOR | **RESOLVED**, exactly as required | Section 3.2 |
| R906-1-F1 | MAJOR | **RESOLVED BY OWNER DECISION** of 2026-11-24 (`issuecomment-7121892317`); not raised again. | Section 3.3 |
| R905-1-R1 | RESIDUE | **FIXED** exactly: `sim_main.cpp:8286` reads `// which the jump wound (no anti-windup: #107, the servo unchanged)`. | Source |
| R905-1-R2 | RESIDUE | **FIXED** exactly: the PR body carries the required sentence ("the 8x8 LUT rise is the net of moves in cells whose RTL this change does not touch … −80 LUT in both images"). | PR body |
| R905-1-S1 | SUGGESTION | **APPLIED** (`309292f`), and correct (see below). | Source |
| R905-1-S2 | SUGGESTION | **APPLIED**: `docs/INTEGRATION.md:461-463` gives phase authority by direction. | Source |
| R905-1-S3, S4 | SUGGESTION | **Retained** as owners' items. They are unchanged by the delta and carried in HANDOFF-r3 "For the owners". | Packet |

S1 is correct. `docs/INTEGRATION.md:834-836` now reads "With credit, it reaches the wire … Without credit, the next beat tries again, 1 s later." In `prog_leg_anntx` (`hdl/ucode/gen_gptp_ucode.py:2498-2502`), the 1,000 ms slot-3 re-arm runs before the role, asCapable and credit gates. So a credit-less first Announce is retried one second later, exactly as stated.

### 3.1 R905-1-F1, the follow range against the B.1.1 corner

Each required outcome, checked:

- **Range as implemented.** `docs/INTEGRATION.md:418-432` says the envelope is `RATE_PPM_C` as an integer addend clamp, gives it per clock, and says "Grandmasters up to the envelope from this oscillator are followed. Phase authority shrinks to zero there."
- **B.1.1 corner just outside, followed only with periodic steps.** Lines 441-457 say this, and give the shortfall, the offset growth and the step interval per clock. The slow corner is stated as inside.
- **What the suite grades.** Lines 434-438: ±10 ppm and ±`LOCAL_CLOCK_PPM_C` from this oscillator, covering #107's ±100 ppm.
- **The enumerated locations.** All are corrected:
  - INTEGRATION.md: the old ":422/424" claims are gone, and the old ":448-452" sentence now reads "B.1.1's fast corner lies just beyond, as above" (line 483);
  - TEST_DEVELOPER.md:208;
  - the phase-59 comment, function name and check name in `sim_main.cpp:8225-8245`;
  - the PR body: "Any grandmaster within B.1.1 is followed" is gone, and the corner paragraph replaces it.

Every figure was recomputed independently in exact rationals from the generator's `ppm_addend()` expression (`envelope_check.py`, `receipts_envelope.txt`):

| Clock | Addend | Envelope | Beyond fast corner | Offset growth | Step interval |
|---|---|---|---|---|---|
| 50 MHz | 67,109 | ±200.000405 ppm | 0.019597 ppm | 19.597 ns/s | 5,102.9 s |
| 100 MHz | 33,554 | ±199.997425 ppm | 0.022577 ppm | 22.577 ns/s | 4,429.3 s |
| 125 MHz | 26,844 | ±200.003386 ppm | 0.016616 ppm | 16.616 ns/s | 6,018.1 s |
| 2 MHz | 1,677,722 | ±200.000048 ppm | 0.019954 ppm | 19.954 ns/s | 5,011.4 s |

- The fast corner is +200.020002 ppm and the slow corner −199.980002 ppm.
- "17 to 23 ns each second" is right, as are the docs' 5,103, 4,429, 6,018 and 5,011 s.
- Every value matches the docs, the phase-59 comment (±200.000048 ppm at 2 MHz) and the PR body.
- The 50 MHz parent clock is the author's statement. The figure for it is exact.

Two remaining B.1.1 parentheticals from round 2 are true statements outside F1's list; they are under SUGGESTION S-A.

### 3.2 R906-1-F2, the phase-61 duration

- `sim_main.cpp:8310-8312` now reads "each for 120 Sync pairs, grading the last 80 pairs". That matches `p107_follow(c.tag, 120)` and the `k == pairs - 80` window (`:8184-8193`).
- Phase 59's "within 30 s" carried the same error and is corrected the same way (`:8232-8234`).
- No "30 s" duration claim remains in the engine harness, the #106/#107 tables or the two guides.
- The new line break is cosmetic: see RESIDUE R-B.

### 3.3 R906-1-F1, the image size: PR-body record only

- The PR body's "Owner decision (2026-11-24)" paragraph says the +455 LUT at 8x8/1if is accepted as a recorded exception. It links `pull/108#issuecomment-7121892317`, keeps area recovery with the optimisation line, and keeps fit and the #818 floor gating the pinned image. That matches the owner comment.
- Every figure the body and the owner comment cite was re-derived from the raw published reports, `routes/<shape>-<side>-<directive>/` (`route_recheck.py`, `receipts_route_recheck.txt`):
  - all 12 routes: image LUT, FF, slices, BRAM tiles and DSP; worst-corner WNS and WHS over the four signoff corners; zero failing endpoints and zero routing errors;
  - `best()` under WNS ≥ +0.030 ns and WHS ≥ 0 at every corner: 1x1 base and head ExtraTimingOpt, 8x8 base and head ExtraPostPlacementOpt, and the 8x8 base AltSpreadLogic_high route missing the floor at +0.006 ns;
  - the qualifying deltas: 1x1 −322 LUT, −4 FF, −3 slices; 8x8 +455 LUT (+1.06 %), −110 FF, −80 slices, with BRAM and DSP equal;
  - each head directive against the qualifying base: 8x8 +455, +514 and +567; 1x1 −322, −311 and −379 ("no head directive grows");
  - the per-cell split, from `baseline_hierarchy.rpt` as disjoint leaf and own rows (129 pieces at 8x8): `KL_mbx_cdc/u_edit` (own) +1,569, `milan_datapath/csr` −1,338, the `u_gptp_shadow` own logic +335, the `milan_datapath` own logic +220; the pieces sum to +470 against the image's +455 (the shared-LUT sites);
  - the engine row: −74 LUT, +1 FF at 8x8, and −80 LUT at 1x1;
  - FF moves in 13 pieces, the largest being `ptp_clock_validity` at −64.
- The per-corner table in the PR body matches every corner I parsed.
- Route-input identity holds: the digests of the route inputs for `KL_gptp_engine.sv` are `c9be0c2b3688c68c` (base) and `3ef11dfe571024a7` (head). Those equal the sha256 prefixes of `1616fc8f:hdl/top/KL_gptp_engine.sv` and of `331e27d:hdl/top/KL_gptp_engine.sv`.
- The routes used `a728cc3`, whose `hdl` tree is the head's (`e0d11b2f`). The PR body says so ("this branch's `hdl/` tree").
- **Fit and the #818 floor at both shapes:** every qualifying image meets WNS ≥ +0.030 ns and WHS ≥ 0 at all four signoff corners, with 0 routing errors. The 8x8 image uses 98.07 % of slices (15,544 of 15,850): it fits, with little room.

## 4. Merge of main (item 2): both sides' mutants are kept

`merge_mutants_check.py` imports each tree's `MUTATIONS` (base, branch `309292f`, main `7cfd6a0`, merge `331e27d`) and compares the full tuples, not only the names (`receipts_merge_mutants.txt`):

| Tree | Mutants |
|---|---|
| base | 159 |
| branch | 167 (+13 −5; the 5 removed are the #100 controls retargeted in round 2) |
| main | 159 (+0 −0; main moved the path controls to `path_mutants.py` without changing a tuple) |
| merge | 167 |

- The merge equals the base, less the removals, plus both sides' additions (True), and all 167 names are unique.
- The named-check rule in `named_verdict` keeps main's signature and adds `"#106 "` and `"#107 "`.
- `mutants.py` is 865 lines, within the parent's 1,000-line module rule.

My own run at the head, with the pinned Verilator 5.050 (identity checked: `Verilator 5.050 2026-07-01 rev v5.050`):

- **The merged arm's own `main()` over the 9 #106/#107 controls, `--jobs 9`** (`arm_p106_p107.py`, `receipts/arm.log`): the positive control passes, and **9 of 9 controls are caught, each by every check it names** (10 checks, 10 PASS, rc 0).
- **Main's order test** (`make mutants-order-test`) on the merged arm: 10 of 10 PASS.

## 5. Gates at the head (item 4)

Author receipts (`gates-331e27d.txt`):
- contract, ucpu, parser, engine, gaskets, tsngen, bench, lint and docs all rc 0;
- engine 2,199 ×3 and 61, with "153 INFO lines and the four tallies identical to a728cc3";
- arm 167 caught, in table order, with the positive control 2 of 2.

The arm ran as two halves through `armslice3.py`. That script calls `mutants.main(["--jobs","8"])` on `MUTATIONS[a:b]`, with the control, build and grading unchanged. I read it in full. The deviation is disclosed in the PR body and in HANDOFF-r3.

Packet integrity: all 214 entries of `MANIFEST.json` verify against `published_sha256` (0 bad, 0 unlisted), 108 of them under `author-r3/` (`receipts_evidence_manifest.txt`).

This review's own probes, on disposable extractions of the head, with the pinned Verilator 5.050:

| Probe | Result | Receipt |
|---|---|---|
| Engine suite (`make run`) | 2,199 / 2,199 ×3 and 61 / 61, 0 FAIL, rc 0. 153 INFO lines, the author's count. The 43 #100/#106/#107 INFO lines of the shipping pass are byte-identical to the author's receipt (made with 5.054). | `receipts/suite.log`, `receipts/info-100-106-107-shipping-pass.txt` |
| #106/#107 arm controls | 9 / 9 caught, rc 0 | `receipts/arm.log` |
| `make contract`, `make lint`, `make docs` | rc 0 each. Docs: 14 current pages, source evidence 20 exact, 0 findings. | `receipts/gate-*.log` |
| `make mutants-order-test` | 10 / 10 PASS | `receipts/gate-order.log` |
| Microcode regeneration | The 4 tracked images are byte-identical; 1,013 of 1,024 words | Section 2 |

Not rerun here: parser, ucpu, gaskets, tsngen and bench, which the delta does not touch; the whole 167-control arm; the jobs test (about 7 h); OOC; any parent gate; any route.

## 6. Findings

No BLOCKER, MAJOR or MINOR finding.

### R-A: RESIDUE (Docs, wording only), `docs/INTEGRATION.md:422`

- **Issue:** "The expression below gives its exact value per clock:" introduces the per-clock table. The expression it refers to is 67 lines further down (`:489`, "In addend units the bound is this integer expression:"). A reader takes the table for the expression.
- **Impact:** wording only. No figure, anchor or claim changes.
- **Exact fix:** `Per clock, the integer expression [below](#rate-envelope) gives:`, or simply `Its exact value per clock:`.
- **Verification:** `make docs`.

### R-B: RESIDUE (Tests comment, wording only), `tb/verilator/engine/sim_main.cpp:8310-8312`

- **Issue:** the F2 fix leaves a broken line: "// slow, then 10 ppm fast again," ends short at 8311, and the sentence goes on at 8312.
- **Exact fix:** reflow to `// slow, then 10 ppm fast again, each for 120 Sync pairs, grading the last` / `// 80 pairs, and replaces each. Each time, the scaledLastGmFreqChange of ...`.
- **Verification:** the comment is unchanged in content, and the suite output is unchanged.

### Suggestions (they do not affect the verdict)

- **S-A (Conformance, Docs; round-2 lines, outside F1's list).** Two parentheticals are true, but read as if phase 59 grades B.1.1's two-clock pairs:
  - `sim_main.cpp:275-276`, the phase-59 header: "(802.1AS-2020 B.1.1: two LocalClocks each within 100 ppm of TAI)";
  - `p107_mutants.py:92`: "a trim short of 802.1AS-2020 B.1.1's two 100 ppm LocalClocks".

  Consider aligning them with the corrected phase-59 comment: "the ±100 ppm #107 asks for; the B.1.1 fast corner is not graded".
- **S-B (Docs, PR body).** The heading "Image size: the 8x8/1if image grows, so the no-growth rule is NOT met" is still accurate. Consider appending "; accepted by the owner as a recorded exception (2026-11-24)" so the heading alone shows the disposition.
- **S-C (Tests, pre-existing).** `p107_pair` and `p100` (`:8139`, `:7700`) say "One 125 ms interval", and `p107_follow`'s docstring and INFO line say "the last 80 (10 s)". These are nominal: a pair spans 250,000 + 9,000 cycles at 2 MHz (about 129.5 ms), plus 4,000 cycles every eighth pair. Consider "(nominal)" at a later change. Leaving the INFO string alone keeps the INFO-identity check meaningful.
- **S-D (Evidence hygiene).** The packet's `routes/*/run.txt` files carry absolute build-storage and lock-file paths. They are not device or host names, and they passed the author's scrubber. The manager may wish to normalise them in later packets.
- **S-E (Robustness, fit).** The 8x8/1if image is at 98.07 % slice utilisation after this change. That does not block this PR. The optimisation line that owns the area recovery should watch it.

## 7. Comment rule and privacy (delta)

- I scanned every added line of `a728cc3..331e27d` for lane labels (letter plus digits), "lane", "round", "reviewer", comment IDs, dates, host or home paths, and AI tool or model names. Nothing matched. The round-2 date reference ("the 2026-11-23 ruling") is removed.
- The PR body names no private device or host. "the build host's load" is generic.

## 8. Reviewer-owned ledger

| Lens | Verdict | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | CLEAN | R905-1-F1 fix against 802.1AS-2020 B.1.1 (both corners recomputed); #107 ruling D1–D3; S1 claim against ANNTX's re-arm order (`gen_gptp_ucode.py:2498-2502`); #106/#107 behaviour unchanged (`hdl` tree identity); PR-body clause text | R905-2 (delta); round-2 behaviour verdict carried, its `hdl` unchanged | 331e27de137a1d4f7acd4f3f2cc7e373b6e8e869 |
| RTL | CLEAN | `hdl/`, `syn/` identity with `a728cc3`; 4 regenerated microcode images; route-input engine digests; 12 raw route reports; engine cell −74 / −80 LUT; #818 floors at both shapes | R905-2 | 331e27de137a1d4f7acd4f3f2cc7e373b6e8e869 |
| Robustness | CLEAN | Credit-less first Announce retried at 1 s; the fast-corner step interval; no behaviour change in the delta; 8x8 slice margin (S-E); owners' S3/S4 carried | R905-2 (delta); round-2 verdict carried | 331e27de137a1d4f7acd4f3f2cc7e373b6e8e869 |
| Tests | CLEAN | Merge MUTATIONS tuple proof (both sides kept); engine suite at head (own run); 9 #106/#107 controls through the merged arm (own run); order test; R906-1-F2 fix; check rename (no mutant references it); author arm halves and `armslice3.py`; packet manifest | R905-2 | 331e27de137a1d4f7acd4f3f2cc7e373b6e8e869 |
| Docs | CLEAN (R-A, R-B are RESIDUE) | INTEGRATION.md rate envelope and Announce text; TEST_DEVELOPER.md; phase 59/61 comments; `p107_mutants.py` docstring; PR-body figures, exception record, R2 sentence; `make docs` | R905-2 | 331e27de137a1d4f7acd4f3f2cc7e373b6e8e869 |

## 9. Real limits

- No manager source bank was run at this head. This review claims none and infers none. Source-head execution evidence is the author's published receipts, plus the focused probes above.
- No hosted checks were found at this head: the check-runs API returned 0 runs, and the combined status was `pending` with 0 contexts. No hosted job was executed or skipped for this SHA. Hosted and act acceptance stay with the manager.
- The parent consumer gates, routes, OOC and the whole 167-control arm were not rerun. They rest on the author's receipts, which were spot-checked:
  - the route figures were fully re-derived from the raw reports;
  - the 9 changed-area controls and the suite were rerun.
- The parent's `ax1x1gptp` leg was not run to completion by the author; this is disclosed.
- The round-2 takeover gate and the −100 ppm shadow variant were cited at `a728cc3`, whose `hdl` tree the head carries unchanged.
- Physical calibration was NOT RUN. Field skips are not hardware proof. No hardware was used.
- The parent clock of 50 MHz is the author's statement. The envelope figure for it is exact.

## 10. Pending manager duties

- Build and validate the current-dev merge candidate: source base `1616fc8f`, live dev `e275d7950ef3385753e6a15d2e191ba855b171ed`, builder and native banks. Link its receipts on the PR.
- Owner's merge conditions: fit and the #818 floor on the image that carries this pin, at both shapes; both reviews POSITIVE at the head; the parent pin adoption's own gates.
- Carry R-A and R-B to the residue checklist. Track S3/S4 (owners) and the anti-windup residue (D2).
- Hosted and act acceptance at the exact head.

## 11. Clone state after probes

- The clone is at `331e27de…`. `git write-tree` = `7b579e33…` = `HEAD^{tree}`.
- The worktree and index equal HEAD, with 0 untracked or ignored entries.
- File modes: 116 × 100644 and 4 × 100755. There are 0 gitlinks: the repository has no submodules (`receipts/clone-integrity.txt`).
- All probes ran on `git archive` extractions under the packet's `scratch/`.
- The only addition to the clone's object store is the fetched public evidence commit `2c2ba060`.

R905-2 FINISHED
