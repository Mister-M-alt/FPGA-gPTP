[OBSOLETE + 2026-10-30]

> Status: Historical
>
> Original path: `docs/MANAGER.md`
>
> Archived: 2026-10-30
>
> Current successor: [current HDL guide](../../HDL_DEVELOPER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Resource deltas before main `5dce647a`

These two out-of-context measurements preceded the current snapshot.

Both used the then-unconstrained `make ooc` flow.

The current figures live in the HDL guide.

## PR #76 slew-level output

Measurements finished on 2026-09-24.

PR #76 adds 80 LUTs and six registers.

The baseline used 4,773 LUTs and 3,646 registers.

Memory LUTs remain 466; BRAM and DSP usage stay unchanged.

WNS moves from +2.249 ns; timing remains met.

The parent tree at `4999d8d6` holds the [measurement reports](https://github.com/kebag-logic/milan-fpga/tree/4999d8d6344e373e0204995cb36c93cf616e8f9e/review-evidence/gptp75-r1/author).

## Timer storage in distributed RAM

Measurements finished on 2026-10-10 for milan-fpga #640.

| Block | LUTs | Registers | BRAM tiles | DSPs | WNS |
|---|---:|---:|---:|---:|---:|
| Complete engine | 4,748 | 3,396 | 1.5 | 4 | +2.249 ns |
| Standalone microCPU | 1,643 | 733 | 1.5 | 4 | +1.941 ns |

They describe timer storage at head `18dd997b`.

The timer's deadlines move from registers to distributed RAM.

The engine sheds 105 LUTs since PR #76.

It also sheds 256 registers.

Memory LUTs rise from 466 to 490.

BRAM and DSP usage stay unchanged.

WNS moves from +1.773 ns; timing remains met.

The standalone microCPU repeats the PR #76 figures exactly.
