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
| PHC control | Addend and step outputs implemented | [Integration guide](INTEGRATION.md#phc-control) |
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

The shipping image uses 932 words.

The ROM capacity is 1,024 words.

These figures describe one synthesis instrument.

See the [historical resource record](history/v1/RESOURCE_VALIDATION.md).

## Open risks

- [Issue #31](https://github.com/Mister-M-alt/FPGA-gPTP/issues/31) covers timestamp overwrite risk.
- [Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) covers mid-frame receive errors.
- Parent gitlink updates require separate review.
- Physical acceptance remains product-specific.

## Management decisions

- Keep product integration enabled.
- Retain disabled builds for comparisons only.
- Track both open correctness issues explicitly.
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
