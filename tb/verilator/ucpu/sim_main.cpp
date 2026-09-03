// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_ucpu arithmetic battery.
//
// Drives the µCPU directly (no wrap needed: every observable is a port),
// dispatching the TB battery µprogram at entry 704 with random and directed
// operand pairs preloaded into r14/r15. The program computes twelve results
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
#include "../../common/verilator_harness.hpp"

// The battery's twelve results, written to scratch words 0..11.
constexpr int kOps = 12;

// State-port address encoding (hdl/ucode/gen_gptp_ucode.py): the upper bits
// select the region -- RG_SCR = 0x2_0000, so region 2 is scratch -- and the
// low 16 bits are the word index. The recorder mirrors the whole 16-word
// window the battery writes into.
constexpr uint32_t kScratchWords     = 16;
constexpr uint32_t kStateRegionShift = 16;
constexpr uint32_t kScratchRegion    = 2;
constexpr uint32_t kStateWordMask    = 0xFFFFu;
constexpr uint32_t kScratchIndexMask = 0xFu;

// Cap on the FAIL lines printed, so a broken DUT cannot flood the log.
constexpr int kMaxFailReports = 20;

// Reset sequencing, in tick()s: held low, then settled before the dispatch.
constexpr int kResetTicks     = 8;
constexpr int kPostResetTicks = 4;

// The battery dispatch: the µprogram entry, the operand pairs driven per run,
// the give-up guard, and the two immediates the µcode's ADDI/SHRI carry
// (hdl/ucode/gen_gptp_ucode.py, prog_tb_battery).
constexpr int      kBatteryEntryUpc = 704;
constexpr int      RUNS             = 64;
constexpr uint64_t kCycleTimeout    = 2000000;
constexpr uint64_t kAddiImm         = 0xABCull;
constexpr unsigned kShriShift       = 16;

struct Recorder {
  uint64_t scratch[kScratchWords];
  bool     seen[kScratchWords];
  void clear() {
    for (uint32_t i = 0; i < kScratchWords; i++) { scratch[i] = 0; seen[i] = false; }
  }
};

namespace {

//! The whole battery: the µCPU, the state-port recorder that stands in for
//! scratch memory, the operand generator, and the independent model the DUT is
//! judged against. All of it was file-scope state and free functions; holding
//! it in one object is C++ Core Guidelines I.2 applied to this harness.
class UcpuArithmeticBattery {
 public:
  int run();

 private:
  //! One dispatched operand pair: `a` reaches r14, `b` reaches r15.
  struct Operands {
    uint64_t a;
    uint64_t b;
  };

  uint64_t xs64();
  void expect(const char *what, int run, uint64_t got, uint64_t exp, bool seen);
  void tick();
  void release_the_core_from_reset();
  Operands operands_for_run(int run);
  void dispatch_the_battery(Operands ops, int run);
  void compare_scratch_against_the_model(Operands ops, int run);

  const milan::tb::Model<VKL_gptp_ucpu> model;
  VKL_gptp_ucpu *const dut = model.get();

  Recorder rec;
  uint64_t cyc = 0;

  uint64_t xs_state = 0x243F6A8885A308D3ull;

  int checks = 0;
  int fails = 0;
};

uint64_t UcpuArithmeticBattery::xs64() {
  uint64_t x = xs_state;
  x ^= x << 13; x ^= x >> 7; x ^= x << 17;
  return xs_state = x;
}

void UcpuArithmeticBattery::expect(const char *what, int run, uint64_t got,
                                   uint64_t exp, bool seen) {
  checks++;
  if (!seen || got != exp) {
    fails++;
    if (fails <= kMaxFailReports)
      printf("FAIL run %d %-10s got %016llx exp %016llx%s\n", run, what,
             static_cast<unsigned long long>(got),
             static_cast<unsigned long long>(exp),
             seen ? "" : " (never written)");
  }
}

void UcpuArithmeticBattery::tick() {
  dut->clk_i = 0; dut->eval();
  dut->clk_i = 1; dut->eval();
  // state port: always ready; record writes; reads return zero
  dut->st_ready_i  = 1;
  dut->st_rvalid_i = dut->st_req_o && !dut->st_we_o;
  dut->st_rdata_i  = 0;
  if (dut->st_req_o && dut->st_we_o) {
    uint32_t addr = dut->st_addr_o;
    if ((addr >> kStateRegionShift) == kScratchRegion &&
        (addr & kStateWordMask) < kScratchWords) {
      rec.scratch[addr & kScratchIndexMask] = dut->st_wdata_o;
      rec.seen[addr & kScratchIndexMask]    = true;
    }
  }
  dut->gx_valid_i = dut->gx_req_o;
  dut->gx_data_i  = 0;
  dut->rb_ready_i = 1;
  dut->tx_ready_i = 1;
  cyc++;
}

// reset
void UcpuArithmeticBattery::release_the_core_from_reset() {
  dut->rst_n = 0;
  dut->disp_valid_i = 0;
  dut->st_ready_i = 1; dut->st_rvalid_i = 0; dut->st_rdata_i = 0;
  dut->st_err_i = 0;
  dut->gx_valid_i = 0; dut->gx_data_i = 0;
  dut->lock_held_i = 0; dut->lock_ctlr_i = 0;
  dut->rb_ready_i = 1; dut->tx_ready_i = 1;
  for (int i = 0; i < kResetTicks; i++) tick();
  dut->rst_n = 1;
  for (int i = 0; i < kPostResetTicks; i++) tick();
}

UcpuArithmeticBattery::Operands UcpuArithmeticBattery::operands_for_run(int run) {
  uint64_t a;
  uint64_t b;
  switch (run) {                       // directed edges first
    case 0: a = 0; b = 1; break;
    case 1: a = ~0ull; b = 1; break;
    case 2: a = 0x8000000000000000ull; b = 63; break;
    case 3: a = 0x123456789ABCDEF0ull; b = 64; break;  // shift by 0
    case 4: a = 1; b = ~0ull; break;   // divisor low32 = ffffffff
    default: a = xs64(); b = xs64(); break;
  }
  if (static_cast<uint32_t>(b) == 0) b |= 1;  // DIVU: µcode guards div-by-0
  return Operands{a, b};
}

void UcpuArithmeticBattery::dispatch_the_battery(Operands ops, int run) {
  rec.clear();
  dut->disp_upc_i  = kBatteryEntryUpc;
  dut->disp_ev_i   = ops.b;            // -> r15
  dut->disp_ts0_i  = ops.a;            // -> r14
  dut->disp_valid_i = 1;
  tick();
  while (!dut->disp_ready_o) {
    dut->disp_valid_i = 0;
    tick();
    if (cyc > kCycleTimeout) {
      printf("TIMEOUT run %d\n", run);
      fails++;
      break;
    }
  }
  dut->disp_valid_i = 0;
}

// independent model
void UcpuArithmeticBattery::compare_scratch_against_the_model(Operands ops, int run) {
  const uint64_t a = ops.a;
  const uint64_t b = ops.b;
  unsigned sh = static_cast<unsigned>(b & 63);
  uint64_t exp[kOps];
  exp[0]  = a + b;
  exp[1]  = a - b;
  exp[2]  = a & b;
  exp[3]  = a | b;
  exp[4]  = a ^ b;
  exp[5]  = a << sh;                    // sh==0 -> a (serial: 0 beats)
  exp[6]  = a >> sh;
  exp[7]  = static_cast<uint64_t>(static_cast<int64_t>(a) >> sh);
  exp[8]  = static_cast<uint64_t>(
      static_cast<int64_t>(static_cast<int32_t>(static_cast<uint32_t>(a))) *
      static_cast<int64_t>(static_cast<int32_t>(static_cast<uint32_t>(b))));
  exp[9]  = a / static_cast<uint64_t>(static_cast<uint32_t>(b));
  exp[10] = a + kAddiImm;
  exp[11] = a >> kShriShift;

  static constexpr const char *names[kOps] = {
    "ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "SAR",
    "MULS", "DIVU", "ADDI", "SHRI"};
  for (int i = 0; i < kOps; i++)
    expect(names[i], run, rec.scratch[i], exp[i], rec.seen[i]);
}

int UcpuArithmeticBattery::run() {
  release_the_core_from_reset();

  for (int r = 0; r < RUNS; r++) {
    const Operands ops = operands_for_run(r);
    dispatch_the_battery(ops, r);
    compare_scratch_against_the_model(ops, r);
  }

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  return fails ? 1 : 0;
}

}  // namespace

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  UcpuArithmeticBattery battery;
  return battery.run();
}
