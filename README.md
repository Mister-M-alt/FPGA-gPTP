<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# gptp-processor — the 802.1AS time-sync plane

The gPTP sibling of the `protocol-processor` submodule: a micro-coded
engine consumed by `milan-fpga` as its `gptp-processor` submodule through
`hdl/ieee8021as/gptp_plane/KL_gptp_shadow.sv`, option-gated by the
`milan_datapath` parameter `GPTP_PLANE_EN_P` (RTL default off; the shipping
AX7101 configuration opts in with `board.features.fabric_gptp: true`). With
the option on it owns the duties `ptp4l` + `milan-statd` perform on the soft
core -- BTCA, Announce, Sync/Follow_Up, both Pdelay roles, the PHC servo, and
the publication surface (GM identity, asCapable, sync verdict, peer delay) --
as one clock domain of fabric, byte in / byte out. The CSR readback words and
the rootfs daemons stay software until parent issue #116 flips the default.

**Status: the state machines are landing as µcode revisions.** The round
that created this repo (2026-08-14) priced the plane on the ship part;
everything structural (the grown-ISA µCPU, the 802.1AS receive parser,
the TX build slot, the timer service, the engine region map) is real and
verified. Since then the ROM has grown through bench-proven revisions:
v2 both Pdelay roles + announce adopt, v3 grandmaster capability (BTCA
two-node subset, Announce with path trace, two-step Sync + Follow_Up,
bilateral BMCA interop with third-party silicon on the bench), v4 the
asCapable ladder, the sync/Follow_Up receipt timeouts and
neighborRateRatio with the Milan v1.2 Table 4.1/4.2 profile numbers,
mutation-proven in the engine suite, and v5 the PHC servo: observe-only
is retired. Offsets beyond 20 us (the linuxptp first_step_threshold
default) re-base the clock in one adjtime write per the GM-loss DLL
policy, smaller ones drive a clock-aware PI addend (kp 3/4, ki 1/4 of
the normalized gain: critically damped), and the engine suite proves
lock closed-loop against a +140 ppm master, and v6 the full-compare
round: BTCA against a stored best vector (parent updates, stepsRemoved
and sourcePortIdentity tie-breaks, immediate takeover on parent
degradation), Sync/Follow_Up sequence-and-source pairing, asCapable
gating sync consumption, and the paired Follow_Up preciseOriginTimestamp
carrying the live egress stamp, and v7 the cease-rule round -- the
deliberate end of the zero-RTL era: the engine gains a SECOND message
bank (each accepted frame lands in the bank its event names, retiring
the torn-read window) and a 64-word scratch, and the Milan 4.2.6.2.5
multiple-responder cease rule lands on that room (three multi-identity
intervals stop Pdelay_Req, a 5-minute timer resumes, duplicates from
one identity are not a storm), and the parent's field campaign then
found the receive side ignoring domainNumber (#6): the parser refuses
any domain but 0 at the header byte, ahead of every bank write, so no
handler can see a foreign-domain frame (-15 LUT: the domain byte of
bank word 0 became the constant the parser admits), then its two
transmit-side findings, the Table 11-7 control field per message type
(#9: Sync 0x0, Follow_Up 0x2, Announce and the three Pdelay messages
0x5) and the ten reserved zero bytes of the two-step Sync body (#10: the
live egress time rides only in the Follow_Up's preciseOriginTimestamp),
both ROM-only, and accepting a
Follow_Up without the mandatory information TLV (#11): the parser now
requires the 76-octet message of Table 11-9, refuses a short
messageLength ahead of every bank write and the wrong TLV header
(11.4.4.3) ahead of the event, so a TLV-less or truncated Follow_Up
no longer reaches the servo (+34 LUT for the two compares, the
redundant per-type minimum flag retired), and a header-only Pdelay_Req
drawing a Pdelay_Resp (#12): the request's minimum is the 54 octets of
Table 11-11, one line of the same per-type table, so a truncated
request is refused ahead of the responder, and then the announce
handler admitting every well-formed Announce (#7): 802.1AS-2011
10.3.10.2.1 qualifyAnnounce now runs ahead of BTCA and of every write
the handler makes (our own clockIdentity as the source, stepsRemoved 255
and above, our identity anywhere in the path trace the bank holds), its
count-gated hop walk the first consumer of OP_DESC_ADDR (+23 ROM words,
zero LUT), and then one unsolicited Pdelay_Resp_Follow_Up poisoning
neighborPropDelay and dropping asCapable (#8): both Pdelay receive
handlers now pair per 802.1AS-2011 11.2.15.3, a Pdelay_Resp taken only
for the outstanding request's sequenceId and never again once its
exchange has completed, a Follow_Up only behind that Pdelay_Resp and
from its sender (+32 ROM words, zero LUT). Nothing of #6 through #12
remains open, and #23 closes here. The donor issues open at this commit
are all review findings on pre-existing behaviour: #26 (a Pdelay_Req
sourced from our own clockIdentity is answered, the same 1588-2008
9.5.2.2 rule on the responder side), #28 (a Pdelay_Req arriving while
our own request waits for its egress timestamp steals it through the
shared pending cell, so the delay reads 500,600 ns), #27 (a zero-gap
1-byte runt landing the cycle after a dropped frame is not counted) and
#30 (the requestingPortIdentity gate is unpinned and omits Figure
11-8's portNumber term); the issue tracker is the authority, not this
paragraph. Measured at this commit (`main` c33fb1af plus the
self-sourced response arm): ucpu 768 / parser 167 / engine 328 checks,
sixty-seven planted mutations red, lint clean; the ROM is 929 of 1,024
words, 95 free; the engine synthesizes OOC at 3,116 LUT / 2,390 FF /
WNS +1.898 ns
(`docs/RESOURCE_VALIDATION.md`).

**Parent status:** the splice is landed (parent #114, 2026-08-19,
option-gated) and the pin advances by pin-bearing commits on the
parent's `dev`, at `5c330fc8` (the #16 merge): the pin trails the donor
by design, and the parent tickets below move it forward. The parent's
`tb/verilator/tsn_fuzz` field campaign (`make ptp`, `fuzz_ptp.py`) grades
the whole slice in both directions -- every spec-constrained field of all
six of the plane's own TX message types (Pdelay_Req, Pdelay_Resp,
Pdelay_Resp_Follow_Up, Announce, Sync and Follow_Up) against the tsn-gen
8021as models, and the parser's drop and ignore arms under per-field
illegal probes -- and found #6 through #10. Each donor fix retires its
own allowance at the repin, one parent ticket per donor issue, by one of
two mechanisms. A tracked gap marker covers #6, #9, #10, #7 and #8: the
ones still standing on `dev` `4ec73a15` are
`gaps={"origin_timestamp": 10}` (`fuzz_ptp.py:489`, #137 for #10), the
issue-8 arm (`:675`, #141 for #8) and the issue-7 arms (`:747`, plus
`:719` reached from its two issue-7 `reject_probe` call sites `:736`
and `:739`, #136 for #7), while #138 (#6) is done at the `dd0f56e3` pin
and #139 (#9) at the `5c330fc8` pin (PR #208, dev `4ec73a15`), both
markers already gone. For #11 and #12 there is no allowance to delete:
what moves is the campaign's truncation oracle, which cuts at this
parser's donor minima (`:573-582`, in frame bytes: Sync 58, Follow_Up
58, Announce 78, Pdelay_Req 48), so #140 (#11) carries the Follow_Up cut
to the legal 90 bytes and #142 (#12) the Pdelay_Req cut to 68. #137,
#140, #142, #136 and #141 are pending. Parent PR #135
(default on at VERSION
0x0002_0055) was closed unmerged: the default flip, the CSR compatibility
transition and the rootfs service retirement stay with parent issue #116,
reference-plane latency characterization and the two-board wire campaign
with parent issue #117. The parent's page of record is its
`docs/design/GPTP_PLANE.md`.

## Why a µCPU with an ALU

The AECP µCPU (measured 1,070 LUT / 3 RAMB36) deliberately has no
arithmetic — AEM is data shuffling. gPTP is 64-bit timestamp subtraction,
scaled-ns correction fields, a rate-ratio division and a servo multiply,
all at ≤ 8 Hz with millisecond deadlines (Milan relaxes the Pdelay
turnaround to 15 ms). One shared serial ALU walked by µcode is the
area-minimal shape for that; `KL_gptp_ucpu` is therefore a PURE SUPERSET
of the AECP µCPU — every base port and decode arm kept — plus:

| op | what |
|---|---|
| `OP_ALU` | 64-bit ADD/SUB/AND/OR/XOR single-cycle; SHL/SHR/SAR serial, one bit per cycle |
| `OP_MULDIV` | MULS signed 32×32→64 (DSP-inferred); DIVU restoring 64/32→64, one bit per cycle |

so its OOC delta against the 1,070-LUT anchor prices the ISA growth alone.

## Tree

| path | what |
|---|---|
| `hdl/ucpu/` | `gptp_ucpu_pkg.sv` (µISA), `KL_gptp_ucpu.sv` |
| `hdl/wire/` | `KL_gptp_rx_parser.sv` (802.1AS byte parse → message bank), `KL_gptp_tx_slot.sv` (build slot + serializer) |
| `hdl/common/` | `KL_gptp_timer.sv` (ms deadline service, 8 slots) |
| `hdl/top/` | `KL_gptp_engine.sv` (parser + µCPU + slot + timer + region map + publish wires) |
| `hdl/ucode/` | `gen_gptp_ucode.py` — ROM image generator (entry table mirrored by the engine) |
| `tb/verilator/ucpu/` | arithmetic battery vs an independent C++ model (mutation-proven) |
| `tb/verilator/parser/` | 802.1AS field extraction + drop arms (mutation-proven) |
| `tb/verilator/engine/` | whole-plane round-trip vs a scripted peer + spec-formula pdelay model (mutation-proven) |
| `syn/ooc/` | the measurement instrument + `docs/RESOURCE_VALIDATION.md`'s numbers |

## Run everything

```sh
make            # all three Verilator suites (exit 0 = PASS)
make lint       # verilator --lint-only on the engine top
syn/ooc/run.sh  # Vivado 2026.1 OOC measurement into syn/ooc/work/
```

## Implemented integration contract (parent: milan-fpga)

What `KL_gptp_shadow` wires to `KL_gptp_engine` when `GPTP_PLANE_EN_P` is
set. With it clear the control lane passes straight through, the PHC knobs
constant-fold to the CSR face and the publish words read zero, so every
other build is bit-identical.

- RX: an input-only tap on the MAC RX AXIS stream (a beat is real when
  `tvalid && tready`) classifies EtherType 0x88F7 at the aligned lanes into
  a frame FIFO (frame mode; bad and oversize frames dropped, drops counted)
  and serializes each delivered frame to the engine at 1 byte/clk, DA first.
  The ingress timestamp is latched at the frame's first tap beat, pushed
  into a side FIFO on the frame FIFO's commit pulse (once per delivered
  frame; the shed rule of parent #122 keeps it from lapping a live stamp)
  and popped at sof. The engine's `rx_err_i` is tied low: the frame FIFO
  never delivers a bad frame.
- TX: the engine's byte stream gears up to one wide, frame-held lane that
  joins the control TX after the min-IFG gasket through its own staggered
  merge (`adp_tx_arbiter`, diagnostics lane 4); `KL_gptp_txstamp` watches
  the true MAC boundary, armed by the lane's sof, and returns {timestamp,
  sequenceId} on `txts_*` for the engine's pending exchange.
- PHC: `phc_ns_i` is the live `timestamp_counter` value; the engine's
  adjfine pulse is latched to a level in the shadow and its adjtime passes
  through, both onto the counter's knobs in place of the CSR face's
  `/dev/ptpN` writes; settime stays with the CSR face (boot sets the epoch).
- Publish bank out: GM identity, parent identity, flags (present, gm,
  asCapable, sync), peer delay, offset and `pub_annq` leave the shadow as
  wires beside the engine's commit pulse. Today only the GM identity has a
  fabric consumer (`milan_datapath` muxes it over the CSR-published value
  for the ADPDU/GET_AVB_INFO/AS_PATH face, the Milan-info answers and the
  recentre latch); the other words and the commit pulse stay unconsumed
  until #116 re-points the CSR readback words (ADP_GM 0x624/0x628,
  GPTP_PDELAY 0x6E4, the 0x730 AS_PATH group) and the `tu` bit at the
  plane.
- ROM: the parent's builder generates the per-configuration 1,024-word
  image from this repo's `hdl/ucode/gen_gptp_ucode.py` (`--mac`, `--p1`,
  `--clk-hz` from the station YAML) and passes its path as
  `GPTP_UCODE_HEX_P`; the parent tracks no image of its own, and its CI
  fetches this submodule for the RTL and documentation gates.

## Measured record

See `docs/RESOURCE_VALIDATION.md`. Every number in it is a Vivado 2026.1
out-of-context post-synthesis figure on `xc7a100tfgg484-2` at 100 MHz —
the same instrument as every anchor in the protocol-processor's
`10_RESOURCE_AND_EFFORT.md`, whose OOC-vs-real-SoC calibration was
accurate to one LUT.
