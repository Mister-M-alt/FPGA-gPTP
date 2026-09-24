<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# HDL developer guide

This guide explains structure, timing, and invariants.

![FPGA-gPTP architecture](diagrams/gptp_architecture.png)

The editable source remains [available](diagrams/gptp_architecture.drawio).

## Module map

| Module | Responsibility |
|---|---|
| `KL_gptp_engine` | Integration, queues, state, arbitration |
| `KL_gptp_rx_parser` | Byte parsing and message banking |
| `KL_gptp_ucpu` | Microcode execution and arithmetic |
| `KL_gptp_tx_slot` | Frame construction and serialization |
| `KL_gptp_timer` | Eight millisecond deadline slots |
| `gptp_ucpu_pkg` | Opcodes, constants, event identifiers |

All modules use one clock domain.

## Receive path

The parser accepts one byte each valid cycle.

It validates headers before dispatching events.

Accepted data enters ping-pong message banks.

Ingress timestamps follow the same bank selection.

Announce uses one frozen context.

Chasing Announces become counted drops.

Other event types may continue.

### Receive timing

![Accepted receive event timing](diagrams/wavedrom/rx_accept.png)

EOF stores the final parser decision.

Finalization occupies the next cycle.

The accepted event follows finalization.

[WaveDrom source](diagrams/wavedrom/rx_accept.json) defines this timing.

## Event arbitration

- Four entries buffer parser and timer events.
- Parser events win simultaneous queue pushes.
- Timer expiry waits using valid-ready flow control.
- Timestamp results use a priority side path.
- Dispatch waits until serialization becomes idle.
- Later requests wait behind response ownership.

Never bypass ownership without preserving context.

## Egress result ownership

One result is accepted per valid-ready beat.

Its value, tag, outcome and generation latch together.

Readiness falls until that result dispatches.

A later offer therefore waits at its producer.

Backpressure can never replace an earlier result.

The dispatched word carries outcome and generation.

Both ride above the masked claim comparison.

## Retained pairing context

A peer answer can precede our own transmit time.

The completed pair then waits for that time.

Its identity and measurements stay in scratch.

A later response cannot rewrite the waiting pair.

Responder bookkeeping still counts every matching response.

Only the waiting pair's own arrival releases it.

Reset-backed validity guards both retained pairing cells.

A measured zero remains a valid time.

## State regions

The microCPU uses `st_addr_o[19:16]` for selection.

| Region | Access | Contents |
|---:|---|---|
| 0 | Read-only | Ping-pong message banks |
| 1 | Read-only | Ingress time, egress time, credit |
| 2 | Read-write | Sixty-four protocol scratch words |
| 3 | Read-write | Publication staging bank |
| 4 | Read-write | PHC controls and policy completion qualifier |
| 5 | Write-only | Timer arming interface |

Scratch storage survives warm resets.

Resettable claim-valid bits do not survive.

Pairing validity bits do not survive either.

The PHC slew qualifier also resets independently.

Microcode writes its remaining completion pairs through PHC word 2.

Nonzero decisions immediately assert `phc_slew_active_o`.

A zero decision clears it with the next rate write.

PHC word 3 retires an active correction during mastership.

## MicroCPU shape

- ROM contains 1,024 forty-eight-bit instructions.
- Register storage contains sixteen sixty-four-bit words.
- Integer logic supports common sixty-four-bit operations.
- Shifts run serially.
- Signed multiplication uses inferred DSP resources.
- Unsigned division runs serially.
- Dispatch preloads event and timestamp registers.
- Multi-cycle operations hold execution safely.

Protocol rates tolerate serial arithmetic.

## Transmit timing

![Transmit backpressure timing](diagrams/wavedrom/tx_backpressure.png)

Valid remains asserted during stalls.

Data and markers remain stable during stalls.

State advances only after ready acceptance.

[WaveDrom source](diagrams/wavedrom/tx_backpressure.json) defines this timing.

## Publication invariant

Microcode stages publication values first.

`OP_COMMIT` exposes the complete staged tuple.

Consumers sample only during `pub_commit_o`.

Inactive path entries must remain zero.

## Change checklist

- Preserve single-clock assumptions.
- Preserve valid-ready transfer rules.
- Preserve bank and timestamp pairing.
- Preserve event ownership snapshots.
- Preserve reset-validity separation.
- Preserve accepted-result immutability.
- Preserve message scope on every cancellation.
- Gate only the three initiating legs.
- Update microcode and tests together.
- Add negative and boundary tests.
- Update both WaveDrom sources when timing changes.
- Update Draw.io after structural changes.
- Regenerate every committed diagram.
- Run lint and complete simulations.
