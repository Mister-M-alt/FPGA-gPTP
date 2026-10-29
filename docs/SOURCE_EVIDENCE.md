<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Source evidence

This ledger binds guide claims to executable sources.

Line numbers describe the current branch layout.

| Claim | Source evidence | Executable evidence |
|---|---|---|
| Single clock domain | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L64) | `make lint` |
| Four instantiated blocks | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L209) | `make lint` |
| Any-byte receive refusal | [`KL_gptp_rx_parser`](../hdl/wire/KL_gptp_rx_parser.sv) | Parser suite and named mutation controls |
| Deferred receive event | [`KL_gptp_rx_parser`](../hdl/wire/KL_gptp_rx_parser.sv#L392) | Parser suite |
| Four-entry event queue | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L467) | Engine suite |
| Parser arbitration priority | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L494) | Engine suite |
| Priority timestamp return | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L405) | Engine suite |
| Accepted-beat result face | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L411) | Engine suite |
| Explicit lost result | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Retained Pdelay pairing context | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Reset-backed pairing validity | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L291) | Engine suite |
| Transmit admission credit | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L106) | Engine suite |
| Eight timer slots | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L447) | Engine suite |
| Six state regions | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L20) | Engine suite |
| Stable stalled transmission | [`KL_gptp_tx_slot`](../hdl/wire/KL_gptp_tx_slot.sv#L129) | Engine suite |
| Committed publication | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L140) | Engine suite |
| 1,024-word microcode ROM | [`KL_gptp_ucpu`](../hdl/ucpu/KL_gptp_ucpu.sv#L105) | MicroCPU suite |
| Sixteen registers | [`KL_gptp_ucpu`](../hdl/ucpu/KL_gptp_ucpu.sv#L113) | MicroCPU suite |
| Python image generation | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Media-dependent transmit flags | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine and tsngen suites |
| Step-versus-slew policy | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Registered policy slew level | [Port](../hdl/top/KL_gptp_engine.sv#L123), [word 2](../hdl/top/KL_gptp_engine.sv#L1071), [word 3](../hdl/top/KL_gptp_engine.sv#L1076), [policy](../hdl/ucode/gen_gptp_ucode.py#L1026) | Engine suite and named mutation controls |
| PHC rate envelope | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Ignored receive flag bits | [`KL_gptp_rx_parser`](../hdl/wire/KL_gptp_rx_parser.sv#L472) | Engine suite |
| C++ test harnesses | [`tb/verilator`](../tb/verilator) | `make` |
| PHC and result face contract | [`check_phc_contract.py`](../tb/check_phc_contract.py) | `make contract` |
| Load-bearing engine checks | [`mutants.py`](../tb/verilator/engine/mutants.py) | Engine suite |
| Sync receipt timeout ages the port | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Aged port holds mastership until Sync | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Sync ageing needs gmPresent | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Unaged Sync timeout clears sync-ok | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Mastership keeps both Sync watches | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Fifth lost response clears asCapable | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Duplicate response resets the exchange | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Port enable ends the cease | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| Disabled port sends nothing | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv) | Engine suite and named mutation controls |
| Disabled port withdraws an unstarted frame | [`KL_gptp_tx_slot`](../hdl/wire/KL_gptp_tx_slot.sv) | Engine suite and named mutation controls |
| NOT_ENABLED dispatches first | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv) | Engine suite and named mutation controls |
| NOT_ENABLED completes no exchange | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite and named mutation controls |
| First sample is the port reference | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv) | Engine suite and named mutation controls |
| Parent default enabled | [Pinned parent parameter](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L73) | Parent integration gates |
| Fabric owns product time | [Pinned parent contract](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L6) | Parent integration gates |
| Option-off verifies comparisons only | [Pinned parent boundary](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/ARCHITECTURE_HW_SW_SPLIT.md#L165-L175) | Parent integration gates |

These parent ownership citations resolve at `ac2c5e77`.

Closed work still binds its interface.

- [Issue #31](https://github.com/Mister-M-alt/FPGA-gPTP/issues/31) defines the result face above.
- [Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) defines the receive refusal above.
