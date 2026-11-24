# [A836] FPGA-gPTP #109, round 1: HANDOFF

**Status (11-24 16:55): REVIEW READY. Head 8e4889b on 109-negative-delay-clamp (local, not pushed; base 1213ac5b). Everything passes: reproduction (24 FAIL at 1213ac5b), engine suite 2296 x3 + 61 at the head, engine arm 175/175 (8 new #109 controls), repo gates, OOC identical (delta 0), parent consumer gates in scratch (milan_dp gptp/gptp-lat, gptp_shadow, gptp_plane/tables/txts, gm_steps, milan_dp_gptp). See REVIEW-READY.md, PR-BODY.md, receipts/INDEX.md. ETA: done.**

## Cause (at 1213ac5b)
- `_pdpost_verdict` judges the computed 64-bit D as good iff `(D + NPD_LO_C) u<= NPD_HI_C + NPD_LO_C`, i.e. -80 <= D <= 800.
  A D below -80 is "bad": S_PDOK is cleared and asCapable falls on that one exchange.
- `_pdpost_corrected_delay` writes D unclamped to S_PDELAY (the Sync path's link delay) and to PUB 3 (`pub_pdelay_ns_o`, 32 bits).
  So inside [-80, 0) the negative value is published and subtracted; the issue's "clamped to 0" describes only the parent CSR (KL_gptp_shadow.sv clamps on bit 31).

## Fix (generator only; word-neutral: shipping 1013 / seeded 1014 words, same leg map)
- Floor, branch-free: `m = (D + NPD_HI_C) >>arith 63; D -= (D + NPD_HI_C) & m`, i.e. D = max(D, -800). Written to S_PDELAY and PUB 3.
- Verdict: bad iff the sign of `D - (NPD_HI_C + 1)` is clear, i.e. D > 800. Any negative D is good (ASCAP_UP_C ladder, lostResponses as before).
- NPD_LO_C retired: generator, docs/INTEGRATION.md table, scripts/check_docs.py CONSTANTS. The parent parses no NPD_* constant (searched builder, tests, scripts).

## Design notes
- Datapath range: t2/t3 fold as int32(seconds[31:0]) * 1e9 + nanoseconds (MULS is signed 32x32; the nanoseconds field is not range-checked), so t3 - t2 <= (2^32-1)(1e9+1); corr >= 0. The wire-reachable D is at least -2,147,483,649,647,483,648 ns; the test drives -2,147,483,641,057,566,821.
- pub_pdelay_ns_o is 32 bits and the shadow clamps on bit 31, so an unfloored D below -2^31 can reach the CSR with either sign (1213ac5b published 0x9DCD1F9B for the wire minimum). The engine publishes the floored, signed value (= the used value); the CSR clamp to 0 stays the only clamp to 0. A control ("the engine publishes the unfloored delay") pins this.
- No "-81 clears" test exists in this repo or the parent (searched both). Phase 22's scenario check is the nearest; it is kept and reworded, and the new phases 62-64 carry the inverted expectation.
- Clause check: 802.1AS-2011 computePropTime is 11.2.15.2.4 (11.2.15.3.4 does not exist); 11.2.13.2.1 f), 11.2.2, Figure 11-8; 2020 11.2.2, 11.2.13.7, 11.2.14.2.1 f), 11.2.19.3.4 confirmed (receipts/clauses.txt).

## Log (11-24)
- 06:33 issue read; '[A836] TAKEN' posted (earlier session); origin and HEAD 1213ac5b confirmed.
- 06:48 restarted; ruling read; parent scratch cloned at origin/dev-soft-core aa30d77f (gitlink 1616fc8f, an ancestor of 1213ac5b).
- 07:0x reproduction at 1213ac5b: -81, -263, the over-stated case, -800, -801, -5 ms and the wire minimum lose asCapable (24 FAIL); -3 and -80 pass.
- 07:3x fix; engine suite 2296/2296 x3 + 61/61.
- 07:42 committed f3c33d0 (fix, tests, controls) and 124683a (docs).
- 07:45-08:10 repo gates; OOC before/after identical (engine 5,375 LUT, 3,617 FF, WNS +2.093 ns).
- 08:10-10:05 parent gates (Verilator 5.050, the parent's CI pin; 5.054 cannot build milan_dp's gptp harness, an unrelated harness/tool issue).
- 09:42 arm slice 0:7 ran at 4 jobs beside one parent sim, i.e. 5 legs for ~11 min: my leg counter (pgrep -x, 15-char name limit) read 0. Fixed (pgrep -f); every later slice counts the parent sim.
- 09:53 slice 7:12 was killed by my own 590 s command timeout before any verdict; it reruns inside 7:18.
- 10:04 milan_dp_gptp's make wrappers stopped (SIGKILL) so its 2-job verify step cannot start under the arm; its ax1x1gptp sim keeps running to completion; verify_abort.py and verify_recentres.py run by hand afterwards.
- 10:05 arm loop started detached (waited on from the foreground), slices sized 4 x jobs - 1.
- 12:31 milan_dp_gptp's ax1x1gptp sim finished: 151/151, exit 0 (10,314 s wall).
- 12:55-13:35 verify_abort.py (1 leg, arm at 3 jobs): 6/6, 20/20, 14/14.
- 13:42-14:05 verify_recentres.py --jobs 2 (arm at 2 jobs): 14/14.
- 14:00-14:20 final engine suite at 8e4889b: 2296 x3, 61 (two passes at a time, arm at 2 jobs).
- 16:43 engine arm complete: 175/175 caught across 17 slices, every slice's control passing.
- 16:55 outputs final (REVIEW-READY.md, PR-BODY.md, receipts/INDEX.md); '[A836] REVIEW READY' posted on #109.

REVIEW READY 8e4889b
