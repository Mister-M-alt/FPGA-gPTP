# [A831] FPGA-gPTP #106 / #107, round 2: review readiness

**Review-ready: branch `106-107-announce-rate` at `a728cc3`, from `1616fc8f`, local only (never pushed). It closes #106 and #107.**

## Commits
- `c5b4f8c` #106: SELF ends in ANNTX, so the first master Announce leaves in the handler that takes the role. Tests, controls and images.
- `105ef8f` #106: docs and the ROM budget.
- `7427fc0` #107: phase 59 (±10 and ±100 ppm grandmasters followed within 0.2 ppm) and the stated follow range.
- `a3347e2` source-evidence line after the #106 docstring.
- `d0a0e3b` #107, D1 = C:
  - BECOME writes rate 0 through PHC word 3, which now always applies.
  - Word 3's high word carries the integrator, so scaledLastGmFreqChange = −(the slave's estimate).
  - Phase 60 is retargeted and phase 61 is added; phase 52 is retargeted, with an unfollowed-grandmaster case.
  - Seven #107 controls, two #100 controls moved to the new word-3 layout, and the four images.
  - The arm module is back to 1,000 lines.
- `a728cc3` #107 docs:
  - the mastership rate;
  - phase authority, 200 − |rate| ppm;
  - the near-clamp settling times;
  - the TLV after a wound takeover;
  - the test-clock setup step (A1).

## Evidence at `a728cc3`
- Processor gates:
  - engine suite 2,199 ×3 and 61;
  - the mutation arm, 167 of 167 caught by every check they name, with the positive control passing;
  - contract, ucpu, parser, gaskets, tsngen, bench, lint and docs, all rc 0.
- OOC: the engine is 5,375 LUT (−20 against 1616fc8f), 3,617 FF (−3), 1.5 BRAM and 6 DSP, WNS +2.093 ns; the µCPU is unchanged. The ROM is 1,013 of 1,024 words.
- Parent, with its gitlink at the head (scratch, local):
  - milan_dp gptp 212/212 and gptp-lat 212/212;
  - gptp_shadow at +100 and −100 ppm, 327/327 each;
  - milan_dp_gm_steps: the clean leg 196/196 and its 5 controls caught;
  - the Python, SystemVerilog and C++ ratchets pass.
- Takeover gate (the gmstep leg plus a scratch phase, takeovers from +100 and −100 ppm grandmasters): 252/252.
  - No PHC step; the PHC runs at 0.000 ppm as grandmaster.
  - tu is held at least the 0.25 s holdover.
  - MEDIA_UNLOCKED is unchanged, and every PDU is presented once in order at one offset; nothing is refused or slipped, and there is no MEDIA_RESET.
  - The same phase at 1616fc8f fails exactly its two oscillator checks.
- Routes (split image, one interface, ExtraTimingOpt), each meeting the #818 floor at every corner with 0 failing endpoints:
  - 1x1/1if: +0.276 / +0.036 ns;
  - 8x8/1if: +0.244 / +0.036 ns.
- Against the base routes:
  - 1x1: −322 LUT, −4 FF, −3 slices;
  - 8x8: +588 LUT, −107 FF, −459 slices;
  - BRAM and DSP are unchanged.
  - The engine cell is −80 LUT in both. The 8x8 rise is in KL_mbx_cdc/u_edit and csr, whose RTL is unchanged.
- Receipts: `receipts/INDEX.md`. PR body: `PR-BODY.md`.

## Reviewer focus
- `KL_gptp_engine.sv` word 3 now writes `phc_addend_o` unconditionally. Every BECOME therefore makes one addend pulse, and before #107 a settled mastership made none. Parent consumers see one more rate write per mastership. gptp_shadow and the takeover gate show its value, 0.
- `slave_rate_seen_r` now means "a word-0 rate since reset or since the last mastership" (set by word 0, cleared by word 3). It gates the TLV to zero when the time base has not moved.
- BECOME stays three words: `RDST S_INTG`, `ALU SHL 32`, `WRST PHC|3`. The low word is rate 0. The high word is the integrator, which the servo keeps negated, so it is exactly the change.
- The integrator is not cleared at a takeover, so a later slave period starts from the estimate, as after a step. With D2 = no servo change, a mid-transient takeover reports the wound integrator (phase 60's INFO line: −200 ppm against a 60 ppm grandmaster). That case is documented, not graded; anti-windup is on the residue list.
- The parent's AECP went silent for about 0.4 s after the −100 ppm takeover in the scratch phase, at 1616fc8f as well. That is not from #107; it is recorded in `receipts/parent-takeover-gate.txt` for the parent's owners.
- At the +100 ppm grandmaster change into the follow (before any takeover), the render stage counted 2 slips at the head and 13 at the base. That event is not the change under review; it is reported only.
