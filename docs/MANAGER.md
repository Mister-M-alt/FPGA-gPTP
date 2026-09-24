<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Manager guide

This page summarizes value, readiness, evidence, and risk.

## Product value

- Timing control stays inside programmable logic.
- Protocol work shares one deterministic clock domain.
- Parent systems receive direct committed status.
- Microcode supports rapid protocol-policy changes.
- Dedicated RTL handles predictable byte movement.

## Delivery status

| Area | Current state | Evidence |
|---|---|---|
| Parent ownership | Enabled by default | [Integration evidence](INTEGRATION.md#parent-ownership) |
| Receive path | Implemented and regression-tested | [HDL guide](HDL_DEVELOPER.md#receive-path) |
| Transmit path | Backpressure-tested | [TX timing](HDL_DEVELOPER.md#transmit-timing) |
| PHC control | Addend, step, and slew-level outputs implemented | [Integration guide](INTEGRATION.md#phc-control) |
| Publication | Atomic commit pulse implemented | [Integration guide](INTEGRATION.md#publication) |
| Bench evidence | Historical silicon campaigns available | [History](history/v1/README.md) |

Current RTL remains reviewable and regression-tested.

No certification claim is made.

## Latest measured snapshot

Measurements used Vivado 2026.1.

The target was `xc7a100tfgg484-2` at 100 MHz.

Measurements finished on 2026-08-27.

| Block | LUTs | Registers | BRAM tiles | DSPs | WNS |
|---|---:|---:|---:|---:|---:|
| Complete engine | 4,719 | 3,639 | 1.5 | 4 | +2.249 ns |
| Standalone microCPU | 1,643 | 733 | 1.5 | 4 | +1.941 ns |

These figures describe one synthesis instrument.

See the [historical resource record](history/v1/RESOURCE_VALIDATION.md).

## Current ROM budget

Shipping usage: 1,008 of 1,024 words (98.4%).

Only 16 words remain free, spread across packing gaps.

Shared legs may occupy the formerly reserved prefix.

That prefix spans addresses 0..15.

The current map places `SERVO@0` and `FUTO@13` there.

Engine dispatch entries start at address 16.

Reset parks the sequencer without fetching an instruction.

Keep these invariants when changing dispatch or reset behavior.

Packing requires each leg to fit one available gap.

Total free space alone does not guarantee a fit.

Regenerate all four tracked images after every microcode change.

The [generator](../hdl/ucode/gen_gptp_ucode.py) rejects overflow and overlapping programs.

## Open risks

- [Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) covers mid-frame receive errors.
- Parent gitlink updates require separate review.
- Physical acceptance remains product-specific.

## Management decisions

- Keep product integration enabled.
- Retain disabled builds for comparisons only.
- Track every open correctness issue explicitly.
- Require exact-head verification before parent updates.
- Preserve dated campaigns within versioned history.

## Release evidence

Require these results:

- Documentation checks pass.
- Diagram bindings pass.
- All Verilator suites pass.
- Engine lint passes.
- Bench integration lint passes.
- Open risks remain visible.
