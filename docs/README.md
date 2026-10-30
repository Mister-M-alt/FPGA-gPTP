<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Documentation map

Use current guides before historical records.

New readers start at the [repository README](../README.md#start-here).

The [glossary](GLOSSARY.md) defines every recurring term.

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

## Document status

Every Markdown page outside the archive has one row.

`make docs` rules are `scripts/check_docs.py`; its [`selftest()`](../scripts/check_docs.py) cases are the specification.

Current means checked against the source and clauses.

Historical pages carry their own archive banners.

| Page | Audience | Describes | Status |
|---|---|---|---|
| `README.md` | Every reader | Start here: scope, layout, reading order | Current |
| `docs/README.md` | Every reader | Documentation map and document status | Current |
| `docs/GLOSSARY.md` | Every reader | Defined terms and their clauses | Current |
| `docs/MANAGER.md` | Manager | Readiness, ROM budget, open risks | Current |
| `docs/INTEGRATION.md` | System integrator | Engine ports, policy, protocol constants | Current |
| `docs/HDL_DEVELOPER.md` | HDL contributor | `hdl/` modules, state regions, synthesis figures | Current |
| `docs/TEST_DEVELOPER.md` | Test developer | `tb/` and `bench/` suites, gates, mutation arms | Current |
| `docs/SOURCE_EVIDENCE.md` | Reviewer | Claims bound to source line anchors | Current |
| `docs/diagrams/README.md` | Maintainer | Diagram sources, rendering and checks | Current |
| `tb/verilator/engine/README.md` | Test developer | Engine suite entry point | Current |
| `tb/verilator/parser/README.md` | Test developer | Parser suite entry point | Current |
| `tb/verilator/ucpu/README.md` | Test developer | MicroCPU suite entry point | Current |
| `tb/verilator/gaskets/README.md` | Test developer | Bench gasket suite entry point | Current |
| `tb/tsngen/README.md` | Test developer | Independent decode suite entry point | Current |
| `docs/history/v1/` | Maintainer | Dated campaigns, listed in the history index | Historical |

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
