[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/VERIFICATION.md`
>
> Archived: 2026-09-01
>
> Current successor: [current test guide](../../../TEST_DEVELOPER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Verification — what is proven, by what, and how to run it

Five simulation suites (**1,297 checks**), an independent-tool wire
cross-check that runs both in simulation and against real captures,
and a hardware bench. The organising principle: **no check may share
its source of truth with the thing it judges.** Every suite below
either models the standard independently in C++/Python, or hands the
bytes to a tool built from a separate protocol description.

```sh
make            # all five suites + lint (exit 0 = PASS)
make tb         # suites only
make lint       # verilator --lint-only -Wall on the engine top
make ooc        # Vivado 2026.1 out-of-context measurement
```

`tb/tsngen` skips cleanly (exit 0) when no tsn-gen checkout is present;
set `TSAGEN_DIR` if it is not at `~/prjs/tsn-gen` or `~/tsn-gen`.

## The suites

### `tb/verilator/ucpu` — 768 checks

The grown arithmetic ISA against an independent C++ model: every
`OP_ALU` function and both `OP_MULDIV` functions, directed edge cases
(sign boundaries, shift counts 0/1/63/64, divide extremes) plus 64
random operand pairs per operation, dispatched through the real
dispatch handshake at ROM entry 704. Mutation-proven.

### `tb/verilator/parser` — 32 checks

802.1AS field extraction from byte-serial frames built independently
from the standard: Announce with path trace, Sync, Follow_Up with the
information TLV, Pdelay_Resp, and six drop arms (EtherType,
transportSpecific, versionPTP, **domainNumber**, truncation,
`rx_err`). Mutation-proven.
This suite caught three real field-straddle bugs and an end-of-frame
race *before* the first synthesis.

### `tb/verilator/engine` — 144 checks

The protocol round-trip: one continuous scenario that boots the
engine, runs both pdelay roles, climbs the asCapable ladder, wins and
loses elections, locks the servo, and exercises every fault arm. All
frames and expectations are built from 802.1AS-2011 in the harness,
not from the µcode's own view. Notable arms:

| phase | proves |
|---|---|
| 1 / 1b / 1c | Pdelay_Req byte-exact; asCapable rises only after a judged sub-threshold exchange; **negative-quantization clamp** on a near-zero link; **neighborRateRatio** against a rate-skewed peer (1000 ppm) |
| 2 | our two-step Pdelay_Resp + Resp_Follow_Up, timestamps and echoed requestor identity |
| 3–4 | announceReceiptTimeout → master; Announce / Sync / Follow_Up byte-exact, FU origin equals the egress stamp of *that* Sync |
| 5–6 | BTCA reject / adopt, publish words |
| 6b | **MDSyncReceive pairing**: orphan, mismatched, paired, replayed Follow_Up |
| 6c | **PortAnnounceReceive/Information**: worse other announcer ignored, better one switches, incumbent degrading → reselect, path-trace loop rejected, self-announce and stepsRemoved ≥ 255 discarded |
| 7–8 | offset arithmetic and the PI servo **bit-exact against a C++ mirror** of the µcode's own arithmetic; step beyond 1 ms; delayAsymmetry, signed both ways |
| 9 | closed loop against a modeled detuned PHC that obeys the DUT's addend/step writes, with same-GM re-announces injected |
| 10–13 | syncReceiptTimeout aging; threshold breach; multiple responders; lost responses; recovery from each |

### `tb/verilator/gaskets` — 81 checks

The bench MII gaskets — the seam the engine suites do not cover, and
where the wire TAP found a real deadlock. Loopback at the true
100 MHz/25 MHz clock ratio: size sweep 60…128 bytes byte-exact,
20 back-to-back frames with the 96-bit-time IFG measured and enforced,
FCS fault injection, and the **wedge regression** that recreates a
full-FIFO-during-IFG race. The producer has a bounded ready-wait so a
wedge fails the suite instead of hanging it.

### `tb/tsngen` — 272 checks

The independent judge. Frames the engine **transmits** are decoded by
tsn-gen's `packet_gen` against 802.1AS protocol YAMLs (upstreamed to
that project, `protocols/data_link/ptp/`), and every field the
standard pins is enforced from the YAML's own `expected` values —
a separate implementation of the bit layout. Frames it **generates**
(seeded, reproducible) are fed in as stimulus: an 8-announce BTCA
sweep and Sync+Follow_Up pairs with random 64-bit correction fields,
checked against a Python model of the same state machines. The
driver also cross-checks the YAML pin table against its own clause
table, so neither copy can drift silently.

This layer earns its keep: its pins caught the `control` field being
5 on Sync and Follow_Up where Table 10-6 requires 0 and 2 — a field
no other suite was looking at, because both the µcode and the C++
harness came from the same reading of the standard.

## Mutation record

A check that cannot fail is not a check. Every behavioural claim below
was verified by breaking the implementation and requiring the suites
to go red; all were caught.

| mutation | suite that caught it |
|---|---|
| `neighborPropDelayThresh` 800 → 80000 | engine |
| `allowedLostResponses` 3 → 30 | engine |
| `syncReceiptTimeout` 375 → 3750 ms | engine |
| servo `Kp` halved | engine |
| step threshold 1 ms → 10 ms | engine |
| multiple-responder compare off-by-one | engine |
| `syncOk` flag never set | engine |
| Sync `control` field 0 → 5 | tsngen |
| self-announce discard removed | engine |
| path-trace loop check removed | engine |
| incumbent-portPriority comparison → own vector | engine |
| `stepsRemoved ≥ 255` discard removed | engine |
| Follow_Up sequence pairing removed | engine |
| neighborRateRatio correction removed | engine (needed a rate-skewed peer arm — see below) |
| TX FIFO level truncated 7 → 6 bits | gaskets |
| `domainNumber` ≠ 0 drop removed | parser |

**One mutation initially survived** — removing the neighborRateRatio
correction changed nothing, because every modeled peer in the suite
ran at exactly our rate, making `r = 1.0` and the correction a no-op.
That was a genuine coverage hole, not a false alarm: the fix was a new
arm with a 1000 ppm rate-skewed peer, where the corrected and naive
formulas differ by 8 ns. Recorded here because the lesson generalises
— a passing mutation test can mean the *stimulus* is too clean.

## Wire verification (`bench/pcap_verdict.py`)

The same YAML pins applied to real captures. Reads pcap/pcapng
including the TAP's live-mode framing (28-byte prepend, hardware
timestamps), pushes every 0x88F7 frame through `packet_gen`, enforces
the pins on everything our MAC transmitted (peer deviations are
reported, not counted as our failure), and derives what only a TAP
timebase can show: cadences, FU-after-Sync gap, response turnaround
against Milan's 15 ms allowance, the timestamp-point latency sum, and
our PHC rate against the TAP clock.

Best result to date: **65,464 pin checks, 0 FAIL** over a 4-minute
capture (4,230 frames).

## What is not covered by simulation

Stated plainly, because these are where hardware found real bugs:

- **The bench gaskets' interaction with real PHY timing** — covered
  now by `tb/verilator/gaskets`, added *after* a TX FIFO level
  truncation deadlocked the plane on the wire.
- **Link delays near zero.** Every simulated link was 700 ns; the real
  switch link is ~5 ns, where per-exchange pdelay legitimately
  straddles zero. Found on hardware, now an engine-suite arm.
- **Peer behaviour.** A 1 Hz same-GM re-announce (which the switch
  does and the earlier simulated peers did not) was zeroing the servo
  integrator. Found on hardware, now an engine-suite arm.
- **Analogue reality**: crystal ppm, PHY latency, cable propagation.
  Handled by calibration constants derived from the PHY datasheet and
  verified with an independent TAP (`BENCH_TAP_WIRETRUTH.md`).

Every item in that list ended the same way — as a regression check in
a suite, within the hour it was found.
