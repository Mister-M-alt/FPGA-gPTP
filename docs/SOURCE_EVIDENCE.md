<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Source evidence

This ledger binds guide claims to executable sources.

Line numbers describe the current branch layout.

| Claim | Source evidence | Executable evidence |
|---|---|---|
| Single clock domain | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L54) | `make lint` |
| Four instantiated blocks | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L139) | `make lint` |
| Deferred receive event | [`KL_gptp_rx_parser`](../hdl/wire/KL_gptp_rx_parser.sv#L373) | Parser suite |
| Four-entry event queue | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L358) | Engine suite |
| Parser arbitration priority | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L386) | Engine suite |
| Priority timestamp return | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L373) | Engine suite |
| Eight timer slots | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L340) | Engine suite |
| Six state regions | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L20) | Engine suite |
| Stable stalled transmission | [`KL_gptp_tx_slot`](../hdl/wire/KL_gptp_tx_slot.sv#L117) | Engine suite |
| Committed publication | [`KL_gptp_engine`](../hdl/top/KL_gptp_engine.sv#L103) | Engine suite |
| 1,024-word microcode ROM | [`KL_gptp_ucpu`](../hdl/ucpu/KL_gptp_ucpu.sv#L105) | MicroCPU suite |
| Sixteen registers | [`KL_gptp_ucpu`](../hdl/ucpu/KL_gptp_ucpu.sv#L113) | MicroCPU suite |
| Python image generation | [`gen_gptp_ucode.py`](../hdl/ucode/gen_gptp_ucode.py) | Engine suite |
| C++ test harnesses | [`tb/verilator`](../tb/verilator) | `make` |
| PHC boundary contract | [`check_phc_contract.py`](../tb/check_phc_contract.py) | `make contract` |
| Parent default enabled | [Pinned parent source](https://github.com/kebag-logic/milan-fpga/blob/3178b13638d11d67376a24ca52ee1332cbe23ad3/hdl/milan/milan_datapath.sv#L89) | Parent integration gates |

Open issues qualify unresolved claims.

- [Issue #31](https://github.com/Mister-M-alt/FPGA-gPTP/issues/31) qualifies timestamp return capacity.
- [Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) qualifies receive error handling.
