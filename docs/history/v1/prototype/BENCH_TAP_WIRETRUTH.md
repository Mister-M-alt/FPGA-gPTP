[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/BENCH_TAP_WIRETRUTH.md`
>
> Archived: 2026-09-01
>
> Current successor: [current manager guide](../../../MANAGER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Wire truth through the TAP — 2026-08-15, afternoon

Sequel to `BENCH_ASCAPABLE.md`. Two wire TAPs went in-line on
the lab bench; one TAP interface covers OUR
Arty↔STM32 link, the other taps an unrelated AVB pair. This round is
what independent wire-level ground truth bought us — including one
real deadlock our 1,183-check simulation surface could never have seen.

## The TAP itself, characterized

- **Live-mode framing**: each captured packet carries a 28-byte
  prepend — u32 type, u32 length, u32 TAP port (2/3 = direction), and
  a hardware timestamp stored as two LE u32 words high-first:
  `ts_ns = (u32le@12 << 32) | u32le@16`, 1 ns LSB. BPF filters miss
  (the EtherType sits at offset 40); `bench/pcap_verdict.py` handles
  the format natively and prefers the hardware stamps.
- **Timestamp quality**: our Arty's hardware 1 s pdelay cadence
  resolves to mean 1000.003 ms with a **4 ns standard deviation** —
  i.e. our XO measured at +2.748 ppm against the TAP clock. The
  STM32's software cadences wander by hundreds of µs against the same
  ruler (announce 998.5 ms, pdelay 996.3 ms).
- **Insertion latency**: the TAP's PHYs raised measured meanLinkDelay
  from ~750 ns to **~1550 ns**, and the asCapable ladder correctly
  un-participated the port (F=00, pdelay-only — 10.2.4.1 doing its
  job against a link that genuinely got worse). Bench builds through
  the TAP use `THRESH=2500 ./build.sh` (generator `--thresh`), a
  bench-only deviation from the 800 ns profile number, stated here.

## The verdicts the wire delivered

1. **1,520 YAML-pin checks green on 16 s of live link** — every field
   of every frame both nodes transmitted, judged by tsn-gen's
   packet_gen against the same 802.1AS YAML pins that judge the sim
   suites. The STM32's frames pass the pins too.
2. **Our pdelay response turnaround: 11 µs** against Milan's 15 ms
   allowance.
3. **The MII timestamp-point latency sum, measured**: TAP req→resp
   wire gap minus our (T3−T2) fields = **1186…1316 ns (mean 1242)**
   over 16 exchanges. The latency-calibration round scheduled by
   FIRSTLIGHT now has its input number from an independent instrument.
4. **The STM32's master Sync is intermittent, not absent**: the TAP
   caught genuine two-step Sync+Follow_Up bursts from it (~100 ms
   spacing, real preciseOrigin values) — and then hours of announcing
   GM with no Sync at all. v3's "absent or disabled" characterization
   upgrades to "intermittent"; the 375 ms sync-receipt aging remains
   the correct defense either way.

## The deadlock the TAP caught (and simulation could not)

With THRESH=2500/p1=248 the plane adopted the STM32 and ran the
375 ms-aging flap as designed — until, 37 s in, **our node went
completely mute mid-become-master**: the wire shows Sync seq 140 +
Follow_Up + a pdelay exchange at t=44.334…44.335, then the Announce
due 1 ms later never appears, and nothing of ours ever again. The
UART kept reporting F=07 with T= frozen: engine wedged, RX alive.

Root cause, from the capture timing: `bench_arty_top` fed the MII TX
gasket a **6-bit truncation of the 7-bit TX FIFO level**. A FIFO
holding exactly 64 words reads as level 0, so the gasket's start
condition (`level >= 8`) never fires: nothing drains, `tx_ready`
stays low, the µCPU's OP_SEND_RESP stalls its E-stage forever, and
dispatch — and with it every timer handler — halts. The trigger is a
back-to-back TX burst (become-master: Sync+FU+Pdelay_Req+Announce
inside 2 ms) that parks the FIFO at exactly 64 during the previous
frame's FCS/IFG window — a race that hit once in ~40 s of flapping.
The engine honored its backpressure contract throughout; the
bench-only gasket lied about the level. Fix: pass the full 7-bit
level. The 1,183-check sim surface covers the engine, not the bench
gaskets — exactly the seam the TAP was bought to watch.

## The soak, after the fix

234 s through the flap, TAP recording: **zero frozen seconds** — T=
advanced every single second through ~230 become-master bursts, each
exercising the race that previously killed the plane inside 17. On the
wire: **61,549 pin checks, 0 FAIL** across 4,230 frames; 1,168
Sync+Follow_Up pairs from us with the FU trailing its Sync by a
constant 8.6 µs; announce at 999.003 ms; pdreq at 1000.003 ms with
min = max at ns resolution; response turnaround 11 µs. The
timestamp-point latency sum reproduced at 1188…1314 ns (mean 1251),
and the PHC-rate cross-check closed: −2.79 ppm from FU origin deltas
vs +2.748 ppm from the cadence ruler — two independent derivations
agreeing to 0.04 ppm. The STM32 transmitted exactly ONE Sync in the
whole 4 minutes: its intermittency, quantified.

## The calibration round: timestamp points to the MDI plane

With the sum measured, the split comes from the PHY's own record and
the RTL's cycle counts. TI AN-1507 (SNLA084B) fixes the DP83848 at
100BASE-TX: **transmit 5 bit-times (50 ns) fixed**, **receive 25.5
bit-times (255 ns) fixed**, both < 1 bit-time PVT — and the DP83848
derives RX_CLK from the data, eliminating the 1..5 bit realignment
nondeterminism (which is why the TAP saw our cadence at 4 ns σ).
Adding the gasket and synchronizer arithmetic:

- **ingress** (RX latch is LATE): 255 ns PHY + 25 ns sync/latch mean
  − 40 ns (the RX gasket's toggle fires on the SFD-nibble edge, one
  MII clock before the 802.1AS-2011 11.3.9 timestamp point) =
  **INGRESS_NS_P = 240** (subtract).
- **egress** (TX latch is EARLY vs the wire): the first-data symbol
  hits the wire 2 MII clocks + 50 ns after the toggle edge (130 ns),
  minus the 25 ns latch sync = **EGRESS_NS_P = 105** (add).

Both are `bench_arty_top` parameters applied at the PHC latch points
(802.1AS-2011 8.4.3 ingressLatency/egressLatency shape). Prediction,
refereed by the TAP: the req→resp latency sum drops by exactly
INGRESS+EGRESS = 345 ns (≈1251 → ≈906 — the remainder being cable,
the TAP's own pass-through toward us, and the ±10 ns latch
quantization), and measured D drops by (INGRESS+EGRESS)/2 ≈ 172 ns.

**Measured**: the capture that spans the reconfiguration shows the
step exactly — uncompensated exchanges at 1214…1288 ns (mean 1246),
compensated ones at 827…939 (mean 892): **a 354 ns step against the
345 ns applied**, agreement inside the ±10 ns latch quantization.
The UART's D dropped 1495–1520 → ~1312 ns (−183 vs −172 predicted).
10,394 pin checks green on the same capture; the flap kept running
throughout. The ~890 ns residual is the cable, the TAP's own
pass-through toward our side, and the peer's share — not ours to
compensate. The constants are now traceable end to end: AN-1507's
fixed PHY latencies + RTL cycle counts in, an independently-measured
exact shift out.

## The tuner: calibration without rebuilds

The Arty's second UART direction (A9) now carries a runtime tuner
(`bench_uart_tune`): `Y<8 hex>` sets delayAsymmetry (signed ns, the
engine's new `cfg_asym_i` — 802.1AS-2011 10.2.4.5, applied in the
Follow_Up offset path via gather sel 2), `I`/`E` set the
ingress/egress latency registers live. The report line grew a `Y=`
readback field. Keep the port open across commands (`exec 3<>` — every
OPEN resets the board) and expect: `I`/`E` changes move `D=` by
(ΔI+ΔE)/2 on the next exchange — the same arithmetic the TAP verified
statically — while `Y` moves only the sync offset, never `D=`.

## First closed-loop hardware session — and the GM put on the scale

Late in the day the STM32 returned with master Sync ENABLED (10 Hz
two-step, real FU origins): **F=0D on the wire for the first time** —
gmPresent, asCapable, syncOk all up, offsets computed every beat, the
servo stepping (|o| > 1 ms) and PI-slewing live. It did not converge,
and the TAP proved precisely whose fault that is:

- the GM's **wire cadence is healthy**: sync every 124.57 ms, σ 540 µs;
- its **claimed origin timebase is broken**: between corrections it
  drifts at a steady −3445 ppm against the TAP clock (σ 46 µs — a
  precise wrongness, 0.34 %, no crystal does that), and ~once a second
  something steps it forward ~0.55 ms — a sawtooth that does not even
  cancel the drift. Detrended wander: σ 3.5 ms, ±10 ms peak.

Our measured offsets (median −0.66 ms, swinging to ±1.2 ms) are that
sawtooth, faithfully tracked. The slave loop is verified live; lock
quality is 100 % master-limited. For the Zephyr image: this signature
suggests the PTP clock's rate/addend constant is computed for a
different clock-tree frequency than the part is running, with a
periodic coarse corrector on top — fix the rate constant and the
sawtooth should collapse to crystal-level ppm our PI can null.

## The lock — 2026-08-15, end of day

The AVB switch (3C:C0:C6, p1=246) took the domain, the clean
spec-threshold bitstream went on the bare 5 ns link, and after two
same-day µcode fixes the switch exposed (the same-GM integrator reset;
the negative-quantization clamp) the servo delivered the number this
plane was built for:

**Offset from GM: mean −0.3 ns, σ = 3.3 ns, worst excursion 8 ns,
over 136 consecutive locked seconds** — F=0D unbroken from second
four, acquisition +1271 → ±ns in ~10 beats, D steady at 21–27 ns,
zero CRC, zero drops, the strict 802.1AS-2011/Milan profile with no
deviations, on the 3,011-LUT µcoded plane whose every protocol
behavior is ROM words. Two independently calibrated timestamp planes
(our AN-1507 constants, the switch's own) agreeing a patch cable is
two dozen nanoseconds — and a PI servo holding their clocks together
at crystal-jitter scale.

## Re-verified on the audited µcode — 2026-08-16

The lock above was measured before the FSM conformance audit. Repeated
with **v5** (MDSyncReceive sequence pairing, PortAnnounceReceive
qualification, the incumbent-portPriority comparison,
neighborRateRatio, the domainNumber drop) on the same bench, same
spec-strict 800 ns bitstream:

| | pre-audit (a4a6124) | v5 audited (bc2d201) |
|---|---|---|
| offset mean | −0.3 ns | **+0.01 ns** |
| offset σ | 3.3 ns | **3.20 ns** |
| worst \|offset\| | 8 ns | **9 ns** |
| locked seconds | 136 | **168 of 179** (rest is boot) |
| meanLinkDelay | 21–27 ns | 0–11 ns (mean 5.3) |
| CRC / event drops | 0 / 0 | **0 / 0** |

Two things this run proves that the earlier one could not:

1. **MDSyncReceive pairing interoperates.** The µcode now refuses any
   Follow_Up that does not carry its pending Sync's `sequenceId` — and
   the switch's stream pairs correctly, so the lock is unaffected. A
   conformance gate that had only ever been exercised by our own
   harness now holds against commercial silicon.
2. **The near-zero-link clamp is load-bearing in the steady state.**
   `D` now reads 0–11 ns (the earlier 21–27 was before the last
   calibration touch); individual exchanges land at or below zero and
   the clamp keeps asCapable up instead of flapping.

One counter moved and is worth explaining rather than hiding: parser
drops (`Q=`) rose from 1.13/s to 3.31/s between the two runs. That is
**not** the new domainNumber check rejecting traffic we used to
process — delivered frames rose by the same amount (`R` +2.14/s vs `Q`
+2.18/s), i.e. every extra drop is an extra *arriving* frame, and the
bench feeds the parser everything the MII gasket receives because it
has no EtherType classifier in front of it (the parent integration
does). The switch simply floods more non-gPTP multicast now that more
devices sit on it. The decisive argument: we are *locked to the
switch*, so its gPTP is domain 0 and the check cannot be touching it.

## What's next

- The servo's LOCK-QUALITY verdict (loop activity is now proven live)
  waits on a GM whose own clock holds together — the repaired Zephyr
  image, a second Arty, or a host-stack PTP box.
- Feed the measured ~1.25 µs timestamp-point latency sum into the
  ingress/egress latency constants (the calibration round proper),
  splitting RX from TX via a second measurement with roles swapped.
- A bench-gasket testbench, so the next gasket bug dies in simulation
  instead of on the wire.
