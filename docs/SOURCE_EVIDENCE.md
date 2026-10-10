<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Source evidence

This ledger binds guide claims to executable sources.

Line numbers describe the current branch layout.

| Claim | Source evidence | Executable evidence |
|---|---|---|
| Single clock domain | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L58) | `make lint` |
| Four instantiated blocks | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L160) | `make lint` |
| Deferred receive event | [`KL_gptp_rx_parser`](../hdl/wire/KL_gptp_rx_parser.sv#L374) | Parser suite |
| Four-entry event queue | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L405) | Engine suite |
| Parser arbitration priority | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L432) | Engine suite |
| Priority timestamp return | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L343) | Engine suite |
| Accepted-beat result face | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L349) | Engine suite |
| Explicit lost result | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Retained Pdelay pairing context | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Reset-backed pairing validity | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L240) | Engine suite |
| Transmit admission credit | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L100) | Engine suite |
| Eight timer slots | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L385) | Engine suite |
| Six state regions | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L20) | Engine suite |
| Stable stalled transmission | [`KL_gptp_tx_slot`](../hdl/wire/KL_gptp_tx_slot.sv#L117) | Engine suite |
| Committed publication | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L124) | Engine suite |
| 1,024-word microcode ROM | [`KL_gptp_ucpu`](../hdl/ucpu/KL_gptp_ucpu.sv#L105) | MicroCPU suite |
| Sixteen registers | [`KL_gptp_ucpu`](../hdl/ucpu/KL_gptp_ucpu.sv#L113) | MicroCPU suite |
| Python image generation | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Media-dependent transmit flags | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine and tsngen suites |
| Step-versus-slew policy | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Registered policy slew level | [Port](../hdl/top/KL_gptp_engine.sv#L109), [word 2](../hdl/top/KL_gptp_engine.sv#L929), [word 3](../hdl/top/KL_gptp_engine.sv#L934), [policy](../hdl/ucode/gen_gptp_ucode.py#L837) | Engine suite and named mutation controls |
| PHC rate envelope | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| Ignored receive flag bits | [`KL_gptp_rx_parser`](../hdl/wire/KL_gptp_rx_parser.sv#L456) | Engine suite |
| C++ test harnesses | [`tb/verilator`](../tb/verilator) | `make` |
| PHC and result face contract | [`check_phc_contract.py`](../tb/check_phc_contract.py) | `make contract` |
| Load-bearing engine checks | [`mutants.py`](../tb/verilator/engine/mutants.py) | Engine suite |
| Parent default enabled | [Pinned parent source](https://github.com/kebag-logic/milan-fpga/blob/3178b13638d11d67376a24ca52ee1332cbe23ad3/hdl/milan/milan_datapath.sv#L89) | Parent integration gates |

Open issues qualify unresolved claims.

- [Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) qualifies receive error handling.

Closed work still binds its interface.

- [Issue #31](https://github.com/Mister-M-alt/FPGA-gPTP/issues/31) defines the result face above.
