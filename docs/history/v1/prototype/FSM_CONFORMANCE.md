[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/FSM_CONFORMANCE.md`
>
> Archived: 2026-09-01
>
> Current successor: [current source evidence](../../../SOURCE_EVIDENCE.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# State-machine conformance — 802.1AS-2011, element by element

Every state machine the standard specifies for a **single-port
time-aware end station**, mapped to the µcode/RTL that implements it,
with the check that proves it. "1:1" here means *behaviourally* 1:1 —
this plane is event-dispatched µcode, not a literal transcription of
the SM diagrams, so a state is a scratch word and a transition is a
handler path. Where the mapping is a deliberate consolidation, the
row says so and why it cannot change observable behaviour.

Audit date 2026-08-15, extended 2026-08-16 (µcode v5). Suites:
`tb/verilator/engine` (144), `tb/tsngen` (272, independent decode +
independent SM mirror), `tb/verilator/parser` (32),
`tb/verilator/ucpu` (768), `tb/verilator/gaskets` (81) — **1,297
checks**.

## 11.2 — MD entity (per-port pdelay + sync receipt)

| SM (clause) | states / transitions of record | implementation | proof |
|---|---|---|---|
| **MDPdelayReq** (11.2.15) | NOT_ENABLED → INITIAL_SEND_PDELAY_REQ → {WAITING_FOR_PDELAY_RESP, WAITING_FOR_PDELAY_RESP_FOLLOW_UP, WAITING_FOR_PDELAY_INTERVAL_TIMER}; `rcvdPdelayResp`, `rcvdPdelayRespFollowUp`, `pdelayIntervalTimer`; lostResponses counting; neighborRateRatio; meanLinkDelay | timer slot 0 (1 s cadence) is the interval timer; `S_PEND=1` is WAITING_FOR_PDELAY_RESP (the TX-timestamp event supplies t1); `prog_rx_pdresp` latches t2/t4 and counts responders; `prog_rx_pdrfu` computes `r = (t3ₙ−t3ₚ)/(t4ₙ−t4ₚ)` in Q16 and `meanLinkDelay = (r·(t4−t1) − (t3−t2))/2` | `nrr ratio Q16`, `nrr corrects delay` (rate-skewed peer, mutation-proven); `pub pdelay`; `negclamp*` |
| **MDPdelayResp** (11.2.16) | NOT_ENABLED → INITIAL_WAITING_FOR_PDELAY_REQ → SENT_PDELAY_RESP_WAITING_FOR_TIMESTAMP → sending the follow-up | `prog_rx_pdreq` builds Resp with t2 and sets `S_PEND=2`; the egress-timestamp event routes to `L_RFU`, which emits Resp_Follow_Up with t3. Runs unconditionally, *not* gated on asCapable (11.2.16 has no such gate) | `pdresp *` / `pdrfu *` byte checks in both engine and tsn-gen suites |
| **MDSyncReceive** (11.2.13) | DISCARD → WAITING_FOR_FOLLOW_UP → WAITING_FOR_SYNC; a Follow_Up is consumed only when it matches the pending Sync's `sequenceId`; a new Sync discards a stale pending one | `prog_rx_sync` latches the ingress stamp and arms `S_SYNCPEND = {valid, seqId}`; `prog_rx_followup` requires valid+seq-match, then CLEARS the pending word (so a replay is discarded) | `orphan FU ignored`, `mismatched FU ignored`, `paired FU accepted`, `replayed FU ignored`; mutation `FU pairing off` caught |
| **MDSyncSend** (11.2.14) | forwards a PortSyncSync into Sync + Follow_Up with the egress stamp | `L_SYNCTX` builds the two-step Sync (`S_PEND=3`), the egress-timestamp event routes to `L_SYNCFU` which emits the Follow_Up carrying that exact stamp | `syncfu origin` (equals the harness's egress stamp for that frame); wire-verified at 8.6 µs FU-after-Sync |
| **LinkDelaySyncIntervalSetting** (11.2.17) | applies interval requests from Signaling | **Consolidated**: intervals are the Milan v1.2 Table 4.1 constants in the ROM; Signaling is parsed and ignored (`prog_rx_signal`). A conformant endpoint may use its profile's intervals; the SM's only other job is honouring peer requests, which Milan does not require. Adding it is ROM words, not structure. | `announce/pdreq/sync` cadences measured on the wire at 1000.003 ms / 124.57 ms |

## 10.2 — Port sync / site sync / clock slave

| SM (clause) | states / transitions of record | implementation | proof |
|---|---|---|---|
| **PortSyncSyncReceive** (10.2.7) / **SiteSyncSync** (10.2.6) / **ClockSlaveSync** (10.2.8) | the chain that turns a received sync into `syncReceiptTime` and drives the local clock | **Consolidated into one path** (`prog_rx_followup`): a single port means SiteSync's "select one port" is the identity function and the PortSync↔SiteSync hand-off carries no information a second port could change. Computes `offset = t2ₗₒcₐₗ − (preciseOrigin + correctionField + meanLinkDelay + delayAsymmetry)` (10.2.12 / 10.2.4.5) and steers the PHC | `pub offset ±`, `servo pi #1/#2`, `asym+/- offset`, closed-loop convergence; hardware: −0.3 ns mean / 3.3 ns σ vs an AVB switch GM |
| **ClockMasterSyncSend** (10.2.9) / **PortSyncSyncSend** (10.2.11) | GM-side sync generation at `syncInterval` | timer slot 1 → `L_SYNCTX`, gated on `S_AMGM` | `sync *` byte checks; wire: 8 Sync + 8 FU per second as master |
| **syncReceiptTimeout** (10.2.4.2 / 10.6.3.1) | `syncReceiptTimeoutTime` expiry → the master is aged out | timer slot 4, armed on adopt and re-armed by every paired Sync+FU; expiry → `L_SRTO` → become-master | `srto became master`; mutation `syncrto 375→3750` caught; observed live against a sync-less peer |

## 10.3 — BMCA

| SM (clause) | states / transitions of record | implementation | proof |
|---|---|---|---|
| **PortAnnounceReceive** (10.3.10) | qualifies a received Announce: port enabled+asCapable; `stepsRemoved ≥ 255` discard; announce from the receiving port's own clock discard; **path-trace loop** discard | `prog_rx_announce` gates in order: `F_ASCAP`, `sourceClockIdentity ≠ ourClockIdentity`, `stepsRemoved < 255`, then `L_PTRACE` walks the path-trace TLV (parser-capped at 8 hops; a capped read is treated as unqualified because absence cannot be proven) | `self announce: ignored`, `steps 255: ignored`, `path loop: rejected`, `path clean: adopted`; mutations `self`, `loop` caught |
| **PortAnnounceInformation** (10.3.11) | classifies against **portPriority**: SuperiorMasterPort / RepeatedMasterPort / InferiorMasterPort / OtherPort, and ages the info out on `announceReceiptTimeout` | `L_BTCA` selects the comparison target the SM specifies: no incumbent → our own vector; same gmId (repeated) → our own vector (still better = refresh, degraded = reselect); different gmId → the **incumbent portPriority** (`S_PPV`, better = switch, worse = ignore). Timer slot 2 is the receipt timeout | `other worse: gm kept` (the case the old code got wrong), `other better: switched`, `incumbent degraded: master`, `same-gm keeps acc/syncOk`; mutation `incumbent` caught; tsn-gen's independent mirror agrees over a seeded sweep |
| **PortRoleSelection / state decision** (10.3.12, 10.3.13) | assigns MasterPort / SlavePort / PassivePort and drives the announce cadence | two-role reduction for a single-port endpoint: `S_AMGM` is the role, `L_BECOME` is the master transition (announce + sync armed), adopt is the slave transition (both disarmed). PassivePort cannot arise with one port | `became master`, `adopted`, `sync TX stopped`, bidirectional election vs STM32 and switch on hardware |
| **PortAnnounceTransmit** (10.3.14) | Announce every `announceInterval` when MasterPort, with the path-trace TLV | timer slot 3 → `L_ANNTX`, gated on `S_AMGM`; emits our vector + path trace carrying our clockIdentity | `ann *` byte checks incl. `ann tlv`, `ann path0`; wire cadence 999 ms |
| **AnnounceIntervalSetting** (10.3.15) | applies interval requests from Signaling | **Consolidated** — same rationale as 11.2.17 | (as above) |

## 10.2.4 — asCapable

| SM (clause) | states / transitions of record | implementation | proof |
|---|---|---|---|
| **asCapable computation** (10.2.4.1 with 11.2.13's conditions) | TRUE requires a complete, single-responder pdelay exchange with `neighborPropDelay ≤ neighborPropDelayThresh`; FALSE on multiple responders, `lostResponses > allowedLostResponses`, or threshold breach; a FALSE port stops participating in time transfer | the ladder at the end of `prog_tmr` judges the PREVIOUS interval once per cadence (`S_PDRSPN`, `S_GOTFU`, `S_LOST`, threshold with a sign-aware clamp for near-zero links); TRUE arms the announce watch (admission to the BMCA), FALSE clears role/flags/cadences | `asCap risen`, `thresh: asCap fell`, `multi: asCap fell`, `lost: asCap fell`, `incapable: TX quiet`, `negclamp asCap holds`, `negfault*`; mutations `thresh`, `lostmax`, `multi detect` caught |

## Deliberate non-implementations (stated, not hidden)

- **Multi-port / bridge SMs** (10.2.6 site-sync selection across ports,
  10.3.12 per-port role assignment, PortAnnounceInformationExt): this
  is an end station with one port. Nothing in the code assumes a
  second port could not exist; adding one is a parser bank + role
  vector per port.
- **One-step Sync** (11.1.3): we transmit two-step (twoStepFlag set)
  and accept two-step. One-step *reception* would need the origin
  taken from the Sync itself — a short µcode arm, not needed by any
  peer on this bench.
- **gmPresent/gmRateRatio propagation** (10.2.9.2) and
  `cumulativeScaledRateOffset` in our transmitted Follow_Up: we
  transmit zero (correct for a GM whose local clock is the reference)
  and do not yet forward a measured ratio when acting as a relay —
  a bridge behaviour.
- **Signaling transmission** (10.5.4 / 11.4.8): parsed and ignored;
  never transmitted. Milan fixes the intervals.
- **Domains other than 0**: 802.1AS-2011 has exactly one (8.1); the
  parser drops non-zero `domainNumber` frames, counted, with no event.
  *(This audit's own first draft claimed that and was wrong — nothing
  checked the field. Implemented and mutation-proven 2026-08-16.)*

## Where the audit changed behaviour (v5)

Four gaps were found by this audit and closed; each is
mutation-proven, and two of them were latent *correctness* bugs
rather than missing features:

1. **MDSyncReceive pairing** — any Follow_Up was previously accepted
   while slave; a duplicate or crossed FU corrupted the offset.
2. **PortAnnounceReceive qualification** — self-announce, stepsRemoved
   and the path-trace loop check were all absent (the loop check is
   what stops an announce that a bridge reflects from electing us
   through our own echo).
3. **PortAnnounceInformation target** — comparing every announce
   against our own vector meant a *second, worse* announcer displaced
   an adopted better grandmaster. Now the incumbent portPriority is
   the target, exactly as 10.3.11 says.
4. **neighborRateRatio** — the pdelay computation ignored the peer's
   rate; at Milan's 15 ms turnaround allowance a 100 ppm rate error is
   1.5 µs of link-delay error.
5. **domainNumber** (added 2026-08-16, while checking this document
   against the code): no message-type handler and no parser arm looked
   at the field, so a frame from another PTP domain was processed as
   if it were ours. The parser now drops it (8.1).

The fifth item is the documentation pass doing its job: the claim was
written first, found false against the code, and the code was fixed —
not the claim.
