<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Documentation map

Use current guides before historical records.

## Reader guides

| Perspective | Guide | Focus |
|---|---|---|
| Manager | [Manager](MANAGER.md) | Value, status, evidence, risks |
| System integrator | [Integration](INTEGRATION.md) | Interfaces, timing, ownership |
| HDL contributor | [HDL development](HDL_DEVELOPER.md) | Structure, state, changes |
| Test developer | [Test development](TEST_DEVELOPER.md) | Frameworks, suites, extensions |

## Truth order

Trust evidence using this order:

1. Current RTL and generated microcode.
2. Executable tests and assertions.
3. Current role-based guides.
4. Dated historical records.

Issues record unresolved behavior.

[Source evidence](SOURCE_EVIDENCE.md) binds claims to implementation.

## Visual documentation

- [Architecture source](diagrams/gptp_architecture.drawio)
- [Architecture PNG](diagrams/gptp_architecture.png)
- [RX timing source](diagrams/wavedrom/rx_accept.json)
- [TX timing source](diagrams/wavedrom/tx_backpressure.json)
- [Generation guide](diagrams/README.md)

PNG previews embed their editable-source SHA-256.

The manifest also pins every committed diagram asset.

## History

- [History index](history/v1/README.md)
- [Resource campaign](history/v1/RESOURCE_VALIDATION.md)
- [Bench records](history/v1/BENCH_FIRSTLIGHT.md)
- [Earlier project status](history/v1/PROJECT_STATUS.md)

Historical pages never define current behavior.

## Validation

```sh
make docs
make diagrams-check
```

Run both checks before documentation commits.
