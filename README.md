<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# gptp-processor — the 802.1AS time-sync plane

The gPTP sibling of the `protocol-processor` submodule: a micro-coded
engine intended to take over the duties `ptp4l` + `milan-statd` perform on
the milan-fpga soft core today — BTCA, Announce, Sync/Follow_Up, both
Pdelay roles, the PHC servo, and the publication surface (GM identity,
asCapable, sync verdict, peer delay) — as one clock domain of fabric,
byte in / byte out, in the `KL_pp_shadow` integration shape.

**Status: resource-validation skeleton.** The round that created this repo
(2026-08-14) exists to answer one question with a measurement instead of an
estimate: *what does the gPTP plane cost on the ship part?* Everything
structural is real and verified — the grown-ISA µCPU, the 802.1AS receive
parser, the TX build slot, the timer service, the engine region map — and
the µcode entry handlers are honest first cuts that exercise every new
datapath. The 802.1AS state machines of record (BTCA, asCapable ladder,
receipt timeouts, the Milan v1.2 Table 4.1/4.2 profile numbers) land as
µcode revisions on this same ROM; they are NOT here yet, and nothing in
this repo claims otherwise.

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
| `syn/ooc/` | the measurement instrument + `docs/RESOURCE_VALIDATION.md`'s numbers |

## Run everything

```sh
make            # both Verilator suites (exit 0 = PASS)
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
