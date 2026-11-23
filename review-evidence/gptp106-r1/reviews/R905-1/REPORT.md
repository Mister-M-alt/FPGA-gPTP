[R905] NEGATIVE - exact head a728cc3ce9d0342aa596c8170fecf1284c0b604c

# R905-1 independent review: Mister-M-alt/FPGA-gPTP PR #108 (issues #106, #107)

- Exact head `a728cc3ce9d0342aa596c8170fecf1284c0b604c`, tree `d99b9b065b9acebdae5d39519023b785e249222c`, 6 commits on `1616fc8f062fbf58c35ad31674b5b233207bbdb8`.
- Round 1. Internal reviewer. I worked in a cleared context, from public scope, requirements, the diff and public evidence.
- Verdict: **NEGATIVE**, on one open MINOR (F1). Everything else is either clean, RESIDUE or SUGGESTION.
- The change itself is sound:
  - #106 and #107 are each fixed at their cause.
  - I reproduced the #106 wire failure at the base and the pass at the head.
  - Every #106/#107 mutation control is caught when I re-run it.
- F1 is a conformance overstatement in the docs and test text about the B.1.1 follow range. It needs a text correction, not a code change.

## Sources reconstructed, in order

1. Repository guidance. There is no AGENTS.md or CONTRIBUTING.md in this repository. I read `README.md`, `docs/README.md` (the truth order and the document-status table) and `docs/MANAGER.md`.
2. The issues' frozen acceptance and the public scope decisions:
   - the body of issue #106 and the author's REVIEW READY comment on it;
   - the body of issue #107 and the ruling on #107 (D1 = C, D2 = no servo change, D3 = no grading change, A1 = a step in the qualification harness).
3. The PR #108 body.
4. Interface authorities in the tree:
   - `docs/INTEGRATION.md`, covering PHC control, admission credit, the servo envelope and the Follow_Up TLV;
   - `docs/HDL_DEVELOPER.md`;
   - the module header of `hdl/top/KL_gptp_engine.sv`, covering region 4, PHC control;
   - the generator `hdl/ucode/gen_gptp_ucode.py`, covering BECOME, BECGATE, SELF, ANNTX, the servo and `ppm_addend`;
   - the parent's public `scripts/check_py_idiom.py` (dev), for the module-length rule.
5. The diff `1616fc8f..a728cc3`: 16 files, +994/-221. I read the RTL, generator, harness, mutation tables, docs and the four images.
6. The public executable evidence:
   - the author packet at `42e140e6768105b5b53231367046800f630b834e:review-evidence/gptp106-r1`, all 38 files. They match their `MANIFEST.json` published hashes (`receipts/author-packet-files.txt`);
   - the tools tarball, unpacked as `receipts/tools-r2`.
7. There are no manager evidence comments on #106 or #108 yet.

Prior public review findings on this PR:
- There were none when this round started. The PR had no reviews, no inline comments, and only the two review-start notices.
- A concurrent external report from this round (R906-1) was posted while I was working. I saw only its first line, the verdict word, in a comment listing. I did not read its content before writing this verdict and ledger, and nothing here depends on it.
- Reconciling the two reports is the manager's job.

## What I executed

- Every probe ran in a disposable `git archive` export under `scratch/`. The review clone itself was never modified (`receipts/clone-state.txt`).
- The simulator is the scoped Verilator 5.050. Its identity was checked: the wrapper sha256 is `905795b9…`, and it reports "Verilator 5.050 2026-07-01 rev v5.050".
- The author's processor gates used host 5.054. My 5.050 run gives the same tallies and byte-identical #106/#107 INFO lines.
- The host was heavily loaded (load average about 190) by unrelated work, so the runs took longer. That changes no result.

| Run | Result | Receipt |
|---|---|---|
| ucode regeneration, 4 tracked images | All four identical to the tracked bytes; shipping ROM 1,013/1,024, seeded 1,014/1,024 | `receipts/ucode-regen.txt` |
| contract, lint (engine and bench), docs (diagrams, docs, source evidence, selftests) | rc 0 each; lint 0 warnings | `receipts/cheap-gates.txt` |
| ucpu suite, tsngen suite (their images changed) | 768/768, 4/4 | `receipts/cheap-gates.txt` |
| Engine suite at the head, `make run` | 2,199/2,199 ×3 and 61/61; rc 0 | `receipts/engine-head.txt` |
| Engine suite at the base with its own harness | 2,098/2,098 ×3 and 61/61; rc 0 | `receipts/engine-base.txt` |
| **Head harness against the base RTL and microcode** | 25 FAIL. Phase 57 fails in all 8 gaps from 3.000 to 3.002 s; 3.005 and 3.010 s pass. Phase 58 fails on at-once and on the race; its cadence check passes. Phase 59 passes. Phases 60 and 61, the #100 retargets and the slew rate-0 checks fail | `receipts/hybrid-base-rtl-head-harness.txt` |
| Mutation slice at the head, through the arm's own `run_mutant()`. It covers: all 2 p106 controls, all 7 p107 controls, the 2 #100 controls on the new `TLV_DLT`, and 4 reviewer probes | Positive control passes. All 11 arm controls are caught by every check they name. 2 probes are caught as named. The other 2 are caught, but by checks other than the ones I guessed (next row) | `receipts/mutslice-head.txt` |
| Probe FAIL lines | "First Announce waits 1 ms" fails 5 #106 instant checks. It passes the race check, as a 1 ms beat should. "BECOME clears the integrator" fails 79 servo-mirror checks, so the documented "the integrator keeps the estimate through the mastership" is covered | `receipts/probes-fail-lines.txt` |
| Merge probe against main `7cfd6a0` (scratch clone, `merge-tree`) | One conflict, `tb/verilator/engine/mutants.py`. `docs/TEST_DEVELOPER.md` auto-merges | `receipts/merge-probe.txt` |
| B.1.1 corner against the trim envelope, from the generator's own `ppm_addend` | See F1 | `receipts/envelope-b11-corner.txt` |
| 8x8 route split, from the author's `routes.txt` | See check (5) | `receipts/route-8x8-split.txt` |
| Hosted checks at the exact head | 0 check runs; combined status pending with 0 statuses | `receipts/hosted-checks.txt` |

## The seven checks

### (1) #106

**Cause and fix.**
- At the base, BECOME armed the first Announce on a 2 ms slot-3 beat. An Announce queued at the instant ran BTCA `take` first, which writes slot 3 to zero (`gen_gptp_ucode.py:1935`, the only disarm). So the aged port's mastership never reached the wire.
- At the head, SELF ends in `BR ANNTX` (`gen_gptp_ucode.py:2065`). ANNTX re-arms slot 3 at 1000 ms before its gates (`:2498-2499`), then sends.
- This matches 802.1AS-2011 Figure 10-15: newInfo leads to TRANSMIT_ANNOUNCE at once, and the period counts from that transmission. Milan v1.2 4.2.6.2.3 and Table 4.2 together with the ruling "the timeout wins at the instant, graded on the wire" are met at the head.

**Wire grading.**
- Phase 57 grades our master Announces by sourcePortIdentity and grandmasterIdentity, by first-octet cycle, in [prev+2999 ms, next+1000 ms] (`sim_main.cpp` phase 57).
- At the base, I reproduced the PR's claim: all 8 gaps up to 3.002 s fail.
- At the head, all 10 gaps pass. The INFO cycles match the author's receipt exactly.

**Regain cases.**
- Regain at once: at the base the first master Announce leaves 3,296 cycles (1.6 ms) after the worse Announce and fails; at the head it leaves after 628 cycles. The four 1 s gaps pass at both.
- Race: the base sends no master Announce, the head sends one.

**p106 mutants.**
- Both are caught by every named check.
- My 1 ms-deferral probe is caught too, so the phase is not tuned to the 2 ms constant alone.

**New behaviour I checked.**
- BECGATE's drop path (an incapable port drops its peer and goes to SELF) now also enters ANNTX.
- The AMGM gate skips the send, but the 1 s beat keeps re-arming itself until an adoption disarms it.
- This is stated in the `prog_self` docstring. It is harmless: one skipped dispatch per second, and nothing is sent while not master. The engine suite's incapable-port phases pass.

### (2) #107

**RTL.**
- Word 3 now always applies its low word (`KL_gptp_engine.sv:1283-1292`). The microcode writes `INTG << 32`, so the low word is rate 0 and the high word is the integrator (`gen_gptp_ucode.py:2010-2012`).
- The TLV takes `tlv_dlt_r <= seen ? st_wdata_w[63:32] : 0` (`KL_gptp_engine.sv:983-985`).
- `slave_rate_seen_r` is set by a PHC word-0 write, which includes a step's rate tail, and cleared by BECOME (`:961-964`, `:980-981`).
- The servo writes `-clamp(P+I)` (`gen_gptp_ucode.py` SVRATE). The integrator is therefore the negated rate estimate, and change = 0 − estimate = INTG.
- This is exactly D1 = C: 802.1AS-2020 10.1.2.1 and 10.2.4.14 (a ClockMaster on its LocalClock), and 10.2.8.2.1 l) and 11.4.4.3.9 (scaled by 2^41).
- The 25-bit width is safe: `set_servo_gains` asserts `2·ilim+1 < 2^24`, and 200 ppm × 2^41 < 2^31.

**Tests.**
- Phase 60 (takeover after a 90 µs jump): rate 0 within one unit. A 10 ppm grandmaster is then followed.
- Phase 61: the TLV is within 50 % of 2^41·(0 − rate) under ±8 ns noise, which is D3's grading.
- Phase 59 (±10, ±100 ppm) passes at the head, and at the base too, as the PR states.
- The unfollowed-grandmaster case gives zero.
- All 7 p107 controls and both retargeted #100 controls are caught by every named check. So are my probes "seen set by any addend pulse" and "BECOME high word zero".

**Documented wound-integrator case.**
- INTEGRATION.md states that a takeover during a phase transient sends the wound integrator: −200 ppm against a 60 ppm grandmaster, per the INFO line.
- That case fails D3's 50 % grading by construction. It is what D2 accepted, with anti-windup on the residue list.

**INTEGRATION.md's phase authority of 200 − |rate|.**
- This is true in the direction that speeds the clock toward the clamp. In the other direction there is up to 200 + |rate| (S2).
- The 5 to 17 s and 50 s settling figures match `near-clamp-C.txt`: 5.000 to 17.250 s, and 50.000 s. They are marked as not graded.
- **But the follow-range claims overstate B.1.1: see F1.**

### (3) ROM and OOC

- ROM: shipping 1,013 ≤ 1,013, seeded 1,014, both regenerated by me (`ucode-regen.txt`). MANAGER.md agrees.
- OOC: engine 5,395 → 5,375 LUT (−20), 3,620 → 3,617 FF (−3), WNS +2.043 → +2.093 ns. The µCPU is unchanged. These are from the author's receipt `ooc-r2.txt`, including its utilisation-report diff.
- I could not re-run OOC: there is no Vivado on this host.

### (4) Parent gates

All of these come from the author's receipts. I did not run any parent gate.

- Takeover gate:
  - 252/252 at the head;
  - the same harness at the base fails exactly its two "PHC runs on this oscillator" checks;
  - takeovers from ±100 ppm: no PHC step, MEDIA_UNLOCKED unchanged, every PDU presented once in order at one offset, no MEDIA_RESET;
  - tu is set at the commit and held 165,528 and 254,168 cycles, against the 131,072-cycle compressed 0.25 s (B.1.1/B.1.2).
- milan_dp gptp and gptp-lat: 212/212 each.
- gptp_shadow: 327/327 at +100 ppm and at −100 ppm, with the addend 0 as grandmaster.
- milan_dp_gm_steps: 196/196, and its 5 controls are caught.

**The two disclosed harness-defect reruns.** I read the scratch gate patch (`tools-r2/parent-scratch-gate.patch`) and the failure lines.
- Try 1 failed only in follow and media checks. Its cause, a stale origin override and the PHC moved by earlier settime trials, is a harness state leak, and the takeover checks themselves passed.
- Try 2 failed only the three Stream Input counter reads, because GET_COUNTERS was unanswered within the window. The final harness retries up to four times.
- The retry is legitimate for grading MEDIA_UNLOCKED, which counts from reset.
- However, the station sent **no AECP frame at all** for two windows after the −100 ppm takeover, and this reproduces at the base. That is a pre-existing parent behaviour, not caused by this change, and the retry now hides it (S3).

### (5) Routes and the 8x8 +588 LUT judgement

- The #818 floor (WNS ≥ +0.030 ns, WHS ≥ 0) is met at every corner of all four routes, with 0 failing endpoints and 0 routing errors (author `routes.txt`).
- Head: 1x1 +0.276 / +0.036 ns, 8x8 +0.244 / +0.036 ns.
- The 8x8 base's Fast WHS of +0.027 misses the stricter +0.030 line; the head meets it.

**My judgement: the 8x8 +588 LUT is synthesis/implementation variance in RTL this change does not touch. It is not growth caused by this change.** The comparison uses the same directive on both sides: the split image, one interface, ExtraTimingOpt, AreaOptimized_high and ExploreArea, Vivado 2026.1. The evidence, from `receipts/route-8x8-split.txt`:

| 8x8 cell (same directive) | base → head LUT | RTL changed by this PR? |
|---|---|---|
| `u_engine` | 3,820 → 3,740 (**−80**) | yes, the only changed cell |
| `u_edit` (mailbox edit window, in `KL_mbx_cdc`) | 3,746 → 5,318 (+1,572) | no |
| `csr` | 4,107 → 2,765 (−1,342) | no |
| `(g_gptp_plane.u_gptp_shadow)` own logic | 1,778 → 2,113 (+335) | no (parent wrapper) |
| `(milan_datapath)` own logic | 4,165 → 4,386 (+221) | no |
| `chan_map_capture` / `crf_rx` / bridge / `(KL_mbx_cdc)` | −110 / +83 / +93 / −87 | no |
| image | 42,998 → 43,586 (+588); FF −107; slices −459 | |

- The image's +588 is the engine cell's −80 plus +668 in cells whose RTL is identical on both sides. Of that +668, +230 is the `u_edit`/`csr` swap and +438 is spread over other untouched cells.
- Attribution between cells is visibly noisy by hundreds of LUTs:
  - the **identical** engine RTL places as 4,717 LUT in 1x1 and 3,820 in 8x8;
  - unchanged sub-cells move by ±65 to 167 (`u_timer` −96/−65, `u_txslot` +167/−67);
  - untouched logic loses 107 FFs, which unchanged RTL can only do through implementation choices;
  - the same change gives −322 LUT on 1x1.
- No engine port or constant changed that could propagate into the mailbox or CSR.
- Limit: this is an attribution argument, not a proof. A same-directive control route with a perturbed seed or a no-op change at the base would settle it, and I could not run Vivado here. The literal owner rule, that the 1x1/8x8 images must not grow, applied to totals rather than to attribution, is the owner's and manager's call at the merge-turn routes (pending duty P3).

### (6) mutants.py length

- 1,000 lines at the head. The parent's rule is `len(lines) > LONG_MODULE_LINES` with the limit at 1000 (parent `scripts/check_py_idiom.py:148,355`), so 1,000 is within it.
- The author's ratchet receipt shows long module 10 ≤ 10.
- On main (#104) the file is 863 lines, so the merge has room.

### (7) The merge with main

- `merge-tree` confirms the only conflict is `tb/verilator/engine/mutants.py`. Main's #104 added `--jobs`, ccache and `path_mutants.py`.
- The merge turn must keep P106/P107 in `MUTATIONS` and the `#106 `/`#107 ` named-check prefixes. It must then re-run the merged arm. This is pending duty P1.

## Findings

### F1 — MINOR — Conformance, Docs, Tests — the stated follow range overstates 802.1AS-2020 B.1.1

**Where.**
- `docs/INTEGRATION.md:422` ("Twice that bound fits inside the envelope (#107).") and `:424` ("So any conforming grandmaster can be followed.").
- `docs/INTEGRATION.md:448-452` ("A grandmaster beyond `RATE_PPM_C` cannot be followed. … Such a grandmaster is outside B.1.1.").
- `docs/TEST_DEVELOPER.md:208` ("Follows grandmasters across the B.1.1 range (#107).").
- `tb/verilator/engine/sim_main.cpp:8225-8231`, the phase 59 comment: "must follow a grandmaster up to 200 ppm from it … across the B.1.1 range". The phase grades ±10 and ±100 ppm only.
- The PR body: "Any grandmaster within B.1.1 is followed."

**Authority and evidence.**
- B.1.1 bounds each LocalClock to ±100 ppm of TAI. Two conforming clocks can therefore differ by (1+10⁻⁴)/(1−10⁻⁴) − 1 = **200.020 ppm**.
- The trim envelope is the integer clamp `ppm_addend(RATE_PPM_C, clk)`:
  - 199.997 ppm at the 100 MHz default;
  - 200.003 ppm at 125 MHz;
  - 200.000 ppm at the suites' 2 MHz.
- The corner exceeds the envelope by 0.017 to 0.023 ppm (`receipts/envelope-b11-corner.txt`, computed from the generator's own constants).
- By the docs' own rule (line 448 onward), such a grandmaster's offset grows by 17 to 23 ns/s and steps again about every 4,400 to 6,000 s.
- Also by the docs' own rule (line 432), phase authority vanishes as the rate approaches the envelope.

**Impact.**
- This is a false conformance claim, small in magnitude, on the very range #107's acceptance asks to be stated.
- An integrator or qualification reader is told that every B.1.1 grandmaster is followed and that anything not followed is outside B.1.1. At the corner, neither holds.
- The issue's own acceptance ("the adjustment range is stated and covers ±100 ppm") is met. The overreach is the added "any conforming grandmaster" claim.

**Required outcome.**
- State the range as implemented: grandmasters up to the envelope, `ppm_addend(RATE_PPM_C, clk)` (about 200 ppm, 199.997 at 100 MHz), from this oscillator, with phase authority shrinking to zero there.
- Say that B.1.1's extreme pair (200.02 ppm) lies just outside the envelope and is followed only with periodic steps.
- Say the suite grades ±10 and ±100 ppm against this oscillator.
- Correct the four locations above and the PR body to match, or obtain a ruling that widens the envelope (outside D2's scope).
- No RTL or microcode change is required.

**Verification.** `make docs` passes. The text matches `r905_envelope.py`'s output. The phase 59 comment and the TEST_DEVELOPER line no longer claim the whole B.1.1 range.

### R1 — RESIDUE — Docs (comment wording) — `tb/verilator/engine/sim_main.cpp:8282`

- The comment reasons with a date ("no anti-windup, the 2026-11-23 ruling") instead of an issue ID. The owner comment rule asks for issue and requirement IDs.
- None of the forbidden forms appear: no lane label, lane name, round, reviewer ID or comment ID.
- **Exact fix:** `// which the jump wound (no anti-windup: #107, the servo unchanged)`.

### R2 — RESIDUE — PR body — the 8x8 attribution sentence

- The sentence "The 8x8 LUT rise lies in the mailbox edit window (+1,572) and the CSR block (−1,342), RTL this change does not touch." is loose: those two cells net only +230 of the +588.
- **Exact fix:** "The 8x8 LUT rise is the net of moves in cells whose RTL this change does not touch, under the same directive (the mailbox edit window +1,572, the CSR block −1,342, the gPTP wrapper's own logic +335, the datapath's own logic +221, smaller moves elsewhere); the engine cell, the only changed RTL, is −80 LUT in both images."
- Every figure stays as it is.

### Suggestions (they do not affect the verdict)

- **S1 — Docs.** `docs/INTEGRATION.md:801-803` says the first Announce "reaches the wire before any queued Announce". ANNTX keeps its credit gate, so with `tx_credit_i` low the first Announce is postponed to the next cadence, 1 s later (the same as the base's 2 ms beat). Add "while transmit credit is present".
- **S2 — Docs.** `docs/INTEGRATION.md:432-434`: phase authority is `RATE_PPM_C − |rate|` only toward the clamp; it is `RATE_PPM_C + |rate|` away from it. Say "in the direction of the rate".
- **S3 — Robustness (parent, pre-existing).** After the −100 ppm takeover, the station sends no AECP frame for two GET_COUNTERS windows, at the head and at the base alike. The final scratch harness retries and the counter checks pass. Open a parent issue so the retry does not normalise a missing AEM response. Adopt the takeover phase, now a local scratch patch, into the parent's regression with the gitlink bump.
- **S4 — Conformance (evidence wording).** The issue's regain observation was one Announce, then 3.0 s of silence, with continuous sequence numbers.
  - In simulation the base already kept a 1 s cadence after regaining. Only the at-once and race checks fail there.
  - Only an adoption disarms slot 3, so that observation needs a better Announce shortly after the regain.
  - At the head, that sequence still gives one Announce and then silence until the better grandmaster ages out. That is correct BMCA behaviour.
  - Record this so the qualification rerun does not read it as a regression.

## Reviewer-owned ledger

| Lens | Status | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN (F1) | #106: 802.1AS-2011 Fig 10-13/10-15 against SELF→ANNTX and ANNTX's re-arm order; Milan v1.2 4.2.6.2.3/Table 4.2 and the "timeout wins, on the wire" rule, against phase 57 at head and base. #107: D1 = C against BECOME `INTG<<32`, the word-3 apply and `tlv_dlt_r`, against 802.1AS-2020 10.1.2.1, 10.2.4.14, 10.2.8.2.1 j)-l), 11.4.4.3.9 and B.1.1 (F1); D2 (servo unchanged in the diff); D3 (phase 61 grading); A1 (documented as setup); the documented wound-integrator case | R905-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| RTL | CLEAN | `KL_gptp_engine.sv` region-4 decode, word 3 always applied, `slave_rate_seen_r` set/clear priority, 25-bit `tlv_dlt_r` and product widths, reset; generator BECOME/BECGATE/SELF/ANNTX control flow and timer slots; four images regenerated byte-identical; lint 0 warnings; OOC −20 LUT/−3 FF and the route cells (author receipts) | R905-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| Robustness | CLEAN | Credit gate on the first Announce (S1), idle beat on the drop path, the regain race at 1 ms, the 1 ms-deferral probe, warm-reset "unknown rate", the unfollowed grandmaster, near-clamp settling (author receipt), parent takeover media/tu/AECP behaviour (S3) | R905-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| Tests | UNCLEAN (F1) | Phases 52-61 and the retargeted slew checks; head 2,199×3 + 61; the head harness at base RTL (25 FAIL, as claimed); base suite 2,098×3 + 61; 11 arm controls and 4 probes through `run_mutant()`; arm length 1,000 against the parent rule; the merge conflict | R905-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| Docs | UNCLEAN (F1) | INTEGRATION, HDL_DEVELOPER, MANAGER (ROM 1,013/1,014), SOURCE_EVIDENCE anchors (20 exact), TEST_DEVELOPER, generator and engine comments, the comment rule over the added lines (R1; no lane, round, reviewer or comment IDs found), PR body (R2) | R905-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |

## Real limits

- I ran no parent gate, route or OOC synthesis. There is no Vivado on this host, and parent banks are out of scope. Items (3) to (5) rest on the author's published receipts, which I checked for internal consistency and against the packet manifest.
- The +588 judgement is an attribution argument without a control route.
- I could not check clause numbers against the standards' text, because no copy is available here. That covers the editions cited for 10.2.8.2.1, and the 802.1AS-2011 "10.2.2.3.12 and 10.2.3.6" in the phase 61 comment. I judged state-machine semantics from the clause structure the sources quote.
- There is no hosted CI at the exact head: 0 check runs. I claim no hosted, act or manager source bank.
- Physical calibration was NOT RUN. Simulation passes are not hardware proof. #107's "3 of 3 runs each" and #106's two qualification scenarios are owed by the qualification rerun on hardware.

## Pending manager duties

- **P1.** At the merge turn, resolve the `mutants.py` conflict with main (#104):
  - keep `P106_MUTATIONS`/`P107_MUTATIONS` and the `#106 `/`#107 ` named-check prefixes;
  - keep the file within 1,000 lines;
  - run the merged arm with `--jobs`;
  - run the builder and native banks on the current-dev candidate (source base `1616fc8f`, live dev `e275d795`) and link their receipts.
- **P2.** Carry R1 and R2 to the residue checklist, and see F1 corrected before acceptance.
- **P3.** Re-measure the 1x1/8x8 routes on the merge candidate and apply the owner's image-growth rule. If the 8x8 still shows a rise, a same-directive control route would settle attribution.
- **P4.** Parent follow-ups from S3: track the missing AECP answers after the takeover, and adopt the takeover phase in parent regression with the gitlink update.
- **P5.** Qualification rerun on hardware, with A1 applied as a harness setup step: #106 gaps and regain; #107 ±10 ppm 3 of 3 and the TLV after a grandmaster change.

R905-1 FINISHED
