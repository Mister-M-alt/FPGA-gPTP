<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# System integration guide

This guide defines the external engine contract.

![FPGA-gPTP architecture](diagrams/gptp_architecture.png)

## Parent ownership

Parent integration enables `GPTP_PLANE_EN_P` by default.

The disabled mode supports comparison builds only.

This repository contains no nested submodules.

[Pinned parent source](https://github.com/kebag-logic/milan-fpga/blob/3178b13638d11d67376a24ca52ee1332cbe23ad3/hdl/milan/milan_datapath.sv#L89) records that default.

Parent integration owns these surrounding services:

- Frame classification and receive buffering.
- Frame-check validation before engine delivery.
- MAC-boundary egress timestamp capture.
- PHC implementation and adjustment application.
- Publication capture after commit.
- Per-configuration microcode generation.

## Clock and reset

- `clk_i` clocks every functional engine block.
- `rst_n` is synchronous and active-low.
- Reset clears queues, timers, and pending events.
- Scratch memory preserves warm-reset protocol state.
- Reset invalidates outstanding timestamp claims.
- Bootstrap microcode rearms required cadences.

Keep every input synchronous to `clk_i`.

## Receive interface

| Signal | Direction | Contract |
|---|---|---|
| `rx_valid_i` | Input | Qualifies each presented byte |
| `rx_data_i[7:0]` | Input | Carries destination-MAC-first bytes |
| `rx_sof_i` | Input | Marks the first byte |
| `rx_eof_i` | Input | Marks the final byte |
| `rx_err_i` | Input | Qualifies terminal frame failure |
| `rx_ts_i[63:0]` | Input | Stable during the SOF transfer |

Parent sends preclassified `0x88F7` frames.

Parent removes frames failing frame checks.

No receive-ready signal exists.

The engine never backpressures receive traffic.

`rx_valid_i` may insert gaps between bytes.

Assert receive errors with the final byte.

Current parent integration drives `rx_err_i` low.

[Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) tracks mid-frame error handling.

## Transmit interface

| Signal | Direction | Contract |
|---|---|---|
| `tx_valid_o` | Output | Qualifies every output byte |
| `tx_data_o[7:0]` | Output | Carries destination-MAC-first bytes |
| `tx_sof_o` | Output | Marks the first transfer |
| `tx_eof_o` | Output | Marks the final transfer |
| `tx_ready_i` | Input | Accepts the current byte |

A transfer needs both valid and ready.

Outputs remain stable while ready stays low.

The serializer blocks new event dispatches.

## Egress timestamps

| Signal | Meaning |
|---|---|
| `txts_valid_i` | Qualifies one returned timestamp |
| `txts_ns_i[63:0]` | Carries boundary time |
| `txts_seq_i[15:0]` | Carries PTP sequence identifier |
| `txts_type_i[3:0]` | Carries PTP message type |

Return tags must match transmitted headers.

One pending timestamp register currently exists.

[Issue #31](https://github.com/Mister-M-alt/FPGA-gPTP/issues/31) tracks overwrite exposure.

## PHC control

| Output | Meaning |
|---|---|
| `phc_addend_we_o` | Applies one rate update |
| `phc_addend_o[31:0]` | Carries unsigned rate addend |
| `phc_step_we_o` | Applies one phase step |
| `phc_step_o[63:0]` | Carries signed phase adjustment bits |

Treat each write-enable as a pulse.

Apply its data during that cycle.

## Publication

The engine publishes protocol state as wires.

Sample outputs when `pub_commit_o` rises.

| Output group | Contents |
|---|---|
| Identity | Grandmaster and parent identities |
| Status | Presence, mastership, capability, synchronization |
| Measurements | Peer delay and signed offset |
| Announce | Raw selected priority vector |
| Path | Count plus seven retained tail identities |

Zero path count means no received PathTrace.

Counts include the separately published grandmaster.

Retained paths contain at most eight identities.

Inactive path entries remain zero.

## Microcode configuration

Generate one image for each hardware configuration.

```sh
python3 hdl/ucode/gen_gptp_ucode.py \
  --mac 02:a1:b2:c3:d4:e5 \
  --p1 248 \
  --clk-hz 100000000 \
  -o /tmp/gptp_ucode.hex
```

Set `UCODE_HEX_P` to that generated image.

Set `CLK_HZ_P` to the actual engine frequency.

## Integration checklist

- Use one shared synchronous clock.
- Deliver complete validated frames.
- Preserve byte order and frame markers.
- Hold transmit readiness correctly.
- Return exact timestamp tags.
- Apply PHC pulses once.
- Capture publication only on commit.
- Review both open interface risks.
- Run every repository gate.
