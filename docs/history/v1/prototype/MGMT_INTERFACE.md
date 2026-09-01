[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/MGMT_INTERFACE.md`
>
> Archived: 2026-09-01
>
> Current successor: [current integration guide](../../../INTEGRATION.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# The management interface — what Milan needs, as wires

The publish bank IS the software contract this plane retires: every
word a host service used to poll from the host PTP tools and mirror into fabric
CSRs (`gptp2csr.sh` on the milan-fpga softcore) is a latched output of
`KL_gptp_engine`, updated by µcode and strobed by `OP_COMMIT`
(`pub_commit_o` marks every coherent update). This file is the
traceable map: publish word ↔ the Milan/AVDECC consumer that needs it
↔ the CSR it replaces ↔ the 802.1AS source of the value.

## Publish bank (state-port region 3, wires `pub_*_o`)

| word | wire | contents | Milan / AVDECC consumer | replaces CSR |
|---|---|---|---|---|
| 0 | `pub_gm_id_o[63:0]` | grandmasterIdentity of the current GM (our clockIdentity when we are GM) | ADP `gptp_grandmaster_id` (1722.1 6.2.1.16); GET_AVB_INFO `gptp_grandmaster_id` (7.4.40); Milan 5.4.4.2 PAAD advertisement | `ADP_GPTP_GM_LO/HI` 0x624/0x628 |
| 1 | `pub_parent_id_o[63:0]` | parent (master port) clockIdentity from the adopted Announce's sourcePortIdentity; = our clockIdentity when we are GM | GET_AS_PATH (7.4.41) first hop / PARENT_DATA_SET | `A_AS2_LO/HI` 0x730/0x734 |
| 2 | `pub_flags_o[31:0]` | status flags, table below | GET_AVB_INFO flags (AS_CAPABLE, GPTP_ENABLED); the AVTP `tu` bit source | `CLKV_CTRL` sync-claim lease 0x778 |
| 3 | `pub_pdelay_ns_o[31:0]` | meanLinkDelay, ns (11.2.15) | GET_AVB_INFO `propagation_delay` (7.4.40.2) | `A_GPTP_PDELAY` 0x6E4 |
| 4 | `pub_offset_o[31:0]` | last Sync offset from GM, ns, signed (10.2.12 computation, truncated to 32 bits) | servo observability / diagnostics counters | (host-side only) |
| 5 | `pub_annq_o[63:0]` | last RECEIVED announce vector, raw: {currentUtcOffset, gmPriority1, gmClockQuality, gmPriority2} | diagnostics: what the peer claims, BTCA input visibility | (new) |
| 6 | `pub_asinfo_o[63:0]` | adopted announce {stepsRemoved[63:48], timeSource[47:40], 40'0}; zero when we are GM | GET_AS_PATH `count`/hop depth; AVB_INTERFACE descriptor context | (new) |
| 7 | `pub_nrr_o[63:0]` | neighborRateRatio, Q16 unsigned (1.0 = 0x10000), measured per pdelay interval (802.1AS-2011 11.2.15); 1.0 until the second exchange | link-quality diagnostics; the ratio a bridge would propagate | (new) |

## Flags word (publish 2)

| bit | name | set by | cleared by | standard hook |
|---|---|---|---|---|
| 0 | `gmPresent` | Announce adopt (BTCA), become-master | asCapable FALSE transition | 10.3.8.21 gmPresent |
| 1 | `amGm` | become-master (announce receipt timeout 10.3.12, sync receipt aging, BTCA reject while unelected) | adopt, asCapable FALSE | port role == MasterPort (10.3.12) |
| 2 | `asCapable` | pdelay ladder: exactly one Resp+FU AND neighborPropDelay ≤ 800 ns | multi-responder, lostResponses > 3, threshold breach | 10.2.4.1 / 11.2.13; thresh 11.2.15.3; allowedLost 11.5.3 |
| 3 | `syncOk` | each valid Sync+Follow_Up pair processed as slave | sync receipt timeout (375 ms, 10.6.3.1), role change | the honest `tu`-bit source Milan wants (a servo fact, not a fabric guess) |

`GPTP_ENABLED` is static true for this plane; `SRP_ENABLED` is not this
plane's fact. The AVB_INTERFACE descriptor's static fields
(clock_identity, priority1/2, clockQuality, log intervals, domain 0)
are build-time constants of the µcode image (`gen_gptp_ucode.py`
Milan-default vector) and need no wires.

## Configuration inputs

| wire | direction | contents |
|---|---|---|
| `cfg_asym_i[63:0]` | in | delayAsymmetry for this link, signed ns (802.1AS-2011 10.2.4.5: `t_ms = meanLinkDelay + delayAsymmetry`). A per-port managed object — a CSR in the parent integration; on the bench, the UART tuner (`bench_uart_tune`, command `Y<8 hex>`). µcode reads it through gather sel 2 in the Follow_Up offset path; ONLY the slave side of a link may compensate, or corrections double. |

The bench additionally makes the timestamp-point constants runtime
registers (`I<8 hex>` ingressLatency, `E<8 hex>` egressLatency, both
ns; power-on defaults are the AN-1507-derived 240/105) and reports the
live delayAsymmetry as the `Y=` field of the once-a-second line.

## PHC face (the servo's actuators)

| wire | direction | contents |
|---|---|---|
| `phc_ns_i[63:0]` | in | free-running PHC snapshot |
| `phc_addend_we_o` + `phc_addend_o[31:0]` | out | signed Q8.24 ns/tick rate trim (the parent `timestamp_counter` adjfine shape) |
| `phc_step_we_o` + `phc_step_o[63:0]` | out | signed ns step (adjtime shape), written when \|offset\| > 1 ms |

## Consumption contract

- Words update atomically per µcode handler; `pub_commit_o` pulses
  after each coherent group. A CSR bridge may latch on commit or
  free-run — each word is itself written in one cycle.
- On `asCapable` FALSE every role bit clears and cadences stop; word 3
  (pdelay) intentionally keeps the last measured value so diagnostics
  can see WHY (e.g. a 900 ns link stays visible).
- The bench UART line (`bench_uart_report.sv`) prints words 0–5 plus
  the live delayAsymmetry once per second: `F=` is `flags[7:0]` —
  `07` capable master, `05` capable slave awaiting sync, `0D` synced
  slave, `00` not asCapable. Full field table in `BENCH_OPERATIONS.md`.

## Integration checklist (milan-fpga)

*(Deploying onto any FPGA, step by step, including timestamp
calibration and PHC knob scaling: `INTEGRATION_GUIDE.md`.)*

What the parent must provide and consume, in one place:

| direction | signal | parent source / sink |
|---|---|---|
| in | classified 0x88F7 byte stream, DA first, FCS checked+stripped | the `KL_pp_shadow` classifier pattern (add the 0x88F7 leg) |
| in | `rx_ts_i` ingress stamp, stable at sof | `ptp_ts_top` RX capture |
| out | TX byte stream with sof/eof | the control TX cascade |
| in | `txts_valid_i` / `txts_ns_i` egress stamp | `ptp_ts_top` TX capture |
| in | `phc_ns_i` | `timestamp_counter` |
| out | `phc_addend_we_o` / `phc_addend_o` | `timestamp_counter` adjfine knob |
| out | `phc_step_we_o` / `phc_step_o` | `timestamp_counter` adjtime knob |
| in | `cfg_asym_i` | a CSR (per-port managed object) |
| out | publish bank + `pub_commit_o` | the CSR window that replaces `gptp2csr.sh` |

Timestamp points must be compensated to the MDI reference plane
(802.1AS-2011 8.4.3) with the parent's own PHY/MAC latencies — the
bench does this with `INGRESS_NS_P`/`EGRESS_NS_P`; see
`BENCH_TAP_WIRETRUTH.md` for the derivation method and how it was
verified with an independent TAP.
