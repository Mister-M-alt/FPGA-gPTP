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
- Reset invalidates retained Pdelay pairing state.
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

## Egress timestamp results

| Signal | Direction | Contract |
|---|---|---|
| `txts_valid_i` | Input | Offers one complete result |
| `txts_ready_o` | Output | Accepts the offered result |
| `txts_ns_i[63:0]` | Input | Carries boundary time |
| `txts_seq_i[15:0]` | Input | Carries PTP sequence identifier |
| `txts_type_i[3:0]` | Input | Carries PTP message type |
| `txts_ok_i` | Input | Marks a measured result |
| `txts_gen_i[3:0]` | Input | Carries the producer generation |

A transfer needs both valid and ready.

Hold every offered field stable until acceptance.

Never replace an unaccepted offer.

Ready stays low throughout reset.

Ready stays low until dispatch consumes the result.

Return tags must match transmitted headers.

Provide bounded result storage upstream of this interface.

This interface never assumes elapsed time supplies space.

### Lost results

A cleared `txts_ok_i` reports an explicitly lost result.

Such a result carries no usable time.

It retires only the claim its tag names.

It builds no timestamped Follow_Up companion.

A lost request result cancels that request's pairing.

A lost Sync result leaves that pairing untouched.

A lost response result leaves that pairing untouched.

Current microcode reads no generation field.

## Transmit admission credit

| Signal | Direction | Contract |
|---|---|---|
| `tx_credit_i` | Input | Permits initiating transmissions |

Drive credit as a level, never a pulse.

Low credit postpones three initiating beats.

Those beats are Pdelay_Req, Sync and Announce.

Each postponed beat retries at its next cadence.

Responses and both companions always keep service.

Low credit also postpones request interval bookkeeping.

Restore credit to resume every normal cadence.

## PHC control

| Output | Meaning |
|---|---|
| `phc_addend_we_o` | Applies one rate update |
| `phc_addend_o[31:0]` | Carries signed Q8.24 ns-per-tick rate trim |
| `phc_step_we_o` | Applies one phase step |
| `phc_step_o[63:0]` | Carries signed phase adjustment nanoseconds |

Treat each write-enable as a pulse.

Apply its data during that cycle.

### Pulse semantics

Each write-enable stays high for exactly one `clk_i` cycle.

Only a consumed slave Sync and Follow_Up pair writes.

Each consumed pair writes exactly one addend pulse.

At most one step pulse precedes that addend pulse.

Add `phc_step_o` to PHC time on its pulse.

A step carries the measured offset, negated.

Its addend then carries the retained rate estimate alone.

Each addend pulse replaces the previous rate trim.

The addend is signed; a negative trim slows the PHC.

Both data outputs hold their values between pulses.

Reset zeroes both data outputs.

Each step pulse is exactly one phase step.

Count step pulses to count phase steps.

### Step versus slew policy

[Issue #68](https://github.com/Mister-M-alt/FPGA-gPTP/issues/68) records this policy.

The offset is local time minus grandmaster time.

| Servo state | Slews up to | Steps above |
|---|---|---|
| Link-up | 20 us | 20 us |
| Locked | 100 us | 100 us |

An offset of exactly the threshold slews.

Every other pair slews through the rate path.

#### Link-up

A link-up pair is the first pair consumed after:

- asCapable rising, including after any reset.
- A 375 ms Sync receipt timeout.
- This plane becoming grandmaster.

Losing asCapable stops Sync consumption.

The receipt timeout follows before asCapable can return.

So the first pair after asCapable is a link-up.

#### Locked

Every consumed pair locks the servo.

A grandmaster identity change clears the synchronization verdict.

It leaves the servo locked.

So the next pair uses the 100 us threshold.

A new parent under the same grandmaster changes nothing.

#### Rate envelope

The trim sums a proportional and an integral term.

That whole trim never exceeds 200 ppm in magnitude.

The integrator is clamped to the same bound.

In addend units the bound is this integer expression:

```text
(200 * 2^24 * 1000 + clk_hz / 2) / clk_hz
```

Here `clk_hz` is the generator's `--clk-hz` value.

The division truncates, so the bound rounds half up.

Derive a consumer's addend envelope from this expression.

That consumer then accepts every trim the plane writes.

When consumption stops, the last trim stays applied.

That held trim is inside the bound too.

A 100 us slew needs at least 0.5 s.

#### Publication during a slew

`pub_flags_o` bit 3 publishes the synchronization verdict.

Every consumed pair raises it, stepping or slewing.

So a slew may still be in progress.

Its remaining offset is at most 100 us.

`pub_offset_o` carries each pair's offset before correction.

It holds only the low 32 bits.

Offsets beyond about 2.147 s therefore wrap.

Such a pair always steps.

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
- Hold result offers until acceptance.
- Report unmeasured results explicitly.
- Drive admission credit as a level.
- Apply PHC pulses once.
- Count each step pulse as one step.
- Derive addend envelopes from the generator clock.
- Capture publication only on commit.
- Review the open interface risk.
- Run every repository gate.
