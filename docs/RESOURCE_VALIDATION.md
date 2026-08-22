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

## What is NOT in the 2,878

- **The 802.1AS state machines of record.** The entry handlers are real
  first cuts that exercise every datapath (they are what keeps synthesis
  from folding anything), but BTCA, the asCapable ladder, the receipt
  timeouts and the Milan profile numbers are µcode still to be written.
  µcode costs ROM words, not LUTs — the ROM has 904 of 1,024 words free —
  but if the full state set outgrows 1,024 words, the next ROM step is
  2048 × 48 = 3 tiles (+1.5).
- **Integration glue in the parent**: the 0x88F7 leg on the KL_pp_shadow
  classifier, the TX cascade port, the CSR debug window, possibly a
  second message bank if double-buffering is wanted. Expect +100…+400 LUT
  at the milan_datapath boundary.
- **The egress-timestamp plumbing** already exists in the parent
  (`ptp_ts_top`); this repo only consumes it.

## Verification state at this measurement

- `tb/verilator/ucpu`: 768 checks green against an independent C++ model
  (directed edges + 64 random operand pairs), mutation-proven.
- `tb/verilator/parser`: 31 checks green (Announce + path trace, Sync,
  Follow_Up + information TLV, Pdelay_Resp, five drop arms),
  mutation-proven. This suite caught three real field-straddle bugs and
  an end-of-frame race before synthesis — the harness money worked.
- `verilator --lint-only -Wall` clean on the engine top.

## The v7 engine re-measured: the second bank and the 64-word scratch

v7 is the first structural revision of the ENGINE CORE since the
skeleton was priced -- the bench rounds' own re-measures above (2,944
at first light, 2,995 at the grandmaster round) already moved the
engine, so the honest baseline is the latest prior record, not the
skeleton. What changed: the message bank ping-pongs (2 x 32 x 64 --
each accepted frame lands in the bank its event names, retiring the
torn-read window the v6 announce guard could only narrow) and the
scratch doubles to 64 words for the Milan 4.2.6.2.5 cease-rule state.
Same instrument, Vivado 2026.1 OOC on `xc7a100tfgg484-2` at 100 MHz,
2026-08-19:

| | v3 record (grandmaster round) | v7 | delta |
|---|---|---|---|
| Slice LUTs | 2,995 | **3,046** (2,720 logic + 326 LUTRAM) | **+51** |
| Registers | 2,269 | 2,270 | +1 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

+51 LUT squares with doubling two 64-bit-wide distributed RAMs (+42
LUTRAM) plus the bank-select mux and one select flop. The µCPU itself
is byte-identical (1,701 LUT / +1.949 ns): the ISA has not moved since
the skeleton; seven ucode revisions later the plane prices at
**3,046 LUT** against the parent's budget. Verification at this
measurement: ucpu 768 / parser 31 / engine 162 checks, thirty-one
planted mutations red (one of them RTL: the read bank tied to the
write bank), lint clean.

## The domain round re-measured: the parser's domainNumber drop arm

FPGA-gPTP #6, found by the parent's field campaign: the receive path
ignored domainNumber, so a domain-5 Announce moved the grandmaster and
a domain-5 Sync/Follow_Up pair steered the PHC. The fix is one header
drop arm in `KL_gptp_rx_parser` (802.1AS-2011 8.1: the domain number of
a gPTP domain shall be 0; IEEE 1588-2008 9.5.1: a message whose
domainNumber does not match is not accepted for processing), placed at
header byte 4 ahead of every message-bank write; the domain byte of
bank word 0 became the constant the parser admits, so the 8-bit domain
register went with it. Same instrument, Vivado 2026.1 OOC on
`xc7a100tfgg484-2` at 100 MHz, 2026-08-22. The honest baseline is the
tree at a29e8106 (PR #5, the per-bank ingress stamp) re-measured the
same day, not the v7 row above, which predates that PR:

| | a29e8106 (PR #5) | the domain arm | delta |
|---|---|---|---|
| Slice LUTs | 3,096 (2,770 logic + 326 LUTRAM) | **3,081** (2,755 + 326) | **-15** |
| `u_parser` LUTs | 523 | 508 | -15 |
| Registers | 2,400 | 2,392 | -8 |
| `u_parser` registers | 267 | 259 | -8 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

The compare against a constant is cheaper than the register it
replaced and the mux that fed bank word 0 from it. Verification at this
measurement: ucpu 768 / parser 51 / engine 183 checks, thirty-six
planted mutations red (the three new ones: the domain arm removed fails
16 parser and 23 engine checks, the compare narrowed to its low nibble
7 and 2, the end-of-frame gate without its bad_r term 5 and 2), lint
clean.

## The Follow_Up round re-measured: the information TLV arms

FPGA-gPTP #11, found by the parent's field campaign: the receive path
accepted a 44-octet Follow_Up, the header and preciseOriginTimestamp
without the information TLV that 802.1AS-2011 11.4.4.3 makes a field
of the 76-octet message (Table 11-9), and that frame paired with a
pending Sync and steered the servo. The fix is three arms in
`KL_gptp_rx_parser`: the per-type minimum for a Follow_Up becomes the
last octet of the 76 (the end-of-frame gate), the declared
messageLength is compared against the same per-type table at header
octets 2..3, ahead of every message-bank write (10.5.2.2.4 counts the
TLV in it), and the TLV header at octets 44..53 must be
{0x0003, 28, 00-80-C2, 1} (11.4.4.3.2 to 11.4.4.3.5) or the frame is
refused. The 16-bit and 64-bit compares against constants are the
cost; the per-type minimum flag that mirrored the end-of-frame gate
and the TLV-type flag that only withheld bank word 11 are retired,
which is the two flops back. Same instrument, Vivado 2026.1 OOC on
`xc7a100tfgg484-2` at 100 MHz, 2026-08-22. The baseline is the tree
at 9e69681f (PR #17; #16 and #17 are ROM-only changes, and both
re-measure byte-identical to the domain-arm row above):

| | 9e69681f (PR #17) | the Follow_Up arms | delta |
|---|---|---|---|
| Slice LUTs | 3,081 (2,755 logic + 326 LUTRAM) | **3,115** (2,789 + 326) | **+34** |
| `u_parser` LUTs | 508 | 542 | +34 |
| Registers | 2,392 | 2,390 | -2 |
| `u_parser` registers | 259 | 257 | -2 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Verification at this measurement: ucpu 768 / parser 119 / engine 210
checks, forty planted mutations red (the three new ones: the Follow_Up
minimum reverted to the 44-octet shape fails 9 parser and 12 engine
checks, the TLV header arms removed 13 and 6, the Follow_Up TLV block
applied to Sync as well 3 and 3; three more are visible to the parser
suite alone: the messageLength arm removed fails 18, the arm narrowed
to Follow_Up 16, the tlvType compared alone 10), lint clean.

## The Pdelay_Req round re-measured: the 54-octet minimum

FPGA-gPTP #12, found by the parent's field campaign beside #11: the
receive path accepted a header-only Pdelay_Req, the 34-octet common
header without the two reserved 10-octet fields that 802.1AS-2011
11.4.5 / Table 11-11 make the 54-octet message (IEEE 1588-2008 13.9
pads the request to the response's length on purpose), and the
responder answered it. The fix is one line of the per-type minimum
table in `KL_gptp_rx_parser`: Pdelay_Req joins the Pdelay_Resp /
Pdelay_Resp_Follow_Up line at byte 67, so the end-of-frame gate needs
the 54 octets and the messageLength arm of the Follow_Up round refuses
a declared length below 54 ahead of every bank write. Same instrument,
Vivado 2026.1 OOC on `xc7a100tfgg484-2` at 100 MHz, 2026-08-22; the
baseline is the Follow_Up row above (the #18 head):

| | the Follow_Up arms (#18) | the Pdelay_Req line | delta |
|---|---|---|---|
| Slice LUTs | 3,115 (2,789 logic + 326 LUTRAM) | **3,115** (2,789 + 326) | **0** |
| `u_parser` LUTs | 542 | 542 | 0 |
| Registers | 2,390 | 2,390 | 0 |
| `u_parser` registers | 257 | 257 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Re-grouping one constant in the table moves no LUT: the minimum mux
was already there for the other five types. Verification at this
measurement: ucpu 768 / parser 140 / engine 213 checks, forty-one
planted mutations red (the new one: the Pdelay_Req minimum reverted to
the 34-octet header fails 15 parser and 2 engine checks), lint clean.
