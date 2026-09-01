<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# FPGA-gPTP

Fabric-native time synchronization for Milan FPGA systems.

![FPGA-gPTP architecture](docs/diagrams/gptp_architecture.png)

The engine keeps protocol work inside programmable logic.

## Choose your view

| Reader | Start here | Main questions |
|---|---|---|
| Manager | [Manager guide](docs/MANAGER.md) | Value, readiness, evidence, risks |
| System integrator | [Integration guide](docs/INTEGRATION.md) | Ports, clocks, resets, ownership |
| HDL contributor | [HDL developer guide](docs/HDL_DEVELOPER.md) | Modules, state, timing, invariants |
| Test developer | [Test developer guide](docs/TEST_DEVELOPER.md) | Python, C, C++, suites, failures |

## Current shape

- Parent integration enables this plane by default.
- The disabled mode supports comparison builds only.
- One synchronous clock domain carries all processing.
- RX consumes validated, preclassified gPTP frames.
- TX honors downstream byte-level backpressure.
- Microcode owns protocol decisions and servo arithmetic.
- RTL owns parsing, queues, timers, and serialization.
- Publication outputs expose committed protocol state.

## Verify quickly

```sh
make
make docs
make diagrams-check
```

Each command returns nonzero after failures.

Detailed commands appear in the [test guide](docs/TEST_DEVELOPER.md).

## Known risks

- [Issue #31](https://github.com/Mister-M-alt/FPGA-gPTP/issues/31) tracks timestamp overwrite exposure.
- [Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) tracks mid-frame error handling.

No certification claim is made.

## Documentation

- [Documentation map](docs/README.md)
- [Source evidence](docs/SOURCE_EVIDENCE.md)
- [Architecture diagram source](docs/diagrams/gptp_architecture.drawio)
- [Diagram generation](docs/diagrams/README.md)
- [Historical records](docs/history/v1/README.md)

Current guides describe the present implementation.

Historical pages preserve dated engineering evidence.
