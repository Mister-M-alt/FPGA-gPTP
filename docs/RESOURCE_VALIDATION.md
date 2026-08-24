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
measurement: ucpu 768 / parser 140 / engine 215 checks, forty-one
planted mutations red (the new one: the Pdelay_Req minimum reverted to
the 34-octet header fails 15 parser and 2 engine checks), lint clean.

## The qualification round re-measured: ROM words only

FPGA-gPTP #7, found by the parent's field campaign: the announce handler
fed BTCA every well-formed Announce, so a better vector from our own
clockIdentity, with stepsRemoved 255, or carrying our identity in its
path trace moved the grandmaster. The fix is 802.1AS-2011 10.3.10.2.1
qualifyAnnounce in ucode, ahead of every write the handler makes; its
count-gated walk of the bank's path-trace hops is the first consumer
of OP_DESC_ADDR, the state-port base register the ISA always had. No
RTL logic changed (the package gained a comment). The ROM grew from 872
to 895 real words of 1,024 (the announce handler 28 to 51 in its own
slot; every leg address unchanged). Same instrument, Vivado 2026.1 OOC
on `xc7a100tfgg484-2` at 100 MHz, 2026-08-22, against main at 310a6ea
(PR #19) re-measured the same day (the parser arms of #18 and #19 moved the
baseline by +34 LUT; this round moves nothing):

| | 310a6ea (PR #19) | the qualification round | delta |
|---|---|---|---|
| Slice LUTs | 3,115 (2,789 logic + 326 LUTRAM) | **3,115** (2,789 + 326) | **0** |
| `u_ucpu` LUTs | 1,997 | 1,997 | 0 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Byte-identical, as a ROM-only change must be: protocol behavior is ROM
words, not fabric. Verification at this
measurement: ucpu 768 / parser 140 / engine 284 checks, fifty-three
planted mutations red (the twelve new ones, engine checks failed: the
own-source rule removed 42 and its identity compare narrowed to 32 bits
3, the stepsRemoved bound off by one 48 upward and 3 downward and its
compare narrowed to a byte 30, a dead path-trace compare 44, the hop
compare narrowed to 32 bits 3, the hop read from the next bank word 32,
the hop-count gate removed 56, a walk one hop past the count 19, a
one-hop walk 45, the state-port base left offset after the walk 78),
lint clean. The review round added the first-hop loop (the one an end
station meets without forgery), stepsRemoved 0x0100 and 0xFFFF, and two
half-identity adopt-controls; the five mutations that had escaped the
first round are red with them.

## The pairing round re-measured: ROM words only

FPGA-gPTP #8, found by the parent's field campaign: the
Pdelay_Resp_Follow_Up handler qualified requestingPortIdentity and
nothing else, so one unsolicited Follow_Up with a stale sequenceId
computed a delay from stale scratch, published 20 ms of
neighborPropDelay and dropped asCapable. The fix is 802.1AS-2011
11.2.15.3 (Figure 11-8) in ucode on both Pdelay receive messages: a
Pdelay_Resp is taken only for the outstanding request's sequenceId and
arms the pairing, a Follow_Up only behind that Pdelay_Resp and from its
sender, one per Resp, and each new request clears the arm. No RTL
changed. The ROM grew from 895 to 927 real words of 1,024 (+32: the
Pdelay_Resp handler 27 to 43 in its own slot; the Follow_Up handler
kept at 16 so SERVO keeps the 48-word gap behind it; the pairing opens
the PDPOST leg, 63 to 77, which the packer moves to the tail and ANNTX
takes its old gap). Same instrument, Vivado 2026.1 OOC on
`xc7a100tfgg484-2` at 100 MHz, 2026-08-22, against main at 48f299ab
(PR #20, the announce qualification) re-measured the same day (main carries the qualification round's ROM and the parser arms of
#18 and #19; this round moves nothing):

| | 48f299ab (PR #20, the announce qualification) | the pairing round | delta |
|---|---|---|---|
| Slice LUTs | 3,115 (2,789 logic + 326 LUTRAM) | **3,115** (2,789 + 326) | **0** |
| `u_ucpu` LUTs | 1,997 | 1,997 | 0 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Byte-identical, as a ROM-only change must be. Verification at this
measurement: ucpu 768 / parser 140 / engine 319 checks, sixty-three
planted mutations red (this round's ten, engine checks failed: a
Pdelay_Resp taken for any sequenceId 46 and its sequence compare
narrowed to a byte 44, the arm cleared on the Resp itself 129 of 281
before the run times out, a Follow_Up taken with nothing armed 64 and
the armed bit dropped from its compare 3, the pairing not consumed 44,
the responder identity not paired 42, the arm surviving the next request
42, a completed exchange armed again 2, the completed path skipping the
identity bookkeeping 2; the qualification round's twelve re-run at this
ROM layout, since the packer moved four legs: the own-source rule
removed 42 and its compare narrowed 3, the stepsRemoved bound off by one
48 and 3 and its compare narrowed 30, the dead path-trace compare 44,
the hop compare narrowed 3, the hop read from the next word 32, the count
gate removed 56, the walk one past the count 19, the one-hop walk 45, the
base left offset 83), lint clean. The review rounds added the
completed-exchange rule (the round's earlier head fails its two probes
exactly as the review measured: asCapable 4 after a replayed pair, the
delay 601 to 1600 ns after a skewed one), the high-byte-stale pair, the
boot Follow_Up, the skewed forged pairs of the cease phase, and the
late second identity of phase 27b, which pins the completed path's
identity bookkeeping (a completed path sent to END passes phase 27 and
fails 27b).

## The unlisted-type round re-measured: one LUT

FPGA-gPTP #22, found by the cleared-context review of PR #18 and raised
by the parent lane as a regression its field campaign can see: the
parser admitted any messageType with a valid header, so a frame no
handler claims dispatched all the same, and the entry table's arm for
an unclaimed code is the timer program, whose slot came from the
descriptor's low bits. Slot 0 is the cadence leg, so a type-0x1 frame
drew a Pdelay_Req off the 11.5.2.2 interval and walked the
lost-response count toward an asCapable fall; as master, slot 1 emitted
a Sync off cadence. The dispatch path is old, but the observable
refusal regressed with #18: until then the length term refused the
campaign's 44-octet probes before the type ever mattered, and retiring
the per-type minimum flag left an unlisted type, which has no minimum
of its own, with nothing to fail. The fix is one membership compare at
the type byte, beside the transportSpecific arm and ahead of every bank
write: Table 10-5 (Announce 0xB, Signaling 0xC) and Table 11-3 (Sync
0x0, Pdelay_Req 0x2, Pdelay_Resp 0x3, Follow_Up 0x8,
Pdelay_Resp_Follow_Up 0xA) name the seven types a gPTP port carries,
and the NOTE under Table 11-3 says the other nine values are not used
in this standard. No ucode changed; the ROM stays at 927 real words of
1,024. Same instrument, Vivado 2026.1 OOC on `xc7a100tfgg484-2` at 100
MHz, 2026-08-22, against main at 9d5fb025 re-measured the same day in
its own worktree:

| | 9d5fb025 (PR #14) | the unlisted-type arm | delta |
|---|---|---|---|
| Slice LUTs | 3,115 (2,789 logic + 326 LUTRAM) | **3,116** (2,790 + 326) | **+1** |
| `u_parser` LUTs | 542 | 543 | +1 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

One LUT for a seven-of-sixteen membership test: it joins the compare
the transportSpecific nibble already drives at that byte, and a frame
refused there costs nothing downstream. Verification at this
measurement: ucpu 768 / parser 167 / engine 323 checks, sixty-four
planted mutations red (this round's one, the arm removed: 28 of the
parser suite's checks, and in the engine suite 105 of the 288 the run
reaches, because the cadence leg the injected frame re-arms
desynchronises every exchange after it), lint clean. The parser suite
carries one more that the engine suite cannot see, one type dropped
from the list: Signaling refused, 5 checks.

## The self-sourced round re-measured: ROM words only

FPGA-gPTP #23, found by the cleared-context review of PR #21: the
Pdelay_Resp handler qualified the response's requestingPortIdentity
against thisClock, which asks "is this answering OUR request", but never
qualified its sourcePortIdentity, which asks "is this someone else". A
Pdelay_Resp and Follow_Up pair carrying our own clockIdentity as their
source, our requestingPortIdentity, and the outstanding sequenceId, the
shape a loop or a misconfigured bridge reflects back at us, therefore
computed a delay and climbed the asCapable ladder on evidence we
generated ourselves. The fix is IEEE 1588-2008 9.5.2.2 in ucode, one
64-bit compare of bank word 2 against the S_CID cell the boot leg
already writes from the ROM's identity constant, placed ahead of the
pairing and of the Milan 4.2.6.2.5 bookkeeping alike, because a frame
of our own is not a responder at all. No RTL changed. The ROM grew from
927 to 929 real words of 1,024, 95 free (+2: the compare and its
branch, with the handler's existing read of their source hoisted above
the sequence gate to carry it), every leg base unchanged and 38 word
positions differing, all of them inside the Pdelay_Resp handler's own
slot. Same
instrument, Vivado 2026.1 OOC on `xc7a100tfgg484-2` at 100 MHz,
2026-08-22, against main at c33fb1af re-measured the same day in its
own worktree:

| | c33fb1af (PR #24) | the self-sourced arm | delta |
|---|---|---|---|
| Slice LUTs | 3,116 (2,790 logic + 326 LUTRAM) | **3,116** (2,790 + 326) | **0** |
| `u_ucpu` LUTs | 1,997 | 1,997 | 0 |
| `u_parser` LUTs | 543 | 543 | 0 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Byte-identical, as a ROM-only change must be. Verification at this
measurement: ucpu 768 / parser 167 / engine 328 checks, sixty-seven
planted mutations red (this round's three, engine checks failed: the
compare removed 4, the same compare applied to requestingPortIdentity
instead of sourcePortIdentity 129 of the 285 the run reaches, because
every genuine response carries our requesting identity by definition,
and the compare narrowed to 32 bits 6, caught by the second responder
identity of the Milan 4.2.6.2.5 probes, which now shares our low 32
bits and differs above them), lint clean. The parser suite is untouched
at 167: the parser holds no identity of its own, so the rule cannot be
qualified there.

## The reflected-request round re-measured: ROM words only

FPGA-gPTP #26, found while measuring #23: the responder answered any
Pdelay_Req with a valid header, including one carrying our own
clockIdentity as its source, which is our own request returned by a loop
or a misconfigured bridge. IEEE 1588-2008 9.5.2.2 is the rule ("A
message received at the same port that issued the message shall be
ignored", compared on sourcePortIdentity against the port's own
portIdentity, its Table 17); 802.1AS-2011 Figure 11-9, the MDPdelayResp
machine this handler implements, carries no condition of its own, so
9.5.2.2 is the whole mandate on this side, unlike the requester side
where Figure 11-8 states it. Answering is not merely useless: the
response claims the shared S_PEND cell, so the egress timestamp our own
outstanding Pdelay_Req was waiting for is routed to the Follow_Up leg
and t1 is lost, which publishes 500,600 ns against a modelled 600 and
puts the measurement far outside the -80 to 800 ns verdict window. That
theft is its own defect, #28, reachable by any peer's request in the
same window and NOT closed by this change; what this change removes is
the one trigger guaranteed to land there, since a reflection of our own
request arrives immediately after we send it. The fix is one 64-bit
compare of bank word 2 against the S_CID cell, ahead of every scratch
write, so a refused request leaves no residue. No RTL changed. The ROM
grew from 929 to 932 real words of 1,024, 92 free (+3: the two reads,
the compare and its branch, less the handler's existing read of their
source, hoisted to feed it), every leg base unchanged and 54 word
positions differing, all inside the Pdelay_Req handler's own slot. Same
instrument, Vivado 2026.1 OOC on `xc7a100tfgg484-2` at 100 MHz,
2026-08-22, against main at 03ad3caf re-measured the same day in its own
worktree:

| | 03ad3caf (PR #25) | the reflected-request arm | delta |
|---|---|---|---|
| Slice LUTs | 3,116 (2,790 logic + 326 LUTRAM) | **3,116** (2,790 + 326) | **0** |
| `u_ucpu` LUTs | 1,997 | 1,997 | 0 |
| `u_parser` LUTs | 543 | 543 | 0 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Byte-identical, as a ROM-only change must be. Verification at this
measurement: ucpu 768 / parser 167 / engine 340 checks, seventy
planted mutations red (this round's three, engine checks failed: the
compare removed 17, because the answered reflection also steals the
boot request's egress timestamp; the compare narrowed to the low half 4
and narrowed to the high half 4, each caught by the genuine requester
that differs from us in only the other half), lint clean. Nothing is
counted when the request is refused: the refusal is in ucode, and
`dbg_rx_drop_o` counts what the parser refused, which holds no identity
of its own.

## The tag-matched stamp round re-measured: ROM words only

FPGA-gPTP #28: one scratch cell said which pending transmission the next
egress timestamp belonged to, so any Pdelay_Req arriving while our own
request was still owed its stamp overwrote it, and our t1 was never
stored. The exposure is not a race of a few cycles: measured by sweeping
a genuine peer request against the stamp, the steal works at leads of 0,
1, 10, 100, 2,000, 20,000, 200,000 and 1,000,000 cycles and stops only
once the stamp has already arrived, so the window is the whole interval
our request is outstanding. Its floor here is the frame's own
serialization, 68 bytes at one byte per clock, and the rest of it is the
parent's path to the MAC boundary and back, which this repository does
not model; kebag-logic/milan-fpga#213 measures the real width and the
real stamp separation on hardware.

The arm routes each stamp to a claim by the sequenceId the stamp names,
which narrows the credit without making it unambiguous, so #28 stays
open. Sixteen bits of sequenceId is not an identity: two outstanding
frames whose tags coincide cannot be told apart here, and since both
ends of a link run this implementation and both start S_MYSEQ at zero
and advance once a second, their request sequences are equal FROM BOOT
rather than coinciding one time in 65,536. Three legs also SEND and
leave no claim, prog_leg_anntx, prog_leg_syncfu and prog_leg_rfu, while
the parent's stamper stamps every armed 0x88F7 frame without filtering
on messageType, so a stamp from one of those can match and clear a claim
belonging to a different frame. What this round does achieve is the
shared cell gone, each claim explicit, and the case that was a certainty
rather than a coincidence closed: a peer request landing anywhere in our
outstanding interval no longer diverts our stamp. The clean closure is
msgType beside the sequenceId (kebag-logic/milan-fpga#214), after which
the compare takes both and #28 can close.
KL_gptp_txstamp already reports that sequenceId, the engine already
carries it in the event descriptor, and the dispatch already preloads
the descriptor into REV; only the ucode ignored it. Matching on it is
order-independent, so it rests on no assumption about the order stamps
come back in, which is a parent property this repository cannot
establish. Two claim cells are enough rather than three: the two
timer-driven transmitters already skip their beat while a timer-driven
stamp is owed, so no second timer-driven frame joins them, and a
flag bit above the sequenceId says which of the two a timer claim is.
That shape was forced by measurement, not chosen: the three-cell form
put the timer program at 197 words against its hard 192-word slot. The
flags sit at bits 20 and 21 because a bank-word-0 read leaves the
messageType nibble at bits [19:16], which collided with a flag at bit
16 and cost the responder its match until every claim was masked to
TXQ_MASK_C before comparison. A third fact belongs beside them: the tag
must be bounded to 16 bits BEFORE the flags are or'd in, because
S_MYSEQ is a free-running counter whose bit 21 is TXP_SYNC_C. Unbounded,
every Pdelay_Req stamp from request 2,097,152 onwards, 24.3 days at this
cadence, routes to the Sync Follow_Up leg and the plane emits Follow_Ups
built from a request's egress time while a slave, which 802.1AS-2011
11.2.14 does not permit; it is a certainty at a fixed uptime rather than
a race. The mask that bounds it needed a word, and entry 512 had none,
which is the fourth fact: a fourth transmitter needs all of them.

No RTL changed. The ROM grew from 932 to 941 real words of 1,024 (+9).
The headline free figure, 83, is misleading on its own: the free words
are in other gaps, and the timer program at entry 512 has almost none.
It is 191 of its 192 words in the shipping image and 192 of 192 in the
seeded regression image, whose two extra init instructions replace one,
so the seeded build is the binding constraint and anything added to the
timer program must free a word first. The mask above was paid for that
way, by removing two init zero writes that are redundant under the
invariant recorded beside their definitions, S_CEASECNT and S_MULTI.
This round also moves legs: RFU 964 to 470, SYNCFU 914 to 967 and
SYNCTX 459 to 914, with the other nine bases unchanged, so 288 word
positions differ. Same instrument, Vivado 2026.1 OOC on
`xc7a100tfgg484-2` at 100 MHz, 2026-08-22, against main at 5d4fcc67
re-measured the same day in its own worktree:

| | 5d4fcc67 (PR #29) | the tag-matched stamp | delta |
|---|---|---|---|
| Slice LUTs | 3,116 (2,790 logic + 326 LUTRAM) | **3,116** (2,790 + 326) | **0** |
| `u_ucpu` LUTs | 1,997 | 1,997 | 0 |
| `u_parser` LUTs | 543 | 543 | 0 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

Byte-identical, as a ROM-only change must be. Verification at this
measurement: ucpu 768 / parser 167 / engine 348 checks, seventy-three
planted mutations red (this round's five, engine checks failed: the
response's claim written into the timer transmitter's cell so the two
share one again 12 of the 338 the run reaches, the stamp's sequenceId
ignored so the first claim present takes it 4, the response leaving no
claim at all 151 of 305, the compare narrowed to the low 8 bits 4, and
the claim tag left unbounded 130 of the 314 the seeded regression image
reaches while the shipping image passes it 352 of 352), lint clean.

Two things this round does not close, both recorded rather than
implied. The engine still holds ONE egress timestamp and samples it at
dispatch, so two stamps closer together than the dispatch latency lose
the first value whatever the claims say (#31); the equal-sequence phase
above reproduces it in one line if its gap is removed. And #28 itself
stays open for the reasons in the second paragraph: colliding tags and
frames that leave no claim. The suite pins what the arm does achieve,
including a pair of claims differing only in the high byte of the
sequenceId, which a compare narrowed to the low 8 bits fails, and a
seeded regression image that starts the request counter above 16 bits,
which no ordinary run can reach.

## The counted-refusal round re-measured: one LUT

FPGA-gPTP #27, found by the cleared-context review of PR #24: two
increments of `drop_cnt_r` lived in one `always_ff`, the deferred
end-of-frame arm and the one-byte-frame arm, and a one-byte frame
arriving in the cycle after a dropped frame's end of frame drove both on
the same edge, so only one survived and one refusal went uncounted.
`dbg_rx_drop_o` is the oracle the parent's conformance probes read, and
the parent's campaign asserts a counted refusal in many places, so a
lost increment weakens each of them.

Measured before the change: drop then zero-gap runt gives
one drop where two are owed; the reverse ordering, runt then drop, gives
two, because a runt resolves on its own edge while the frame behind it
resolves on its own edge and a multi-byte frame exactly one cycle after
its eof, so coincidence forces the drop-then-runt order whatever the
frame length or gap; both orderings at a one-cycle gap give two.
The issue measured only the first of those four. The fix is one write
site fed by both conditions, `fin_drop_w` and `runt_drop_w`, adding two
when they coincide. Per-frame exclusivity is untouched: a frame either
dispatches or counts, never both, and what changes is only that two
frames resolving on one edge now produce two outcomes instead of one.
The parent's #210 review leaned on that exclusivity for its retry
argument, and this round does not weaken it. No ucode changed, so the
ROM stays at 941 real words of 1,024, and the three tracked
images are byte-identical. Same instrument, Vivado 2026.1 OOC on
`xc7a100tfgg484-2` at 100 MHz, 2026-08-23, against main at e74485a
re-measured the same day in its own worktree, this round having been
rebased onto the tag-matched stamp of #32 before it landed:

| | e74485a (PR #32) | the counted-refusal arm | delta |
|---|---|---|---|
| Slice LUTs | 3,116 (2,790 logic + 326 LUTRAM) | **3,117** (2,791 + 326) | **+1** |
| `u_parser` LUTs | 543 | 544 | +1 |
| Registers | 2,390 | 2,390 | 0 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+1.898 ns, met** | 0 |

One LUT for the coincidence term, all of it in the parser. Verification
at this measurement: ucpu 768 / parser 179 / engine 352 checks,
seventy-five planted mutations in the engine suite and the parser
ledger's own five new ones red (the two-frame increment collapsed to
one, 2; the same collision written the old way as two sites, the same 2;
the runt term dropped, 5; that term's rx_valid_i qualifier dropped, 2,
which was structural at base and became deletable here; and a zero-gap
successor suppressing the predecessor's deferred dispatch, 3), lint
clean. Two ledger figures elsewhere in that README moved with this
round's frames and were re-measured rather than left: the domain arm
removed is 21, not 16, and the end-of-frame gate without its bad_r term
is 59, not 54. Their neighbours were re-measured too and did not move:
the domain compare narrowed to its low nibble is 7 and the messageLength
arm removed is 24, at base and at head alike.

Swept for the same shape elsewhere in the parser while here: `drop_cnt_r`
was the only register read-modify-written from two sites that can fire
on one edge. Two of the reasons that first stood here did not establish
that, and are replaced with the ones that do. The bank signals are not
safe because a default is overridden later: they have fourteen set
sites, and two of those colliding would lose a bank write, the same bug
class on the data path. They are safe because the `unique case (cnt_r)`
contributes at most one arm, and the per-type body writes sit at
disjoint indices for every `mtype_r`: Sync at 53 and 57, Follow_Up
adding 73, Pdelay_Resp and Pdelay_Resp_Follow_Up adding 65 and 67,
Announce at 66, 74 and 77 plus a path-trace hop write that needs
`pt_run_r` and so cannot fire below index 82. And `fin_r` is not a near
miss whose later assignment happens to win: its two sites can never fire
on one edge at all, because the end-of-frame arm needs `run_r`, which
the eof that set `fin_r` already cleared, and the only way to raise it
again in that cycle is a sof in the eof cycle, which on a one-byte face
is a runt, and the runt arm clears `run_r` without entering the eof arm.

## Complete egress-stamp tags close #28

FPGA-gPTP #28 remained after the sequence-matched round above because a
16-bit sequenceId is not a frame identity. Two identical endpoints start
their Pdelay counters together, while a peer Pdelay_Req makes our response
echo that peer's counter; a response and our own request can therefore have
the same sequenceId for long intervals. Sync has the same collision against
a peer response. Announce and both Follow_Up kinds are stamped too, despite
deliberately leaving no claim, so sequence-only credit could also let one of
those returns clear an unrelated claim.

The parent stamper now exports the messageType nibble beside sequenceId. This
round adds `txts_type_i`, holds the complete pair while the event queue is
busy, and packs `{messageType, sequenceId}` into event `aux[19:0]`. Each
transmitter claim carries the same pair. The TX handler masks and compares all
20 tag bits plus the pending flag before consuming a timestamp. A same-sequence
Pdelay_Resp stamp therefore builds its own Resp_Follow_Up before the outstanding
Pdelay_Req stamp is returned, and a same-sequence response cannot build a Sync
Follow_Up. A subsequent stamp for the unclaimed Follow_Up is ignored in both
cases. The independent one-entry timestamp buffering defect remains #31.

Packing the tag in the event descriptor also removes the handler's two shift
instructions, so the ROM falls from 941 to 940 real words of 1,024. The timer
program remains at 191 of its 192 words in the shipping image and 192 of 192 in
the seeded image. Same instrument, Vivado 2026.1 OOC on
`xc7a100tfgg484-2` at 100 MHz, 2026-08-24, with exact base `10b6f353`
re-measured in a separate worktree:

| | `10b6f353` (`main`) | complete stamp tag | delta |
|---|---|---|---|
| Slice LUTs | 3,117 (2,791 logic + 326 LUTRAM) | **3,171** (2,837 + 334) | **+54** |
| `u_ucpu` LUTs | 1,997 | 2,030 | +33 |
| `u_parser` LUTs | 544 | 557 | +13 |
| Registers | 2,390 | 2,407 | +17 |
| BRAM tiles | 1.5 | 1.5 | 0 |
| DSP48E1 | 4 | 4 | 0 |
| WNS at 100 MHz, OOC | +1.898 ns | **+2.445 ns, met** | +0.547 ns |

The hierarchy figures include Vivado's cross-boundary optimization; the
top-level delta is the stable cost statement. Verification at this measurement:
ucpu 768 / parser 179 / engine 358 checks in both the normal and seeded engine
images, full repository `make` and lint clean. The two new planted mutations
both turn the run red: forcing the returned messageType to zero breaks the
type-specific collision oracles, and removing the type bits from event and
claims to restore sequence-only credit fails six of the 343 checks reached,
including both response-first collisions and the missing/corrupt Follow_Up
outcomes.
