// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_ucpu arithmetic battery.
//
// Drives the µCPU directly (no wrap needed: every observable is a port),
// dispatching the TB battery µprogram at entry 768 with random and directed
// operand pairs preloaded into r14/r13. The program computes twelve results
// (ADD/SUB/AND/OR/XOR/SHL/SHR/SAR/MULS/DIVU + two immediate forms) and
// writes each to scratch words 0..11 through the state port; this harness
// implements the state port, records the writes, and compares every one
// against an INDEPENDENT C++ model of the operations — never against the
// DUT's own logic. A DUT/model mismatch fails the run.

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <verilated.h>
#include "VKL_gptp_ucpu.h"

static uint64_t xs_state = 0x243F6A8885A308D3ull;
static uint64_t xs64() {
  uint64_t x = xs_state;
  x ^= x << 13; x ^= x >> 7; x ^= x << 17;
  return xs_state = x;
}

struct Recorder {
  uint64_t scratch[16];
  bool     seen[16];
  void clear() { for (int i = 0; i < 16; i++) { scratch[i] = 0; seen[i] = false; } }
};

static int checks = 0, fails = 0;

static void expect(const char *what, int run, uint64_t got, uint64_t exp,
                   bool seen) {
  checks++;
  if (!seen || got != exp) {
    fails++;
    if (fails <= 20)
      printf("FAIL run %d %-10s got %016llx exp %016llx%s\n", run, what,
             (unsigned long long)got, (unsigned long long)exp,
             seen ? "" : " (never written)");
  }
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  auto *dut = new VKL_gptp_ucpu;

  Recorder rec;
  uint64_t cyc = 0;

  auto tick = [&]() {
    dut->clk_i = 0; dut->eval();
    dut->clk_i = 1; dut->eval();
    // state port: always ready; record writes; reads return zero
    dut->st_ready_i  = 1;
    dut->st_rvalid_i = dut->st_req_o && !dut->st_we_o;
    dut->st_rdata_i  = 0;
    if (dut->st_req_o && dut->st_we_o) {
      uint32_t addr = dut->st_addr_o;
      if ((addr >> 16) == 2 && (addr & 0xFFFF) < 16) {
        rec.scratch[addr & 0xF] = dut->st_wdata_o;
        rec.seen[addr & 0xF]    = true;
      }
    }
    dut->gx_valid_i = dut->gx_req_o;
    dut->gx_data_i  = 0;
    dut->rb_ready_i = 1;
    dut->tx_ready_i = 1;
    cyc++;
  };

  // reset
  dut->rst_n = 0;
  dut->disp_valid_i = 0;
  dut->st_ready_i = 1; dut->st_rvalid_i = 0; dut->st_rdata_i = 0;
  dut->st_err_i = 0;
  dut->gx_valid_i = 0; dut->gx_data_i = 0;
  dut->lock_held_i = 0; dut->lock_ctlr_i = 0;
  dut->rb_ready_i = 1; dut->tx_ready_i = 1;
  for (int i = 0; i < 8; i++) tick();
  dut->rst_n = 1;
  for (int i = 0; i < 4; i++) tick();

  const int RUNS = 64;
  for (int run = 0; run < RUNS; run++) {
    uint64_t a, b;
    switch (run) {                       // directed edges first
      case 0: a = 0; b = 1; break;
      case 1: a = ~0ull; b = 1; break;
      case 2: a = 0x8000000000000000ull; b = 63; break;
      case 3: a = 0x123456789ABCDEF0ull; b = 64; break;  // shift by 0
      case 4: a = 1; b = ~0ull; break;   // divisor low32 = ffffffff
      default: a = xs64(); b = xs64(); break;
    }
    if ((uint32_t)b == 0) b |= 1;        // DIVU: µcode guards div-by-0

    rec.clear();
    dut->disp_upc_i  = 704;
    dut->disp_ev_i   = 0x0102030405060708ull;
    dut->disp_ts0_i  = a;                // -> r14
    dut->disp_ts1_i  = b;                // -> r13
    dut->disp_valid_i = 1;
    tick();
    while (!dut->disp_ready_o) { dut->disp_valid_i = 0; tick();
      if (cyc > 2000000) { printf("TIMEOUT run %d\n", run); fails++; break; } }
    dut->disp_valid_i = 0;

    // independent model
    unsigned sh = (unsigned)(b & 63);
    uint64_t exp[12];
    exp[0]  = a + b;
    exp[1]  = a - b;
    exp[2]  = a & b;
    exp[3]  = a | b;
    exp[4]  = a ^ b;
    exp[5]  = a << sh;                    // sh==0 -> a (serial: 0 beats)
    exp[6]  = a >> sh;
    exp[7]  = (uint64_t)(((int64_t)a) >> sh);
    exp[8]  = (uint64_t)((int64_t)(int32_t)(uint32_t)a *
                         (int64_t)(int32_t)(uint32_t)b);
    exp[9]  = a / (uint64_t)(uint32_t)b;
    exp[10] = a + 0xABCull;
    exp[11] = a >> 16;

    static const char *names[12] = {
      "ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "SAR",
      "MULS", "DIVU", "ADDI", "SHRI"};
    for (int i = 0; i < 12; i++)
      expect(names[i], run, rec.scratch[i], exp[i], rec.seen[i]);
  }

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
