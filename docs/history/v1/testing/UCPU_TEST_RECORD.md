[OBSOLETE + 2026-08-31]

> Status: Historical
>
> Original path: `tb/verilator/ucpu/README.md`
>
> Archived: 2026-08-31
>
> Current successor: [current test guide](../../../TEST_DEVELOPER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# tb/verilator/ucpu — arithmetic battery

Proves the grown µISA against an INDEPENDENT C++ model (never the DUT's
own logic): the battery µprogram at ROM entry 768 computes twelve results
per dispatch — ADD/SUB/AND/OR/XOR, SHL/SHR/SAR by a register amount,
MULS, DIVU, and two immediate forms — over directed edges (zero, all-ones,
sign bit + SAR 63, shift-by-0, 32-bit-max divisor) plus 64 random operand
pairs, writing each through the state port where this harness records and
compares them. 768 checks. Mutation-proven: planting `+1` into the
model's ADD fails exactly the 64 ADD checks.

DIVU's divide-by-zero is µcode's contract to guard, so the harness never
issues one; the hardware behavior there is unspecified by design.

`make` — exit 0 = PASS.
