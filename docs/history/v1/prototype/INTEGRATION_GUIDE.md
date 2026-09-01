[OBSOLETE + 2026-09-01]

> Status: Historical
>
> Original path: `docs/INTEGRATION_GUIDE.md`
>
> Archived: 2026-09-01
>
> Current successor: [current integration guide](../../../INTEGRATION.md)

<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Deploying the gPTP engine on an FPGA — step by step

For the integrator putting `KL_gptp_engine` into a real design, and the
developer bringing it up on real silicon. Every number here is measured
or derived from the sources; every step says how to tell it worked.

Worked instantiation: `examples/gptp_integration_ref.sv`
(lint-clean; a reference skeleton, not part of the verified IP).
Working end-to-end example: `bench/arty/` (100BASE-TX on an Arty
A7-100T, verified on hardware).

**Time budget for a first bring-up:** an afternoon if your MAC already
gives you timestamps; a day if you have to build the timestamp path.

---

## Step 0 — Decide the shape before you wire anything

Four decisions drive everything else.

| decision | options | consequence |
|---|---|---|
| **Line rate** | 100 Mbit/s or 1 Gbit/s FDX | at 1 Gbit the RX face needs classification or a faster clock — step 5 |
| **Engine clock** | ≥ 100 MHz recommended | `CLK_HZ_P` must be the true frequency **and a whole number of MHz** (it divides to the 1 ms tick) |
| **Role** | GM-capable endpoint, or slave-only | sets `--p1` (priority1) at µcode build time |
| **Profile** | plain 802.1AS-2011, or Milan v1.2 | the shipped constants are Milan-compatible; `--thresh` is the only knob you would normally touch |

The IP is a **single-port time-aware end station**. Bridge/multi-port
state machines are deliberately not implemented — see
`FSM_CONFORMANCE.md` for the exact list.

---

## Step 1 — Take the sources

Six files are the IP. Everything else in the repository is testbench,
bench, tooling or documentation.

```
hdl/ucpu/gptp_ucpu_pkg.sv       # µISA package — compile FIRST
hdl/ucpu/KL_gptp_ucpu.sv
hdl/wire/KL_gptp_rx_parser.sv
hdl/wire/KL_gptp_tx_slot.sv
hdl/common/KL_gptp_timer.sv
hdl/top/KL_gptp_engine.sv       # the top you instantiate
hdl/ucode/gen_gptp_ucode.py     # generates the ROM image (build tool)
```

No vendor primitives, no IP cores, no clock generators, no external
dependencies. SystemVerilog-2012, one clock domain.

---

## Step 2 — Verify in *your* environment before integrating

```sh
make            # 1,297 checks across five suites + lint  (needs verilator)
make ooc        # Vivado out-of-context measurement on your part
```

Expect `exit 0` and, on `xc7a100t-2` at 100 MHz: **3,029 LUT, 2,398 FF,
1.5 BRAM, 4 DSP, +1.898 ns slack**. If your part is smaller/slower,
this is the moment to find out — not after the SoC is wired.

---

## Step 3 — Generate the µcode image

The protocol lives in a ROM image, not in the RTL. Build it with your
own identity:

```sh
python3 hdl/ucode/gen_gptp_ucode.py \
        -o gptp_ucode.hex \
        --mac 0x02A1B2C3D4E5 \      # YOUR port MAC — mandatory
        --p1 248 \                  # priority1: 248 = Milan GM-capable default
        --thresh 800                # neighborPropDelayThresh, ns
```

| flag | meaning | when to change it |
|---|---|---|
| `--mac` | your port's MAC. Becomes `clockIdentity` as EUI-64 (`MAC[47:24] ‖ FF-FE ‖ MAC[23:0]`), the source MAC of every frame, and the BMCA tiebreak | **always** — two nodes with the same identity cannot elect |
| `--p1` | announced `priority1`. Lower wins | 246–250 to bias the election; 255 = never grandmaster |
| `--thresh` | `neighborPropDelayThresh` in ns (11.2.15.3) | only for a link with real added latency (e.g. an in-line TAP). The spec/Milan number is 800 |

Output: 1024 lines of 12 hex digits, plus a report of ROM occupancy
(currently 849/1024) and where the shared legs were packed.

**Getting the image into your synthesis flow** — pick one:

1. *Absolute path* (simplest): pass `UCODE_HEX_P` as an absolute path.
2. *Design source*: add `gptp_ucode.hex` to the project so the tool
   finds it (Vivado searches the run directory; a non-project flow
   resolves relative paths against the working directory — the bench
   `cd`s into `work/` and generates the hex there).
3. *Generated at build time*: call the generator from your build
   script, as `bench/arty/build.sh` does, so the MAC and profile can
   never drift from the bitstream.

> The ROM is loaded with `$readmemh` in an `initial` block. It becomes
> BRAM content in the bitstream — there is no run-time load path and no
> processor to load it.

---

## Step 4 — Instantiate

```systemverilog
KL_gptp_engine #(
    .UCODE_HEX_P ("/abs/path/gptp_ucode.hex"),
    .CLK_HZ_P    (100_000_000)          // MUST match clk_i, whole MHz
) u_gptp (
    .clk_i (clk), .rst_n (rst_n),
    // wire faces ................................. step 5
    .rx_valid_i, .rx_data_i, .rx_sof_i, .rx_eof_i, .rx_err_i, .rx_ts_i,
    .tx_valid_o, .tx_data_o, .tx_sof_o, .tx_eof_o, .tx_ready_i,
    .txts_valid_i, .txts_ns_i, .txts_seq_i (16'd0),
    // clock ...................................... step 7
    .phc_ns_i, .phc_addend_we_o, .phc_addend_o,
                .phc_step_we_o,   .phc_step_o,
    // management ................................. step 8
    .cfg_asym_i,
    .pub_gm_id_o, .pub_parent_id_o, .pub_flags_o, .pub_pdelay_ns_o,
    .pub_offset_o, .pub_annq_o, .pub_asinfo_o, .pub_nrr_o, .pub_commit_o,
    // unused base-ISA effect strobes — leave open
    .eff_nvm_stb_o (), .eff_nvm_mark_o (),
    .eff_notify_stb_o (), .eff_notify_class_o (),
    // observability .............................. step 11
    .dbg_rx_drop_o, .dbg_ev_drop_o, .dbg_busy_o, .dbg_status_o
);
```

Compile `gptp_ucpu_pkg.sv` before anything that imports it.

---

## Step 5 — The wire faces

### RX (into the engine)

| requirement | why |
|---|---|
| **DA first**, one byte per clock, `rx_sof_i` with the first byte, `rx_eof_i` with the last | the parser counts absolute byte offsets |
| **FCS checked and stripped** by your MAC | the engine has no CRC |
| `rx_err_i` on the last byte aborts the frame | counted, no event raised |
| **one frame at a time**, no interleaving | single message bank |
| **no backpressure** — the engine always accepts | you own rate matching |

The parser itself drops anything that is not gPTP (EtherType ≠ 0x88F7,
`transportSpecific` ≠ 1, `versionPTP` ≠ 2, `domainNumber` ≠ 0), counted
in `dbg_rx_drop_o`. So a classifier is *optional for correctness* —
but not for throughput:

> **The rate rule.** The RX face consumes **one byte per engine clock**.
> At 100 MHz that is 100 MB/s.
> * 100BASE-TX = 12.5 MB/s → 8× headroom, feed it everything.
> * 1000BASE-T = 125 MB/s → **exceeds 100 MB/s.** Either clock the
>   engine ≥ 125 MHz, or classify upstream so only 0x88F7 frames reach
>   it (gPTP is ~20 frames/s — nothing).

Put a small FIFO between MAC and engine to absorb bursts and cross
clock domains (the bench uses a 64-entry async FIFO;
`bench/arty/bench_afifo.sv`).

### TX (out of the engine)

`tx_valid_o` / `tx_data_o` / `tx_sof_o` / `tx_eof_o` with `tx_ready_i`
backpressure — the serializer advances only when ready. Your MAC adds
preamble, SFD and FCS. Only **one frame is ever outstanding**
(dispatch is gated on the serializer being idle), so no arbitration
is needed inside the engine — but if you share the MAC with other
traffic, gPTP frames must not be reordered relative to their egress
timestamps.

---

## Step 6 — Timestamps (the part that decides your accuracy)

### What the engine expects

| port | meaning |
|---|---|
| `rx_ts_i[63:0]` | ingress time of the frame being delivered, **stable while `rx_sof_i` is high** (the engine latches it there) |
| `txts_valid_i` + `txts_ns_i[63:0]` | egress time of the frame just transmitted, one pulse per frame |

Both are free-running nanoseconds from the same PHC as `phc_ns_i`.

### The timestamp point, and why it must be compensated

802.1AS measures time at the **MDI reference plane** (8.4.3) — the
connector, not your logic. Your capture point is somewhere inside the
MAC/PHY, so:

```
rx_ts_i  = PHC_at_capture − ingressLatency     (capture is LATE)
txts_ns_i = PHC_at_capture + egressLatency      (capture is EARLY)
```

Derive the two constants from your PHY's datasheet plus your own RTL:

1. **PHY fixed latency** — a good datasheet states it. The bench's
   DP83848 at 100BASE-TX: transmit 5 bit-times (50 ns), receive
   25.5 bit-times (255 ns), both sub-bit PVT (TI AN-1507).
2. **Your gasket/synchronizer cycles** between the real SFD and the
   moment you latch the PHC — count them in the RTL.
3. Add them. The bench lands on **ingress 240 ns, egress 105 ns**; the
   derivation is in `BENCH_TAP_WIRETRUTH.md`.

### How to know you got it right

The engine publishes `meanLinkDelay` every second. On a direct link it
should equal the **cable propagation delay only** — about **5 ns per
metre** of Cat5e. The bench measures 0–11 ns on a short patch cable
after calibration, against 750 ns before it.

Three ways to verify, best first:

* **Two calibrated nodes, short cable** — `meanLinkDelay` should be a
  few nanoseconds. This is the strongest check because a symmetric
  error in *both* constants still shows up.
* **An in-line TAP with hardware timestamps** — compare the TAP's
  observed request→response gap against the `t3−t2` your node reports;
  the difference is your ingress+egress sum. (An in-line TAP adds
  ~730 ns per direction, so raise `--thresh` while it is inserted.)
* **A known-good peer** (a commercial AVB switch) — if its
  `meanLinkDelay` and yours agree, both timestamp planes agree.

> **Mandatory: every transmitted frame must return an egress
> timestamp.** The µcode holds a "which TX is pending" flag and will
> not build the next frame until the stamp arrives; a permanently lost
> stamp stalls transmission until reset. If your TX path can drop
> frames, add a watchdog that fabricates a stamp (or asserts
> `txts_valid_i` late) rather than losing it.

---

## Step 7 — The PHC and its two knobs

### What you must provide

`phc_ns_i` — a free-running 64-bit nanosecond counter, incremented
from the same clock domain, with a **fractional accumulator** so it can
be rate-adjusted smoothly (the bench uses Q8.24;
`bench/arty/bench_phc.sv` is 40 lines and works).

### What the engine drives

| knob | format | semantics |
|---|---|---|
| `phc_addend_we_o` + `phc_addend_o[31:0]` | **signed Q8.24 nanoseconds per tick** | rate trim, *replaces* the previous value (not cumulative) |
| `phc_step_we_o` + `phc_step_o[63:0]` | **signed nanoseconds** | one-shot phase jump, added once |

At 100 MHz the base increment is 10 ns/tick = `10 << 24`, so one
addend LSB is `2⁻²⁴ ns/tick` = **5.96 ppb**.

### If your PHC's rate register is a different format — read this

The servo's gains are expressed in *those* units:

```
trim = −((offset·86) >> 8) − ((acc·86) >> 12)      [Q8.24 ns/tick]
```

`86/2⁸ ≈ 0.336` addend-LSB per nanosecond of offset. If you hand that
number to a knob with different scaling, your loop gain is wrong by
that ratio — it will converge slowly, or ring, or diverge. Two fixes:

1. **Rescale in fabric** (preferred): a shift or a small multiply on
   `phc_addend_o`. See `ADDEND_SHL_P` in the reference wrapper. It
   changes at most 8 times a second — cost is nothing.
2. **Re-tune the µcode**: `KP_NUM/KP_SHR` and `KI_NUM/KI_SHR` in
   `gen_gptp_ucode.py`, keeping `Ki = Kp/16`. Re-run the engine suite;
   its closed-loop arm will tell you if the loop still converges.

The step/slew boundary (`STEP_THRESH_NS`, 1 ms) is independent of
scaling.

---

## Step 8 — The management surface

Eight published words become your CSR window; the full map, with the
AVDECC/Milan consumer of each and the CSR it replaces, is
`MGMT_INTERFACE.md`. The reference wrapper implements a plain 32-bit
read window plus the one writable word:

* `cfg_asym_i` — `delayAsymmetry` (10.2.4.5), signed ns. **Only the
  slave side of a link may apply it**, or the correction doubles.
  Leave it 0 unless you have measured an asymmetric link.

`pub_commit_o` pulses after each coherent group of updates; latch on it
or free-run — every word is written in a single cycle.

---

## Step 9 — Reset, clocking and one contract that will bite you

* **Single clock domain.** All CDC belongs outside the engine.
* **`rst_n` is synchronous-release, active low.** Hold it until your
  PHY reference clock is stable.
* **The LUTRAM power-on contract.** The message bank and scratch RAM
  are distributed RAM with **no reset** — the bitstream's initial
  contents *are* the reset, and the µcode's init-once flag depends on
  power-on zero. This is guaranteed by FPGA configuration.
  Consequences:
  * a **soft reset does not re-run µcode init** — protocol state
    survives `rst_n`; only reconfiguration clears it;
  * on a flow that does **not** guarantee zeroed RAM (some partial
    reconfiguration flows, or an ASIC port), you must add an explicit
    clear sequence or change `S_INIT` to a resettable flop.
* **Timing.** Nothing inside needs false paths or multicycles. The
  design closed +1.898 ns at 100 MHz OOC with no floorplanning.

---

## Step 10 — Synthesize and sanity-check

Non-project Vivado, straight from the bench's own script:

```tcl
read_verilog -sv [list \
  hdl/ucpu/gptp_ucpu_pkg.sv hdl/ucpu/KL_gptp_ucpu.sv \
  hdl/wire/KL_gptp_rx_parser.sv hdl/wire/KL_gptp_tx_slot.sv \
  hdl/common/KL_gptp_timer.sv hdl/top/KL_gptp_engine.sv ]
synth_design -top <your_top> -part <your_part>
```

Check three things in the reports before you go near hardware:

1. **BRAM inferred for the ROM** — 1.5 tiles (1×RAMB36 + 1×RAMB18). If
   you see LUTRAM instead, `$readmemh` did not find your hex file and
   the ROM is being optimised away.
2. **4 DSPs** for the multiplier. Fewer means the `use_dsp` attribute
   was overridden; harmless but it costs LUTs.
3. **No latches, no critical warnings.**

---

## Step 11 — Bring-up, in the order things should happen

Watch `pub_flags_o` (bits: 0 `gmPresent`, 1 `amGm`, 2 `asCapable`,
3 `syncOk`) and `pub_pdelay_ns_o`. On a link to a healthy peer:

| # | expect | within | if it does not happen |
|---|---|---|---|
| 1 | a **Pdelay_Req** leaves your port, then one every second | ~1.5 s of reset release | nothing transmits → see T1 below |
| 2 | `pub_pdelay_ns_o` becomes non-zero and sane (a few ns to a few hundred) | after the first complete exchange | T2 |
| 3 | `asCapable` (bit 2) rises | one cadence *after* step 2 — it judges the previous interval | T3 |
| 4 | Announces are accepted / transmitted; `gmPresent` or `amGm` sets | ≤ 3 s (announceReceiptTimeout) | T4 |
| 5 | as slave: `syncOk` (bit 3) sets and `pub_offset_o` starts moving | one Sync+Follow_Up pair | T5 |
| 6 | `pub_offset_o` converges toward zero | a few beats (step) then seconds (slew) | T6 |

Instrument these four outputs from day one — every failure below was
diagnosed with them:

* `dbg_rx_drop_o` — parser drops (also counts non-gPTP traffic if you
  did not classify).
* `dbg_ev_drop_o` — **event-queue overflow. Should always be 0.**
* `dbg_busy_o` — µCPU executing.
* `dbg_status_o` — µCPU status code.

---

## Step 12 — Troubleshooting

| # | symptom | likely cause | check / fix |
|---|---|---|---|
| **T1** | nothing is ever transmitted | ROM not loaded (`$readmemh` path), or `CLK_HZ_P` ≠ real clock so the ms tick never fires, or your TX face never asserts `tx_ready_i` | confirm BRAM inferred (step 10.1); check the timer's tick in simulation; scope `tx_valid_o` |
| **T2** | `meanLinkDelay` stays 0 or is absurd (µs, or huge) | timestamps not wired, wrong units (must be **ns**), or ingress/egress swapped | feed a known constant into `rx_ts_i` in simulation and check the arithmetic |
| **T3** | `asCapable` never rises, or flaps | delay exceeds `--thresh`; more than one responder; the peer's Follow_Up is missing | read `pub_pdelay_ns_o` — if it is ~750 ns you have not calibrated (step 6); if a TAP is in-line, raise `--thresh` |
| **T4** | never adopts a grandmaster | announce qualification rejected it: `stepsRemoved ≥ 255`, the announce is from your own identity (MAC collision!), or a path-trace loop | check `pub_annq_o` — it publishes the *received* vector even when unqualified |
| **T5** | `syncOk` never sets although Sync arrives | Follow_Up not paired: its `sequenceId` must match its Sync (11.2.13). A peer that renumbers, or a lost Sync, will not pair | capture the wire; compare `sequenceId` of Sync and Follow_Up |
| **T6** | offset does not converge, or oscillates | PHC rate-knob scaling ≠ Q8.24 ns/tick (step 7); or the grandmaster's own clock is broken | verify with a step: write a known addend and measure the resulting ppm. On the bench a peer was found running +3470 ppm as GM — measure *its* rate before blaming the loop |
| **T7** | transmission stops permanently after a while | an egress timestamp was lost — the pending flag never clears | add a TX watchdog (step 6) |
| **T8** | `dbg_ev_drop_o` non-zero | events arriving faster than they are handled; usually a TX face that stalls dispatch | ensure `tx_ready_i` is not held low for long periods |
| **T9** | works, then stops after `rst_n` pulse | expected: a soft reset does not re-run µcode init (step 9) | reconfigure, or make `S_INIT` resettable |

---

## Step 13 — Porting notes

**To 1000BASE-T.** Two changes: satisfy the rate rule (step 5), and
re-derive the timestamp constants — a gigabit PHY's latencies differ
from a 100 Mbit one, and the bit time is 8 ns instead of 10. The
protocol, the µcode and the profile constants are unchanged.

**To another FPGA family.** No vendor primitives are used. Confirm
(a) distributed RAM initialises to zero at configuration (step 9),
(b) `$readmemh` in an `initial` block is honoured by your synthesiser
for ROM inference, (c) the DSP inference attribute is respected or
harmlessly ignored.

**To an ASIC.** Replace the LUTRAM power-on contract with an explicit
init sequence, and provide the ROM as a compiled memory or a ROM
generator instead of `$readmemh`.

**Adding a second port** (becoming a bridge) is *not* a wiring
exercise: the multi-port state machines named in `FSM_CONFORMANCE.md`
would have to be written first.
