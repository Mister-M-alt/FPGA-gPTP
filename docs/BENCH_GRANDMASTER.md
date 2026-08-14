<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# The grandmaster round on the bench — 2026-08-14, evening

Sequel to `BENCH_FIRSTLIGHT.md`. The peer's missing Sync was diagnosed by
the spec (802.1AS-2011 5.3.1/10.1.2: a node that never transmits Announce
never enters the best-master contest), so µcode v3 added Grandmaster
Capability — BTCA, PortAnnounceTransmit with the path trace TLV, two-step
Sync + Follow_Up as master — and the bench ran the election both ways
against the STM32 on the direct Arty link.

## Build 1 — equal vectors, identity tiebreak (default p1=248)

```
S=04 G=0280E1FFFE6F14AB P=0280E1FFFE6F14AB A=0025F8F8FE436AF8 F=01 D=2C6 ...
```

The new A= field shows the STM32's announced vector verbatim: utc 37,
priority1 248, clockQuality 0xF8FE436A, priority2 248 — byte-identical to
our own Milan-default vector, so BTCA fell through to the
grandmasterIdentity tiebreak, its 0280E1… beat our 02A1B2…, and we
correctly adopted (F=01, not master). Even as the winning GM the STM32
sent no Sync (R stayed at announce+pdelay only).

## Build 2 — forced win (`P1=100 ./build.sh`)

```
S=04 G=02A1B2FFFEC3D4E5 P=02A1B2FFFEC3D4E5 A=0025F8F8FE436AF8 F=03 ...
S=05 ... T=001E   (T +20/s from here on)
```

- Its announce arrived, our p1=100 rejected it, become-master ran:
  **F=03, GM = us**.
- **T = +20/s**: 8 Sync + 8 Follow_Up + 1 Announce + pdelay, all
  µcode-built, every second — the full 10.2.8/10.2.11/10.3.13 transmit
  set live on the wire.
- **R fell from +4/s to +3/s and stayed there: the STM32 stopped
  announcing.** Its BMCA accepted the better vector and yielded, while
  its pdelay kept running both ways (D= live at ~700–750 ns throughout).

## Verdicts

1. **Bidirectional BMCA interop with third-party silicon**: we yield on
   the identity tiebreak (build 1); it yields to a better priority
   (build 2). Both transitions clean, no protocol errors, zero CRC/drop
   counters moving.
2. **The peer's characterization is complete**: the ST stack is a correct
   BMCA participant and pdelay responder/initiator, but master-side Sync
   transmission is absent or disabled — it never synced as the winning
   GM (build 1) and went correctly quiet as the loser (build 2). Time
   transfer on this bench therefore runs with OUR node as GM — the
   direction Milan wants anyway (talkers shall be GM-capable,
   Milan 4.3.1.1).
3. Whether the STM32's clock now locks to our Sync is observable only on
   its side; from our wire everything it needs is present and

   spec-shaped.

## Engineering note

The 78-check engine suite caught a real dispatch race while building this
round: back-to-back events in the queue clobbered the µCPU's preload
operands mid-handshake and silently ate the second event (become-master
ran with a TX-timestamp event's registers). The fix is a proper
valid/accept handshake on dispatch — found in simulation, before the
bitstream, which is the whole point of the suite.

## What's next for the µcode

BTCA is the two-node subset (stepsRemoved tiebreaks out), asCapable is
not yet computed (we answer/initiate pdelay unconditionally), receipt
timeouts cover announce only (sync/followUp timeouts pending), and the
servo is still observe-only. Those, plus latency calibration for the MII
timestamp points, are the next rounds — each is µcode ROM words, not
LUTs (539 of 1,024 words used).
