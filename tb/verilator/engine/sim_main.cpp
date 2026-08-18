// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_engine protocol round-trip -- v5, the servo round.
//
//  1  boot cadence -> our Pdelay_Req, byte-validated; asCapable LOW
//  2  one good exchange (D = 600 ns) -> pdelay published, asCapable
//     STILL low (Milan 4.2.6.2.4: not before the second exchange)
//  3  peer Pdelay_Req -> our two-step Resp + Resp_FU, byte-validated
//  4  the auto-responder peer comes up (drift +2^-13) -> the second
//     exchange raises asCapable; pub pdelay matches the nrr-corrected
//     integer model exactly
//  5  no announce heard -> announce receipt timeout -> BECOME MASTER
//     (which the ladder now gates on asCapable)
//  6  our Announce byte-validated (vector, gm id, path trace TLV)
//  7  our two-step Sync + Follow_Up byte-validated; FU origin = the
//     egress timestamp this harness returned for that exact Sync
//  8  worse announce (p1=250) -> BTCA rejects, we stay master
//  9  better announce (p1=100) -> BTCA adopts, sync TX stops
// 10  as slave: peer Sync + Follow_Up -> pub_offset; sync-ok rises
// 11  a Sync whose Follow_Up is 135 ms late pairs with NOTHING
//     (followUpReceiptTimeout 125 ms voided it); the next proper pair
//     still lands
// 12  375 ms with no Sync -> syncReceiptTimeout -> sync-ok falls
//     while still slave
// 13  a +1 ms offset STEPS the phc by its negation (the DLL re-base;
//     linuxptp first_step_threshold 20 us) and never touches the addend
// 14  a +5 us offset SLEWS: the PI addend matches the exact-integer
//     mirror, and never steps
// 15  closed loop: a +100 ppm master, 1 ms ahead, converges -- one
//     re-base, then the measured offset locks under 200 ns with the
//     integrator carrying the master's rate
// 16  negative pdelay in [-80, 0) -> published signed, asCapable HELD
//     (Milan 4.2.6.2.7)
// 17  pdelay over the 800 ns threshold -> asCapable falls
//     (neighborPropDelayThresh, Milan 4.2.6.1.1)
// 18  recovery needs TWO good exchanges again, not one
// 19  the peer goes silent -> the FOURTH lost response clears asCapable
//     (allowedLostResponses, 802.1AS-2011 11.2.12.4)
// 20  a ratio window wider than 2^32 ns is skipped, not divided stale
//
// All frames and expectations built independently from 802.1AS-2011 +
// Milan v1.2 4.2.6. The pdelay model mirrors the SPEC formula in exact
// integer arithmetic (Q2.30 ratio, arithmetic shift for /2), never the
// DUT's internals.

#include <cstdint>
#include <cstdio>
#include <vector>
#include <verilated.h>
#include "VKL_gptp_engine.h"

static const uint64_t OUR_MAC = 0x02A1B2C3D4E5ull;
static const uint64_t OUR_CID = 0x02A1B2FFFEC3D4E5ull;
static const uint64_t PEER_CID = 0x0080E1FFFE112233ull;
static const uint32_t OUR_CQ = 0xF8FE436A;

// publish flags bits (the retired software contract)
static const uint32_t FL_PRESENT = 1, FL_AMGM = 2, FL_ASCAP = 4,
                      FL_SYNCOK = 8;

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

// ---- the PHC: a live timestamp_counter model the servo can steer ----------
// Q24 accumulator, 500 ns nominal per tick (2 MHz); adjfine addend and
// adjtime steps applied exactly as the parent counter would
static unsigned __int128 phc_acc = 0;
static int32_t phc_adj = 0;
static std::vector<uint64_t> steps_seen;         // every adjtime write
static std::vector<uint32_t> adj_seen;           // every adjfine write

static uint64_t phc() { return (uint64_t)(phc_acc >> 24); }

static void tick() {
  if (auto_pend >= 0 && !dut->txts_valid_i) {
    uint64_t ns = phc() + 200;                   // MAC pipeline latency
    dut->txts_valid_i = 1;
    dut->txts_ns_i = ns;
    txns[auto_pend] = ns;
    auto_pend = -1;
  }
  dut->clk_i = 0; dut->eval();
  dut->clk_i = 1; dut->eval();
  if (dut->phc_addend_we_o) {
    phc_adj = (int32_t)dut->phc_addend_o;
    adj_seen.push_back(dut->phc_addend_o);
  }
  if (dut->phc_step_we_o) {
    steps_seen.push_back(dut->phc_step_o);
    phc_acc += (unsigned __int128)(
        (__int128)(int64_t)dut->phc_step_o << 24);
  }
  phc_acc += (unsigned __int128)(uint64_t)((500ll << 24) + phc_adj);
  dut->phc_ns_i = phc();
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

// ---- pdelay model: the spec formula in the ROM's exact integer forms ------
// nrr = ((t3-t3')<<30)/(t4-t4') when the window fits 32 bits;
// D = (((nrr*(t4-t1))>>30) - (t3-t2)) >>arith 1, uncorrected before the
// first ratio. Mirrors 802.1AS-2011 11.2.15.3 / Milan 4.2.6, not the DUT.
static struct {
  uint64_t nr3 = 0, nr4 = 0, nrr = 0;
  int64_t d = 0;
  int count = 0;
  bool stale_skip = false;       // last window rejected as > 2^32 ns
} pdm;

static void model_exchange(uint64_t t1, uint64_t t2, uint64_t t3,
                           uint64_t t4) {
  pdm.stale_skip = false;
  if (pdm.nr3 != 0) {
    uint64_t num = t3 - pdm.nr3, den = t4 - pdm.nr4;
    if ((den >> 32) == 0 && (den & 0xFFFFFFFFull) != 0)
      pdm.nrr = (num << 30) / (den & 0xFFFFFFFFull);
    else
      pdm.stale_skip = true;
  }
  pdm.nr3 = t3; pdm.nr4 = t4;
  uint64_t turn = t4 - t1;
  uint64_t corr = turn;
  if (pdm.nrr != 0) {
    int64_t prod = (int64_t)(int32_t)(pdm.nrr & 0xFFFFFFFFull) *
                   (int64_t)(int32_t)(turn & 0xFFFFFFFFull);
    corr = ((uint64_t)prod) >> 30;
  }
  pdm.d = ((int64_t)(corr - (t3 - t2))) >> 1;
  pdm.count++;
}

// ---- servo mirror: the ROM's step-vs-slew in exact integer form -----------
// constants match gen_gptp_ucode.py at --clk-hz 2000000
static const int64_t SV_STEP_NS = 20000;
static const int64_t SV_GAIN_M = 4295, SV_GAIN_S = 6;
static const int64_t SV_ILIM = 1677722;          // 200 ppm at 2 MHz
static struct {
  int64_t intg = 0;
  bool stepped = false;                          // last sample stepped
  uint64_t step_val = 0;
  int64_t addend = 0;
} svm;

static void servo_mirror(int64_t off) {
  uint64_t mag = (uint64_t)(off + SV_STEP_NS);
  if (mag > (uint64_t)(2 * SV_STEP_NS)) {
    svm.stepped = true;
    svm.step_val = (uint64_t)(-off);
    return;                                      // integrator survives
  }
  svm.stepped = false;
  int64_t t = (off * SV_GAIN_M) >> SV_GAIN_S;
  svm.intg += (t >> 2);
  if (svm.intg > SV_ILIM) svm.intg = SV_ILIM;
  if (svm.intg < -SV_ILIM) svm.intg = -SV_ILIM;
  svm.addend = -((t - (t >> 2)) + svm.intg);
}

// ---- auto peer: answers every Pdelay_Req the DUT transmits ----------------
// peer clock runs at +2^-13 (~122 ppm) against ours; turnaround fields are
// constants of the mode, the ingress stamp is t1 + wire turnaround.
enum PdMode { PD_OFF, PD_NORMAL, PD_NEG, PD_FAR, PD_SKIP };
static PdMode pd_mode = PD_SKIP;         // SKIP: consume silently
static size_t pd_seen = 0;

static uint64_t peer_ns(uint64_t ours) {
  return 5000000ull + ours + (ours >> 13);
}

static void service_pdelay() {
  while (pd_seen < txf.size()) {
    size_t i = pd_seen;
    if ((txf[i].size() <= 14) || ((txf[i][14] & 0xF) != 0x2)) {
      pd_seen++;
      continue;
    }
    if (txns[i] == 0) return;            // egress ts not fed yet
    pd_seen++;
    if (pd_mode == PD_OFF) continue;     // lost response
    if (pd_mode == PD_SKIP) continue;    // pre-enable housekeeping
    uint16_t seq = (uint16_t)((txf[i][44] << 8) | txf[i][45]);
    uint64_t t1 = txns[i];
    uint64_t t2 = peer_ns(t1 + 300);
    uint64_t resid = 20000;              // D = +600 after correction
    if (pd_mode == PD_NEG) resid = 21300;   // D ~ -49: the Milan floor
    if (pd_mode == PD_FAR) resid = 19200;   // D ~ +1001: over threshold
    uint64_t t3 = t2 + resid;
    uint64_t t4 = t1 + 21200;
    Frame f = ptp(0x3, seq, 0, 0x0200, 20);
    f.ts(t2); f.u64(OUR_CID); f.u16(1);
    send_frame(f.b, t4);
    run(400);
    Frame g = ptp(0xA, seq, 0, 0x0000, 20);
    g.ts(t3); g.u64(OUR_CID); g.u16(1);
    send_frame(g.b, t4 + 1000);
    run(400);
    model_exchange(t1, t2, t3, t4);
  }
}

static void run_svc(uint64_t n) {
  while (n--) { tick(); if ((n & 255) == 0) service_pdelay(); }
}

static bool wait_flags(uint32_t mask, uint32_t want, uint64_t max_ticks) {
  for (uint64_t n = 0; n < max_ticks; n++) {
    if ((dut->pub_flags_o & mask) == want) return true;
    tick();
    if ((n & 255) == 0) service_pdelay();
  }
  return false;
}

static bool wait_exchanges(int count, uint64_t max_ticks) {
  for (uint64_t n = 0; n < max_ticks; n++) {
    if (pdm.count >= count) return true;
    tick();
    if ((n & 255) == 0) service_pdelay();
  }
  return false;
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
    if ((n & 255) == 0) service_pdelay();
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

  // ---- 1: our Pdelay_Req; asCapable must start low ----------------------
  std::vector<uint8_t> req = wait_tx(0x2, 3200000);
  if (!req.empty()) {
    check_common("pdreq", req, 0x2, 0x0000, 54, 0x00);
    uint64_t z = 0;
    for (int i = 48; i < 68; i++) z |= req[i];
    expect("pdreq body zero", z, 0);
  }
  expect("asCapable low at boot", dut->pub_flags_o & FL_ASCAP, 0);
  const uint64_t T1 = 1000000ull;
  txts(T1);
  run(2000);

  // ---- 2: one good exchange (D = 600); not capable yet ------------------
  const uint64_t T2 = peer_ns(T1 + 300), T3 = T2 + 20000,
                 T4 = T1 + 21200;
  {
    Frame f = ptp(0x3, 0, 0, 0x0200, 20);
    f.ts(T2); f.u64(OUR_CID); f.u16(1);
    send_frame(f.b, T4);
    run(4000);
    Frame g = ptp(0xA, 0, 0, 0x0000, 20);
    g.ts(T3); g.u64(OUR_CID); g.u16(1);
    send_frame(g.b, T4 + 1000);
    run(6000);
    model_exchange(T1, T2, T3, T4);
  }
  expect("pub pdelay ex1", dut->pub_pdelay_ns_o, (uint32_t)pdm.d);
  expect("one exchange not capable", dut->pub_flags_o & FL_ASCAP, 0);

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

  // ---- 4: the live peer raises asCapable on the SECOND exchange ---------
  auto_txts = true;
  pd_seen = txf.size();                  // answer only fresh requests
  pd_mode = PD_NORMAL;
  expect("second exchange -> capable",
         wait_flags(FL_ASCAP, FL_ASCAP, 6000000ull), 1);
  expect("capable at two exchanges", pdm.count, 2);
  expect("pub pdelay corrected", dut->pub_pdelay_ns_o, (uint32_t)pdm.d);

  // ---- 5: announce receipt timeout -> become master ---------------------
  expect("became master",
         wait_flags(FL_AMGM, FL_AMGM, 12000000ull), 1);
  expect("master flags", dut->pub_flags_o & 7,
         FL_PRESENT | FL_AMGM | FL_ASCAP);
  expect("gm is us", dut->pub_gm_id_o, OUR_CID);

  // ---- 6: our Announce ---------------------------------------------------
  tx_seen = txf.size();
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

  // ---- 7: our Sync + Follow_Up ------------------------------------------
  size_t sidx = 0;
  std::vector<uint8_t> sy = wait_tx(0x0, 800000, &sidx);
  uint16_t sseq = 0;
  if (!sy.empty()) {
    check_common("sync", sy, 0x0, 0x0208, 44, 0xFD);
    sseq = fld16(sy, 44);
  }
  run_svc(20000);                                // let its FU emerge
  std::vector<uint8_t> fu = wait_tx(0x8, 800000);
  if (!fu.empty()) {
    check_common("syncfu", fu, 0x8, 0x0008, 76, 0xFD);
    expect("syncfu seq", fld16(fu, 44), sseq);
    expect("syncfu origin", fld48(fu, 48) * 1000000000ull + fld32(fu, 54),
           txns[sidx]);
    expect("syncfu tlv", fld32(fu, 58), 0x0003001C);
    expect("syncfu org", fld48(fu, 62), 0x0080C2000001ull);
  }

  // ---- 8: worse announce -> stay master ---------------------------------
  {
    Frame f = ptp(0xB, 9, 0, 0x0008, 30);
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(250); f.u32(OUR_CQ); f.u8(248);
    f.u64(0xAABBCCFFFE010203ull);
    f.u16(0); f.u8(0xA0);
    send_frame(f.b, 5000000);
    run_svc(6000);
  }
  expect("still master", dut->pub_flags_o & FL_AMGM, FL_AMGM);
  expect("gm still us", dut->pub_gm_id_o, OUR_CID);
  expect("annq published",
         dut->pub_annq_o,
         (0xFFC4ull << 48) | (250ull << 40) | ((uint64_t)OUR_CQ << 8) |
         248ull);

  // ---- 9: better announce -> adopt, sync stops --------------------------
  // a rogue Sync heard while still master would leave a stale ingress
  // stamp; adopt must void it so it cannot pair with a post-adopt FU
  {
    Frame f = ptp(0x0, 0x0101, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, 19000000000ull);
    run(2000);
  }
  const uint64_t GMID = 0x00AACCFFFE010203ull;
  {
    Frame f = ptp(0xB, 10, 0, 0x0008, 30);
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(100); f.u32(OUR_CQ); f.u8(248);
    f.u64(GMID);
    f.u16(0); f.u8(0xA0);
    send_frame(f.b, 6000000);
    run_svc(6000);
  }
  expect("adopted", dut->pub_flags_o & 3, FL_PRESENT);
  expect("adopt keeps capable", dut->pub_flags_o & FL_ASCAP, FL_ASCAP);
  expect("gm is theirs", dut->pub_gm_id_o, GMID);
  {
    run_svc(20000);                              // drain anything in flight
    size_t before = txf.size();
    run_svc(700000);                             // 0.35 s: ~3 sync slots
    int syncs = 0;
    for (size_t i = before; i < txf.size(); i++)
      if ((txf[i][14] & 0xF) == 0x0) syncs++;
    expect("sync TX stopped", syncs, 0);
  }

  // ---- 10: as slave, peer sync -> offset; sync-ok rises -----------------
  expect("sync-ok low before sync", dut->pub_flags_o & FL_SYNCOK, 0);
  const uint64_t TRX = 20000000000ull, ORIGIN = 19999000000ull,
                 CORR_NS = 1000ull;
  {
    // an FU pairing with the pre-adopt rogue Sync must find nothing
    Frame g = ptp(0x8, 0x0101, CORR_NS << 16, 0x0000, 10);
    g.ts(ORIGIN - 1000000000ull);
    send_frame(g.b, TRX - 999999500ull);
    run(6000);
  }
  expect("rogue sync voided on adopt", (uint32_t)dut->pub_offset_o, 0);
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
  const uint64_t OFF = TRX - (ORIGIN + CORR_NS + (uint64_t)pdm.d);
  expect("pub offset", (uint32_t)dut->pub_offset_o, (uint32_t)OFF);
  expect("sync-ok rose", dut->pub_flags_o & FL_SYNCOK, FL_SYNCOK);
  servo_mirror((int64_t)OFF);
  expect("big offset re-bases the phc",
         !steps_seen.empty() && svm.stepped &&
             steps_seen.back() == svm.step_val, 1);

  // ---- 11: a Follow_Up later than 125 ms pairs with nothing -------------
  // the lone pair's origin is skewed -777 ns so a wrong pairing would
  // move the published offset instead of reproducing it
  {
    Frame f = ptp(0x0, 0x0103, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX + 1000000000ull);
    run_svc(270000);                             // 135 ms: FU watch fires
    Frame g = ptp(0x8, 0x0103, CORR_NS << 16, 0x0000, 10);
    g.ts(ORIGIN + 999999223ull);
    send_frame(g.b, TRX + 1000000500ull);
    run(6000);
  }
  expect("late FU dropped", (uint32_t)dut->pub_offset_o, (uint32_t)OFF);
  expect("late FU never steers", steps_seen.size() + adj_seen.size(),
         1);                                     // only phase 10's step
  const uint64_t TRX2 = TRX + 2000000000ull, ORIGIN2 = ORIGIN + 1999000000ull;
  {
    Frame f = ptp(0x0, 0x0104, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX2);
    run(2000);
    Frame g = ptp(0x8, 0x0104, CORR_NS << 16, 0x0000, 10);
    g.ts(ORIGIN2);
    send_frame(g.b, TRX2 + 500);
    run(6000);
  }
  const uint64_t OFF2 = TRX2 - (ORIGIN2 + CORR_NS + (uint64_t)pdm.d);
  expect("next pair lands", (uint32_t)dut->pub_offset_o, (uint32_t)OFF2);
  servo_mirror((int64_t)OFF2);

  // ---- 12: syncReceiptTimeout (375 ms) -> sync-ok falls -----------------
  expect("sync-ok falls on timeout",
         wait_flags(FL_SYNCOK, 0, 900000ull), 1);
  expect("still slave at the verdict", dut->pub_flags_o & 3, FL_PRESENT);
  expect("timeout keeps capable", dut->pub_flags_o & FL_ASCAP, FL_ASCAP);

  // ---- 13: a +1 ms offset STEPS the phc by its negation -----------------
  {
    size_t adj_before = adj_seen.size();
    const uint64_t TRX3 = 30000000000ull;
    const uint64_t ORG3 = TRX3 - CORR_NS - (uint64_t)pdm.d - 1000000ull;
    Frame f = ptp(0x0, 0x0105, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX3);
    run(2000);
    Frame g = ptp(0x8, 0x0105, CORR_NS << 16, 0x0000, 10);
    g.ts(ORG3);
    send_frame(g.b, TRX3 + 500);
    run(6000);
    servo_mirror(1000000);
    expect("step is the negation",
           !steps_seen.empty() && steps_seen.back() == svm.step_val &&
               svm.step_val == (uint64_t)(-1000000ll), 1);
    expect("a step is not a slew", adj_seen.size(), adj_before);
  }

  // ---- 14: a +5 us offset SLEWS: the PI addend matches the mirror -------
  {
    size_t steps_before = steps_seen.size();
    const uint64_t TRX4 = 31000000000ull;
    const uint64_t ORG4 = TRX4 - CORR_NS - (uint64_t)pdm.d - 5000ull;
    Frame f = ptp(0x0, 0x0106, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX4);
    run(2000);
    Frame g = ptp(0x8, 0x0106, CORR_NS << 16, 0x0000, 10);
    g.ts(ORG4);
    send_frame(g.b, TRX4 + 500);
    run(6000);
    servo_mirror(5000);
    expect("slew addend matches the PI mirror",
           !adj_seen.empty() &&
               adj_seen.back() == (uint32_t)(int32_t)svm.addend, 1);
    expect("a slew is not a step", steps_seen.size(), steps_before);
  }

  // ---- 15: closed loop -- a +100 ppm master converges to lock -----------
  // the master clock runs independent of our phc: 1 ms ahead at start,
  // +0.05 ns per cycle faster. The first pair steps; the PI then drives
  // the measured offset to zero with the integrator carrying the rate.
  {
    size_t steps_before = steps_seen.size();
    uint64_t mst_base = phc() + 1000000ull - cyc * 500ull - cyc / 20ull;
    uint16_t sq = 0x0200;
    for (int k = 0; k < 24; k++) {
      if ((k % 8) == 0) {                        // keep the GM elected
        Frame a = ptp(0xB, (uint16_t)(20 + k), 0, 0x0008, 30);
        for (int i = 0; i < 10; i++) a.u8(0);
        a.u16(0xFFC4); a.u8(0);
        a.u8(100); a.u32(OUR_CQ); a.u8(248);
        a.u64(GMID);
        a.u16(0); a.u8(0xA0);
        send_frame(a.b, phc() + 150);
        run(4000);
      }
      run_svc(250000);                           // one 125 ms interval
      uint64_t origin = mst_base + cyc * 500ull + cyc / 20ull;
      uint64_t local_rx = phc() + 150;
      Frame f = ptp(0x0, sq, 0, 0x0208, 10);
      f.ts(0);
      send_frame(f.b, local_rx);
      run(1000);
      Frame g = ptp(0x8, sq, 0, 0x0000, 10);
      g.ts(origin);
      send_frame(g.b, local_rx + 500);
      run(4000);
      sq++;
    }
    expect("one re-base then lock", steps_seen.size(), steps_before + 1);
    int32_t final_off = (int32_t)dut->pub_offset_o;
    expect("measured offset converged",
           final_off > -200 && final_off < 200, 1);
    // ideal rate correction for +100 ppm at 2 MHz: +0.05 ns/tick
    // = +838,861 addend units; the integrator must carry it
    int32_t final_adj = (int32_t)phc_adj;
    expect("addend carries the master's rate",
           final_adj > 755000 && final_adj < 923000, 1);
  }

  // ---- 16: negative pdelay inside the Milan floor is accepted -----------
  pd_mode = PD_NEG;
  {
    int base = pdm.count;
    expect("neg exchange ran", wait_exchanges(base + 1, 4000000ull), 1);
    run(4000);
  }
  expect("neg pdelay published", dut->pub_pdelay_ns_o, (uint32_t)pdm.d);
  expect("neg pdelay in floor",
         pdm.d < 0 && pdm.d >= -80, 1);
  expect("neg keeps capable", dut->pub_flags_o & FL_ASCAP, FL_ASCAP);

  // ---- 17: over the 800 ns threshold -> asCapable falls -----------------
  pd_mode = PD_FAR;
  {
    int base = pdm.count;
    expect("far exchange ran", wait_exchanges(base + 1, 4000000ull), 1);
    run(4000);
  }
  expect("far pdelay published", dut->pub_pdelay_ns_o, (uint32_t)pdm.d);
  expect("far pdelay over thresh", pdm.d > 800, 1);
  expect("threshold clears capable", dut->pub_flags_o & FL_ASCAP, 0);

  // ---- 18: recovery takes two good exchanges again ----------------------
  pd_mode = PD_NORMAL;
  {
    int base = pdm.count;
    expect("recovery ex1 ran", wait_exchanges(base + 1, 4000000ull), 1);
    run(4000);
    expect("one good is not enough", dut->pub_flags_o & FL_ASCAP, 0);
    expect("recovery ex2 ran", wait_exchanges(base + 2, 4000000ull), 1);
    run(4000);
    expect("two goods recover", dut->pub_flags_o & FL_ASCAP, FL_ASCAP);
  }

  // ---- 19: lost responses clear asCapable at the FOURTH -----------------
  // 802.1AS-2011 11.2.12.4: the count must EXCEED allowedLostResponses=3
  pd_mode = PD_OFF;
  size_t off_mark = txf.size();
  expect("lost responses clear capable",
         wait_flags(FL_ASCAP, 0, 12000000ull), 1);
  {
    int reqs = 0;
    for (size_t i = off_mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2) reqs++;
    expect("fall at the fourth lost", reqs == 4 || reqs == 5, 1);
  }

  // ---- 20: a window wider than 2^32 ns must not update the ratio --------
  // the OFF span above left > 4.3 s between answered exchanges; the
  // first answer after it takes the staleness path in model and DUT
  pd_mode = PD_NORMAL;
  {
    int base = pdm.count;
    expect("post-gap exchange ran", wait_exchanges(base + 1, 4000000ull), 1);
    run(4000);
  }
  expect("gap took the stale path", pdm.stale_skip, 1);
  expect("stale window skips ratio", dut->pub_pdelay_ns_o, (uint32_t)pdm.d);

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
