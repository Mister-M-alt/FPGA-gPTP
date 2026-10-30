<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# FPGA-gPTP

Fabric-native time synchronization for Milan FPGA systems.

![FPGA-gPTP architecture](docs/diagrams/gptp_architecture.png)

The engine keeps protocol work inside programmable logic.

## Start here

FPGA-gPTP is an IEEE 802.1AS-2011 time-synchronization engine.

It follows the Milan v1.2 chapter 4 profile.

That profile adds 802.1AS-2011 Cor1 and Cor2.

The parent end station instantiates it as `KL_gptp_engine`.

Read in this order:

1. This page, for scope and layout.
2. The [glossary](docs/GLOSSARY.md), for defined terms.
3. The guide for your role, below.
4. The [source evidence](docs/SOURCE_EVIDENCE.md), to check claims.
5. The [document status](docs/README.md#document-status) table.

## Repository layout

| Path | Contents |
|---|---|
| `hdl/` | Engine RTL and the microcode generator |
| `tb/` | Simulation suites, mutation arms, contract check |
| `bench/` | Bench-only board top, MII gaskets, capture verdict |
| `syn/ooc/` | Out-of-context synthesis scripts and clock check |
| `scripts/` | Documentation and diagram gates |
| `docs/` | Guides, glossary, evidence, diagrams, history |

## Choose your view

| Reader | Start here | Main questions |
|---|---|---|
| Manager | [Manager guide](docs/MANAGER.md) | Value, readiness, evidence, risks |
| System integrator | [Integration guide](docs/INTEGRATION.md) | Ports, clocks, resets, ownership |
| HDL contributor | [HDL developer guide](docs/HDL_DEVELOPER.md) | Modules, state, timing, invariants |
| Test developer | [Test developer guide](docs/TEST_DEVELOPER.md) | Python, C, C++, suites, failures |

## Current shape

- Parent `GPTP_PLANE_EN_P` [defaults on](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L73).
- [Fabric gPTP](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L6) owns product time synchronization.
- The disabled mode supports [verification-only comparison builds only](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L49).
- One synchronous clock domain carries all processing.
- RX consumes validated, preclassified gPTP frames.
- TX honors downstream byte-level backpressure.
- Microcode owns protocol decisions and servo arithmetic.
- RTL owns parsing, queues, timers, and serialization.
- Egress timestamp results arrive on accepted beats.
- Admission credit postpones only initiating transmissions.
- Publication outputs expose committed protocol state.

Parent evidence is pinned at `ac2c5e77`.

The [integration guide](docs/INTEGRATION.md#option-off-behavior) details option-off behavior.

## Verify quickly

```sh
make
make docs
make diagrams-check
```

Each command returns nonzero after failures.

Detailed commands appear in the [test guide](docs/TEST_DEVELOPER.md).

## Known risks

- [Issue #58](https://github.com/Mister-M-alt/FPGA-gPTP/issues/58) remains open: asymmetry, calibration, and live tuning.
- [Parent #117](https://github.com/kebag-logic/milan-fpga/issues/117) still owes physical acceptance against the reference peer.
- [Parent #64](https://github.com/kebag-logic/milan-fpga/issues/64) and [#488](https://github.com/kebag-logic/milan-fpga/issues/488) still owe physical timestamp calibration.

The [manager guide](docs/MANAGER.md#open-risks) separates donor and product gaps.

No certification claim is made.

## Documentation

- [Documentation map](docs/README.md)
- [Source evidence](docs/SOURCE_EVIDENCE.md)
- [Architecture diagram source](docs/diagrams/gptp_architecture.drawio)
- [Diagram generation](docs/diagrams/README.md)
- [Historical records](docs/history/v1/README.md)

Current guides describe the present implementation.

Historical pages preserve dated engineering evidence.
