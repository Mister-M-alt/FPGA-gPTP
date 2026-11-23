Closes #106, closes #107

## #106: a master announcement on the wire at every receipt-timeout instant

When the announce receipt watch expired, the plane took the grandmaster role and armed its first Announce on a 2 ms timer beat (and its Sync on a 1 ms beat). An Announce already queued at the timeout instant, or arriving within those 2 ms, then ran first: it re-elected its grandmaster and disarmed both beats, so the aged port's mastership never reached the wire. The expiry-first ordering of #100 was right; its tests graded only the commits, which name thisClock whether or not anything was sent.

The fix: SELF, where BECOME ends, continues into ANNTX. The handler that takes the role sends the first Announce and arms the 1 s cadence from it (802.1AS-2011 Figure 10-15: UPDATE's newInfo takes IDLE to TRANSMIT_ANNOUNCE, and announceSendTime counts from that transmission). The ROM shrinks by two words, to 1,013 of 1,024.

Tests, graded on transmitted frames:
- Phase 57: a better grandmaster announces 3.000 s to 3.010 s after its previous Announce, at several phases against the millisecond tick. In every gap the port is aged and a master Announce leaves after the instant, before the next Announce re-elects the grandmaster. At 1616fc8f, the eight gaps up to 3.002 s fail.
- Phase 58: on regaining the role from a grandmaster that turned worse, the first master Announce leaves within 1 ms, then four more 1 s apart. With a better Announce 1 ms behind the worse one, the master Announce still leaves first. At 1616fc8f, the at-once and race checks fail.
- Two planted defects (`tb/verilator/engine/p106_mutants.py`): the deferred first Announce, and a first Announce that arms no cadence. Each is caught by every check it names.

Milan v1.2 4.2.6.2.3 and Table 4.2 apply, with the project's ruling that the timeout wins at the instant, graded on the wire.

## #107: grandmasters across the B.1.1 range, and a mastership on this oscillator

The servo has no sign or limit defect. Phase 59 follows grandmasters at +10, −10, +100 and −100 ppm against this oscillator, each settling within 0.2 ppm; it passes at 1616fc8f too. The failure came from the rate the plane kept as grandmaster. Its slave was still correcting a phase step when its grandmaster left, so the integrator it kept had been wound to the +200 ppm rail. A test clock that then followed the plane put a grandmaster "10 ppm away" from it beyond the trim.

Per the ruling on this issue (D1 = C), a mastership now runs on this oscillator. This is 802.1AS-2020's ClockMaster on its LocalClock (10.1.2.1, 10.2.4.14):
- BECOME's PHC word-3 write carries rate 0 in its low word. The engine now always applies it; before, it applied only while a slew was active. The time base keeps its phase, and its frequency steps by the departed grandmaster's rate.
- The high word carries the integrator, which is the negated rate estimate. So the engine sends scaledLastGmFreqChange = −(the slave's estimate) (10.2.8.2.1 l), 11.4.4.3.9). It sends zero when no slave rate has been written since reset or since the last mastership; the time base has then not moved.
- gmTimeBaseIndicator still counts BECOME's write, once per mastership. BECOME stays three words, so the ROM stays at 1,013 words.
- The servo is unchanged (D2), and so is the TLV grading (D3).

Tests:
- Phase 60: a grandmaster at +60 ppm jumps 90 µs and leaves two pairs later. The mastership's rate is this oscillator's, within one trim unit, although the integrator holds +200 ppm. A grandmaster 10 ppm from this oscillator is then followed within 0.2 ppm.
- Phase 61: under ±8 ns origin noise, after grandmasters at +10, −10 and +10 ppm, scaledLastGmFreqChange is within 50 % of the time base's change (the qualification's grading).
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

Documented behaviour (INTEGRATION.md):
- Phase authority is `RATE_PPM_C` less the rate followed, so 200 − |rate| ppm. In simulation, 197 ppm from this oscillator took 5 to 17 s to settle, and −199 ppm, from a +199 ppm estimate, took 50 s. Any grandmaster within B.1.1 is followed.
- A takeover during a phase transient sends the wound integrator as scaledLastGmFreqChange: −200 ppm after phase 60's jump, where the departed grandmaster ran at 60 ppm. Anti-windup is on the residue list.
- A grandmaster about 207 ppm from this oscillator is outside B.1.1 and the follow range. A test grandmaster derived from a drifted test clock can be there. Zero that clock's frequency adjustment before the grandmaster-change and tie scenarios.

## Evidence

All at `a728cc3`.

Processor gates:
- Engine suite: three passes of 2,199 checks and the priority1-255 pass of 61, all passing.
- Mutation arm: all 167 controls are caught, each by every check it names, and the unmutated sources pass.
- contract, ucpu, parser, gaskets, tsngen, bench, lint and docs all pass.
- OOC (xc7a100t, 100 MHz, post-synthesis): the engine is 5,375 LUT (−20), 3,617 FF (−3), 1.5 BRAM and 6 DSP, WNS +2.093 ns; the µCPU is unchanged. The ROM is 1,013 of 1,024 words.

Parent, with its gitlink at this head (a local integration, not pushed):
- Consumer gates:
  - milan_dp gptp 212/212 and gptp-lat 212/212;
  - gptp_shadow 327/327 with its +100 ppm master, and 327/327 with a −100 ppm one (the counter's addend 0 as grandmaster);
  - milan_dp_gm_steps: the clean gmstep leg 196/196, its five controls caught.
- Takeover gate: a phase added locally to the gmstep leg, 252/252. Takeovers from +100 and −100 ppm grandmasters:
  - the PHC is not stepped and runs at 0.000 ppm as grandmaster;
  - tu is set at the commit and held for the 0.25 s holdover (Milan v1.2 B.1.1);
  - the listener stays locked (MEDIA_UNLOCKED unchanged), and every PDU is presented once, in order, at one offset (B.1.2);
  - nothing is refused or slipped, and there is no MEDIA_RESET.
  - The same phase at 1616fc8f fails exactly its two oscillator checks.
- Routes (the split image, one interface, ExtraTimingOpt), each meeting the build floor at every corner with 0 failing endpoints and 0 routing errors:
  - 1x1: WNS +0.276 ns, WHS +0.036 ns;
  - 8x8: WNS +0.244 ns, WHS +0.036 ns.
- Against the same routes at 1616fc8f:
  - 1x1: −322 LUT, −4 FF, −3 slices;
  - 8x8: +588 LUT, −107 FF, −459 slices;
  - BRAM and DSP are unchanged in both.
  - The engine cell is −80 LUT in both. The 8x8 LUT rise lies in the mailbox edit window (+1,572) and the CSR block (−1,342), RTL this change does not touch.
- The parent's Python, SystemVerilog and C++ ratchets pass. The engine arm module is back to 1,000 lines, within the parent's module-length rule (#106 had taken it to 1,002).
