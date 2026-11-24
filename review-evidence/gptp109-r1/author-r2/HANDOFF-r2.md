# [A836] FPGA-gPTP #109 (PR #110), round 2: HANDOFF

**Status (11-24 19:36): REVIEW READY at 74830c2, on 109-negative-delay-clamp. It is local and not pushed; origin is still at 8e4889b.**

- F1 is fixed: the reproduction was re-run with the committed harness against the 1213ac5b ROM. It gives 31 FAIL, all `#109`, the same as R921-1. The PR body figure and list are corrected.
- F2 is fixed exactly.
- S1 is taken: a new trial and a ninth control.
- S2 is listed, not taken.
- At the head:
  - Engine suite: 2302 x3 and 61.
  - #109 controls: 9/9.
  - The affected existing arm entries: 12/12.
  - Docs, contract and lint pass.
  - The parent ratchets pass.
- No comments posted. Outputs: REVIEW-READY.md, PR-BODY.md (full replacement), receipts/INDEX.md.

## What changed (8e4889b..74830c2)

- f5d28f5: `docs/INTEGRATION.md:978` now reads "That follows 802.1AS-2011 11.2.13.2.1 f)." (F2.)
- 74830c2 (S1):
  - Phase 64 gains "#109 the most positive delay of the wire". It is a `PD_WIRE` exchange: t2 at 0x7FFFFFFF s plus 2^32 - 1 ns, t3 seconds 0x80000000. The plane computes +2,147,483,649,647,485,841 ns.
  - It adds 6 checks: it runs, it ran, D above 2^60, asCapable falls, the next Follow_Up is not used, and capable again afterwards.
  - The ninth control, in `p109_mutants.py`, is "the verdict reads D - 801 from bit 31" (R921-1's probe R5). It is word-neutral, and both checks it names catch it.
- No generator, RTL or ROM change.

## F1, the figure

- At 8e4889b's harness on the base ROM: 2296 checks, 2265 PASS, 31 FAIL. This is identical to R921-1's `repro_suite.txt`, got and exp values included.
- At the head's harness on the base ROM: 2302 checks, 2271 PASS, the same 31 FAIL lines. The new positive trial passes at base.
- The 7 failures beyond the earlier 24 are "its offset uses the delay exactly" (got 0xb = `P109_BG_OFF`), at -81, -263, over-stated, -800, -801, -5 ms and the wire minimum.
- The earlier 24 came from an uncommitted harness whose background pairs used offset 0.
- The PR body now says 31, adds "its offset is not exact" to the list, and names the unfloored publication at -801, -5 ms and the wire minimum.

## Judgement calls

- I re-ran the 12 existing arm entries whose named checks include a whole-run grade (`#82`, `#84`, `#85`), not only the #109 controls.
  - The new trial runs before those grades, and mutants.py requires a control to fail every check it names, so these 12 could in principle have changed verdict. All 12 are caught.
  - The other 155 entries grade only earlier, unchanged stimulus, so they were not re-run. The PR body and REVIEW-READY state this.
- I measured the reproduction at both harnesses: 8e4889b's, to match the reviewer, and the head's, to show the claim at the new head.
- S2 is not taken, because it is outside the brief. It is a comment and identifier change only and could go to the residue checklist.

## Log (11-24, from log and commit times)

- 18:31: read R921-1 and round 1. The lane is clean at 8e4889b, which equals origin.
- 18:32-18:38: reproduction at 8e4889b's harness on the base ROM (detached): 2296 / 2265 / 31 FAIL.
- 18:33: F2 committed (f5d28f5).
- 18:34-18:40: S1 trial and control written, and a scratch shipping pass gave 2302/2302.
- 18:40: committed 74830c2. Started the head suite, the head-harness reproduction and the #109 controls (--jobs 2), 4 legs in total.
- 18:40-18:42: docs, contract and lint at the head. The parent ratchets ran in the scratch parent, with the gitlink staged at 74830c2 and never committed.
- 18:47: head-harness reproduction gave 2302 / 2271 / 31 FAIL, identical lines. Started the 12 whole-run-grade entries at --jobs 1.
- 18:58: suite gave 2302 x3 and 61, rc 0.
- 19:08: #109 controls gave 9/9, rc 0.
- 19:09: stopped the --jobs 1 run, which had no verdicts yet, and restarted at --jobs 3.
  - My first kill hit the wrong process group, so the old runner kept going beside the new one for a few seconds: 1 extra leg.
  - I removed its staging directory while it ran, then stopped it by its own process group. Its output is discarded.
- 19:35: whole-run-grade entries gave 12/12, rc 0.
- 19:36: outputs written.

## Leftovers

- Scratch: `$VALIDATION_STORAGE/gptp109-a836/r2`.
- The scratch parent `$VALIDATION_STORAGE/scratch/gptp109-parent` has the gptp-processor gitlink staged at 74830c2 but not committed. It is scratch and never pushed.
- Pending for the manager:
  - push 74830c2;
  - replace the PR #110 body with PR-BODY.md;
  - publish receipts;
  - S2, optionally.

REVIEW READY 74830c2
