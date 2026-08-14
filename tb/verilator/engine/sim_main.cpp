// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_engine protocol round-trip — v3, the grandmaster round.
//
//  1  boot cadence -> our Pdelay_Req, byte-validated
//  2  peer Resp + Resp_FU -> pub_pdelay = ((t4-t1)-(t3-t2))/2
//  3  peer Pdelay_Req -> our two-step Resp + Resp_FU, byte-validated
//  4  no announce heard -> announce receipt timeout -> BECOME MASTER
//  5  our Announce byte-validated (vector, gm id, path trace TLV)
//  6  our two-step Sync + Follow_Up byte-validated; the FU's
//     preciseOriginTimestamp must equal the egress timestamp this
//     harness returned for that exact Sync frame
//  7  worse announce (p1=250) -> BTCA rejects, we stay master,
//     received vector published
//  8  better announce (p1=100) -> BTCA adopts, sync TX stops
//  9  as slave: peer Sync + Follow_Up -> pub_offset
//
// All frames and expectations built independently from 802.1AS-2011.

#include <cstdint>
#include <cstdio>
#include <vector>
#include <verilated.h>
#include "VKL_gptp_engine.h"

static const uint64_t OUR_MAC = 0x02A1B2C3D4E5ull;
static const uint64_t OUR_CID = 0x02A1B2FFFEC3D4E5ull;
static const uint64_t PEER_CID = 0x0080E1FFFE112233ull;
static const uint32_t OUR_CQ = 0xF8FE436A;

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
  f.u48(0x0080E1112233ull);
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

static VKL_gptp_engine *dut;
static uint64_t cyc = 0;
static std::vector<std::vector<uint8_t>> txf;
static std::vector<uint64_t> txns;               // egress ts fed per frame
static std::vector<uint8_t> cur;
static bool in_tx = false;
static bool auto_txts = false;
static int auto_pend = -1;

static void tick() {
  if (auto_pend >= 0 && !dut->txts_valid_i) {
    uint64_t ns = 50000000ull + (uint64_t)auto_pend * 1000000ull;
    dut->txts_valid_i = 1;
    dut->txts_ns_i = ns;
    txns[auto_pend] = ns;
    auto_pend = -1;
  }
  dut->clk_i = 0; dut->eval();
  dut->clk_i = 1; dut->eval();
  dut->phc_ns_i = cyc * 500ull;
  if (dut->tx_valid_o) {
    if (dut->tx_sof_o) { cur.clear(); in_tx = true; }
    if (in_tx) cur.push_back(dut->tx_data_o);
    if (dut->tx_eof_o && in_tx) {
      txf.push_back(cur);
      txns.push_back(0);
      if (auto_txts) auto_pend = (int)txf.size() - 1;
      in_tx = false;
    }
  }
  dut->txts_valid_i = 0;                 // a pulse lasts exactly one edge
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

static size_t tx_seen = 0;
static std::vector<uint8_t> wait_tx(int mtype, uint64_t max_cycles,
                                    size_t *idx_out = nullptr) {
  for (uint64_t n = 0; n < max_cycles; n++) {
    while (tx_seen < txf.size()) {
      size_t i = tx_seen++;
      if (mtype < 0 || (txf[i].size() > 14 && (txf[i][14] & 0xF) == mtype)) {
        if (idx_out) *idx_out = i;
        return txf[i];
      }
    }
    tick();
  }
  printf("FAIL wait_tx type %d: timeout\n", mtype);
  fails++; checks++;
  return {};
}

static uint64_t fld48(const std::vector<uint8_t> &f, size_t o) {
  uint64_t v = 0; for (int i = 0; i < 6; i++) v = (v << 8) | f[o + i];
  return v;
}
static uint64_t fld64(const std::vector<uint8_t> &f, size_t o) {
  uint64_t v = 0; for (int i = 0; i < 8; i++) v = (v << 8) | f[o + i];
  return v;
}
static uint32_t fld32(const std::vector<uint8_t> &f, size_t o) {
  return (f[o] << 24) | (f[o + 1] << 16) | (f[o + 2] << 8) | f[o + 3];
}
static uint16_t fld16(const std::vector<uint8_t> &f, size_t o) {
  return (uint16_t)((f[o] << 8) | f[o + 1]);
}

static void check_common(const char *tag, const std::vector<uint8_t> &f,
                         uint8_t mtype, uint16_t flags, int msglen,
                         uint8_t logint) {
  char n[64];
  if ((int)f.size() != 14 + msglen) {
    snprintf(n, 64, "%s size", tag);
    expect(n, f.size(), (uint64_t)(14 + msglen));
    return;
  }
  snprintf(n, 64, "%s DA", tag);     expect(n, fld48(f, 0), 0x0180C200000Eull);
  snprintf(n, 64, "%s SA", tag);     expect(n, fld48(f, 6), OUR_MAC);
  snprintf(n, 64, "%s type", tag);   expect(n, f[14], 0x10 | mtype);
  snprintf(n, 64, "%s len", tag);    expect(n, fld16(f, 16), msglen);
  snprintf(n, 64, "%s flags", tag);  expect(n, fld16(f, 20), flags);
  snprintf(n, 64, "%s srcCID", tag); expect(n, fld64(f, 34), OUR_CID);
  snprintf(n, 64, "%s srcPN", tag);  expect(n, fld16(f, 42), 1);
  snprintf(n, 64, "%s logint", tag); expect(n, f[47], logint);
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

  // ---- 1: our Pdelay_Req -------------------------------------------------
  std::vector<uint8_t> req = wait_tx(0x2, 3200000);
  if (!req.empty()) {
    check_common("pdreq", req, 0x2, 0x0000, 54, 0x00);
    uint64_t z = 0;
    for (int i = 48; i < 68; i++) z |= req[i];
    expect("pdreq body zero", z, 0);
  }
  const uint64_t T1 = 1000000ull;
  txts(T1);
  run(2000);

  // ---- 2: peer answers -> meanLinkDelay ---------------------------------
  const uint64_t T2 = 500000ull, T3 = 520000ull, T4 = 1600000ull;
  {
    Frame f = ptp(0x3, 0, 0, 0x0200, 20);
    f.ts(T2); f.u64(OUR_CID); f.u16(1);
    send_frame(f.b, T4);
    run(4000);
    Frame g = ptp(0xA, 0, 0, 0x0000, 20);
    g.ts(T3); g.u64(OUR_CID); g.u16(1);
    send_frame(g.b, T4 + 1000);
    run(6000);
  }
  const uint64_t PD = ((T4 - T1) - (T3 - T2)) / 2;
  expect("pub pdelay", dut->pub_pdelay_ns_o, PD);

  // ---- 3: peer initiates -> our Resp + Resp_FU --------------------------
  const uint64_t T2R = 2000000ull, T3R = 2050000ull;
  {
    Frame f = ptp(0x2, 0x55AA, 0, 0x0000, 20);
    f.u64(0); f.u16(0); f.ts(0);
    f.b.resize(68);
    send_frame(f.b, T2R);
  }
  std::vector<uint8_t> resp = wait_tx(0x3, 400000);
  if (!resp.empty()) {
    check_common("pdresp", resp, 0x3, 0x0200, 54, 0x7F);
    expect("pdresp seq", fld16(resp, 44), 0x55AA);
    expect("pdresp t2", fld48(resp, 48) * 1000000000ull + fld32(resp, 54),
           T2R);
    expect("pdresp reqCID", fld64(resp, 58), PEER_CID);
  }
  txts(T3R);
  std::vector<uint8_t> rfu = wait_tx(0xA, 400000);
  if (!rfu.empty()) {
    check_common("pdrfu", rfu, 0xA, 0x0000, 54, 0x7F);
    expect("pdrfu seq", fld16(rfu, 44), 0x55AA);
    expect("pdrfu t3", fld48(rfu, 48) * 1000000000ull + fld32(rfu, 54),
           T3R);
    expect("pdrfu reqCID", fld64(rfu, 58), PEER_CID);
  }

  // ---- 4: announce receipt timeout -> become master ---------------------
  auto_txts = true;
  {
    uint64_t n = 0;
    while (!(dut->pub_flags_o & 2) && n++ < 12000000ull) tick();
  }
  expect("became master", dut->pub_flags_o & 3, 3);
  expect("gm is us", dut->pub_gm_id_o, OUR_CID);

  // ---- 5: our Announce ---------------------------------------------------
  std::vector<uint8_t> ann = wait_tx(0xB, 400000);
  if (!ann.empty()) {
    check_common("ann", ann, 0xB, 0x0008, 76, 0x00);
    expect("ann utc", fld16(ann, 58), 37);
    expect("ann p1", ann[61], 248);
    expect("ann cq", fld32(ann, 62), OUR_CQ);
    expect("ann p2", ann[66], 248);
    expect("ann gmid", fld64(ann, 67), OUR_CID);
    expect("ann steps", fld16(ann, 75), 0);
    expect("ann tsrc", ann[77], 0xA0);
    expect("ann tlv", fld32(ann, 78), 0x00080008);
    expect("ann path0", fld64(ann, 82), OUR_CID);
  }

  // ---- 6: our Sync + Follow_Up ------------------------------------------
  size_t sidx = 0;
  std::vector<uint8_t> sy = wait_tx(0x0, 800000, &sidx);
  uint16_t sseq = 0;
  if (!sy.empty()) {
    check_common("sync", sy, 0x0, 0x0208, 44, 0xFD);
    sseq = fld16(sy, 44);
  }
  run(20000);                                    // let its FU emerge
  std::vector<uint8_t> fu = wait_tx(0x8, 800000);
  if (!fu.empty()) {
    check_common("syncfu", fu, 0x8, 0x0008, 76, 0xFD);
    expect("syncfu seq", fld16(fu, 44), sseq);
    expect("syncfu origin", fld48(fu, 48) * 1000000000ull + fld32(fu, 54),
           txns[sidx]);
    expect("syncfu tlv", fld32(fu, 58), 0x0003001C);
    expect("syncfu org", fld48(fu, 62), 0x0080C2000001ull);
  }

  // ---- 7: worse announce -> stay master ---------------------------------
  {
    Frame f = ptp(0xB, 9, 0, 0x0008, 30);
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(250); f.u32(OUR_CQ); f.u8(248);
    f.u64(0xAABBCCFFFE010203ull);
    f.u16(0); f.u8(0xA0);
    send_frame(f.b, 5000000);
    run(6000);
  }
  expect("still master", dut->pub_flags_o & 2, 2);
  expect("gm still us", dut->pub_gm_id_o, OUR_CID);
  expect("annq published",
         dut->pub_annq_o,
         (0xFFC4ull << 48) | (250ull << 40) | ((uint64_t)OUR_CQ << 8) |
         248ull);

  // ---- 8: better announce -> adopt, sync stops --------------------------
  const uint64_t GMID = 0x00AACCFFFE010203ull;
  {
    Frame f = ptp(0xB, 10, 0, 0x0008, 30);
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(100); f.u32(OUR_CQ); f.u8(248);
    f.u64(GMID);
    f.u16(0); f.u8(0xA0);
    send_frame(f.b, 6000000);
    run(6000);
  }
  expect("adopted", dut->pub_flags_o & 3, 1);
  expect("gm is theirs", dut->pub_gm_id_o, GMID);
  {
    run(20000);                                  // drain anything in flight
    size_t before = txf.size();
    run(700000);                                 // 0.35 s: ~3 sync slots
    int syncs = 0;
    for (size_t i = before; i < txf.size(); i++)
      if ((txf[i][14] & 0xF) == 0x0) syncs++;
    expect("sync TX stopped", syncs, 0);
  }

  // ---- 9: as slave, peer sync -> offset ---------------------------------
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
