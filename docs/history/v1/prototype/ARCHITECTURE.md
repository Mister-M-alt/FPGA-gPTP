[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/ARCHITECTURE.md`
>
> Archived: 2026-09-01
>
> Current successor: [current HDL guide](../../../HDL_DEVELOPER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Architecture — how the gPTP plane is built

One clock domain, one byte in, one byte out. Protocol behaviour lives
in a 1024×48 µcode ROM; fabric provides the datapaths that ROM cannot
be. This document is the reference for the shape: what each module
does, what the µCPU can execute, how an event becomes a handler, and
where every piece of protocol state lives.

Companion documents: `IP_BLOCKS.md` (the same material as a design
book, block by block, with timing diagrams and generated module
tables), `FSM_CONFORMANCE.md` (which 802.1AS state machine each
handler implements), `MGMT_INTERFACE.md` (the outward contract),
`VERIFICATION.md` (how it is proven), `RESOURCE_VALIDATION.md` (what
it costs).

## 1. The stack

```
        rx byte face (0x88F7 pre-classified, DA first, FCS stripped)
                 │        + rx_ts_i (ingress stamp, stable at sof)
                 ▼
        KL_gptp_rx_parser ──────► message bank (32 × 64, region 0)
                 │  ev_valid/code/seq
                 ▼
        ┌─ event queue (4 deep) ─┐   ← txts_valid_i (egress stamp)
        │  arrival order, one     │   ← KL_gptp_timer (8 ms-deadline slots)
        │  dispatch at a time     │
        └────────┬────────────────┘
                 │ entry µPC + r15/r14/r13 preload
                 ▼
        KL_gptp_ucpu (48-bit µops, 1024-deep ROM, 16 × 64 regfile)
           │            │              │             │
           │ state port │ gather       │ build lane  │ effects
           ▼            ▼              ▼             ▼
        region map   PHC/ms/asym   KL_gptp_tx_slot  OP_COMMIT
        (below)      snapshots     → tx byte face   → publish wires
```

Everything above is `KL_gptp_engine`. The parent integration supplies
the classified RX stream, the TX cascade, the PHC and its knobs; on
the bench those are `bench_mii_rx/tx`, `bench_afifo`, `bench_phc`.

## 2. The µISA (`hdl/ucpu/gptp_ucpu_pkg.sv`)

48-bit fixed encoding, identical field layout to the AECP processor's
µISA so tooling carries over:

```
[47:43] op   [42:39] rd   [38:35] ra   [34:31] rb
[30:28] fmt  [27:24] cnd  [23:0]  imm24
```

Opcodes 0…28 are the AECP base, kept in place (several unused here —
`OP_DESC_ADDR`, `OP_NAME_*`, `OP_COPY_BUF`, `OP_CHECK_LOCK`,
`OP_MAP_VALID`, `OP_READ_CTRS`, `OP_NVM_MARK`, `OP_NOTIFY_ENQ` — so
that this module's out-of-context delta prices the arithmetic growth
alone). The two additions are why this derivative exists:

| op | function | timing |
|---|---|---|
| `OP_ALU` (29) | 64-bit ADD/SUB/AND/OR/XOR; SHL/SHR/SAR | logic single-cycle; **shifts serial**, one bit/cycle |
| `OP_MULDIV` (30) | `MULS` signed 32×32→64; `DIVU` 64/32→64 | MULS one registered stage (DSP); **DIVU restoring**, one bit/cycle |

Serial shift and restoring divide are deliberate: every gPTP
computation runs at protocol rate (≤ 8 Hz, and Milan relaxes the
Pdelay turnaround to 15 ms), so latency buys nothing and the barrel /
array structures are saved. Divide-by-zero is µcode's contract to
guard — hardware does not trap.

Pipeline: F/D/E with a single pending-writeback interlock for RAW
hazards; branches resolve in E and flush F/D; multi-cycle operations
(state, gather, build, shift, mul, div, send) hold E. Dispatch
preloads `r15 = {event_code, seq_id, aux}`, `r14 = timestamp 0`
(ingress stamp, or the egress stamp for `EV_TX_TS`, or ms-now for a
timer event), `r13 = PHC at dispatch`.

## 3. Engine-owned state — the region map

The µCPU reaches all engine state through one port, region-selected by
`st_addr[19:16]`:

| region | name | access | contents |
|---|---|---|---|
| 0 | message bank | RO | 32 × 64, parser-written (layout below) |
| 1 | timestamp regs | RO | 0 = ingress stamp, 1 = egress stamp |
| 2 | scratch RAM | RW | 32 × 64, all protocol state (map below) |
| 3 | publish bank | RW | 8 words, the outward contract (`MGMT_INTERFACE.md`) |
| 4 | PHC control | WO | 0 = rate addend, 1 = step |
| 5 | timer arm | WO | address = slot, data = delta ms (0 disarms) |

`OP_GATHER_EXT` provides atomic snapshots: **sel 0** live PHC ns,
**sel 1** free-running ms, **sel 2** `cfg_asym_i` (delayAsymmetry).

Both bank and scratch are LUTRAM with **no reset** — the bitstream's
initial state is the reset, and the µcode's init-once flag (`S_INIT`)
depends on power-on zero. A soft reset therefore does *not* re-run
µcode init; only reconfiguration does.

### Message bank (parser output, region 0)

| word | contents |
|---|---|
| 0 | `{8'0, msgType, seqId, domain, flags, logInterval}` |
| 1 | correctionField |
| 2 | sourcePortIdentity.clockIdentity |
| 3 | `{48'0, sourcePortIdentity.portNumber}` |
| 4 | `{16'0, timestamp.seconds[47:0]}` |
| 5 | `{32'0, timestamp.nanoseconds}` |
| 6 | requestingPortIdentity.clockIdentity |
| 7 | `{48'0, requestingPortIdentity.portNumber}` |
| 8 | `{currentUtcOffset, gmPriority1, gmClockQuality, gmPriority2}` |
| 9 | grandmasterIdentity |
| 10 | `{stepsRemoved, timeSource, 40'0}` |
| 11 | `{cumulativeScaledRateOffset, gmTimeBaseIndicator, 16'0}` |
| 12 | `{56'0, pathTraceCount}` (true count even when capped) |
| 16…23 | path-trace clockIdentities, capped at 8 hops |

### Scratch map (region 2) — the protocol's state variables

| word | name | holds |
|---|---|---|
| 0 | `S_SYNCTS` | ingress stamp of the pending Sync (t2) |
| 1 | `S_SYNCPEND` | `{valid, seqId}` — MDSyncReceive's WAITING_FOR_FOLLOW_UP |
| 2 | `S_T3PREV` | previous interval's t3, for neighborRateRatio |
| 3 | `S_AMGM` | port role: 1 = MasterPort, 0 = SlavePort |
| 4 | `S_PDELAY` | meanLinkDelay, ns |
| 5 | `S_T2` | pdelay t2 (peer's receipt of our request) |
| 6 | `S_SSEQFLY` | sequenceId of the Sync awaiting its egress stamp |
| 7 | `S_LOST` | consecutive lost pdelay responses |
| 8 | `S_PDRSPN` | Pdelay_Resp count this interval (>1 ⇒ multiple responders) |
| 9 | `S_FUORG` | constant `0xC2000001` (info-TLV org tail) |
| 10 | `S_MYPV` | our own priority vector `{p1, cq, p2, 16'0}` |
| 11 | `S_ACC` | servo integral, signed, saturated ±2²³ |
| 12 | `S_GOTFU` | Pdelay_Resp_Follow_Up completed this interval |
| 13 | `S_PPV` | **incumbent portPriority** vector (10.3.11 comparison target) |
| 14 | `S_PPMISC` | incumbent `{stepsRemoved, timeSource}` |
| 16 | `S_T1` | our Pdelay_Req egress stamp |
| 17 | `S_T4` | our receipt of Pdelay_Resp |
| 18 | `S_PEND` | which TX is awaiting its egress stamp (1 req, 2 resp, 3 sync) |
| 19 | `S_RQCID` | requestor clockIdentity being answered |
| 20 | `S_T4PREV` | previous interval's t4, for neighborRateRatio |
| 21 | `S_RQSEQ` | requestor sequenceId being answered |
| 22 | `S_RQPN` | requestor portNumber being answered |
| 23 | `S_INIT` | init-once flag (LUTRAM power-on zero is the contract) |
| 24 | `S_MYSEQ` | our Pdelay_Req sequence counter |
| 25 | `S_CID` | our clockIdentity (from the build MAC) |
| 26 | `S_1E9` | constant 1 000 000 000 |
| 27 | `S_HDR8` | first 8 header bytes (DA + our MAC high half) |
| 28 | `S_SALO` | our MAC low 32 bits |
| 29 | `S_SSEQ` | our Sync sequence counter |
| 30 | `S_ASEQ` | our Announce sequence counter |
| 31 | `S_ANNBODY` | our announce body constant `{utc, p1, cq}` |

## 4. Event dispatch

Events enter a 4-deep queue in arrival order:

- **parser** wins a same-cycle push (a frame in flight cannot wait),
- an **egress-timestamp return** pends until it can be pushed,
- the **timer** waits on its own ready handshake.

Dispatch is gated on the TX serializer being idle, so a handler never
builds into a slot still on the wire, and pops **one** event per
accepted dispatch — the µCPU acknowledges by leaving IDLE one cycle
after valid. (Popping while valid is still asserted clobbers the
preload operands mid-handshake and silently eats the second event;
that was a real bug the 78-check suite caught before the bitstream.)

Entry table — the µPC each event vectors to, mirrored between
`KL_gptp_engine` and `gen_gptp_ucode.py`:

| event | µPC | handler |
|---|---|---|
| `EV_RX_SYNC` (1) | 16 | `prog_rx_sync` |
| `EV_RX_FOLLOWUP` (2) | 64 | `prog_rx_followup` |
| `EV_RX_ANNOUNCE` (3) | 128 | `prog_rx_announce` |
| `EV_RX_PDREQ` (4) | 192 | `prog_rx_pdreq` |
| `EV_RX_PDRESP` (5) | 256 | `prog_rx_pdresp` |
| `EV_RX_PDRFU` (6) | 320 | `prog_rx_pdrfu` |
| `EV_RX_SIGNAL` (7) | 384 | `prog_rx_signal` (parsed, ignored) |
| `EV_TX_TS` (8) | 448 | `prog_tx_ts` (routes by `S_PEND`) |
| `EV_TMR` (16) | 512 | `prog_tmr` (routes by slot in aux) |
| — | 704 | testbench arithmetic battery |

## 5. Timer slots

`KL_gptp_timer` is a 1 ms tick, a free-running 32-bit ms timebase and
8 armed deadlines swept one slot per cycle after each tick, wrap-safe
modular compare. Arming is O(1) through the state port; a delta of 0
disarms.

| slot | purpose | cadence |
|---|---|---|
| 0 | pdelay cadence + one-time init + the asCapable ladder | 1000 ms |
| 1 | Sync TX (master only) | 125 ms |
| 2 | announceReceiptTimeout | 3000 ms |
| 3 | Announce TX (master only) | 1000 ms |
| 4 | syncReceiptTimeout | 375 ms |
| 5–7 | free | — |

Bootstrap: nothing arms a timer before µcode runs and no µcode runs
before an event, so the engine arms slot 0 once, ~256 cycles after
reset; the slot-0 handler owns its re-arm from then on.

## 6. The µcode image (`hdl/ucode/gen_gptp_ucode.py`)

A Python generator emits `gptp_ucode.hex` (1024 lines of 12 hex
digits). It contains a tiny two-pass assembler (`Prog`), emit helpers
for the repeated shapes (`e_hdr` builds the 48-byte Ethernet + PTP
common header; `e_ts_fields` writes a 10-byte timestamp; `e_ult64`
is an unsigned 64-bit compare-and-branch; `e_flag_gate` tests publish
flags), and one function per handler.

**Fixed entries** sit at the addresses the engine's entry table
mirrors. **Shared legs** — BTCA, become-master, the builders, the
servo, the sync-timeout, the path-trace walk — are *auto-packed*:
their sizes are measured in a first pass, then placed first-fit
decreasing into the free windows between fixed entries, so growth can
never silently collide (an over-full window is an assertion, not a
corrupt image). Current occupancy: **849 of 1024 words**.

Build-time parameters: `--mac` (drives clockIdentity and the header
constants), `--p1` (our announced priority1), `--thresh`
(neighborPropDelayThresh, for TAP'd benches — the default is the
spec's 800 ns).

Unused ROM words are filled with a SplitMix-derived pattern, not
zeros, so a µPC that escapes into unused space decodes as garbage and
fails loudly in simulation instead of running NOPs.

## 7. Wire modules

**`KL_gptp_rx_parser`** — byte-serial, one frame at a time, no
backpressure (the integrator's control FIFO owns rate matching).
Extracts the common header and per-type body into the message bank as
packed 64-bit words, walks the announce path-trace TLV (capped at 8
hops, true count reported), and raises one event at end of frame.
Drops (counted, no event): EtherType ≠ 0x88F7, transportSpecific ≠ 1,
versionPTP ≠ 2, `domainNumber` ≠ 0 (802.1AS-2011 8.1), truncation
before the per-type minimum, `rx_err_i`.
End-of-frame settles one cycle late so last-byte field writes and the
per-type minimum flag have landed.

**`KL_gptp_tx_slot`** — a 128-byte slot plus its byte serializer. The
µCPU's 32-bit build lane writes fields at byte cursor addresses
(1/2/4-byte strobes, big-endian, possibly unaligned); a small unpack
FSM turns each lane write into 1…4 byte writes, using `rb_ready`
backpressure — a refused write holds the µCPU's E stage, so nothing
is lost and nothing races. `SEND` latches the built length and streams
bytes with sof/eof.

**`KL_gptp_timer`** — see §5.

## 8. Servo

Implemented entirely in µcode (`prog_servo`, reached from the
Follow_Up handler). On each slave Sync+Follow_Up pair:

```
offset = t2_local − (preciseOrigin + correctionField
                     + meanLinkDelay + delayAsymmetry)

|offset| >  1 ms → step the PHC by −offset, clear the integrator
|offset| ≤ 1 ms → PI in Q8.24 addend units:
                    acc  += offset            (saturated ±2²³)
                    trim  = −((offset·86) >> 8) − ((acc·86) >> 12)
```

86/2⁸ ≈ 0.336 addend-LSB per ns: the proportional pole nulls a held
offset in ~3 beats at 8 Hz, `Ki = Kp/16`. One addend LSB is
1e9/(10·2²⁴) ≈ 5.96 ppb on a 100 MHz PHC. The integrator is *not*
reset by a re-announce from the same grandmaster (that bug pinned the
loop at proportional droop — see `BENCH_TAP_WIRETRUTH.md`).

## 9. Profile constants

802.1AS-2011 with the Milan v1.2 Table 4.1/4.2 profile, all in the
ROM image:

| constant | value | clause |
|---|---|---|
| `neighborPropDelayThresh` | 800 ns | 11.2.15.3 |
| `allowedLostResponses` | 3 | 11.5.3 |
| `announceReceiptTimeout` | 3 × 1 s | 10.6.3.2 |
| `syncReceiptTimeout` | 3 × 125 ms | 10.6.3.1 |
| pdelay / announce interval | 1 s | Milan Table 4.1 |
| sync interval | 125 ms (logInterval −3) | Milan Table 4.1 |
| our vector | p1 248, class 248, accuracy 0xFE, variance 0x436A, p2 248 | Milan 4.2.6.2.1 |
| step/slew boundary | 1 ms | ours (not a profile number) |
