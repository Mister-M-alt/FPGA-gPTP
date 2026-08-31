<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Test developer guide

This guide explains every verification layer.

## Language layers

| Layer | Files | Purpose |
|---|---|---|
| Python | `hdl/ucode/gen_gptp_ucode.py` | Generates configuration-specific ROM images |
| Python | `tb/check_phc_contract.py` | Guards the PHC source boundary |
| C | None | No first-party C harness exists |
| C++ | `tb/verilator/*/sim_main.cpp` | Drives and checks Verilated RTL |
| C++ | `bench/arty/bench_mii_tx_tag_test.cpp` | Checks timestamp-tag transport |
| Make | Repository Makefiles | Builds, runs, and cleans suites |

Verilator converts SystemVerilog into C++ models.

Handwritten C++ drives those generated models.

Python generates ROM data and structural checks.

No handwritten C harness exists.

## Test entry points

| Command | Coverage |
|---|---|
| `make contract` | PHC boundary source contract |
| `make -C tb/verilator/ucpu` | Arithmetic and microCPU behavior |
| `make -C tb/verilator/parser` | Frame parsing and refusal paths |
| `make -C tb/verilator/engine` | Whole-plane protocol behavior |
| `make -C bench/arty test` | MII timestamp-tag transport |
| `make lint` | Engine and bench lint |
| `make` | Every required local gate |

Clean runs return zero.

Each simulation prints its check tally.

## Python workflow

The generator writes hexadecimal microcode images.

Configuration inputs include these values:

- Station MAC address.
- Announced priority one.
- Engine clock frequency.
- Cease-rule duration.
- Optional regression sequence seeds.

Regression seeds exercise unreachable runtime counters quickly.

The PHC contract checks removed and surviving tokens.

It fails after stale interfaces return.

## C++ harness workflow

Each harness follows this loop:

1. Construct the Verilated top-level model.
2. Toggle the clock around `eval()` calls.
3. Apply synchronous reset.
4. Drive only public DUT inputs.
5. Sample outputs after clock edges.
6. Compare against independent expectations.
7. Count every check and failure.
8. Return nonzero after any failure.

Never mirror implementation logic blindly.

Prefer independent protocol formulas and frame builders.

## Suite responsibilities

### MicroCPU suite

- Uses an independent arithmetic model.
- Exercises directed boundaries and random vectors.
- Covers shifts, multiplication, and division.
- Writes results through the state interface.

### Parser suite

- Builds wire frames byte-by-byte.
- Checks bank writes and emitted events.
- Covers valid, malformed, truncated, and padded frames.
- Exercises error and domain refusal paths.

### Engine suite

- Models a scripted protocol peer.
- Runs shipping and seeded ROM images.
- Checks Pdelay, Announce, Sync, and servo behavior.
- Exercises reset, backpressure, ordering, and timeouts.
- Reorders and withholds timestamp returns.

### Bench-tag suite

- Exercises two independent timestamp tags.
- Checks MII completion transport.

## Adding a test

- Name the requirement or defect first.
- Choose the lowest useful test layer.
- Drive the real public interface.
- Include a positive control.
- Include negative and boundary cases.
- Prove the test fails after mutation.
- Restore production code before committing.
- Record only reproducible evidence.

## Failure triage

- Read the first failed invariant.
- Confirm the generated image matches configuration.
- Check handshake advancement carefully.
- Check reset timing and retained state.
- Check sequence and message-type tags together.
- Reproduce using one focused suite.
- Run the complete gate afterward.

Historical mutation details remain [archived](history/v1/README.md).
