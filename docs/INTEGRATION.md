<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# System integration guide

This guide defines the external engine contract.

## Summary

- One clock, one synchronous active-low reset.
- Receive takes validated gPTP bytes; it never backpressures.
- Transmit honors byte-level ready; started frames always finish.
- Egress timestamps return on a valid-ready result face.
- `tx_credit_i` gates initiating transmissions.
- A low `port_enabled_i` starts no frame.
- PHC step and rate writes are one-cycle pulses.
- `phc_slew_active_o` is a level.
- Sample publication outputs on `pub_commit_o`; they change while staging.
- [Protocol constants](#protocol-constants) is the home of protocol values.

Terms are defined in the [glossary](GLOSSARY.md).

![FPGA-gPTP architecture](diagrams/gptp_architecture.png)

## Parent ownership

Parent integration enables [`GPTP_PLANE_EN_P` by default](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L73).

[Fabric gPTP](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L6) owns product time synchronization.

[One atomic bank](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L48) supplies every public consumer.

The disabled mode supports [verification-only comparison builds only](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L49).

Product configurations [cannot disable the plane](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/design/GPTP_PLANE.md#L43-L44).

These references pin parent `dev` at `ac2c5e77`.

This repository contains no nested submodules.

Parent integration owns these surrounding services:

- Frame classification and receive buffering.
- Frame-check validation before engine delivery.
- MAC-boundary egress timestamp capture.
- PHC implementation and adjustment application.
- Publication capture after commit.
- Per-configuration microcode generation.

### Option-off behavior

`GPTP_PLANE_EN_P=0` has [no supported product image](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/docs/ARCHITECTURE_HW_SW_SPLIT.md#L165).

This verification path has [zero runtime gPTP owners](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/README.md#L167-L170).

| Surface | Option-off behavior | Parent evidence |
|---|---|---|
| Control TX | Passes straight through | [Datapath bypass](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L7614-L7624) |
| PHC rate and phase controls | Select the CSR face | [PHC selection](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L2850-L2858) |
| PHC settime | Remains on the CSR face | [Epoch control](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/hdl/milan/milan_datapath.sv#L2850-L2852) |
| GM, parent, PathTrace, peer delay | Zero | [Safe publications](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/README.md#L167-L170) |
| Sync and asCapable | Zero | [Safe health](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/README.md#L167-L170) |
| AVTP `tu` | One | [Uncertain time](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/README.md#L167-L170) |
| Publication writes | Inert; cannot manufacture live state | [Write behavior](https://github.com/kebag-logic/milan-fpga/blob/ac2c5e77bba1c0ae20ce2f69f711a1d17ead94a5/README.md#L167-L170) |

Review the [remaining acceptance gaps](MANAGER.md#open-risks) before product adoption.

## Clock and reset

- `clk_i` clocks every functional engine block.
- `rst_n` is synchronous and active-low.
- Reset clears queues, timers, and pending events.
- Scratch memory preserves warm-reset protocol state.
- Reset invalidates outstanding timestamp claims.
- Reset invalidates retained Pdelay pairing state.
- Reset invalidates the retained best-vector record.
- Reset loads and commits the self publication.
- Bootstrap microcode rearms required cadences.

Keep every input synchronous to `clk_i`.

## Receive interface

| Signal | Direction | Contract |
|---|---|---|
| `rx_valid_i` | Input | Qualifies each presented byte |
| `rx_data_i[7:0]` | Input | Carries destination-MAC-first bytes |
| `rx_sof_i` | Input | Marks the first byte |
| `rx_eof_i` | Input | Marks the final byte |
| `rx_err_i` | Input | Refuses the frame from any byte |
| `rx_ts_i[63:0]` | Input | Stable during the SOF transfer |

Parent sends preclassified `0x88F7` frames.

Parent removes frames failing frame checks.

No receive-ready signal exists.

The engine never backpressures receive traffic.

`rx_valid_i` may insert gaps between bytes.

Assert receive errors with any byte of the frame.

Each refused frame counts exactly one drop.

A refused frame raises no event.

No bank write follows the flagged byte's own edge.

Words written up to that edge are undefined.

No event references a refused frame's words.

The next accepted event reads only its own frame.

Pulsed and held errors refuse alike.

Errors raised between valid bytes are ignored.

Current parent integration drives `rx_err_i` low.

[Issue #35](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35) records this any-byte contract.

[Its bank ruling](https://github.com/Mister-M-alt/FPGA-gPTP/issues/35#issuecomment-6105869522) sets the write boundary.

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

One exception serves a disabled port.

A frame still waiting at its first byte is withdrawn.

Its valid falls with no transfer.

A started frame always runs to its last byte.

The face has no abort signal.

Consume accepted transfers only, never a held valid.

The serializer blocks new event dispatches.

The NOT_ENABLED leg alone skips that wait.

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

## Port enable

Values here come from the [protocol constants](#protocol-constants).

| Signal | Direction | Contract |
|---|---|---|
| `port_enabled_i` | Input | Carries 802.1AS-2011 portEnabled (10.2.4.11) |

Drive it as a level synchronous to `clk_i`.

High means MAC_Operational and administrative enable together.

The parent drives its effective link here.

A low port starts no gPTP frame.

Initiating beats see no credit while it stays low.

Every frame still waiting at its first byte is withdrawn.

That includes a frame whose SEND came while low.

A frame already started completes, as the transmit interface states.

Both egress claims read empty while low.

Received frames still dispatch; their replies are dropped.

No Pdelay exchange completes while the port is low.

The first sample after reset is the reference level.

A port high at release raises nothing.

The boot cadence then sends the first request.

A port low at release makes its rise an edge.

Each edge clears asCapable and commits at once.

A stalled transmit path does not delay that commit.

It also ends the multiple-responder cease and its countdown.

That holds for a cease retained across a warm reset.

Milan 4.2.6.2.5 lists this toggle.

Each edge also disarms the outstanding Pdelay exchange.

Its Follow_Up and its late t1 pair nothing.

A rise then sends one Pdelay_Req at once.

That request counts no lost response.

asCapable returns only after [`ASCAP_UP_C`](#protocol-constants) good exchanges.

The [`CEASE_MS_C`](#protocol-constants) countdown remains the other exit.

A change made while reset is held is not seen.

[Issue #94](https://github.com/Mister-M-alt/FPGA-gPTP/issues/94) records this contract.

## PHC control

| Output | Meaning |
|---|---|
| `phc_addend_we_o` | Applies one rate update |
| `phc_addend_o[31:0]` | Carries signed Q8.24 ns-per-tick rate trim |
| `phc_step_we_o` | Applies one phase step |
| `phc_step_o[63:0]` | Carries signed phase adjustment nanoseconds |
| `phc_slew_active_o` | Registered level covering transient policy correction |

Treat each write-enable as a pulse.

Apply its data during that cycle.

### Pulse semantics

Each write-enable stays high for exactly one `clk_i` cycle.

Consumed slave Sync and Follow_Up pairs write corrections.

Mastership also retires any active slave correction.

That transition writes the integral-only rate, without stepping.

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

### Peer delay across a phase step

A servo step invalidates the crossing rate-estimation history.
It retains the last valid ratio and link delay.
The next clean exchange seeds a new rate window.
A complete overlapping exchange still proves peer liveness.
Its mixed-epoch timestamps cannot replace the retained delay.
Ordinary missing-response and multiple-responder accounting remains active.
The next request resumes measurement normally.

These references are from IEEE 802.1AS-2011 with Cor1.

| Clause | Responsibility |
|---|---|
| 11.2.2 | Capability through peer delay |
| 11.2.15.2.3 | Neighbour rate estimation |
| 11.2.15.2.4 | Link-delay calculation |
| 11.2.16 | Responder timestamp pair |

Parent issue #621 exercises both signed 10 ms steps.
Its real-counter regression uses an independent peer LocalClock.
The parent integration test checks media and public counters.

Count step pulses to count phase steps.

### Step versus slew policy

Values here come from the [protocol constants](#protocol-constants).

[Issue #68](https://github.com/Mister-M-alt/FPGA-gPTP/issues/68) records this policy.

[The owner's decision](https://github.com/Mister-M-alt/FPGA-gPTP/issues/68#issuecomment-5794731372) sets both thresholds.

[The manager's ruling](https://github.com/Mister-M-alt/FPGA-gPTP/issues/68#issuecomment-5798089412) defines link-up.

The offset is local time minus grandmaster time.

| Servo state | Step threshold |
|---|---|
| Link-up | [`STEP_LINKUP_NS_C`](#protocol-constants) |
| Locked | [`STEP_LOCKED_NS_C`](#protocol-constants) |

Offsets up to the threshold slew; larger offsets step.

An offset of exactly the threshold slews.

Every other pair runs the PI rate path.

This includes ordinary tracking and transient offset correction.

#### Link-up

A link-up pair is the first after asCapable rises.

Every reset clears asCapable, so every reset re-arms link-up.

Nothing else re-arms the link-up threshold.

#### Locked

Every consumed pair locks the servo.

Only an asCapable fall and rise unlocks it.

These events clear the synchronization verdict and keep the lock:

- A grandmaster identity change.
- This plane returning from grandmaster duty.

A [`SYNC_RTO_MS_C`](#protocol-constants) Sync receipt timeout ages the grandmaster instead.

This plane then becomes grandmaster, which sets the verdict.

A priority1 255 grandmaster is not aged.

Its timeout clears the verdict instead.

Becoming grandmaster keeps the lock.

A grandmaster failover through a Sync lapse stays locked.

So the next pair uses the locked threshold.

A new parent under the same grandmaster changes nothing.

#### Rate envelope

The trim sums a proportional and an integral term.

That whole trim never exceeds [`RATE_PPM_C`](#protocol-constants) in magnitude.

The integrator is clamped to the same bound.

In addend units the bound is this integer expression:

```text
(RATE_PPM_C * 2^24 * 1000 + clk_hz / 2) / clk_hz
```

Here `clk_hz` is the generator's `--clk-hz` value.

`RATE_PPM_C` is the rate bound, in ppm.

The division truncates, so the bound rounds half up.

Derive a consumer's addend envelope from this expression.

That consumer then accepts every trim the plane writes.

When consumption stops, the last trim stays applied.

That held trim is inside the bound too.

A locked-threshold slew needs at least `STEP_LOCKED_NS_C / RATE_PPM_C` ms.

The master's own rate offset shares that bound.

So a real slew can take much longer.

A slew can overshoot while its trim rides the bound.

A master further apart than the bound outruns the trim.

Its offset then grows past the locked threshold and steps.

#### Slew-active level

[Issue #75](https://github.com/Mister-M-alt/FPGA-gPTP/issues/75) defines the consumer indication.

`phc_slew_active_o` is a registered, `clk_i`-synchronous level.

It marks transient offset correction through the rate path.

The policy distinguishes correction from ordinary frequency tracking.

Its inclusive tracking band is ±[`SLEW_SETTLED_NS_C`](#protocol-constants) around zero.

This tolerance does not change either step threshold.

The existing PI arithmetic and rate clamp remain unchanged.

| Consumed pair | Policy decision |
|---|---|
| Offset exceeds the applicable step threshold | Step; no new slew |
| Non-stepping offset outside the tracking band | Start or continue correction |
| First consecutive pair inside the band | Keep an existing correction active |
| Second consecutive pair inside the band | Complete the correction |
| Tracking inside the band without an active correction | Stay inactive |

Every outside-band pair restarts the two-pair completion qualification.

One zero crossing therefore cannot complete a correction.

The decision precedes the affected addend write.

The level rises when microcode publishes that decision.

It stays high throughout the interval between consumed pairs.

Completion clears it alongside that pair's replacement addend pulse.

Ordinary PI tracking continues, including nonzero frequency trims.

A step alone never raises this level.

Neither the synchronization flag nor addend magnitude determines it.

| Event | Level and correction behavior |
|---|---|
| Synchronous reset | Clear level and qualification immediately |
| Warm reset | Retained scratch cannot revive the level |
| asCapable loss | Hold level and applied rate; restart completion qualification |
| Missing Sync; [`SYNC_RTO_MS_C`](#protocol-constants) receipt timeout | Ages the grandmaster; becoming grandmaster applies |
| The same timeout under priority1 255 | Hold level and rate; clear the verdict |
| Missing Follow_Up; [`FU_RTO_MS_C`](#protocol-constants) timeout | Discard pending pair; retain level and rate |
| Grandmaster identity change | Hold level and rate; restart qualification |
| Replacement step | Hold through step; clear with its integral-only addend |
| Becoming grandmaster | Replace active correction with integral-only rate; clear together |
| Returning to slave duty | Next consumed pair makes the policy decision |

Reset the consumer's retained rate when resetting the engine.

Loss of capability alone cannot remove an applied correction.

A held slew can therefore remain active indefinitely.

There is no elapsed-time completion or slew watchdog.

Completion follows the measured policy verdict above.

Sample this level with the PHC control signals.

It is independent of `pub_commit_o`.

Consumers must preserve alignment with their effective PHC rate.

Discard every measurement window overlapping the level's high interval.

A partly overlapping window remains affected after deassertion.

The parent carries this level through [`KL_gptp_shadow`](https://github.com/kebag-logic/milan-fpga/blob/1e80128f0a467b58bf884b7d9bf62e013a2fb141/hdl/ieee8021as/gptp_plane/KL_gptp_shadow.sv#L150).

[Parent #545](https://github.com/kebag-logic/milan-fpga/issues/545), now closed, connected its media-clock servo.

Its [servo input](https://github.com/kebag-logic/milan-fpga/blob/1e80128f0a467b58bf884b7d9bf62e013a2fb141/hdl/milan/milan_datapath.sv#L7329) pins parent `dev` at `1e80128f`.

#### Publication during a slew

`pub_flags_o` bit 3 publishes the synchronization verdict.

Every consumed pair raises it, stepping or slewing.

So a slew may still be in progress.

Its remaining offset is within the applicable step threshold.

`pub_offset_o` carries each pair's offset before correction.

It holds only the low 32 bits.

Offsets beyond about 2.147 s therefore wrap.

Such a pair always steps.

## Publication

The engine publishes protocol state as wires.

Sample outputs when `pub_commit_o` rises.

Each output follows its staging register directly.

No register holds the outputs at commit.

Microcode writes the fields over several instructions.

Between pulses the outputs can show a partial tuple.

Only the commit cycle presents one complete tuple.

| Output group | Contents |
|---|---|
| Identity | Grandmaster and parent identities |
| Status | Presence, mastership, capability, synchronization |
| Measurements | Peer delay and signed offset |
| Announce | Raw selected priority vector |
| Path | pathTrace from entry 0, with its count |

`pub_path_o` carries eight entries.

Entry k occupies bits 64k through 64k plus 63.

`pub_path_count_o` counts the published entries.

That count runs from one to eight.

Inactive path entries remain zero.

### Path of an elected peer

[Issue #85](https://github.com/Mister-M-alt/FPGA-gPTP/issues/85) appends thisClock.

[Issue #88](https://github.com/Mister-M-alt/FPGA-gPTP/issues/88) keeps the received head.

[Issue #87](https://github.com/Mister-M-alt/FPGA-gPTP/issues/87) keeps a path without TLV.

802.1AS-2011 clause 10.3.10.2.1 defines it.

Its item d copies a path trace TLV.

The received pathSequence is copied unchanged.

thisClock is then appended as the last entry.

Entry 0 is therefore the received head.

That head need not be the grandmaster.

A directly attached grandmaster publishes two entries.

An empty pathSequence publishes thisClock alone.

Seven received entries fill all eight entries.

Longer received paths publish their first eight entries.

Those entries are also pathTrace's first eight.

An Announce without that TLV writes no path.

The previous path therefore stays published.

After reset or mastership, that is thisClock alone.

The grandmaster and its path complete in one commit.

GET_AS_PATH can serve these entries unchanged.

### Before any peer

[Issue #82](https://github.com/Mister-M-alt/FPGA-gPTP/issues/82) defines this self publication.

802.1AS-2011 10.3.12.1.4 i) requires it.

Every reset leaves no port vector.

This plane is then its own grandmaster.

The grandmaster output names thisClock.

The path holds one entry: thisClock.

Parent identity keeps its reset value.

Flags carry gmPresent alone, or nothing with priority1 255.

Reset loads exactly this state into the publication bank.

The engine commits it on the first edge after release.

Cold starts and warm resets behave alike.

No microcode runs before that commit.

thisClock is data in the generated microcode image.

The engine reads it there at configuration.

### Grandmaster presence

Flags bit 0 publishes gmPresent.

802.1AS-2011 10.3.12.1.4 g) defines it.

A priority1 below 255 makes thisClock grandmaster-capable.

The image marks that capability beside thisClock.

A capable thisClock sets gmPresent in every publication.

That includes reset, both departures and mastership.

With priority1 255, only an elected peer sets it.

### Grandmaster synchronization

[Issue #84](https://github.com/Mister-M-alt/FPGA-gPTP/issues/84) records this rule.

A grandmaster's own time is the domain's time.

So mastership counts as synchronized.

Flags bit 1 and bit 3 are therefore set together.

A Sync receipt timeout never clears bit 3 during mastership.

The parent derives tu from bit 3.

Its tu therefore clears during mastership.

Taking mastership from a peer changes the published grandmaster.

That arms the parent's Milan Annex B.1.1 holdover.

Handing mastership to a peer clears bit 3.

The first consumed Sync pair sets it again.

On a slave, an unaged Sync receipt timeout clears it.

That happens under a priority1 255 grandmaster, which stays elected.

A self publication without mastership leaves bit 3 clear.

### Selection after reset

Scratch keeps the last best-vector record across warm resets.

That retained record cannot compete after a reset.

Only a newly received Announce can be elected.

A peer worse than this plane leaves thisClock selected.

A better peer wins through normal selection.

### Departure of the elected peer

Values here come from the [protocol constants](#protocol-constants).

Three departures each return thisClock and {thisClock}.

Announce silence for announceReceiptTimeout ages the peer out.

So does [`SYNC_RTO_MS_C`](#protocol-constants) without a usable Sync pair.

That needs a grandmaster priority1 below 255.

A usable pair is a Sync with its own Follow_Up.

Figure 11-6 of 802.1AS-2011 states that rule.

Ageing follows 10.3.11, whose Figure 10-13 Cor1 corrects.

It holds while the peer keeps announcing.

A missing or late Follow_Up is not usable.

Nor is one naming another sequenceId.

An asCapable port then becomes grandmaster.

Adopting a new grandmaster starts its [`SYNC_RTO_MS_C`](#protocol-constants) Sync watch.

A grandmaster never sending usable Sync is aged too.

The watch belongs to the port, not to its role.

Mastership leaves it running (802.1AS-2011 10.3.11).

So a master-role expiry marks the port aged too.

A port aged by Sync stays aged until usable Sync.

Until then its Announces are aged at once.

So this plane stays grandmaster while that Sync stays broken.

As grandmaster it still pairs that peer's Sync and Follow_Up.

Such a pair steers nothing and publishes nothing.

The next Announce after it elects the peer again, once.

That pair restarts the watch, so lapsing Sync ages again.

A Sync pending at takeover keeps its [`FU_RTO_MS_C`](#protocol-constants) watch.

A later Follow_Up pairs with nothing in either role.

An asCapable rise also clears that aged state.

Ageing on Sync also requires gmPresent (10.3.11).

gmPresent needs a grandmaster priority1 below 255.

So a priority1 255 grandmaster is never aged by Sync.

Its Sync receipt timeout clears sync-ok instead.

That grandmaster stays elected.

An aged port still elects such a grandmaster.

Published flags bit 0 keeps its own meaning, described above.

Losing asCapable drops the peer's vector at once.

That drop commits within about one millisecond.

Its commit clears the sync and mastership flags.

gmPresent stays set for a capable thisClock.

It leaves PHC control and the slew level untouched.

Announces on an incapable port elect nothing.

Restored capability lets the best live peer win.

Without Announces, mastership follows within one receipt interval.

### Lost Pdelay responses

Values here come from the [protocol constants](#protocol-constants).

802.1AS-2011 Figure 11-8 counts lost responses.

Cor1 and Cor2 correct that figure.

Each Pdelay_Req interval without a completed exchange counts one.

That includes a Pdelay_Resp whose Follow_Up never comes.

A second Pdelay_Resp for the outstanding request resets the exchange.

That reset also counts one, from either responder.

Fewer consecutive losses than [`LOST_CLEARS_AT_C`](#protocol-constants) keep asCapable.

The loss that reaches it clears asCapable.

A completed exchange restarts the count.

## Microcode configuration

Generate one image for each hardware configuration.

```sh
python3 hdl/ucode/gen_gptp_ucode.py \
  --mac 0x02A1B2C3D4E5 \
  --clk-hz 100000000 \
  -o gptp_ucode.hex
```

`--mac` takes one integer, such as `0x02A1B2C3D4E5`.

Colon-separated addresses are refused.

`--p1` sets priority1; [`P1_C`](#protocol-constants) is its default.

The generator prints its word count and leg placement.

Set `UCODE_HEX_P` to that generated image.

The engine also reads thisClock from that image.

Set `CLK_HZ_P` to the actual engine frequency.

## Protocol constants

This table is the single home of protocol values.

Each row names the generator constant it reads.

`make docs` fails when a row drifts from its constant.

It also fails on a missing, duplicate or formatted row.

Other pages name the constant and link its row.

Units come from Meaning cells ending ms, ns or ppm.

Elsewhere on current pages, `make docs` rejects that row value as:

- the integer and its unit symbol, as in `7 ms`;
- ms in whole seconds, ns in whole microseconds, by symbol;
- ms as one to ten whole minutes: `2 min`, `two minutes`.

Fenced code and this section are exempt.

Rows without such a unit are not checked for copies.

Decimals and other unit words, such as milliseconds, pass.

Review keeps those forms out.

Clauses without a prefix are IEEE 802.1AS-2011.

| Constant | Value | Meaning | Reference |
|---|---:|---|---|
| `P1_C` | 248 | Default announced priority1 | Milan 4.2.6.2.1 |
| `ASCAP_UP_C` | 2 | Good exchanges before asCapable rises | Milan 4.2.6.2.4 |
| `LOST_N_C` | 3 | allowedLostResponses | 11.5.3 |
| `LOST_CLEARS_AT_C` | 5 | Consecutive lost response that clears asCapable | 11.2.15, Figure 11-8 |
| `NPD_HI_C` | 800 | neighborPropDelayThresh, ns | Milan 4.2.6.1.1 |
| `NPD_LO_C` | 80 | Largest tolerated negative delay magnitude, ns | Milan 4.2.6.2.7 |
| `SYNC_RTO_MS_C` | 375 | syncReceiptTimeout, ms | Milan 4.2.6.2.3, Table 4.2 |
| `FU_RTO_MS_C` | 125 | followUpReceiptTimeout, ms | Milan 4.2.6.2.3, Table 4.2 |
| `CEASE_N_C` | 3 | Successive multi-answered requests before the cease | Milan 4.2.6.2.5 |
| `CEASE_MS_C` | 300,000 | Default cease countdown, ms | Milan 4.2.6.2.5 |
| `STEP_LINKUP_NS_C` | 20,000 | Link-up step threshold, ns | Issue #68 |
| `STEP_LOCKED_NS_C` | 100,000 | Locked step threshold, ns | Issue #68 |
| `SLEW_SETTLED_NS_C` | 100 | Tracking band half-width, ns | Issue #75 |
| `RATE_PPM_C` | 200 | Rate trim and integrator bound, ppm | Issue #68 |
| `DEPTH` | 1,024 | Microcode ROM words | [ROM budget](MANAGER.md#current-rom-budget) |
| `ROM_CID_HI_C` | 1,022 | ROM word holding thisClock's high half | Issue #82 |
| `ROM_GMCAP_BIT_C` | 32 | Grandmaster-capable bit in that word | Issue #82 |

`--cease-ms` overrides the cease countdown per image.

The engine suite uses 3,000 ms to stay fast.

These cadences are literals inside generator legs.

`make docs` does not check them.

| Cadence | Value | Timer slot | Reference |
|---|---:|---:|---|
| Pdelay_Req interval | 1 s | 0 | Milan 4.2.6.2.2, Table 4.1 |
| Sync interval | 125 ms | 1 | Milan 4.2.6.2.2, Table 4.1 |
| announceReceiptTimeout | 3 s | 2 | Milan 4.2.6.2.3, Table 4.2 |
| Announce interval | 1 s | 3 | Milan 4.2.6.2.2, Table 4.1 |

## Integration checklist

- Use one shared synchronous clock.
- Deliver complete validated frames.
- Preserve byte order and frame markers.
- Hold transmit readiness correctly.
- Return exact timestamp tags.
- Hold result offers until acceptance.
- Report unmeasured results explicitly.
- Drive admission credit as a level.
- Drive portEnabled from the effective link.
- Apply PHC pulses once.
- Count each step pulse as one step.
- Align the slew level with effective rate changes.
- Derive addend envelopes from the generator clock.
- Capture publication only on commit.
- Review the open interface risk.
- Run every repository gate.
