// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// Bench MII gasket loopback suite — the seam the engine suites do not
// cover, where the wire TAP found a real deadlock (TX FIFO level
// truncated 7->6 bits: a full FIFO read as level 0 and the gasket never
// started). Checks, at the bench_arty_top clock ratio (sys 100 MHz,
// MII 25 MHz):
//
//   1  byte-exact loopback across the size range 60..128, sof/eof
//      placement, per-frame SFD toggles on both gaskets
//   2  20 back-to-back frames pushed at full sys rate: all delivered,
//      inter-frame gap >= 24 MII clocks (96 bit-times, 4.2.3.2.2)
//   3  THE WEDGE REGRESSION: a >=64-byte frame blasted into the FIFO
//      during the previous frame's FCS/IFG window parks the level at
//      exactly 64 — the gasket must still start (the old 6-bit level
//      port wedged here forever)
//   4  a corrupted frame fails FCS: crc_bad counts, nothing clean
//      emerges for it

#include <cstdint>
#include <cstdio>
#include <vector>
#include <verilated.h>
#include "Vgasket_tb_top.h"

static Vgasket_tb_top *dut;
static uint64_t half_ns = 0;              // advances 5 ns per sys half
static int checks = 0, fails = 0;

static void expect(const char *what, uint64_t got, uint64_t exp) {
  checks++;
  if (got != exp) {
    fails++;
    printf("FAIL %-30s got %llu exp %llu\n", what,
           (unsigned long long)got, (unsigned long long)exp);
  }
}

struct RxWord { uint8_t data; bool sof, eof, err; };
static std::vector<RxWord> rxw;
static uint64_t idle_mii = 0;             // MII clocks with en low
static uint64_t min_gap = ~0ull;          // min idle gap between frames
static bool en_prev = false;
static bool seen_first_frame = false;

static void tick() {                      // one sys clock (10 ns)
  for (int h = 0; h < 2; h++) {
    half_ns += 5;
    dut->sys_clk_i = !dut->sys_clk_i;
    if (half_ns % 20 == 0) {
      dut->mii_clk_i = !dut->mii_clk_i;
      if (dut->mii_clk_i) {               // MII posedge bookkeeping
        if (dut->mii_en_o) {
          if (!en_prev && seen_first_frame && idle_mii < min_gap)
            min_gap = idle_mii;
          if (!en_prev) idle_mii = 0;
          seen_first_frame = true;
        } else if (seen_first_frame) {
          idle_mii++;
        }
        en_prev = dut->mii_en_o;
      }
    }
    dut->eval();
    if (dut->sys_clk_i && half_ns % 10 == 5) {
      if (dut->rx_valid_o)
        rxw.push_back({dut->rx_data_o, !!dut->rx_sof_o,
                       !!dut->rx_eof_o, !!dut->rx_err_o});
    }
  }
}

static void run(uint64_t n) { while (n--) tick(); }

// push one frame at full sys rate, honoring tx_ready backpressure;
// a bounded wait so a wedged gasket FAILS the suite instead of
// hanging it (the ready starvation IS the deadlock's symptom)
static int push_timeouts = 0;
static void push_frame(const std::vector<uint8_t> &b) {
  uint64_t stall = 0;
  for (size_t i = 0; i < b.size();) {
    dut->tx_valid_i = 1;
    dut->tx_data_i = b[i];
    dut->tx_sof_i = (i == 0);
    dut->tx_eof_i = (i + 1 == b.size());
    bool ready = dut->tx_ready_o;
    tick();
    if (ready) { i++; stall = 0; }
    else if (++stall > 100000) { push_timeouts++; break; }
  }
  dut->tx_valid_i = 0; dut->tx_sof_i = 0; dut->tx_eof_i = 0;
}

static std::vector<uint8_t> mk_frame(int len, uint8_t seed) {
  std::vector<uint8_t> b(len);
  for (int i = 0; i < len; i++) b[i] = (uint8_t)(seed + i * 7);
  return b;
}

// pop the next complete received frame (sof..eof), with a cycle
// budget; the read pointer only commits once the WHOLE frame is
// present, so a frame still arriving is retried, never half-eaten
static bool pop_frame(std::vector<uint8_t> &out, bool &err,
                      uint64_t budget) {
  static size_t rp = 0;
  for (uint64_t n = 0; n < budget; n++, tick()) {
    while (rp < rxw.size() && !rxw[rp].sof) rp++;
    for (size_t e = rp; e < rxw.size(); e++) {
      if (rxw[e].eof) {
        out.clear(); err = false;
        for (size_t i = rp; i <= e; i++) {
          out.push_back(rxw[i].data);
          err |= rxw[i].err;
        }
        rp = e + 1;
        return true;
      }
    }
  }
  return false;
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  dut = new Vgasket_tb_top;
  dut->rst_n = 0;
  dut->sys_clk_i = 0; dut->mii_clk_i = 0;
  dut->tx_valid_i = 0; dut->tx_data_i = 0;
  dut->tx_sof_i = 0; dut->tx_eof_i = 0;
  dut->corrupt_i = 0;
  run(32);
  dut->rst_n = 1;
  run(32);

  // ---- 1: size sweep, byte-exact ----------------------------------------
  const int sizes[] = {60, 61, 64, 72, 94, 128};
  int nf = 0;
  for (int s : sizes) {
    auto f = mk_frame(s, (uint8_t)(0x30 + s));
    int tgl_tx = dut->tx_sfd_tgl_o, tgl_rx = dut->rx_sfd_tgl_o;
    push_frame(f);
    std::vector<uint8_t> got; bool err = false;
    char n[64];
    snprintf(n, 64, "size %d delivered", s);
    expect(n, pop_frame(got, err, 40000), 1);
    snprintf(n, 64, "size %d bytes", s);
    expect(n, got == f, 1);
    snprintf(n, 64, "size %d clean", s);
    expect(n, err, 0);
    run(400);
    snprintf(n, 64, "size %d tx sfd", s);
    expect(n, dut->tx_sfd_tgl_o != tgl_tx, 1);
    snprintf(n, 64, "size %d rx sfd", s);
    expect(n, dut->rx_sfd_tgl_o != tgl_rx, 1);
    nf++;
  }
  expect("sweep tx_cnt", dut->tx_cnt_o, nf);
  expect("sweep crc_bad", dut->crc_bad_o, 0);

  // ---- 2: 20 back-to-back frames, IFG held -------------------------------
  min_gap = ~0ull;
  std::vector<std::vector<uint8_t>> sent;
  for (int k = 0; k < 20; k++) {
    sent.push_back(mk_frame(64 + (k % 5) * 8, (uint8_t)(0x80 + k)));
    push_frame(sent.back());
  }
  for (int k = 0; k < 20; k++) {
    std::vector<uint8_t> got; bool err = false;
    char n[64];
    snprintf(n, 64, "b2b[%d] delivered", k);
    expect(n, pop_frame(got, err, 60000), 1);
    snprintf(n, 64, "b2b[%d] bytes", k);
    expect(n, got == sent[k], 1);
  }
  expect("b2b tx_cnt", dut->tx_cnt_o, nf + 20);
  expect("b2b IFG >= 24 mii clks", min_gap >= 24, 1);

  // ---- 3: the wedge regression -------------------------------------------
  // frame A drains; the moment the gasket leaves the data phase (en
  // still high through FCS, then IFG), blast frame B so the FIFO parks
  // at exactly 64 with no reader active. The 6-bit level port wedged
  // S_IDLE here forever; the 7-bit port must start frame B.
  {
    auto fa = mk_frame(72, 0x11);
    push_frame(fa);
    // wait for A's en falling edge (gasket entering IFG)
    bool was = false; uint64_t n = 0;
    while (n++ < 60000) {
      if (dut->mii_en_o) was = true;
      else if (was) break;
      tick();
    }
    auto fb = mk_frame(94, 0x22);
    push_frame(fb);                       // 94 > 64: parks level at 64
    std::vector<uint8_t> got; bool err = false;
    expect("wedge: A delivered", pop_frame(got, err, 60000), 1);
    expect("wedge: A bytes", got == fa, 1);
    expect("wedge: B delivered (no stall)", pop_frame(got, err, 90000), 1);
    expect("wedge: B bytes", got == fb, 1);
  }

  // ---- 4: corrupted frame fails FCS --------------------------------------
  {
    uint16_t bad0 = dut->crc_bad_o;
    auto f = mk_frame(64, 0x55);
    // corrupt mid-frame: flip nibbles for a short window while the
    // frame is on the MII
    dut->corrupt_i = 0;
    int tgl = dut->tx_sfd_tgl_o;
    push_frame(f);
    // anchor on the SFD toggle, then poison nibbles well inside DATA
    uint64_t n = 0;
    while (dut->tx_sfd_tgl_o == tgl && n++ < 40000) tick();
    run(40);                              // ~10 MII clocks into the body
    dut->corrupt_i = 0xF;
    run(16);
    dut->corrupt_i = 0;
    std::vector<uint8_t> got; bool err = false;
    bool delivered = pop_frame(got, err, 60000);
    expect("corrupt: flagged or dropped", !delivered || err, 1);
    run(2000);
    expect("corrupt: crc_bad counted", dut->crc_bad_o, bad0 + 1);
  }

  expect("no push starvation", push_timeouts, 0);

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
