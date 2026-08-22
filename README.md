<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# gptp-processor — the 802.1AS time-sync plane

The gPTP sibling of the `protocol-processor` submodule: a micro-coded
engine intended to take over the duties `ptp4l` + `milan-statd` perform on
the milan-fpga soft core today — BTCA, Announce, Sync/Follow_Up, both
Pdelay roles, the PHC servo, and the publication surface (GM identity,
asCapable, sync verdict, peer delay) — as one clock domain of fabric,
byte in / byte out, in the `KL_pp_shadow` integration shape.

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
bank word 0 became the constant the parser admits), and accepting a
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
zero LUT). Next: the parent-side integration.

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

## Integration contract (parent: milan-fpga)

- RX: pre-classified EtherType 0x88F7 byte stream (DA first, FCS checked
  and stripped), plus the frame's ingress timestamp latched at sof — both
  already exist in the parent (`KL_pp_shadow` classifier pattern,
  `ptp_ts_top` capture).
- TX: byte stream with sof/eof onto the control TX cascade; egress
  timestamp returned via `txts_*` (same `ptp_ts_top` capture, TX side).
- PHC: `phc_ns_i` snapshot in, rate-addend and step writes out — the
  parent `timestamp_counter`'s adjfine/adjtime knobs, driven from fabric
  instead of from `/dev/ptpN`.
- Publish bank out: GM identity, parent identity, flags (asCapable, sync
  ok), peer delay — the CSR words `milan-statd` mirrors today
  (0x624/0x628, 0x6E4, 0x778, 0x730 group) become wires.

## Measured record

See `docs/RESOURCE_VALIDATION.md`. Every number in it is a Vivado 2026.1
out-of-context post-synthesis figure on `xc7a100tfgg484-2` at 100 MHz —
the same instrument as every anchor in the protocol-processor's
`10_RESOURCE_AND_EFFORT.md`, whose OOC-vs-real-SoC calibration was
accurate to one LUT.
