[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/RESOURCE_VALIDATION.md`
>
> Archived: 2026-09-01
>
> Current successor: [current manager guide](../../../MANAGER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Resource validation — the gPTP plane, measured 2026-08-14

The round that created this repository. The 2026-08-14 no-DDR3 resource
study priced "gPTP engine in fabric" as an ESTIMATE (+1,500…+2,500 LUT,
central +1,900). This page replaces that line with a measurement, on the
same instrument as every protocol-processor anchor: Vivado 2026.1,
`xc7a100tfgg484-2`, out-of-context synthesis at 100 MHz, post-synthesis
(hierarchical) utilization. That instrument's OOC-vs-real-SoC calibration
was accurate to one LUT on the AECP plane.

Reproduce: `syn/ooc/run.sh` (reports land in `syn/ooc/work/`).

## The µCPU: arithmetic ISA growth = +631 LUT

`KL_gptp_ucpu` is a pure superset of the AECP µCPU — every base port and
decode arm kept — so the delta prices the growth alone (OP_ALU: 64-bit
ADD/SUB/AND/OR/XOR + serial SHL/SHR/SAR; OP_MULDIV: DSP MULS 32×32→64 +
restoring DIVU 64/32→64):

| | AECP µCPU (record, 2026-08-13) | gPTP µCPU | delta |
|---|---|---|---|
| Slice LUTs | 1,070 (938 logic + 132 LUTRAM) | **1,701** (1,569 + 132) | **+631** |
| Registers | 491 | 734 | +243 |
| BRAM tiles | 3 (2048 × 48 ROM) | **1.5** (1024 × 48 ROM) | **−1.5** |
| DSP48E1 | 0 | 4 (the 32×32 multiply) | +4 |
| WNS at 100 MHz, OOC | +2.586 ns | +1.949 ns, met | |

The serial shifter and the restoring divider are the deliberate trade:
every gPTP computation runs at protocol rate (≤ 8 Hz, and Milan v1.2
4.2.6.2.6 relaxes the Pdelay turnaround to 15 ms), so one bit per cycle
costs latency nothing needs and saves the barrel/parallel structures.

## The whole engine: 2,878 LUT

`KL_gptp_engine` = parser + µCPU + TX slot + timer + region map + publish
wires, one clock domain, byte in / byte out:

| Instance | Module | LUT | LUTRAM | FF | BRAM | DSP |
|---|---|---|---|---|---|---|
| **KL_gptp_engine** | (top) | **2,878** | 284 | 2,164 | **1.5** | 4 |
| (own: region map, event queue, bank + scratch, publish regs) | | 168 | 128 | 784 | 0 | 0 |
| `u_parser` | `KL_gptp_rx_parser` | 519 | 0 | 267 | 0 | 0 |
| `u_timer` | `KL_gptp_timer` | 264 | 0 | 321 | 0 | 0 |
| `u_txslot` | `KL_gptp_tx_slot` | 72 | 24 | 62 | 0 | 0 |
| `u_ucpu` | `KL_gptp_ucpu` | 1,855 | 132 | 730 | 1.5 | 4 |

WNS at 100 MHz, OOC: **+1.898 ns, 0 failing endpoints**. Zero critical
warnings in either synthesis log.

**Re-measured after µcode v2 + the bench round (same day):** the engine
grew a fifth publish word (sync offset) and the timer boot-arm —
**2,944 LUT** / 2,205 FF / 1.5 tiles / 4 DSP, WNS unchanged. The µCPU is
byte-identical in area (1,701): µcode revisions cost ROM words, not LUTs,
exactly as claimed. On the Arty A7-100T bench build the whole plane plus
MII gaskets, PHC and UART reporter placed at 3,726 LUT with WNS
+0.375 ns — see `docs/BENCH_FIRSTLIGHT.md` for what it did on the wire.

**Re-measured after µcode v3, the grandmaster round (same day):** the
FULL Grandmaster Capability — BTCA, PortAnnounceTransmit with path trace,
two-step Sync + Follow_Up as master, role transitions — plus the raw
announce-vector publish word and the dispatch valid/accept handshake fix
cost **+51 LUT total: 2,995** / 2,269 FF / 1.5 tiles / 4 DSP, WNS +1.898
unchanged. The protocol grew from 304 to 539 ROM words; the µCPU stayed
byte-identical at 1,701. Three revisions in, the architecture's claim
holds exactly: protocol behavior is ROM words, not fabric. Bench outcome
of the round: `docs/BENCH_GRANDMASTER.md` — bidirectional BMCA interop
with the STM32, our node operating as GM on the wire.

**Re-measured after µcode v4, the asCapable + servo round (2026-08-15):**
the asCapable ladder with its full un-participate transition, the sync
receipt watch, the closed-loop PI servo, the announce/BMCA gating, the
Table 10-6 control-field fix and the sixth publish word
({stepsRemoved, timeSource}) cost **+103 LUT total: 2,981** (2,697 logic
+ 284 LUTRAM) / 1.5 tiles / 4 DSP, WNS **+1.898 unchanged**. The µCPU is
again byte-identical at 1,701 — the +103 is the engine's publish
register + mux arm, priced at the boundary; the protocol itself
(539 → 676 ROM words, now auto-packed first-fit into the free windows)
stayed ROM. Four revisions in, the claim still holds exactly.
Verification grew with it: the 116-check engine suite (bit-exact C++
servo mirror, 7/7 targeted mutations caught) and the 268-check tsn-gen
cross-suite (`tb/tsngen` — packet_gen decodes every frame we transmit
against the 802.1AS YAMLs upstreamed to tsn-gen and generates our
receive stimulus; its YAML pins caught the control-field bug).

**Re-measured after the delayAsymmetry input (same day):** the engine's
`cfg_asym_i` management input (802.1AS-2011 10.2.4.5, read by µcode
through gather sel 2 in the Follow_Up offset path) prices at **+30 LUT:
3,011** / 1.5 tiles / 4 DSP, WNS +1.898 unchanged; the µCPU is again
byte-identical at 1,701 and the protocol change is 2 ROM words (678).

**Re-measured after the v5 FSM-conformance round (2026-08-16):** the
audit's four additions — MDSyncReceive sequence pairing,
PortAnnounceReceive qualification (self / stepsRemoved / path-trace
loop walk), the PortAnnounceInformation incumbent comparison, and
neighborRateRatio with its publish word — cost **+18 LUT: 3,029**
(2,745 logic + 284 LUTRAM) / 2,398 FF / 1.5 tiles / 4 DSP, WNS
**+1.898 ns unchanged, 0 failing endpoints**. Per-instance:

| Instance | Module | LUT | LUTRAM | FF | BRAM | DSP |
|---|---|---|---|---|---|---|
| **KL_gptp_engine** | (top) | **3,029** | 284 | 2,398 | **1.5** | 4 |
| (own: region map, event queue, banks, publish regs) | | 176 | 128 | 1,017 | 0 | 0 |
| `u_parser` | `KL_gptp_rx_parser` | 519 | 0 | 267 | 0 | 0 |
| `u_timer` | `KL_gptp_timer` | 248 | 0 | 321 | 0 | 0 |
| `u_txslot` | `KL_gptp_tx_slot` | 72 | 24 | 62 | 0 | 0 |
| `u_ucpu` | `KL_gptp_ucpu` | 2,014 | 132 | 731 | 1.5 | 4 |

The µCPU standalone is **still byte-identical at 1,701 LUT** — five
µcode revisions and a conformance audit later, the architecture's
central claim has never moved: protocol behaviour is ROM words. The
ROM is at 849 of 1,024 (82.9 %); the +18 LUT is the eighth publish
register and its mux arm at the engine boundary.

(The µCPU reads 1,855 in context vs 1,701 standalone — cross-boundary
optimization variance of the same kind the protocol-processor record
documents in the other direction.)

## What this does to the no-DDR3 study

The study's gPTP line moves from ESTIMATE +1,900 (bracket 1,500…2,500) to
**MEASURED 2,878** — the estimate was optimistic by roughly 1,000 LUT, and
the point of building this skeleton was to find that out before anyone
spent the plan. Two consequences, stated honestly:

1. The study's central landing moves from ≈25,900 to **≈26,900 LUT
   (−47%, was −49%)** against the 51,029 baseline. The −50% target is
   still inside the bracket but now REQUIRES the named reserve list
   (SRP `N_VIDS`/depth parameters, SRP encoder/decoder sharing, the
   deeper `milan_csr` decode diet, monitor BRAM-ification, full
   `rx_filter` deletion): with reserves the landing is ≈24,600…25,600
   (−50%…−52%).
2. On the other side of the ledger the skeleton UNDER-runs its budgets:
   BRAM 1.5 tiles vs 2 budgeted, and the whole plane closes timing with
   1.9 ns to spare with no floorplanning.

Against the alternatives table: the shared infrastructure (parser, timer,
slot, glue = 1,023 LUT) is common to EVERY implementation option — only
the compute element varies. A SERV-class bit-serial RV32 in place of the
µCPU would put the engine near 1,700…2,000 LUT at the price of moving all
protocol logic into C firmware; a bare-metal VexiiRiscv variant remains
the most expensive option and is now measurably unjustified.

## What is NOT in the measured figure

*(This section described the original skeleton. The first bullet is
kept for the record and marked with what actually happened.)*

- ~~**The 802.1AS state machines of record.**~~ **RETIRED 2026-08-16.**
  They are now in the ROM and audited element by element against the
  standard (`FSM_CONFORMANCE.md`): BTCA with 10.3.10 qualification and
  the 10.3.11 incumbent comparison, the asCapable ladder, both receipt
  timeouts, MDSyncReceive pairing, neighborRateRatio, the closed servo.
  The prediction held exactly — all of it cost ROM words (304 → 849)
  and **+151 LUT in total** across five revisions (2,878 → 3,029),
  none of it in the µCPU, which is byte-identical at 1,701. If the state set ever outgrows 1,024 words the next ROM step
  is 2048 × 48 = 3 tiles (+1.5).
- **Integration glue in the parent**: the 0x88F7 leg on the KL_pp_shadow
  classifier, the TX cascade port, the CSR debug window, possibly a
  second message bank if double-buffering is wanted. Expect +100…+400 LUT
  at the milan_datapath boundary.
- **The egress-timestamp plumbing** already exists in the parent
  (`ptp_ts_top`); this repo only consumes it.

## Verification state at this measurement

Five suites, **1,297 checks**, all green through one `make`; see
`VERIFICATION.md` for what each covers and the mutation record.

| suite | checks | judges |
|---|---|---|
| `tb/verilator/ucpu` | 768 | the arithmetic ISA vs an independent C++ model |
| `tb/verilator/parser` | 32 | 802.1AS field extraction + drop arms |
| `tb/verilator/engine` | 144 | the protocol round-trip, servo, asCapable ladder, FSM conformance |
| `tb/verilator/gaskets` | 81 | the bench MII gaskets (loopback, IFG, FCS, the wedge regression) |
| `tb/tsngen` | 272 | every transmitted frame decoded by tsn-gen's `packet_gen`, receive stimulus generated by it |

`verilator --lint-only -Wall` clean on the engine top.

## Hardware, at this measurement

Measured on the Arty A7-100T bench (`BENCH_OPERATIONS.md`) with this
exact µcode revision: as slave of a commercial AVB switch on a direct
link, **offset from GM +0.01 ns mean, σ 3.20 ns, 9 ns worst over 168
consecutive locked seconds**, meanLinkDelay 0–11 ns, zero CRC errors,
zero event drops, at the strict 802.1AS/Milan 800 ns threshold with no
profile deviations (`BENCH_TAP_WIRETRUTH.md`).
