# [A831] FPGA-gPTP #106 / #107, round 2: HANDOFF

**Status (11-23 18:55): REVIEW READY at `a728cc3`. Every gate the brief names passes at the final head. Nothing is running; nothing was pushed.**
- **ETA:** none; done. `REVIEW-READY.md` and `PR-BODY.md` (106-107-announce-rate → main, "Closes #106, closes #107") are written, and '[A831] REVIEW READY' is posted on #106 (https://github.com/Mister-M-alt/FPGA-gPTP/issues/106#issuecomment-7109217025).

## Ruling applied (#107, [A10])
- **D1 = C.**
  - BECOME writes rate 0 through PHC word 3, which now always applies.
  - Word 3's high word carries the integrator (the negated estimate), so scaledLastGmFreqChange = −(the slave rate estimate).
  - gmTimeBaseIndicator still counts BECOME's word-3 write, once per mastership.
  - BECOME stays 3 words; the ROM stays at 1,013 of 1,024.
- **D2:** no servo change; no estimator, anti-windup or engine bound was added.
- **D3:** no grading change; phase 61 grades with the existing 50 % / 2,199 rule.
- **A1:** documented only (INTEGRATION.md rate envelope: zero the test clock's frequency adjustment before the grandmaster-change and tie scenarios).

## Brief items
1. BECOME / word 3 / gmTimeBaseIndicator: done (`d0a0e3b`). Word 3 writes `phc_addend_o` unconditionally. The TLV is zero when no word-0 rate was written since reset or since the last mastership; the new phase-52 case and a control cover this.
2. scaledLastGmFreqChange = −(estimate): done; the estimate is S_INTG, unchanged servo.
3. Phase 60 retargeted:
   - after the +60 ppm, 90 µs-jump takeover, the rate is 0 within one trim unit (it is exactly 0, one write);
   - a grandmaster 10 ppm from the oscillator then settles within 0.2 ppm.
   - Phases 59 and 61 are kept. There are seven #107 controls (one each for 59 and 61, the rest on 60/52), each caught by name.
4. The ±197 / ±199 ppm cases are recorded as documented behaviour (receipts/near-clamp-C.txt: 197 ppm from this oscillator takes 5 to 17 s, and −199 from a +199 estimate takes 50 s). INTEGRATION.md now states that phase authority is `RATE_PPM_C` − |rate| (200 − |rate| ppm) and that a mastership runs on the oscillator. The round-1 sentence "that bound is the follow range" is removed.
5. Parent gate with takeovers from ±100 ppm grandmasters (a scratch phase on the gmstep leg): 252/252, **no media unlock, no lost samples, tu for the 0.25 s holdover**.
   - The same phase at 1616fc8f fails exactly its two oscillator checks.
   - gm_steps passes: clean leg 196/196, 5 controls caught.
   - gptp_shadow passes at +100 and −100 ppm (327/327 each, addend 0 as grandmaster).
   - The media clock did not unlock, so no STOP was needed.
6. Limits:
   - ROM 1,013 ≤ 1,013.
   - OOC engine −20 LUT (≤ +40 against 1616fc8f), −3 FF, BRAM/DSP equal, WNS +2.093 ns.
7. Builds: 1x1/1if and 8x8/1if, head and base, through vivado-slot.sh, at most two at a time. All four meet the #818 floor at every corner:

   | Route | Slow WNS | Fast WHS | LUT | FF | Slices | BRAM tiles | DSP |
   |---|---|---|---|---|---|---|---|
   | 1x1 head | +0.276 | +0.036 | 32,455 | 42,624 | 14,271 | 80 | 11 |
   | 1x1 base | +0.158 | +0.033 | 32,777 | 42,628 | 14,274 | 80 | 11 |
   | 8x8 head | +0.244 | +0.036 | 43,586 | 50,886 | 15,221 | 94.5 | 11 |
   | 8x8 base | +0.064 | +0.027 | 42,998 | 50,993 | 15,680 | 94.5 | 11 |

   - The engine cell is −80 LUT in both shapes.
   - The 8x8 +588 LUT is KL_mbx_cdc/u_edit (+1,572) and csr (−1,342), with unchanged RTL (re-synthesis variation).
   - One directive (ExtraTimingOpt, the route-1x1 record's selected one) per image, as the brief asks: one build each.
8. Processor full gates at the final head `a728cc3`:
   - contract, ucpu, parser, engine (2,199 ×3, 61), gaskets, tsngen, bench, lint and docs, all rc 0;
   - **mutation arm 167/167 caught** by every check they name, positive control passing.
   - Parent consumer gates: milan_dp gptp 212/212, gptp-lat 212/212, gptp_shadow passes.

## Not from #107, for the owners
- The parent's AECP sends nothing for about 0.4 s after the −100 ppm takeover in the scratch phase. The same happens at 1616fc8f. The harness asks again (receipts/parent-takeover-gate.txt).
- The render stage counted 2 slips (head) and 13 (base) in the +100 ppm grandmaster change into the follow, before any takeover. That is the GM change into a grandmaster 100 ppm away, with the servo unchanged (D2); it is reported only.
- Round 1's #106 commit had taken `tb/verilator/engine/mutants.py` to 1,002 lines, over the parent's 1,000-line module ratchet ("long module" 10 → 11). Round 2 brings it back to 1,000; the parent's ratchets pass at the pin.
- Residue (D2, unchanged): integrator anti-windup. A takeover during a phase transient reports the wound integrator as scaledLastGmFreqChange: −200 ppm after phase 60's jump, where the grandmaster ran at 60 ppm. This is documented, not graded.

## Lane
- Repo `$LANES/gptp106-107`, branch `106-107-announce-rate` at `a728cc3`, from `1616fc8f`. Push URL disabled; nothing pushed. Tree clean.
- Round-2 commits: `d0a0e3b` (code, tests, controls, images) and `a728cc3` (docs).
- Worktrees (detached at `a728cc3`): `$VALIDATION_STORAGE/gptp106-a831/gate-a728cc3` (gates and arm) and `.../oocwt-a728cc3` (OOC). Remove with `git worktree remove` when no longer needed.
- Scratch parent `$VALIDATION_STORAGE/scratch/gptp106-parent`, branch `gptp106-107-consumer`, local only:
  - `2cf4b61406` pins gptp-processor at `a728cc3`;
  - `f9f8594417`, `bc4e204e08` and `000aef1c42` add the scratch takeover gate (gmstep `--takeovers`, gptp_shadow `P107_MASTER_SIGN`). These are not for push: the gmstep phase trips the parent's C++ ratchet (one long function, one multi-declarator).
- Route builds: `/data-2/milan/tmp/gptp106-a831` (3.9 GB), on /data-2 because /data is 94 % full.
  - Clones: `base` (854bd72367), `head` (2cf4b61406), `basesim` (the base takeover control).
  - Route trees: `route-<base|head>-<1x1|8x8>`.
  - Safe to delete after review.
- Tools: Verilator 5.054 (host) for the processor gates, the pinned 5.050 for the parent; Vivado 2026.1.

## Log
- 14:15 implementation done; pass 1 2199/2199.
- 14:40 the 10 new or changed controls caught; commits `d0a0e3b` and `a728cc3`.
- 14:44 OOC done (−20 LUT).
- 14:56 takeover gate try 1 failed on a harness-state defect in my scratch phase (the slew phase's origin override, a settime-moved PHC); fixed.
- 15:03 processor gates at the head: all rc 0. Arm started.
- 15:09 takeover try 2: one unanswered GET_COUNTERS (marker values); retry added.
- 15:28 takeover gate at the head 252/252; 15:30 the base control fails only its two oscillator checks.
- 15:45 to 17:01 the four routes, all meeting the floor.
- 15:57 milan_dp gptp/gptp-lat 212/212 each.
- 18:46 the arm complete: 167/167.
- Commands longer than the 10-minute foreground limit ran as tracked background tasks of this session (not detached), and each was waited on to completion.

REVIEW READY a728cc3
