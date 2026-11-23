Closes #106, closes #107

## #106: a master announcement on the wire at every receipt-timeout instant

When the announce receipt watch expired, the plane took the grandmaster role and armed its first Announce on a 2 ms timer beat (and its Sync on a 1 ms beat). An Announce already queued at the timeout instant, or arriving within those 2 ms, then ran first: it re-elected its grandmaster and disarmed both beats, so the aged port's mastership never reached the wire. The expiry-first ordering of #100 was right; its tests graded only the commits, which name thisClock whether or not anything was sent.

The fix: SELF, where BECOME ends, continues into ANNTX. The handler that takes the role sends the first Announce and arms the 1 s cadence from it (802.1AS-2011 Figure 10-15: UPDATE's newInfo takes IDLE to TRANSMIT_ANNOUNCE, and announceSendTime counts from that transmission). ANNTX keeps its role, asCapable and transmit-credit gates: without credit at the instant, the next 1 s beat tries again. The ROM shrinks by two words, to 1,013 of 1,024.

Tests, graded on transmitted frames:
- Phase 57: a better grandmaster announces 3.000 s to 3.010 s after its previous Announce, at several phases against the millisecond tick. In every gap the port is aged and a master Announce leaves after the instant, before the next Announce re-elects the grandmaster. At 1616fc8f, the eight gaps up to 3.002 s fail.
- Phase 58: on regaining the role from a grandmaster that turned worse, the first master Announce leaves within 1 ms, then four more 1 s apart. With a better Announce 1 ms behind the worse one, the master Announce still leaves first. At 1616fc8f, the at-once and race checks fail.
- Two planted defects (`tb/verilator/engine/p106_mutants.py`): the deferred first Announce, and a first Announce that arms no cadence. Each is caught by every check it names.

Milan v1.2 4.2.6.2.3 and Table 4.2 apply, with the project's ruling that the timeout wins at the instant, graded on the wire.

## #107: grandmasters ±10 and ±100 ppm from this oscillator, and a mastership on this oscillator

The servo has no sign or limit defect. Phase 59 follows grandmasters at +10, −10, +100 and −100 ppm against this oscillator, each settling within 0.2 ppm; it passes at 1616fc8f too. The failure came from the rate the plane kept as grandmaster. Its slave was still correcting a phase step when its grandmaster left, so the integrator it kept had been wound to the +200 ppm rail. A test clock that then followed the plane put a grandmaster "10 ppm away" from it beyond the trim.

Per the ruling on this issue (D1 = C), a mastership now runs on this oscillator. This is 802.1AS-2020's ClockMaster on its LocalClock (10.1.2.1, 10.2.4.14):
- BECOME's PHC word-3 write carries rate 0 in its low word. The engine now always applies it; before, it applied only while a slew was active. The time base keeps its phase, and its frequency steps by the departed grandmaster's rate.
- The high word carries the integrator, which is the negated rate estimate. So the engine sends scaledLastGmFreqChange = −(the slave's estimate) (10.2.8.2.1 l), 11.4.4.3.9). It sends zero when no slave rate has been written since reset or since the last mastership; the time base has then not moved.
- gmTimeBaseIndicator still counts BECOME's write, once per mastership. BECOME stays three words, so the ROM stays at 1,013 words.
- The servo is unchanged (D2), and so is the TLV grading (D3).

Tests:
- Phase 59: grandmasters at +10, −10, +100 and −100 ppm from this oscillator, each from mastership, each for 120 Sync pairs, grading the last 80 pairs: the mean trim is within 0.2 ppm of the grandmaster's rate and the offset within 1 µs. This is the ±100 ppm #107 asks for.
- Phase 60: a grandmaster at +60 ppm jumps 90 µs and leaves two pairs later. The mastership's rate is this oscillator's, within one trim unit, although the integrator holds +200 ppm. A grandmaster 10 ppm from this oscillator is then followed within 0.2 ppm.
- Phase 61: under ±8 ns origin noise, grandmasters at +10, −10 and +10 ppm, each for 120 Sync pairs, grading the last 80 pairs; after each, scaledLastGmFreqChange is within 50 % of the time base's change (the qualification's grading).
- Phase 52 (#100) is retargeted. BECOME writes rate 0 whatever the slew level, and the change is rate 0 less the estimate. A new case elects a grandmaster and loses it before any pair: its mastership carries no frequency change.
- Seven planted defects (`tb/verilator/engine/p107_mutants.py`), each caught by every check it names:
  - the 1616fc8f BECOME, which keeps the slave's rate;
  - word 3 applied only during a slew;
  - the TLV with its sign inverted;
  - the TLV taken from the last trim;
  - the TLV scaled by 2^39;
  - a mastership that leaves the slave rate seen;
  - a trim short of a grandmaster 100 ppm away.
- Two #100 controls follow the new word-3 layout.

Documented behaviour (INTEGRATION.md, Rate envelope):
- The trim envelope is `RATE_PPM_C` as an integer addend clamp, `ppm_addend(RATE_PPM_C, clk)`. It is ±200.000405 ppm at the parent images' 50 MHz, ±199.997425 ppm at the generator's default 100 MHz, ±200.003386 ppm at 125 MHz and ±200.000048 ppm at the engine suite's 2 MHz. Grandmasters up to the envelope from this oscillator are followed; phase authority shrinks to zero there.
- 802.1AS-2020 B.1.1 bounds each LocalClock to ±100 ppm of TAI. Its fast corner, a LocalClock 100 ppm slow following a grandmaster 100 ppm fast, needs (1 + 100 ppm) / (1 − 100 ppm) − 1 = +200.020002 ppm. That is just beyond every envelope above, by 0.019597 ppm at 50 MHz, 0.022577 ppm at 100 MHz, 0.016616 ppm at 125 MHz and 0.019954 ppm at 2 MHz. Such a grandmaster is followed only with periodic steps: its offset grows 17 to 23 ns each second and passes `STEP_LOCKED_NS_C` every 5,103 s at 50 MHz (4,429 s at 100 MHz, 6,018 s at 125 MHz, 5,011 s at 2 MHz). The slow corner needs −199.980002 ppm, inside every envelope. The suite grades neither corner.
- Phase authority is the envelope less |rate| in the rate's direction, and the envelope plus |rate| against it. In simulation, 197 ppm from this oscillator took 5 to 17 s to settle, and −199 ppm, from a +199 ppm estimate, took 50 s (not graded).
- A takeover during a phase transient sends the wound integrator as scaledLastGmFreqChange: −200 ppm after phase 60's jump, where the departed grandmaster ran at 60 ppm. Anti-windup is on the residue list.
- A grandmaster about 207 ppm from this oscillator is beyond the envelope and beyond B.1.1's fast corner. A test grandmaster derived from a drifted test clock can be there. Zero that clock's frequency adjustment before the grandmaster-change and tie scenarios.

## Evidence

At `331e27d`, the merge of main (#102, #104) into this branch. The merge changes no file under `hdl/`, whose tree is the one `a728cc3` carried; the parent builds nothing else from this repository.

Processor gates:
- Engine suite: three passes of 2,199 checks and the priority1-255 pass of 61, all passing. Every INFO line and tally of the four passes is identical to `a728cc3`'s.
- Mutation arm (main's concurrent arm, `--jobs 8`): all 167 controls are caught, each by every check it names, and the unmutated sources pass. The arm ran in two halves of its table, each with the positive control.
- contract, ucpu, parser, gaskets, tsngen, bench, lint and docs all pass; main's verdict-order test passes on the merged arm.
- OOC at `a728cc3` (xc7a100t, 100 MHz, post-synthesis): the engine is 5,375 LUT (−20), 3,617 FF (−3), 1.5 BRAM and 6 DSP, WNS +2.093 ns; the µCPU is unchanged. The ROM is 1,013 of 1,024 words.

Parent, with its gitlink at `331e27d` (a local integration, not pushed):
- Consumer gates: milan_dp gptp 212/212 and gptp-lat 212/212; gptp_shadow 326/326; gptp_plane, gptp_txts, gptp_tables and clkvalid pass; milan_dp_gm_steps: the clean gmstep leg 196/196, its five controls caught.
- The ax1x1gptp leg (milan_dp_gptp) was not run to completion: at the build host's load it needs more than the two hours a run was given.
- The parent's Python, SystemVerilog, C++ and shell ratchets pass. The engine arm module is 865 lines after the merge, within the parent's 1,000-line module rule.
- At `a728cc3`, with the same `hdl/` tree: the takeover gate (a phase added locally to the gmstep leg) passed 252/252, and gptp_shadow with a −100 ppm master passed. Takeovers from +100 and −100 ppm grandmasters:
  - the PHC is not stepped and runs at 0.000 ppm as grandmaster;
  - tu is set at the commit and held for the 0.25 s holdover (Milan v1.2 B.1.1);
  - the listener stays locked (MEDIA_UNLOCKED unchanged), and every PDU is presented once, in order, at one offset (B.1.2);
  - nothing is refused or slipped, and there is no MEDIA_RESET;
  - the same phase at 1616fc8f fails exactly its two oscillator checks.

## Image size: the 8x8/1if image grows, so the no-growth rule is NOT met

The owner rule is that neither the 1x1/1if image nor the 8x8/1if image may grow. This change meets it at 1x1/1if and does not meet it at 8x8/1if.

The comparison is controlled:
- Base is parent 854bd72367 with gptp-processor 1616fc8f. Head is the same parent with this branch's `hdl/` tree.
- Both use the split image, one interface, Vivado 2026.1, xc7a100t-fgg484-2, AreaOptimized_high synthesis on one thread and ExploreArea optimization.
- Each side and shape is a #818 route set: the shipping route at ExtraPostPlacementOpt, and AltSpreadLogic_high and ExtraTimingOpt placed from its synthesis checkpoint. The scripts are the ones the parent's recipe writes, and the gate's own `bound()` accepts each comparison.
- Generated inputs: the gate's input digest lists 142 files and 6 or 9 memory images per route. Base and head differ only in `KL_gptp_engine.sv`, `gptp_ucode.hex` and the generated top, whose body is identical once comments are removed. The firmware, CSR map, boot ROMs and every other source are the same bytes.
- The qualifying image is the one the gate's `best()` selects: the best worst-corner WNS, which must meet WNS ≥ +0.030 ns and WHS ≥ 0 at all four signoff corners. Figures are the routed utilisation the gate records.

| Shape | Side | ExtraPostPlacementOpt | AltSpreadLogic_high | ExtraTimingOpt | Qualifying image |
|---|---|---|---|---|---|
| 8x8 | base | +0.073 / +0.034 ns, 43,022 LUT | +0.006 / +0.036 ns (misses the floor), 43,000 LUT | +0.064 / +0.027 ns, 42,998 LUT | ExtraPostPlacementOpt: 43,022 LUT, 50,995 FF, 94.5 BRAM tiles, 15,624 slices |
| 8x8 | head | +0.332 / +0.036 ns, 43,477 LUT | +0.237 / +0.036 ns, 43,536 LUT | +0.244 / +0.036 ns, 43,589 LUT | ExtraPostPlacementOpt: 43,477 LUT, 50,885 FF, 94.5 BRAM tiles, 15,544 slices |
| 1x1 | base | +0.099 / +0.036 ns, 32,647 LUT | +0.136 / +0.033 ns, 32,794 LUT | +0.158 / +0.033 ns, 32,777 LUT | ExtraTimingOpt: 32,777 LUT, 42,628 FF, 80 BRAM tiles, 14,274 slices |
| 1x1 | head | +0.161 / +0.032 ns, 32,398 LUT | +0.190 / +0.036 ns, 32,466 LUT | +0.276 / +0.036 ns, 32,455 LUT | ExtraTimingOpt: 32,455 LUT, 42,624 FF, 80 BRAM tiles, 14,271 slices |

(Worst-corner WNS / worst-corner WHS. Every route has 0 failing endpoints and 0 routing errors; the base 8x8 AltSpreadLogic_high route's WNS is positive but under the floor.)

The qualifying images at each signoff corner (WNS / WHS, ns):

| Image | Slow_85C | Slow_0C | Fast_85C | Fast_0C |
|---|---|---|---|---|
| 1x1 base, ExtraTimingOpt | +0.158 / +0.064 | +0.158 / +0.064 | +1.660 / +0.033 | +1.660 / +0.033 |
| 1x1 head, ExtraTimingOpt | +0.276 / +0.102 | +0.276 / +0.102 | +1.691 / +0.036 | +1.691 / +0.036 |
| 8x8 base, ExtraPostPlacementOpt | +0.073 / +0.102 | +0.073 / +0.102 | +1.636 / +0.034 | +1.636 / +0.034 |
| 8x8 head, ExtraPostPlacementOpt | +0.332 / +0.102 | +0.332 / +0.102 | +1.636 / +0.036 | +1.636 / +0.036 |

- 8x8: the qualifying head is **+455 LUT** (+1.06 %), −110 FF and −80 slices against the qualifying base, with BRAM and DSP equal. Every head directive grows: +455, +514 and +567 LUT against the base's qualifying image.
- 1x1: the qualifying head is −322 LUT, −4 FF and −3 slices against the qualifying base, with BRAM and DSP equal; the rule is met. No head directive grows against the base's qualifying image. The engine cell is −80 LUT.

The 8x8 growth is reproducible, not run-to-run noise:
- Each side's synthesis at both shapes, from the same inputs, repeats the earlier routes' (first reported for `a728cc3`) row for row.
- Each of the four ExtraTimingOpt comparisons repeats the earlier ExtraTimingOpt route exactly, in its utilisation, its hierarchy and at every corner.
- The synthesised 8x8 image is already +615 LUT at the head, and every directive places from that netlist.

Where the 8x8 LUTs move. Disjoint cells from the routed hierarchy; Vivado counts a LUT site shared by two cells in each, and the shared sites are reconciled separately:
- At both shapes, no cell moves a RAMB36, RAMB18 or DSP. Vivado's hierarchical report has no slice column, so slices are given for the image only.
- 8x8 FF: −110 over 13 cells. The largest move is the PTP clock-validity block's −64; the engine is +1.
- The engine, the only cell whose RTL or microcode image changes, is −74 LUT.
- The rest is in cells whose RTL is identical: the mailbox edit window +1,569, the CSR block −1,338, the gPTP wrapper's own logic +335, the datapath's own logic +220, and smaller moves elsewhere.
- The earlier same-directive pair (ExtraTimingOpt, now repeated exactly): the 8x8 LUT rise is the net of moves in cells whose RTL this change does not touch, under the same directive (the mailbox edit window +1,572, the CSR block −1,342, the gPTP wrapper's own logic +335, the datapath's own logic +221, smaller moves elsewhere); the engine cell, the only changed RTL, is −80 LUT in both images.

This is the rule as written, applied to the image the parent would ship. Only the owner can allow for growth of this kind. It is caused by this change and reproducible, and it lies in synthesis's mapping of cells whose RTL the change does not touch.
