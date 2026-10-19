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
| Parent default | `GPTP_PLANE_EN_P` enabled | [Parent parameter](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L73) |
| Product time owner | Fabric gPTP | [Parent ownership](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L6) |
| Option-off | Verification-only comparison; no product image | [Parent boundary](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/ARCHITECTURE_HW_SW_SPLIT.md#L165-L175) |
| Receive path | Implemented and regression-tested | [HDL guide](HDL_DEVELOPER.md#receive-path) |
| Transmit path | Backpressure-tested | [TX timing](HDL_DEVELOPER.md#transmit-timing) |
| PHC control | Addend, step, and slew-level outputs implemented | [Integration guide](INTEGRATION.md#phc-control) |
| Publication | Atomic commit pulse implemented | [Integration guide](INTEGRATION.md#publication) |
| Bench evidence | Historical silicon campaigns available | [History](history/v1/README.md) |

Parent ownership references pin `dev` at `ac2c5e77`.

Current RTL remains reviewable and regression-tested.

No certification claim is made.

## Latest measured snapshot

Measurements used Vivado 2026.1 out-of-context synthesis.

The target was `xc7a100tfgg484-2` at 100 MHz.

Both flows measured main `5dce647a` on 2026-10-11.

| Block | Flow | LUTs | Registers | BRAM tiles | DSPs | WNS |
|---|---|---:|---:|---:|---:|---:|
| Complete engine | Constrained | 4,852 | 3,652 | 1.5 | 4 | +1.773 ns |
| Complete engine | Unconstrained | 4,853 | 3,652 | 1.5 | 4 | +1.773 ns |
| Standalone microCPU | Constrained | 1,643 | 733 | 1.5 | 4 | +1.941 ns |
| Standalone microCPU | Unconstrained | 1,643 | 733 | 1.5 | 4 | +1.941 ns |

The constrained flow reads the clock before synthesis.

The unconstrained flow created the clock after synthesis.

Only constrained WNS reflects a synthesis timing target.

Constraining the clock removed one engine LUT; nothing else moved.

The [HDL guide](HDL_DEVELOPER.md#out-of-context-measurement) describes both flows.

PR #76 measurements finished on 2026-09-24.

They used the unconstrained flow.

PR #76 adds 80 LUTs and six registers.

The baseline used 4,773 LUTs and 3,646 registers.

Memory LUTs remain 466; BRAM and DSP usage stay unchanged.

WNS moves from +2.249 ns; timing remains met.

The [PR measurement reports](https://github.com/kebag-logic/milan-fpga/tree/4999d8d6344e373e0204995cb36c93cf616e8f9e/review-evidence/gptp75-r1/author) record the comparison.

### M7 timer-storage measurement

Measurements finished on 2026-10-10 for milan-fpga #640, lane M7.

| Block | LUTs | Registers | BRAM tiles | DSPs | WNS |
|---|---:|---:|---:|---:|---:|
| Complete engine | 4,748 | 3,396 | 1.5 | 4 | +2.249 ns |
| Standalone microCPU | 1,643 | 733 | 1.5 | 4 | +1.941 ns |

These figures used the then-unconstrained `make ooc` flow.

They describe timer storage at lane head `18dd997b`.

The timer's deadlines move from registers to distributed RAM.

The engine sheds 105 LUTs since PR #76.

It also sheds 256 registers.

Memory LUTs rise from 466 to 490.

BRAM and DSP usage stay unchanged.

WNS moves from +1.773 ns; timing remains met.

The standalone microCPU repeats the PR #76 figures exactly.

See the [historical resource record](history/v1/RESOURCE_VALIDATION.md).

## Current ROM budget

Shipping usage: 1,015 of 1,024 words (99.1%).

That count includes thisClock's two data words at 1022..1023.

Only nine words remain free, spread across packing gaps.

Shared legs may occupy the formerly reserved prefix.

That prefix spans addresses 0..15.

The current map places `SERVO@0` in that prefix.

`FUTO@125` sits outside it.

Engine dispatch entries start at address 16.

Reset parks the sequencer without fetching an instruction.

Keep these invariants when changing dispatch or reset behavior.

Packing requires each leg to fit one available gap.

Total free space alone does not guarantee a fit.

Regenerate all four tracked images after every microcode change.

The [generator](../hdl/ucode/gen_gptp_ucode.py) rejects overflow and overlapping programs.

## Open risks

| Gap | Status | Tracking |
|---|---|---|
| Donor asymmetry input, calibration triple, live tuner | Open | [Issue #58](https://github.com/Mister-M-alt/FPGA-gPTP/issues/58) |
| Physical synchronization, GM recovery, conformance, and fabric publication | Acceptance still owed against the reference peer | [Parent #117](https://github.com/kebag-logic/milan-fpga/issues/117) |
| Physical timestamp calibration and ingress/egress split | Incomplete | [Parent #64](https://github.com/kebag-logic/milan-fpga/issues/64), [parent #488](https://github.com/kebag-logic/milan-fpga/issues/488) |

The [parent status](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/guides/gptp/MANAGER.md#L33-L35) keeps calibration and physical acceptance incomplete.

Parent v1.2 [excludes propagation asymmetry](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L350-L366).

Its [timestamp corrections](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L363-L366) remain parent-owned constants, applied once.

Donor #58's live tuner remains outside that product contract.

Parent gitlink updates require separate review.

## Management decisions

- Keep [product integration enabled](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L43-L44).
- Retain disabled builds for [verification-only comparisons](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L49).
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
