# [A831] FPGA-gPTP #106 / #107, round 3: HANDOFF

**Status (11-23 23:21): STOP at `331e27d`. The owner's image rule is not met at 8x8/1if: the qualifying head image is +455 LUT against the qualifying base image, and every head directive grows (+455, +514, +567). Everything else the brief names is done and passes at `331e27d`. Nothing is running; nothing was pushed.**
- **ETA:** none from this lane. The next step is the owner's ruling on the rule (R906-1-F1).
- **Not posted:** '[A831] REVIEW READY' on #106. With a gate unmet under the brief's own STOP condition, that post would be false. `STOP-NOTE.md` is a public-safe note with the measured figures, ready for the manager to post or relay. `REVIEW-READY.md` and `PR-BODY.md` are written to match the measurements.

## Brief items
1. **R906-1-F1, the image rule: measured, NOT MET at 8x8, so STOP.**
   - The comparison is controlled, with all three #818 directives through `vivado-slot.sh`. At most two of mine ran at a time, and each started with MemAvailable ≥ 51 GB.
   - Each side and shape is a route set: the shipping route at ExtraPostPlacementOpt, plus AltSpreadLogic_high and ExtraTimingOpt placed from its synthesis checkpoint by the recipe's script (the gate's `bound()` accepts each). That makes 12 routes, all rc 0, 0 routing errors.
   - Generated inputs, digested the gate's way: base and head differ only in `KL_gptp_engine.sv`, `gptp_ucode.hex` and the generated top, whose comment-free body is identical. The firmware, CSR map, AEM image and boot ROMs are the same bytes.
   - Repeatability: all four syntheses repeat round 2's row for row, and all four ExtraTimingOpt comparisons repeat round 2's routes exactly, hierarchy and corners included. The synthesised 8x8 head is +615 LUT.

   | Shape | Base qualifying (best()) | Head qualifying | LUT | FF | BRAM | Slices | Rule |
   |---|---|---|---|---|---|---|---|
   | 1x1/1if | ETO +0.158/+0.033 ns, 32,777 | ETO +0.276/+0.036 ns, 32,455 | −322 | −4 | = | −3 | met |
   | 8x8/1if | EPPO +0.073/+0.034 ns, 43,022 | EPPO +0.332/+0.036 ns, 43,477 | +455 | −110 | = | −80 | **not met** |

   - The 8x8 base at AltSpreadLogic_high misses the floor (WNS +0.006 ns).
   - The 8x8 change splits into disjoint pieces whose sum is reconciled exactly through the shared-LUT sites:
     - the engine −74;
     - the mailbox edit window +1,569;
     - the CSR block −1,338;
     - the gPTP wrapper's own logic +335;
     - the datapath's own logic +220;
     - no piece moves a RAMB or DSP.
   - The PR body's gate claims now say the rule is met at 1x1 and not met at 8x8. No RTL was touched to chase the count.
2. **R906-1-F2: done (`884c755`).** Phase 61 reads "each for 120 Sync pairs, grading the last 80 pairs". Phase 59's "within 30 s" was the same claim and carries the same wording.
3. **R905-1-F1: done (`884c755`).**
   - INTEGRATION.md gives the exact envelope per clock: ±200.000405 ppm at the parent's 50 MHz, ±199.997425 at 100 MHz, ±200.003386 at 125 MHz and ±200.000048 at 2 MHz.
   - The B.1.1 fast corner, +200.020002 ppm, is stated as just beyond every envelope, with the shortfall, the offset growth and the step interval. The slow corner, −199.980002 ppm, is inside.
   - The suite grades ±10 and ±100 ppm, which meets #107's ±100 ppm.
   - TEST_DEVELOPER.md, phase 59's comment, function name and check name, the `p107_mutants.py` docstring and the PR body are corrected.
   - The parent ships at `milan_clk_hz` = 50 MHz, a clock R905-1's receipt did not list; it is added.
   - RESIDUEs as written: R1 is in `884c755`; R2's sentence is in the PR body, for the ExtraTimingOpt pair round 3 repeats exactly. R906-1 lists none.
   - Also applied: S1 (`309292f`, the credit condition on the first Announce, checked in ANNTX) and S2 (`884c755`, phase authority by direction).
4. **Merge: done (`331e27d`, one merge commit of origin/main `7cfd6a0`).**
   - The one conflict was `mutants.py`: the imports, plus the named-check rule with main's `say()`.
   - The resolved file is main's plus exactly the branch's changes, 865 lines (≤ 1,000), with 167 controls. Main's order test passes. `hdl/` is unchanged.
   - Processor gates at `331e27d`, all rc 0:
     - contract, ucpu, parser, engine (2,199 ×3, 61; every INFO line and tally identical to `a728cc3`'s), gaskets, tsngen, bench, lint, docs;
     - **arm 167/167 caught**, with the positive control passing.
   - Parent with the gitlink at `331e27d`:
     - milan_dp gptp 212/212 and gptp-lat 212/212;
     - gptp_shadow 326/326;
     - gptp_plane, gptp_txts, gptp_tables and clkvalid pass;
     - milan_dp_gm_steps 196/196 with 5 controls caught;
     - the py, sv, cpp and sh ratchets pass (long module 10 ≤ 10).

## Deviations, stated plainly
- **The arm ran in two halves.** The whole-table run at `--jobs 8` paces at about 122 min here, past a session task's 2 h limit, and its output is block-buffered. I stopped it at 27 min, before it had printed anything (rc 143, recorded). Then I ran the arm's own `main()` over `MUTATIONS[0:84]` and `[84:167]`, unbuffered (`tools/lane/armslice3.py`), each with the positive control: 85/85 and 84/84. The 167 verdicts are in table order.
- **milan_dp_gptp (ax1x1gptp) not run to completion.** It ran 70 min and reached 6.5 simulated seconds with 81 `[ ok ]` lines and no failures. A session task cannot hold it past 2 h, so I stopped it. It was not in round 2's consumer set, and round 1's summary records no result for it.
- **Not rerun at `331e27d`: the round-2 scratch takeover gate (252/252) and the −100 ppm gptp_shadow variant.** These are local harness patches, not parent gates. The PR body cites them at `a728cc3`, whose `hdl/` tree `331e27d` carries unchanged.
- OOC was not rerun: `hdl/` is unchanged, so round 2's `a728cc3` OOC stands.

## For the owners (unchanged from round 2)
- S3: the parent's AECP is silent for about 0.4 s after the −100 ppm takeover, at 1616fc8f too.
- S4: the qualification's regain observation needs a better Announce soon after the regain.
- D2 residue: anti-windup.

## Lane
- Repo `$LANES/gptp106-107`, branch `106-107-announce-rate` at `331e27d`. Push URL disabled; nothing pushed; tree clean.
  - Round-3 commits: `884c755`, `309292f`, `331e27d` (merge).
- Worktrees: `$VALIDATION_STORAGE/gptp106-a831/gate-331e27d` (the gates) and `base-1616`. The round-1/2 worktrees and the arm worktree are removed.
- Scratch parent `$VALIDATION_STORAGE/scratch/gptp106-parent`, branch `gptp106-107-r3`: `3611d0d2ad` (854bd72367 + the pin at `331e27d`). Local only. The round-2 branch `gptp106-107-consumer` is untouched.
- Route builds on /data-2 (the round-2 and round-3 trees and clones, 6.1 GB) are **deleted**. The reports each figure comes from are in `receipts/routes/`.
- Logs: `$VALIDATION_STORAGE/gptp106-a831/logs-331e27d` (gates, arm halves, the stopped run) and `logs-parent-r3`.
- Tools: Verilator 5.054 (host) for the processor gates; pinned 5.050 for the parent; Vivado 2026.1.

## Log (11-23)
- 20:01 round-3 route tooling written; the comparison writer checked against the gate's `bound()`.
- 20:09 to 20:33: the four exports; route inputs digested.
- 20:10 and 20:18: the 8x8 shipping routes started (slots 0 and 1).
- 20:36 to 20:45:
  - F1/F2/R1/S1/S2 text, `make docs` passing;
  - commits `884c755` and `309292f`;
  - merge `331e27d`;
  - processor gates, the arm and the parent chains started.
- 20:52 both 8x8 syntheses equal round 2's row for row.
- 21:09 processor gates all rc 0.
- 21:10 the arm stopped and restarted in halves (output buffering, the 2 h limit).
- 21:50 base 8x8 ETO repeats round 2's route exactly.
- 22:15 arm halves 85/85 and 84/84.
- 22:23 8x8 sets complete: +455 LUT, every head directive grows.
- 22:25 milan_dp_gptp stopped; gm_steps run alone, passing at 22:43.
- 23:17 1x1 sets complete: −322 LUT, met.
- 23:17 to 23:21: receipts, scrub and privacy check (0 fail), /data-2 cleanup, documents.

STOP: the 8x8/1if image the parent would ship grows by 455 LUT (43,022 → 43,477; every head directive grows), so the owner's no-growth rule is unmet at 331e27d; only the owner can amend it
