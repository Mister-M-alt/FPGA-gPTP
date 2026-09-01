[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/BENCH_ASCAPABLE.md`
>
> Archived: 2026-09-01
>
> Current successor: [current manager guide](../../../MANAGER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# The asCapable round on the bench — 2026-08-15

Sequel to `BENCH_GRANDMASTER.md`. µcode v4 brought the asCapable ladder,
the sync receipt watch and the closed servo to the same Arty↔STM32
direct link; the bench ran both election directions again. Method note
first: **opening the UART port resets the board**, so every capture is
a fresh boot — and the 1 Hz report phase-locks to the protocol's 1 Hz
cycles, so a sub-second role flap can masquerade as a stable role.
The `T=` (TX frames/s) arithmetic is what tells the truth below.

## Build 1 — equal vectors, identity tiebreak (default p1=248)

```
S=02 ... F=04 D=00000000 ... R=0007 Q=0007 T=0001
S=03 G=0280E1FFFE6F14AB P=0280E1FFFE6F14AB A=0025F8F8FE436AF8 F=05 D=2FD ...
S=04 ... F=05 D=2FD R=+4/s T=+14/s        (steady for the full 60 s)
```

1. **asCapable rises exactly per the ladder** (F=04 before any
   announce business): the first pdelay exchange completes, the next
   cadence judges it — one Resp+FU, 765 ns ≤ 800 ns — and only THEN is
   the announce receipt watch armed. Before that the port is not in
   the BMCA, per 10.3.11.
2. **Adopt on the identity tiebreak** as in v3: equal Milan vectors,
   its 0280E1… beats our 02A1B2… (F=05 = gmPresent|asCapable).
3. **The sync receipt watch does its job, once per second, forever**:
   the STM32 never transmits Sync as GM, so 375 ms after each of its
   announces we age it out (10.3.12 AGED) and take the master role;
   its next announce (better vector) re-elects it. The 1 Hz samples sit
   phase-locked in one window — F=05 on this boot, F=07 on another —
   but T=+14/s is the flap's fingerprint: ~625 ms of mastership buys
   ~5 Sync + ~5 Follow_Up + 1 Announce, plus our pdelay req and the
   resp+FU we answer, ≈ 14 frames/s. A stable slave would send 3/s; a
   stable master 20/s. R=+4/s confirms the peer stays fully active
   (announce + pdelay both ways). O= stays 0 and syncOk never rises:
   time never flows from that GM. This is the spec-correct treatment
   of a sync-less master — the pathology is the peer's, and v4 now
   refuses to sit under it quietly where v3 did.

## Build 2 — forced win (`P1=100 ./build.sh`)

```
S=02 ... F=00 R=0007 T=0001
S=03 ... F=00 D=2DA                        (exchange done, ladder pending)
S=04 G=02A1B2FFFEC3D4E5 P=02A1B2FFFEC3D4E5 F=07 T=+20/s from here
S=3D ... F=07 D=2DA R=+3/s T=+20/s         (steady through 60 s)
```

- **Mastership arrives through the NEW path, faster than v3**: adopt
  its announce at ~3.3 s (only possible once asCapable — the F=00 at
  S=03 with D already measured shows the gate holding), sync receipt
  watch expires 375 ms later, become-master at ~3.7 s — before the 3 s
  announce timeout would have fired. Our p1=100 announces then win its
  BMCA and it goes correctly quiet (R falls to +3/s, pdelay only).
- **F=07 = gmPresent | amGm | asCapable, held for the full minute**,
  with D re-measured every second at 730–770 ns — live proof the
  ladder keeps judging every interval and the link sits under the
  800 ns Milan threshold with ~40 ns of real jitter.
- **T=+20/s**: 8 Sync + 8 Follow_Up + 1 Announce + our Pdelay_Req +
  the Resp+FU answering its initiator — the complete
  10.2.8/10.2.11/10.3.13 master set, µcode-built, byte-validated in
  sim by both the 116-check suite and tsn-gen's independent decode.
- Zero CRC errors (C=0000), zero event drops (E=0000) in every
  capture; Q freezes at 7 non-88F7 boot frames and never moves again.

## What this round could NOT prove on this bench

The closed-loop servo needs a master that sends Sync, and this peer
does not — O= never moved off zero in either build. The servo's
verdict therefore rests on the simulation evidence (bit-exact PI
mirror, step behavior, convergence against a detuned modeled PHC:
3 ms initial offset → 777 ns residual, trim landing within 8 % of the
injected detune) until a sync-transmitting GM is on the link. That
peer — another Arty running this same bitstream, or a host-stack PTP box — is
the natural next bench.

## What's next for the µcode

Sync↔Follow_Up sequence pairing (the FU handler currently accepts any
FU while slave), stepsRemoved in the BTCA compare, neighborRateRatio
into the pdelay computation, and the MII timestamp-point latency
calibration the FIRSTLIGHT round already named. Each is ROM words
(676/1,024 used).
