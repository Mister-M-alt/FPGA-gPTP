# [A831] FPGA-gPTP #106 / #107, round 3: the delta from `a728cc3` and each finding's closure

**Branch `106-107-announce-rate` at `331e27d` (local, never pushed). R906-1-F1 is NOT closed: the 8x8/1if image grows (+455 LUT at the image the parent would ship), so this round STOPS for the owner. Every other finding is closed, the merge is done, and every gate the brief names passes at `331e27d`.**

## Commits since `a728cc3`
- `884c755` #107 text (R905-1-F1, R906-1-F2, R905-1 R1; S2):
  - INTEGRATION.md's rate envelope gives the envelope per clock and both B.1.1 corners;
  - TEST_DEVELOPER.md, phase 59's comment, function name and check name, and the `p107_mutants.py` docstring claim only ±10 and ±100 ppm;
  - phases 59 and 61 give their length in Sync pairs;
  - the R1 comment is applied.
- `309292f` #106 text (S1): the first master Announce reaches the wire first only with transmit credit.
- `331e27d` the merge of main `7cfd6a0` (#102, #104), one merge commit; the one conflict was `tb/verilator/engine/mutants.py`.
- No file under `hdl/` changes: `hdl/`'s tree is `e0d11b2f` at `a728cc3` and at `331e27d`. No generated image changes.

## R906-1-F1, MAJOR: the image rule. NOT CLOSED (STOP)

Measured as the brief asks (`receipts/routes-r3.txt`, `route-inputs.txt`, `route-repeat.txt`):
- One #818 route set per side and shape. The shipping route is at ExtraPostPlacementOpt; AltSpreadLogic_high and ExtraTimingOpt are placed from its synthesis checkpoint by the script the parent's recipe writes (the gate's own `bound()` accepts each one).
- Every route went through `vivado-slot.sh`, at most two of mine at a time, each starting with MemAvailable ≥ 51 GB. Base is 1616fc8f (parent 854bd72367); head is this branch's `hdl/` tree.
- Generated inputs, digested the gate's way: base and head differ only in `KL_gptp_engine.sv`, `gptp_ucode.hex` and the generated top. The top's body is identical once comments are removed; only its dates and an unstable comment order differ.
- The qualifying image is the gate's `best()` route, which must meet WNS ≥ +0.030 ns and WHS ≥ 0 at all four corners. Its figures are the routed utilisation.

| Shape | Base qualifying | Head qualifying | LUT | FF | BRAM tiles | Slices | Rule |
|---|---|---|---|---|---|---|---|
| 8x8/1if | ExtraPostPlacementOpt, +0.073 / +0.034 ns, 43,022 LUT | ExtraPostPlacementOpt, +0.332 / +0.036 ns, 43,477 LUT | +455 | −110 | 0 | −80 | **NOT MET** |
| 1x1/1if | ExtraTimingOpt, +0.158 / +0.033 ns, 32,777 LUT | ExtraTimingOpt, +0.276 / +0.036 ns, 32,455 LUT | −322 | −4 | 0 | −3 | met |

- 1x1: every head directive is at or below the base's qualifying image (32,398, 32,466 and 32,455 LUT against 32,777).
- 8x8: no head directive qualifies without growth. Against the base's qualifying image, the head is +455 (ExtraPostPlacementOpt), +514 (AltSpreadLogic_high) and +567 (ExtraTimingOpt) LUT.
- Reproducible, not noise:
  - all four syntheses repeat round 2's row for row;
  - all four ExtraTimingOpt comparisons repeat round 2's routes exactly, hierarchy and corners included;
  - the synthesised 8x8 head is already +615 LUT.
- Where it moves: the engine, the only changed cell, is −74 LUT. The rest is in cells with identical RTL: the mailbox edit window +1,569, the CSR block −1,338, the gPTP wrapper's own logic +335, the datapath's own logic +220, smaller moves elsewhere.
- The PR body now states the rule as not met at 8x8, with these figures. No RTL was changed to chase the count.
- Only the owner can amend the rule.

## R906-1-F2, MINOR: phase 61's duration. CLOSED (`884c755`)
- `sim_main.cpp` phase 61 now reads "each for 120 Sync pairs, grading the last 80 pairs" on one line, matching `p107_follow(c.tag, 120)` and its `pairs - 80` window.
- Phase 59 said "within 30 s" the same way. It now carries the same wording.

## R905-1-F1, MINOR: the follow range against B.1.1. CLOSED (`884c755`)
- INTEGRATION.md, Rate envelope:
  - The envelope is `RATE_PPM_C` as the integer addend clamp, with its exact value per clock: ±200.000405 ppm at the parent images' 50 MHz (`milan_clk_hz`), ±199.997425 at the generator's default 100 MHz, ±200.003386 at 125 MHz and ±200.000048 at the suite's 2 MHz. Grandmasters up to the envelope from this oscillator are followed, and phase authority shrinks to zero there.
  - B.1.1's fast corner (a LocalClock 100 ppm slow, a grandmaster 100 ppm fast) needs +200.020002 ppm, just beyond every envelope. Per clock, the text gives the shortfall, the offset growth (17 to 23 ns/s) and the step interval (4,429 to 6,018 s). The slow corner needs −199.980002 ppm, inside every envelope.
  - The suite grades ±10 and ±`LOCAL_CLOCK_PPM_C`, the ±100 ppm #107 asks for. "Any conforming grandmaster", "twice that bound fits" and "such a grandmaster is outside B.1.1" are removed.
- TEST_DEVELOPER.md: "Follows grandmasters 10 ppm and `LOCAL_CLOCK_PPM_C` from this oscillator (#107)."
- Phase 59: the comment, the function (`follow_grandmasters_at_10_and_100_ppm`) and its first check (`#107 follow: runs from a capable master`) no longer claim the B.1.1 range. No control names that check.
- `p107_mutants.py`'s docstring says "up to ±100 ppm from this oscillator".
- PR body: the #107 heading and the documented-behaviour list say only what holds.
- The figures come from the generator's own `ppm_addend()` (`receipts/envelope.txt`, `tools/envelope.py`). They match R905-1's receipt for 100, 125 and 2 MHz, and add 50 MHz, the clock the parent ships.
- `make docs` passes.

## RESIDUEs, as written
- R905-1 R1: `// which the jump wound (no anti-windup: #107, the servo unchanged)` (`884c755`).
- R905-1 R2: the PR body carries the sentence as written, for round 2's ExtraTimingOpt pair, which round 3 repeats exactly.
- R906-1 lists no RESIDUE.
- Suggestions applied:
  - S1 (`309292f`): "With credit, it reaches the wire before any queued Announce" and "Without credit, the next beat tries again, 1 s later". ANNTX re-arms the beat before its credit gate.
  - S2 (`884c755`): phase authority is given in the rate's direction and against it.
- S3 and S4 stay with the owners: the parent's AECP silence after the −100 ppm takeover, and the qualification note.

## The merge (`331e27d`; `receipts/merge.txt`)
- Hunk 1: the branch's p106/p107 imports and main's `path_mutants` import, all three kept.
- Hunk 2: main's `say()` (its concurrent arm's printer) with the branch's `#106 ` and `#107 ` prefixes in the all-named-checks rule.
- The resolved file is main's plus exactly the branch's own changes to it.
- `mutants.py` is 865 lines, within the parent's 1,000-line rule; the parent's py ratchet says long module 10 ≤ 10.
- 167 controls; main's verdict-order test passes on the merged arm.

## Gates at `331e27d`
- Processor (`receipts/gates-331e27d.txt`):
  - contract, ucpu, parser, engine, gaskets, tsngen, bench, lint and docs all rc 0;
  - the engine suite is 2,199 ×3 and 61, every INFO line and tally identical to `a728cc3`'s;
  - **mutation arm: 167 of 167 caught**, by every check each names, the positive control passing; run as two halves of the table, with the verdicts in table order.
- Parent, gitlink at `331e27d` (`receipts/parent-r3.txt`):
  - milan_dp gptp 212/212 and gptp-lat 212/212;
  - gptp_shadow 326/326;
  - gptp_plane, gptp_txts, gptp_tables and clkvalid pass;
  - milan_dp_gm_steps: 196/196, its five controls caught;
  - the py, sv, cpp and sh ratchets pass.
  - The ax1x1gptp leg (milan_dp_gptp) was stopped unfinished: at this load it needs more than a session task's 2 h. It was not in round 2's set.

## Reviewer focus
- `receipts/route-inputs.txt`: the gate-style input digest per route, and the comment-free body hash of the generated top across all eight exports.
- `receipts/route-repeat.txt`: synthesis and the ExtraTimingOpt placement, round 2 against round 3, row for row.
- `receipts/routes-r3.txt`: every route's four corners, routed and placed utilisation, `best()`'s pick, and the partition of the 8x8 change into disjoint pieces (the shared-LUT reconciliation is printed).
