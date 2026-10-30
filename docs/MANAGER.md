<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Manager guide

This page summarizes value, readiness, evidence, and risk.

## Summary

- Fabric gPTP owns product time in the parent.
- Interfaces and protocol behavior are regression-tested in simulation.
- Physical acceptance and timestamp calibration remain open.
- The microcode ROM is nearly full.
- No certification claim is made.

Terms are defined in the [glossary](GLOSSARY.md).

## Product value

- Timing control stays inside programmable logic.
- Protocol work shares one deterministic clock domain.
- Parent systems capture status on each commit pulse.
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
| Publication | Commit pulse marks each complete publication | [Integration guide](INTEGRATION.md#publication) |
| Bench evidence | Historical silicon campaigns available | [History](history/v1/README.md) |

Parent ownership references pin `dev` at `ac2c5e77`.

Current RTL remains reviewable and regression-tested.

No certification claim is made.

## Latest measured snapshot

The [HDL guide](HDL_DEVELOPER.md#out-of-context-measurement) holds the latest dated synthesis figures.

They come from main `5dce647a`, measured on 2026-10-11.

Both measured tops met timing at 100 MHz.

Earlier deltas live in the [resource-delta archive](history/v1/RESOURCE_DELTAS_2026_10.md).

## Current ROM budget

The generator prints this budget on every run.

`make docs` fails when this table drifts from it.

| Image | Words used | Free |
|---|---|---:|
| Shipping | 1,022 of 1,024 | 2 |
| Seeded regression | 1,023 of 1,024 | 1 |

Used words include thisClock's data words 1022 and 1023.

Free words lie scattered across packing gaps.

Shared legs may occupy the formerly reserved prefix.

That prefix spans addresses 0..15.

The current map places `SERVO@0` in that prefix.

`FUTO@254` sits outside it.

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
