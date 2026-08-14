// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_engine protocol round-trip — the bench rehearsal.
//
// Runs the whole engine (parser + µCPU + µcode v2 + TX slot + timer) at a
// scaled clock and walks the exact exchanges an 802.1AS peer will drive:
//
//   1. boot-armed cadence fires -> the engine INITIATES Pdelay_Req;
//      every header byte is validated against an independent C++ image
//   2. the peer answers Resp + Resp_Follow_Up -> pub_pdelay_ns must equal
//      ((t4-t1)-(t3-t2))/2 computed independently here
//   3. the peer initiates Pdelay_Req -> the engine must answer a valid
//      two-step Pdelay_Resp (seq + requestingPortIdentity echoed, twoStep
//      flag, t2 = ingress ts) and, on the egress-timestamp return, a
//      Pdelay_Resp_Follow_Up carrying t3
//   4. Announce -> GM + parent published, gm_present set
//   5. Sync + Follow_Up -> pub_offset = t_rx - (origin + corr>>16 + PD)
//
// Frames and expectations are built here from the 802.1AS-2011 layout,
// never from the RTL.

#include <cstdint>
#include <cstdio>
#include <vector>
#include <verilated.h>
#include "VKL_gptp_engine.h"

static const uint64_t OUR_MAC = 0x02A1B2C3D4E5ull;
static const uint64_t OUR_CID = 0x02A1B2FFFEC3D4E5ull;
static const uint64_t PEER_MAC = 0x0080E1112233ull;
static const uint64_t PEER_CID = 0x0080E1FFFE112233ull;

static int checks = 0, fails = 0;
static void expect(const char *what, uint64_t got, uint64_t exp) {
  checks++;
  if (got != exp) {
    fails++;
    printf("FAIL %-28s got %016llx exp %016llx\n", what,
           (unsigned long long)got, (unsigned long long)exp);
  }
}

struct Frame {
  std::vector<uint8_t> b;
  void u8(uint8_t v) { b.push_back(v); }
  void u16(uint16_t v) { u8(v >> 8); u8(v & 0xFF); }
  void u32(uint32_t v) { u16(v >> 16); u16(v & 0xFFFF); }
  void u48(uint64_t v) { u16((v >> 32) & 0xFFFF); u32(v & 0xFFFFFFFF); }
  void u64(uint64_t v) { u32(v >> 32); u32(v & 0xFFFFFFFF); }
  void ts(uint64_t ns) { u48(ns / 1000000000ull); u32(ns % 1000000000ull); }
};

static Frame ptp(uint8_t mtype, uint16_t seq, uint64_t corr,
                 uint16_t flags, uint16_t body_len) {
  Frame f;
  f.u48(0x0180C200000Eull);
  f.u48(PEER_MAC);
  f.u16(0x88F7);
  f.u8(0x10 | mtype); f.u8(0x02);
  f.u16(34 + body_len);
  f.u8(0); f.u8(0);
  f.u16(flags);
  f.u64(corr);
  f.u32(0);
  f.u64(PEER_CID); f.u16(1);
  f.u16(seq);
  f.u8(0x05); f.u8(0x7F);
  return f;
}

// ---- DUT driving -----------------------------------------------------------
static VKL_gptp_engine *dut;
static uint64_t cyc = 0;
static std::vector<std::vector<uint8_t>> txf;   // captured TX frames
static std::vector<uint8_t> cur;
static bool in_tx = false;

static void tick() {
  dut->clk_i = 0; dut->eval();
  dut->clk_i = 1; dut->eval();
  dut->phc_ns_i = cyc * 500ull;
  if (dut->tx_valid_o) {
    if (dut->tx_sof_o) { cur.clear(); in_tx = true; }
    if (in_tx) cur.push_back(dut->tx_data_o);
    if (dut->tx_eof_o && in_tx) { txf.push_back(cur); in_tx = false; }
  }
  cyc++;
}

static void run(uint64_t n) { while (n--) tick(); }

static void send_frame(const std::vector<uint8_t> &bytes, uint64_t rx_ts) {
  dut->rx_ts_i = rx_ts;
  for (size_t i = 0; i < bytes.size(); i++) {
    dut->rx_valid_i = 1;
    dut->rx_data_i = bytes[i];
    dut->rx_sof_i = (i == 0);
    dut->rx_eof_i = (i + 1 == bytes.size());
    dut->rx_err_i = 0;
    tick();
  }
  dut->rx_valid_i = 0; dut->rx_sof_i = 0; dut->rx_eof_i = 0;
}

static void txts(uint64_t ns) {
  dut->txts_valid_i = 1; dut->txts_ns_i = ns; dut->txts_seq_i = 0;
  tick();
  dut->txts_valid_i = 0;
}

//! wait for the next TX frame of a given messageType; -1 = any
static std::vector<uint8_t> wait_tx(int mtype, uint64_t max_cycles) {
  size_t seen = 0;
  for (uint64_t n = 0; n < max_cycles; n++) {
    while (seen < txf.size()) {
      std::vector<uint8_t> f = txf[seen++];
      if (mtype < 0 || (f.size() > 14 && (f[14] & 0xF) == mtype)) return f;
    }
    tick();
  }
  printf("FAIL wait_tx type %d: timeout\n", mtype);
  fails++; checks++;
  return {};
}

static uint64_t fld48(const std::vector<uint8_t> &f, size_t off) {
  uint64_t v = 0;
  for (int i = 0; i < 6; i++) v = (v << 8) | f[off + i];
  return v;
}
static uint64_t fld64(const std::vector<uint8_t> &f, size_t off) {
  uint64_t v = 0;
  for (int i = 0; i < 8; i++) v = (v << 8) | f[off + i];
  return v;
}
static uint32_t fld32(const std::vector<uint8_t> &f, size_t off) {
  return (f[off] << 24) | (f[off + 1] << 16) | (f[off + 2] << 8) | f[off + 3];
}
static uint16_t fld16(const std::vector<uint8_t> &f, size_t off) {
  return (uint16_t)((f[off] << 8) | f[off + 1]);
}

static void check_common(const char *tag, const std::vector<uint8_t> &f,
                         uint8_t mtype, uint16_t flags, uint16_t seq) {
  char n[64];
  if (f.size() != 68) { snprintf(n, 64, "%s size", tag);
    expect(n, f.size(), 68); return; }
  snprintf(n, 64, "%s DA", tag);      expect(n, fld48(f, 0), 0x0180C200000Eull);
  snprintf(n, 64, "%s SA", tag);      expect(n, fld48(f, 6), OUR_MAC);
  snprintf(n, 64, "%s ET", tag);      expect(n, fld16(f, 12), 0x88F7);
  snprintf(n, 64, "%s type", tag);    expect(n, f[14], 0x10 | mtype);
  snprintf(n, 64, "%s ver", tag);     expect(n, f[15], 0x02);
  snprintf(n, 64, "%s len", tag);     expect(n, fld16(f, 16), 54);
  snprintf(n, 64, "%s flags", tag);   expect(n, fld16(f, 20), flags);
  snprintf(n, 64, "%s corr", tag);    expect(n, fld64(f, 22), 0);
  snprintf(n, 64, "%s srcCID", tag);  expect(n, fld64(f, 34), OUR_CID);
  snprintf(n, 64, "%s srcPN", tag);   expect(n, fld16(f, 42), 1);
  snprintf(n, 64, "%s seq", tag);     expect(n, fld16(f, 44), seq);
  snprintf(n, 64, "%s ctrl", tag);    expect(n, f[46], 0x05);
}

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  dut = new VKL_gptp_engine;

  dut->rst_n = 0;
  dut->rx_valid_i = 0; dut->rx_sof_i = 0; dut->rx_eof_i = 0;
  dut->rx_err_i = 0; dut->rx_data_i = 0; dut->rx_ts_i = 0;
  dut->tx_ready_i = 1;
  dut->txts_valid_i = 0; dut->txts_ns_i = 0; dut->txts_seq_i = 0;
  dut->phc_ns_i = 0;
  for (int i = 0; i < 8; i++) tick();
  dut->rst_n = 1;

  // ---- 1: boot cadence -> our Pdelay_Req --------------------------------
  // CLK_HZ_P = 2 MHz in this build: 1 ms = 2,000 cycles; boot arm 1,200 ms.
  std::vector<uint8_t> req = wait_tx(0x2, 3200000);
  if (!req.empty()) {
    check_common("pdreq", req, 0x2, 0x0000, 0);
    expect("pdreq logint", req[47], 0x00);
    uint64_t z = 0;
    for (int i = 48; i < 68; i++) z |= req[i];
    expect("pdreq body zero", z, 0);
  }
  const uint64_t T1 = 1000000ull;
  txts(T1);                                    // our egress ts (t1)
  run(2000);

  // ---- 2: peer answers -> meanLinkDelay ---------------------------------
  const uint64_t T2 = 500000ull, T3 = 520000ull, T4 = 1600000ull;
  {
    Frame f = ptp(0x3, 0, 0, 0x0200, 20);      // Pdelay_Resp
    f.ts(T2);
    f.u64(OUR_CID); f.u16(1);                  // requestingPortIdentity = us
    send_frame(f.b, T4);
    run(4000);
    Frame g = ptp(0xA, 0, 0, 0x0000, 20);      // Pdelay_Resp_Follow_Up
    g.ts(T3);
    g.u64(OUR_CID); g.u16(1);
    send_frame(g.b, T4 + 1000);
    run(6000);
  }
  const uint64_t PD = ((T4 - T1) - (T3 - T2)) / 2;
  expect("pub pdelay", dut->pub_pdelay_ns_o, PD);

  // ---- 3: peer initiates -> our Resp + Resp_FU --------------------------
  const uint64_t T2R = 2000000ull, T3R = 2050000ull;
  {
    Frame f = ptp(0x2, 0x55AA, 0, 0x0000, 20);
    f.u64(0); f.u16(0); f.ts(0);               // 20 reserved bytes
    f.b.resize(68);
    send_frame(f.b, T2R);
  }
  std::vector<uint8_t> resp = wait_tx(0x3, 400000);
  if (!resp.empty()) {
    check_common("pdresp", resp, 0x3, 0x0200, 0x55AA);
    expect("pdresp t2 sec", fld48(resp, 48) * 1000000000ull +
                            fld32(resp, 54), T2R);
    expect("pdresp reqCID", fld64(resp, 58), PEER_CID);
    expect("pdresp reqPN", fld16(resp, 66), 1);
  }
  txts(T3R);
  std::vector<uint8_t> rfu = wait_tx(0xA, 400000);
  if (!rfu.empty()) {
    check_common("pdrfu", rfu, 0xA, 0x0000, 0x55AA);
    expect("pdrfu t3", fld48(rfu, 48) * 1000000000ull +
                       fld32(rfu, 54), T3R);
    expect("pdrfu reqCID", fld64(rfu, 58), PEER_CID);
    expect("pdrfu reqPN", fld16(rfu, 66), 1);
  }

  // ---- 4: announce ------------------------------------------------------
  const uint64_t GMID = 0xAABBCCFFFE010203ull;
  {
    Frame f = ptp(0xB, 7, 0, 0x0008, 30);
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(248); f.u32(0xF8FE436A); f.u8(248);
    f.u64(GMID);
    f.u16(0); f.u8(0xA0);
    send_frame(f.b, 3000000);
    run(4000);
  }
  expect("pub gm", dut->pub_gm_id_o, GMID);
  expect("pub parent", dut->pub_parent_id_o, PEER_CID);
  expect("gm present", dut->pub_flags_o & 1, 1);

  // ---- 5: sync + follow-up -> offset ------------------------------------
  const uint64_t TRX = 10000000ull, ORIGIN = 9000000ull, CORR_NS = 1000ull;
  {
    Frame f = ptp(0x0, 0x0102, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX);
    run(2000);
    Frame g = ptp(0x8, 0x0102, CORR_NS << 16, 0x0000, 10);
    g.ts(ORIGIN);
    send_frame(g.b, TRX + 500);
    run(6000);
  }
  const uint64_t OFF = TRX - (ORIGIN + CORR_NS + PD);
  expect("pub offset", (uint32_t)dut->pub_offset_o, (uint32_t)OFF);

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
