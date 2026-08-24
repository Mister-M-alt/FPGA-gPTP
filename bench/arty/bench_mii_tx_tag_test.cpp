// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0

#include "Vbench_mii_tx.h"
#include "verilated.h"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <vector>

static std::vector<uint16_t> words;
static std::size_t rd_pos;

static void append_frame(uint8_t type, uint16_t seq) {
  std::vector<uint8_t> frame(60, 0);
  frame[12] = 0x88;
  frame[13] = 0xF7;
  frame[14] = static_cast<uint8_t>(0xA0 | type);
  frame[44] = static_cast<uint8_t>(seq >> 8);
  frame[45] = static_cast<uint8_t>(seq);
  for (std::size_t i = 0; i < frame.size(); ++i) {
    uint16_t word = frame[i];
    if (i == 0) word |= 1u << 9;
    if (i + 1 == frame.size()) word |= 1u << 8;
    words.push_back(word);
  }
}

static void drive_fifo(Vbench_mii_tx &dut) {
  const std::size_t left = words.size() - rd_pos;
  dut.f_empty_i = left == 0;
  dut.f_level_i = static_cast<uint8_t>(std::min<std::size_t>(left, 63));
  dut.f_data_i = left ? words[rd_pos] : 0;
}

static void tick(Vbench_mii_tx &dut) {
  drive_fifo(dut);
  dut.tx_clk_i = 0;
  dut.eval();
  const bool read = dut.f_rd_o && !dut.f_empty_i;
  dut.tx_clk_i = 1;
  dut.eval();
  if (read) ++rd_pos;
  drive_fifo(dut);
  dut.tx_clk_i = 0;
  dut.eval();
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  append_frame(0x3, 0x1234);
  append_frame(0xA, 0xBEEF);

  Vbench_mii_tx dut;
  dut.rst_n = 0;
  for (int i = 0; i < 3; ++i) tick(dut);
  dut.rst_n = 1;

  const uint8_t expect_type[2] = {0x3, 0xA};
  const uint16_t expect_seq[2] = {0x1234, 0xBEEF};
  uint8_t last_done = dut.done_toggle_o;
  int seen = 0;
  for (int cycle = 0; cycle < 2000 && seen != 2; ++cycle) {
    tick(dut);
    if (dut.done_toggle_o != last_done) {
      last_done = dut.done_toggle_o;
      if (dut.frame_type_o != expect_type[seen] ||
          dut.frame_seq_o != expect_seq[seen]) {
        std::fprintf(stderr,
                     "frame %d tag got {%x,%04x}, expected {%x,%04x}\n",
                     seen, dut.frame_type_o, dut.frame_seq_o,
                     expect_type[seen], expect_seq[seen]);
        return 1;
      }
      ++seen;
    }
  }

  if (seen != 2 || dut.tx_cnt_o != 2) {
    std::fprintf(stderr, "only %d frames completed, tx_cnt=%u\n",
                 seen, dut.tx_cnt_o);
    return 1;
  }
  std::printf("PASS: two MII done toggles carried tags {3,1234}, {a,beef}\n");
  return 0;
}
