[A836]

Branch: `109-negative-delay-clamp` -> `main`

A computed meanLinkDelay below -80 ns used to be a bad Pdelay exchange, and the port lost asCapable on that exchange.
On the bench, a 100 Mb/s board whose PHY latency compensation was over-stated computed about -263 ns, lost asCapable and elected itself grandmaster.
With this change, a negative delay of any magnitude counts as a good exchange.
Following the manager's ruling on #109, the Sync path uses the delay signed, floored at -800 ns.

## Cause (at 1213ac5b)

- `_pdpost_verdict` (`hdl/ucode/gen_gptp_ucode.py`) judged `D` good iff `(D + NPD_LO_C) u<= NPD_HI_C + NPD_LO_C`, i.e. -80 <= D <= 800 ns.
  Any D below -80 ns was bad: `S_PDOK` was cleared and asCapable fell on that exchange.
- `_pdpost_corrected_delay` wrote D unclamped to `S_PDELAY` (the Sync path's link delay) and to publish word 3 (`pub_pdelay_ns_o`).
  So D in [-80, 0) was already used signed by the engine; only the parent's public bank clamped it to 0.

## Fix

Generator only. No RTL changes, and the ROM stays word-neutral (shipping image 1,013 of 1,024 words, seeded image 1,014, same leg map).

- **Verdict:** a delay is bad iff `D > NPD_HI_C` (the sign of `D - (NPD_HI_C + 1)` is clear).
  A negative D of any magnitude is good: it climbs the `ASCAP_UP_C` ladder and restarts lostResponses as before.
  +800 ns is good; 801 ns is bad and clears asCapable on that exchange, as 802.1AS-2011 Figure 11-8 does.
  The multiple-response, own-response and neighborRateRatio conditions are unchanged.
- **Sync path:** `S_PDELAY = max(D, -NPD_HI_C)`, computed without a branch: `m = (D + NPD_HI_C) >>arith 63; D -= (D + NPD_HI_C) & m`.
  The delay stays signed and is never clamped to 0 in the engine.
  The floor stops a wrong compensation or a faulty peer from injecting an arbitrarily negative delay and stepping the clock. It never rejects the exchange.
- **Publication:** publish word 3 carries the same floored, signed value.
  `pub_pdelay_ns_o` is 32 bits, so an unfloored D below -2^31 ns could reach the parent with either sign.
  At 1213ac5b, the wire's most negative delay published `0x9DCD1F9B`.
- `NPD_LO_C` is retired: generator, `docs/INTEGRATION.md` constants table, and `scripts/check_docs.py`.
  The parent's builder and tests parse no `NPD_*` constant.

**The published and used values differ by design.**
The parent's public bank (`KL_gptp_shadow.sv`, the unsigned CSR and GET_AVB_INFO field) clamps a negative published delay to 0, and that is the only clamp to 0.
The engine keeps using the signed value: D = -263 ns reads 0 at the CSR and is subtracted as -263 ns in the next offset.
`docs/INTEGRATION.md` gains a "Link delay verdict" section that states this.

## Spec basis (each clause checked against the standard's text)

- Milan v1.2 4.2.6.2.7 requires only that -80 to 0 ns not clear asCapable. It sets a minimum tolerance, not a rejection.
- 802.1AS-2011 11.2.2 b) and Figure 11-8 (as corrected by Cor1-2013) set asCapable FALSE only when `neighborPropDelay > neighborPropDelayThresh`.
  802.1AS-2020 11.2.2 b) and 11.2.13.7 do the same with meanLinkDelayThresh. No clause rejects a negative delay.
- Milan v1.2 4.2.6.1.1: neighborPropDelayThresh is 800 ns on copper.
- The delay computation has no clamp: 802.1AS-2020 11.2.19.3.4 (computePropTime; 802.1AS-2011 11.2.15.2.4).
- The same value enters the Sync receipt time: 802.1AS-2020 11.2.14.2.1 f) (802.1AS-2011 11.2.13.2.1 f)).
  Latency constants that are both over-stated by the same amount therefore cancel in the offset.

## Tests

Engine suite (`tb/verilator/engine/sim_main.cpp`). Three new phases run after phase 61 and ahead of the whole-run grades.
A new grandmaster keeps Announce and Sync flowing, and each trial starts from a capable slave after two ordinary exchanges.
The peer answers so that the plane computes exactly D (`PD_SET`), or it sends raw timestamp fields (`PD_WIRE`).
Each trial is graded on the published flags and delay, and on the wire: the next Sync/Follow_Up from the grandmaster is used (one PHC addend pulse) or not, and the grandmaster stays elected through its next Announce.

- **Phase 62:** D = -3, -80, -81 and -263 ns keep asCapable and are published as computed.
  The next Follow_Up's offset uses D exactly (`rx - (origin + correction + D)`), with no step.
  Then a 100 ns link with both latency constants over-stated by 400 ns: the plane computes -300 ns, its Sync is stamped 400 ns early, and the true offset, 0, is measured exactly.
  A delay clamped to 0 would leave -300 ns.
- **Phase 63:** D = -800, -801 and -5,000,000 ns are used and published as -800 ns. They keep asCapable and do not step the PHC.
  The same holds for the most negative delay the wire can make the datapath compute: t2 seconds 0x80000000 and t3 at 0x7FFFFFFF s plus 2^32 - 1 ns.
  The engine folds a timestamp from the seconds' low 32 bits, read as signed, so t3 - t2 is at most (2^32 - 1)(1e9 + 1).
  The plane computes -2,147,483,641,057,566,821 ns. The wire's bound is -2,147,483,649,647,483,648 ns.
- **Phase 64:** 800 ns keeps asCapable; 801 ns clears it, and the next Follow_Up is not used.
- Phase 22 (-49 ns, inside Milan's tolerance) is kept; its wording no longer calls -80 ns a floor.
  There was no "-81 clears" test at 1213ac5b in this repository or the parent; the expectations of phases 62 and 63 are its inversion.

Reproduction: the new phases run against the 1213ac5b image fail 24 checks.
-81, -263, the over-stated constants, -800, -801, -5 ms and the wire minimum each lose asCapable, have their next Follow_Up refused and lose the grandmaster.
-3 and -80 pass, as Milan requires.

Engine suite at the head, all four passes (1213ac5b: 2,199 checks in the shipping pass; the 97 new checks are in phases 62-64):

| Pass | Checks |
|---|---|
| Shipping | 2296 / 2296 |
| Request counter seeded above 16 bits | 2296 / 2296 |
| Sync counter seeded above 16 bits | 2296 / 2296 |
| priority1 255, clockAccuracy 0xFE | 61 / 61 |

## Mutation controls

`tb/verilator/engine/p109_mutants.py` adds eight controls to the arm. Each one must fail every check it names:

| Control | Planted defect | Killed by |
|---|---|---|
| a delay below -80 ns is a bad exchange | the 1213ac5b window, word-neutral | asCapable kept at -81, -263, over-stated, -800, -801, -5 ms, wire minimum |
| the Sync path uses a negative delay as 0 | used value clamped to 0, publication signed | offset exact at -3, -81, -263, over-stated |
| a negative delay is floored at 0 | floor at 0 for both writes | published value and offset at -263; offset over-stated |
| a negative delay has no floor | floor removed | offset at -801; no step at -5 ms and at the wire minimum; published value at the wire minimum |
| the floor is -799 ns | floor 1 ns short | offset and published value at -800 |
| the engine publishes the unfloored delay | publication before the floor | published value at -5 ms and at the wire minimum |
| 801 ns is a good exchange | threshold + 1 | 801 clears asCapable; its Follow_Up not used |
| 800 ns is a bad exchange | threshold - 1 | asCapable kept at 800 |

No existing control was disarmed. Every pattern still matches, and the full arm result is below.

The full engine arm, all 175 entries (167 existing and 8 new), catches every planted defect, and the unmutated build passes the harness.
It ran in slices of `mutants.py`'s own main.

## Gates

- `make contract`, `make lint`, `make docs` (docs, selftest, source evidence) pass.
- ucpu: 768/768. parser: 482/482, plus 35/35 controls. gaskets: 81/81, plus 5/5. tsngen: 288/288, plus 4/4. bench: pass.
- Out-of-context synthesis, before and after (xc7a100t-2, 100 MHz): identical.
  `KL_gptp_engine` is 5,375 LUT, 3,617 FF, 1.5 BRAM tiles and 6 DSP, with WNS +2.093 ns. `KL_gptp_ucpu` is 1,643 LUT and 733 FF, with WNS +1.941 ns.
  The delta is zero, since only the ROM contents change.

## Parent consumer gate

A local parent checkout at `dev-soft-core`, with this head as the `gptp-processor` gitlink, run at the parent's Verilator pin (5.050):

- milan_dp `gptp` 212/212 and `gptp-lat` 212/212.
- gptp_shadow 332/332, its lifecycle test and its 9 controls.
- gptp_plane, gptp_tables and gptp_txts pass.
- milan_dp_gm_steps: 196 checks and its 5 controls.
- milan_dp_gptp: the physical leg 151/151, plus the abort and recentre controls (54 checks).
- The builder tests that read the generator pass, as do the submodule-scanning ratchets (hygiene, naming, port contracts, idiom, fail-fast, test evidence).
- The parent's own -40 ns probes, in both the shadow and milan_dp, still read 0 at the public bank with asCapable held.
- Extra probes at -263 ns and -5 ms (local only) read 0 at the CSR (`0x6E4`) and at the shadow's public word, with asCapable held.
  Against the 1213ac5b image, the same probes lose asCapable.
- The parent's gitlink bump must refresh its donor links and the submodule-boundaries diagram, as every bump does.
  With those regenerated, the imported-gPTP docs gate, the submodule docs gate and the C++ idiom ratchet pass.
  The C++ idiom ratchet scans this repository's harness, which is why 8e4889b declares the new phase's two constants one per line.

Closes #109

