[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/BENCH_OPERATIONS.md`
>
> Archived: 2026-09-01
>
> Current successor: [current manager guide](../../../MANAGER.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Bench operations — build, flash, tune, capture

The Arty A7-100T bench: MII gaskets + PHC + `KL_gptp_engine` + a 1 Hz
UART truth line, no SoC and no software. Everything here is procedure
and hard-won detail; what the bench *found* is in the `BENCH_*.md`
round documents.

## 1. Bitstreams

```sh
cd bench/arty
./build.sh                          # spec-strict: 800 ns threshold
THRESH=1500 ./build.sh              # tolerant, for an in-line TAP
P1=100 ./build.sh                   # force a BMCA win (priority1 = 100)
MAC=0x02A1B2C3D4E5 ./build.sh       # (positional --mac also accepted)
```

`build.sh` regenerates the µcode image with those parameters and runs
Vivado into `bench/arty/work/`. Two variants are kept side by side:

| file | threshold | when |
|---|---|---|
| `work/bench_arty_clean.bit` | **800 ns** (802.1AS-2011 11.2.15.3 / Milan) | direct link — the configuration of record |
| `work/bench_arty_tap.bit` | 1500 ns | the wire TAP is in-line (it adds ~730 ns per direction) |

Both are otherwise identical, including the calibration constants and
the runtime tuner. `Vivado 2026.1` is expected at
`~/Xilinx/2026.1/Vivado/settings64.sh` (override with `VIVADO_SETTINGS`).

Flash (volatile, SRAM):

```sh
openFPGALoader -b arty work/bench_arty_clean.bit
```

## 2. The UART line

115200-8N1, TX-only report once per second, plus an RX tuner (§3).

```
S=1A G=3CC0C6FFFEFE0210 P=3CC0C6FFFEFE0210 A=0000F6F820436AF8 F=0D
D=00000018 O=FFFFFFFE R=9A5C C=0000 Q=0079 E=0000 T=59AC Y=00000000
```

| field | width | meaning |
|---|---|---|
| `S` | 2 | seconds since reset, wrapping |
| `G` | 16 | grandmasterIdentity |
| `P` | 16 | parent (master port) clockIdentity |
| `A` | 16 | last **received** announce vector, raw `{utc, p1, cq, p2}` |
| `F` | 2 | flags — see below |
| `D` | 8 | meanLinkDelay, ns |
| `O` | 8 | last sync offset, ns, **signed** (two's complement) |
| `R` | 4 | RX frames delivered to the engine |
| `C` | 4 | CRC-bad frames (RX gasket) |
| `Q` | 4 | parser drops — **on the bench this counts all non-gPTP traffic too**: there is no EtherType classifier in front of the parser (the parent integration has one), so every flooded frame the MII gasket receives is counted here |
| `E` | 4 | event-queue drops |
| `T` | 4 | TX frames |
| `Y` | 8 | live delayAsymmetry readback, ns signed |

Flags (`F`): bit0 `gmPresent`, bit1 `amGm`, bit2 `asCapable`, bit3
`syncOk`. Common values:

| `F=` | state |
|---|---|
| `00` | not asCapable — no time transfer, pdelay only |
| `04` | asCapable, no grandmaster yet (the announce watch is running) |
| `05` | capable slave, adopted a GM, no Sync yet |
| `0D` | **capable slave, synced** — the servo is running |
| `07` | capable master (we are the grandmaster) |

**Open the port with `-hupcl` or the board resets on every open:**

```sh
stty -F /dev/ttyUSB3 115200 raw -echo -hupcl
cat /dev/ttyUSB3
```

Without `-hupcl`, DTR drops on close and the Arty restarts — every
capture becomes a fresh boot and tuner settings are lost.

**The port number moves.** The FTDI channels re-enumerate; the Arty
console has appeared as `ttyUSB0`, `ttyUSB1` and `ttyUSB3` on the same
bench. Probe rather than assume:

```sh
for p in 0 1 2 3; do stty -F /dev/ttyUSB$p 115200 raw -echo -hupcl 2>/dev/null
  echo "ttyUSB$p: $(timeout 4 dd if=/dev/ttyUSB$p bs=1 count=60 2>/dev/null | wc -c) bytes"; done
```

The bench line always starts `S=`.

**The 1 Hz report phase-locks to the 1 Hz protocol cadence.** A
sub-second role flap can therefore look like a stable role. Trust the
`T=` arithmetic: a stable master sends ~20 frames/s (8 Sync + 8
Follow_Up + 1 Announce + pdelay both roles), a stable slave ~3/s.
Anything between is a flap.

## 3. Runtime calibration tuner

The Arty's UART RX (pin A9) accepts one command per line, 8 hex
digits, CR-terminated — no rebuild needed:

| command | sets | default |
|---|---|---|
| `Y<8 hex>` | `delayAsymmetry`, signed ns (802.1AS-2011 10.2.4.5) | 0 |
| `I<8 hex>` | ingressLatency, ns (subtracted at the RX stamp) | 240 (`0xF0`) |
| `E<8 hex>` | egressLatency, ns (added at the TX stamp) | 105 (`0x69`) |

```sh
stty -F /dev/ttyUSB3 115200 raw -echo -hupcl
printf 'Y00000100\r' > /dev/ttyUSB3      # +256 ns asymmetry
printf 'YFFFFFF00\r' > /dev/ttyUSB3      # −256 ns (sign-extended)
printf 'I000000F0\rE00000069\r' > /dev/ttyUSB3   # restore defaults
```

Expected effects, both verified on hardware: changing `I`/`E` moves
`D=` by `(ΔI+ΔE)/2` on the next exchange; `Y` moves the sync offset
only and never `D=`. Any unexpected character aborts the line, so a
stray keystroke cannot half-apply a value.

Defaults come from TI AN-1507 (DP83848: transmit 5 bit-times, receive
25.5 bit-times fixed, sub-bit PVT) plus the gasket and synchronizer
cycle counts; the derivation and its TAP verification are in
`BENCH_TAP_WIRETRUTH.md`. On a bare link they should stay at default.

## 4. Wire capture (in-line TAP)

Two in-line TAPs live on the capture host; one interface taps the Arty↔peer segment.

```sh
ssh <capture-host> 'sudo -n timeout 60 tcpdump -i <tap-iface> \
    -w /tmp/cap.pcap -s 256; sudo -n chmod 644 /tmp/cap.pcap'
scp <capture-host>:/tmp/cap.pcap .
python3 bench/pcap_verdict.py cap.pcap
```

`-s 256` is enough for every 802.1AS frame plus the TAP header.
**BPF filters do not work** in live mode: the TAP's live mode prepends a
28-byte header, so the EtherType sits at offset 40, not 12. Capture
everything and let `pcap_verdict.py` classify — it detects the header
structurally (type word + duplicated length), never by a byte value
at a fixed offset, because the hardware timestamp marches through
every value including `0x88F7`.

The TAP's own cost: **~730 ns per direction** at 100BASE-TX (it
re-times through its own PHYs). That exceeds the entire 800 ns
threshold budget, so a spec-strict bitstream will correctly refuse an
in-line-TAP'd link — use `bench_arty_tap.bit` while a TAP is inserted,
and pull the TAP for final accuracy numbers (its unmeasured direction
asymmetry biases the offset).

Its timestamps are calibration-grade: they resolve the Arty's
hardware 1 s cadence with σ = 4 ns.

## 5. A standard session

```sh
# 1. suites must be green before the bench sees a bitstream
make

# 2. build and flash
cd bench/arty && ./build.sh && \
  openFPGALoader -b arty work/bench_arty.bit

# 3. watch (in another shell, with -hupcl already applied)
cat /dev/ttyUSB3

# 4. for a wire verdict, start the capture BEFORE flashing so the
#    boot sequence is in the trace
```

Expect, on a direct link to a healthy grandmaster: `F=00` for the
first seconds (no pdelay judged yet) → `F=04` when asCapable rises →
`F=05` on adopting the GM → `F=0D` within a beat of the first
Sync+Follow_Up, and `O=` converging to single-digit nanoseconds.

## 6. Bench-only RTL

`bench/arty/` is **not** the shipping tree — it exists so the engine
can meet a real PHY:

| file | role |
|---|---|
| `bench_arty_top.sv` | top: resets, PHY reference, timestamp points, engine, reporter, tuner |
| `bench_mii_rx.sv` | MII → byte stream, preamble/SFD hunt, CRC32 check, FCS strip, RX-SFD toggle |
| `bench_mii_tx.sv` | byte stream → MII, preamble/SFD, FCS append, 96-bit IFG, TX-SFD + done toggles |
| `bench_afifo.sv` | dual-clock FIFO, gray pointers, show-ahead read |
| `bench_phc.sv` | 64-bit ns clock, Q8.24 fractional accumulator, addend + step inputs |
| `bench_uart_report.sv` | the 1 Hz line |
| `bench_uart_tune.sv` | the RX tuner |

These are covered by `tb/verilator/gaskets` (81 checks) — added after
a gasket bug deadlocked the plane on the wire; see
`BENCH_TAP_WIRETRUTH.md`.

## 7. Known bench facts worth not rediscovering

- The board resets when the UART port is opened without `-hupcl`.
- A soft reset does **not** re-run µcode init: scratch is LUTRAM whose
  power-on zero *is* the init contract, so only reconfiguration
  (re-flashing) clears protocol state.
- `openFPGALoader` writes SRAM; power cycling loses the bitstream.
- The 1 Hz report and 1 Hz protocol cadence phase-lock (see §2).
- The STM32 peer used through 2026-08-15 has a clock-rate
  misconfiguration as grandmaster (+3470 ppm, measured two independent
  ways) and transmits Sync only intermittently; it is a good pdelay
  and BMCA peer but not a time reference.
