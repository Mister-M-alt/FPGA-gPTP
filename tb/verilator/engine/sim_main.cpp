// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_engine protocol round-trip -- v5, the servo round.
//
//  1..4   pdelay bring-up: byte-exact both roles, asCapable at the
//         second good exchange and not the first (Milan 4.2.6.2.4)
//  3b     a foreign-domain Pdelay_Req draws no frame and counts one drop;
//         a domain-0 request right after it is answered (8.1, #6)
//  3c     a header-only and a cut Pdelay_Req draw no frame and count one
//         drop each; the complete request after them is answered (#12)
//  5..9   grandmaster life: timeout become (asCapable-gated), Announce/
//         Sync/Follow_Up byte-exact, BTCA both directions, adoption
//  8b     a better Announce in a foreign domain never reaches BTCA: GM,
//         parent, flags and the raw published vector hold (8.1, #6)
// 10..12  slave sync path: offset, sync-ok verdict, the 125 ms
//         Follow_Up and 375 ms sync receipt timeouts (Table 4.2)
// 11b     a Sync/Follow_Up pair in a foreign domain never steers: the
//         offset, the PHC writes and the flags hold, and the foreign
//         Sync leaves no pending slot for a domain-0 Follow_Up (#6)
// 11c     a Follow_Up without its information TLV never steers and does
//         not consume the pending Sync; the complete one pairs (#11)
// 11d     a Sync padded to the 60-byte Ethernet minimum, and one padded
//         to 74, still pair
// 13..15  the servo: step-vs-slew at 20 us, the PI addend against an
//         exact-integer mirror, closed-loop lock on a +140 ppm master
//         (one re-base carrying the surviving integrator)
// 16..17  Sync/Follow_Up pairing by sequenceId AND source (11.4.4)
// 18,18b  BTCA tie-breaks: steps then source switch the parent with no
//         sync-ok flicker; a delayed dispatch reads the frame its event
//         names (the second bank), so a worse announce rejects cleanly
// 19..21  parent degradation yields mastership immediately (10.3.5);
//         the Sync body stays zero while its Follow_Up carries the live
//         egress stamp; an asCapable fall stops consumption and steering
// 21b,21c become resets the best record (no ghost GM after a quiet
//         ride to mastership); the priority vector outranks the
//         identity in the compare order
// 21d     the delayed-dispatch shape with a BETTER announce adopts:
//         the torn-read window is retired by the second bank
// 22..26  the pdelay verdict tail: the Milan floor, the threshold,
//         two-exchange recovery, the fourth lost response, the stale
//         ratio window
// 27      the Milan 4.2.6.2.5 cease rule: storm, silence, resume,
//         re-earn -- and same-identity duplicates are not a storm
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
                 uint16_t flags, uint16_t body_len,
                 uint64_t src = PEER_CID) {
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
  f.u64(src); f.u16(1);
  f.u16(seq);
  f.u8(0x05); f.u8(0x7F);
  return f;
}

// a Follow_Up: header, preciseOriginTimestamp and the information TLV
// (802.1AS-2011 Table 11-9: 76 octets; 11.4.4.3 / Table 11-10: tlvType
// 0x3, lengthField 28, organizationId 00-80-C2, organizationSubType 1,
// then cumulativeScaledRateOffset, gmTimeBaseIndicator, lastGmPhaseChange
// and scaledLastGmFreqChange). Until #11 every Follow_Up this suite sent
// stopped after the timestamp: the shape the parser wrongly accepted was
// the shape the bench called valid
static Frame follow_up(uint16_t seq, uint64_t corr, uint64_t origin,
                       uint64_t src = PEER_CID) {
  Frame g = ptp(0x8, seq, corr, 0x0000, 42, src);
  g.ts(origin);
  g.u16(0x0003); g.u16(28);
  g.u8(0x00); g.u8(0x80); g.u8(0xC2);
  g.u8(0x00); g.u8(0x00); g.u8(0x01);
  g.u32(0);                                    // cumulativeScaledRateOffset
  g.u16(0);                                    // gmTimeBaseIndicator
  for (int i = 0; i < 12; i++) g.u8(0);        // lastGmPhaseChange
  g.u32(0);                                    // scaledLastGmFreqChange
  return g;
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
    svm.addend = -svm.intg;      // the surviving rate estimate, alone
    return;
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
enum PdMode { PD_OFF, PD_NORMAL, PD_NEG, PD_FAR, PD_SKIP, PD_DUAL,
              PD_DUP };
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
    if (pd_mode == PD_DUAL || pd_mode == PD_DUP) {
      uint64_t src2 = (pd_mode == PD_DUAL) ? 0x0077770077FE0077ull
                                           : PEER_CID;
      Frame d = ptp(0x3, seq, 0, 0x0200, 20, src2);
      d.ts(t2 + 40); d.u64(OUR_CID); d.u16(1);
      send_frame(d.b, t4 + 80);
      run(400);
    }
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

// a sync+FU pair from `src`; returns the offset the plane should see
static void sync_pair(uint16_t seq, uint64_t local_rx, uint64_t origin,
                      uint64_t src = PEER_CID) {
  Frame f = ptp(0x0, seq, 0, 0x0208, 10, src);
  f.ts(0);
  send_frame(f.b, local_rx);
  run(2000);
  Frame g = follow_up(seq, 0, origin, src);
  send_frame(g.b, local_rx + 500);
  run(6000);
}

// an announce carrying {p1, gmid, steps} from `src`
static void announce(uint16_t seq, uint8_t p1, uint64_t gmid,
                     uint16_t steps, uint64_t src) {
  Frame a = ptp(0xB, seq, 0, 0x0008, 30, src);
  for (int i = 0; i < 10; i++) a.u8(0);
  a.u16(0xFFC4); a.u8(0);
  a.u8(p1); a.u32(OUR_CQ); a.u8(248);
  a.u64(gmid);
  a.u16(steps); a.u8(0xA0);
  send_frame(a.b, 5000000);
  run(6000);
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
  // 802.1AS-2011 Table 11-7: Sync and Follow_Up have their own control
  // values; Announce and every Pdelay message use the delay-management
  // value. Keep this oracle independent from the µcode header builder.
  uint8_t control = 0x05;
  if (mtype == 0x0) control = 0x00;
  if (mtype == 0x8) control = 0x02;
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
  snprintf(n, 64, "%s control", tag); expect(n, f[46], control);
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

  // ---- 3b: a foreign-domain Pdelay_Req draws no frame; domain 0 does ----
  // the responder is the wire-visible role, and Pdelay_Req is one of the
  // two header-only types whose min_ok_r is set regardless of bad_r, so
  // the parser's end-of-frame gate is the only barrier after the domain
  // arm: a gate that dropped the frame but still dispatched the event
  // would answer from the STALE bank. Domain 0x10 has a zero low nibble,
  // so a compare narrowed to four bits would admit it (FPGA-gPTP #6)
  {
    uint16_t drops = dut->dbg_rx_drop_o;
    size_t mark = txf.size();
    Frame f = ptp(0x2, 0x55AB, 0, 0x0000, 20);
    f.b[18] = 0x10;                              // domainNumber, byte 4
    f.u64(0); f.u16(0); f.ts(0);
    f.b.resize(68);
    send_frame(f.b, T2R + 100000);
    run(4000);
    int resps = 0;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x3) resps++;
    expect("foreign-domain request: no Pdelay_Resp", resps, 0);
    expect("foreign-domain request: dropped and counted",
           dut->dbg_rx_drop_o, (uint16_t)(drops + 1));
    tx_seen = txf.size();
    Frame g = ptp(0x2, 0x55AC, 0, 0x0000, 20);   // domain 0, right after
    g.u64(0); g.u16(0); g.ts(0);
    g.b.resize(68);
    send_frame(g.b, T2R + 200000);
    std::vector<uint8_t> r2 = wait_tx(0x3, 400000);
    if (!r2.empty()) {
      expect("domestic request after it: answered", fld16(r2, 44), 0x55AC);
      expect("domestic request after it: reqCID", fld64(r2, 58), PEER_CID);
    }
    txts(T3R + 200000);
    std::vector<uint8_t> u2 = wait_tx(0xA, 400000);
    if (!u2.empty())
      expect("domestic request after it: Resp_FU pairs", fld16(u2, 44),
             0x55AC);
  }

  // ---- 3c: a truncated Pdelay_Req draws no frame; a complete one does ---
  // 802.1AS-2011 11.4.5 / Table 11-11: a Pdelay_Req is 54 octets, the
  // header and two reserved 10-octet fields; until #12 the parser's
  // minimum was the 34-octet header, so a header-only request dispatched
  // and the responder answered it from that header. Three shapes in turn:
  // header-only (messageLength 34 in a 48-byte frame, the issue's shape,
  // refused at the messageLength byte ahead of every bank write), a
  // declared 54 cut at 53 octets (refused at the end-of-frame gate), then
  // the complete request. The first two draw no Pdelay_Resp over the
  // window and count one drop each; the third is answered with its own
  // sequence and its Resp_FU, so the refusals left the responder intact
  {
    uint16_t drops = dut->dbg_rx_drop_o;
    size_t mark = txf.size();
    Frame f = ptp(0x2, 0x55AD, 0, 0x0000, 0);      // 34 octets: header only
    send_frame(f.b, T2R + 300000);
    run(4000);
    Frame g = ptp(0x2, 0x55AE, 0, 0x0000, 20);
    g.u64(0); g.u16(0); g.ts(0);
    g.b.resize(67);                                // declared 54, cut at 53
    send_frame(g.b, T2R + 350000);
    run(4000);
    int resps = 0;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x3) resps++;
    expect("truncated requests: no Pdelay_Resp", resps, 0);
    expect("truncated requests: dropped and counted", dut->dbg_rx_drop_o,
           (uint16_t)(drops + 2));
    tx_seen = txf.size();
    Frame k = ptp(0x2, 0x55AF, 0, 0x0000, 20);     // the complete request
    k.u64(0); k.u16(0); k.ts(0);
    k.b.resize(68);
    send_frame(k.b, T2R + 400000);
    std::vector<uint8_t> r3 = wait_tx(0x3, 400000);
    if (!r3.empty()) {
      expect("complete request after them: answered", fld16(r3, 44), 0x55AF);
      expect("complete request after them: reqCID", fld64(r3, 58), PEER_CID);
    }
    txts(T3R + 400000);
    std::vector<uint8_t> u3 = wait_tx(0xA, 400000);
    if (!u3.empty())
      expect("complete request after them: Resp_FU pairs", fld16(u3, 44),
             0x55AF);
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
    uint8_t reserved = 0;
    for (int i = 48; i < 58; i++) reserved |= sy[i];
    expect("sync reserved body zero", reserved, 0);
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
  const uint64_t ANNQ8 =
      (0xFFC4ull << 48) | (250ull << 40) | ((uint64_t)OUR_CQ << 8) | 248ull;
  expect("annq published", dut->pub_annq_o, ANNQ8);

  // ---- 8b: a BETTER announce in a foreign domain cannot move the GM ----
  // 802.1AS-2011 8.1: the gPTP domain number is 0; IEEE 1588-2008 9.5.1:
  // only messages whose domainNumber matches are accepted for processing.
  // priority1 1 wins BTCA outright in domain 0; in domain 5 it must never
  // reach the announce handler, whose FIRST act is publishing the raw
  // vector -- so pub_annq_o still holding phase 8's vector proves the
  // frame was refused before any state moved (FPGA-gPTP #6)
  {
    uint16_t drops = dut->dbg_rx_drop_o;
    uint32_t flags = dut->pub_flags_o;
    Frame f = ptp(0xB, 11, 0, 0x0008, 30, 0x00A5A5FFFE000005ull);
    f.b[18] = 5;                                 // domainNumber, byte 4
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(1); f.u32(OUR_CQ); f.u8(248);
    f.u64(0x0000000000005555ull);
    f.u16(0); f.u8(0xA0);
    send_frame(f.b, 5500000);
    run_svc(6000);
    expect("foreign-domain announce: still master",
           dut->pub_flags_o & FL_AMGM, FL_AMGM);
    expect("foreign-domain announce: gm still us", dut->pub_gm_id_o, OUR_CID);
    expect("foreign-domain announce: parent still us", dut->pub_parent_id_o,
           OUR_CID);
    expect("foreign-domain announce: flags untouched", dut->pub_flags_o,
           flags);
    expect("foreign-domain announce: raw vector never published",
           dut->pub_annq_o, ANNQ8);
    expect("foreign-domain announce: dropped and counted",
           dut->dbg_rx_drop_o, (uint16_t)(drops + 1));
  }

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
    Frame g = follow_up(0x0101, CORR_NS << 16, ORIGIN - 1000000000ull);
    send_frame(g.b, TRX - 999999500ull);
    run(6000);
  }
  expect("rogue sync voided on adopt", (uint32_t)dut->pub_offset_o, 0);
  {
    Frame f = ptp(0x0, 0x0102, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX);
    run(2000);
    Frame g = follow_up(0x0102, CORR_NS << 16, ORIGIN);
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
    Frame g = follow_up(0x0103, CORR_NS << 16, ORIGIN + 999999223ull);
    send_frame(g.b, TRX + 1000000500ull);
    run(6000);
  }
  expect("late FU dropped", (uint32_t)dut->pub_offset_o, (uint32_t)OFF);
  expect("late FU never steers", steps_seen.size() + adj_seen.size(),
         2);                                     // phase 10's step + its -I
  const uint64_t TRX2 = TRX + 2000000000ull, ORIGIN2 = ORIGIN + 1999000000ull;
  {
    Frame f = ptp(0x0, 0x0104, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX2);
    run(2000);
    Frame g = follow_up(0x0104, CORR_NS << 16, ORIGIN2);
    send_frame(g.b, TRX2 + 500);
    run(6000);
  }
  const uint64_t OFF2 = TRX2 - (ORIGIN2 + CORR_NS + (uint64_t)pdm.d);
  expect("next pair lands", (uint32_t)dut->pub_offset_o, (uint32_t)OFF2);
  servo_mirror((int64_t)OFF2);

  // ---- 11b: a Sync + Follow_Up pair in a foreign domain never steers ---
  // the pair is otherwise perfect (matching sequenceId and source, the
  // origin skewed -777 ns so a wrong acceptance would move the published
  // offset by +777) but carries domainNumber 5: both frames drop at the
  // header, the offset and the PHC knobs are untouched, and the foreign
  // Sync left no pending slot, so a domain-0 Follow_Up with its sequence
  // pairs with nothing either (FPGA-gPTP #6)
  {
    uint16_t drops = dut->dbg_rx_drop_o;
    size_t writes = steps_seen.size() + adj_seen.size();
    uint32_t flags = dut->pub_flags_o;
    const uint64_t TRXF = TRX2 + 500000000ull;
    const uint64_t ORGF = ORIGIN2 + 500000000ull - 777ull;
    Frame f = ptp(0x0, 0x0110, 0, 0x0208, 10);
    f.b[18] = 5;                                 // domainNumber, byte 4
    f.ts(0);
    send_frame(f.b, TRXF);
    run(2000);
    Frame g = follow_up(0x0110, CORR_NS << 16, ORGF);
    g.b[18] = 5;
    send_frame(g.b, TRXF + 500);
    run(6000);
    expect("foreign-domain pair: offset unmoved", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF2);
    expect("foreign-domain pair: never steers",
           steps_seen.size() + adj_seen.size(), writes);
    expect("foreign-domain pair: flags untouched", dut->pub_flags_o, flags);
    expect("foreign-domain pair: both dropped and counted",
           dut->dbg_rx_drop_o, (uint16_t)(drops + 2));
    Frame h = follow_up(0x0110, CORR_NS << 16, ORGF);   // domain 0
    send_frame(h.b, TRXF + 600);
    run(6000);
    expect("foreign Sync left no pending slot", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF2);
    expect("orphan Follow_Up never steers",
           steps_seen.size() + adj_seen.size(), writes);
  }

  // ---- 11c: a Follow_Up without its information TLV never steers --------
  // 802.1AS-2011 Table 11-9: a Follow_Up is 76 octets, the header, the
  // preciseOriginTimestamp and the information TLV that 11.4.4.3 makes a
  // field of the message; until #11 the parser's minimum was the 44-octet
  // header-and-timestamp shape, so a TLV-less Follow_Up dispatched, set
  // sync-ok and moved the offset. Against a valid pending Sync, three
  // malformed Follow_Ups in turn: messageLength 44 with 44 octets (the
  // issue's shape, refused at the messageLength byte ahead of every bank
  // write), messageLength 76 cut at 75 octets (refused at the end-of-
  // frame gate), and a 76-octet frame whose TLV type is 0x0008 (refused
  // at the TLV header). Each carries the pairing sequence and source with
  // an origin skewed a further -777 ns, so a wrong acceptance would move
  // the published offset; each is counted and leaves the offset, the PHC
  // knobs and the flags unmoved; none consumes the pending Sync, so the
  // complete Follow_Up that follows pairs with it and lands an offset 333
  // ns from the previous one, then re-bases the PHC by its negation
  {
    uint16_t drops = dut->dbg_rx_drop_o;
    size_t writes = steps_seen.size() + adj_seen.size();
    uint32_t flags = dut->pub_flags_o;
    const uint64_t TRXM = TRX2 + 1000000000ull;
    const uint64_t ORGM = ORIGIN2 + 1000000000ull - 333ull;
    Frame f = ptp(0x0, 0x0111, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRXM);
    run(2000);
    Frame g = ptp(0x8, 0x0111, CORR_NS << 16, 0x0000, 10);   // 44 octets
    g.ts(ORGM - 777ull);
    send_frame(g.b, TRXM + 500);
    run(6000);
    expect("TLV-less Follow_Up: offset unmoved", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF2);
    expect("TLV-less Follow_Up: never steers",
           steps_seen.size() + adj_seen.size(), writes);
    expect("TLV-less Follow_Up: flags untouched", dut->pub_flags_o, flags);
    expect("TLV-less Follow_Up: dropped and counted", dut->dbg_rx_drop_o,
           (uint16_t)(drops + 1));
    Frame h = follow_up(0x0111, CORR_NS << 16, ORGM - 777ull);
    h.b.resize(89);                              // declared 76, cut at 75
    send_frame(h.b, TRXM + 600);
    run(6000);
    expect("cut Follow_Up: offset unmoved", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF2);
    expect("cut Follow_Up: never steers",
           steps_seen.size() + adj_seen.size(), writes);
    expect("cut Follow_Up: dropped and counted", dut->dbg_rx_drop_o,
           (uint16_t)(drops + 2));
    Frame k = follow_up(0x0111, CORR_NS << 16, ORGM - 777ull);
    k.b[59] = 0x08;                              // tlvType 0x0008: path trace
    send_frame(k.b, TRXM + 700);
    run(6000);
    expect("wrong-TLV Follow_Up: offset unmoved", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF2);
    expect("wrong-TLV Follow_Up: never steers",
           steps_seen.size() + adj_seen.size(), writes);
    expect("wrong-TLV Follow_Up: flags untouched", dut->pub_flags_o, flags);
    expect("wrong-TLV Follow_Up: dropped and counted", dut->dbg_rx_drop_o,
           (uint16_t)(drops + 3));
    Frame m = follow_up(0x0111, CORR_NS << 16, ORGM);
    send_frame(m.b, TRXM + 800);
    run(6000);
    const uint64_t OFFM = TRXM - (ORGM + CORR_NS + (uint64_t)pdm.d);
    expect("complete Follow_Up pairs with the surviving Sync",
           (uint32_t)dut->pub_offset_o, (uint32_t)OFFM);
    expect("complete Follow_Up: nothing further dropped", dut->dbg_rx_drop_o,
           (uint16_t)(drops + 3));
    servo_mirror((int64_t)OFFM);
    expect("complete Follow_Up re-bases the phc",
           !steps_seen.empty() && svm.stepped &&
               steps_seen.back() == svm.step_val, 1);
  }

  // ---- 11d: a Sync padded to the Ethernet minimum still pairs ----------
  // a 44-octet Sync is a 58-byte frame, so every Sync a real link
  // delivers arrives padded to 60 bytes (IEEE 1588-2008 13.3.2.4 NOTE:
  // messageLength excludes the padding); an arm keyed on a byte past 57
  // that is not gated on the message type would refuse every one of
  // them while passing a suite that never pads (the #18 review's MR7).
  // Two shapes: the 60-byte minimum, and a Sync padded to 74 bytes, the
  // span of the whole Follow_Up TLV header arm (octets past messageLength
  // are padding to a receiver whatever their count). Each is accepted
  // with no drop, its Follow_Up pairs with it, and the pair re-bases the
  // PHC by the negation of its own offset. The 74-byte shape is the one
  // an arm at byte 59 cannot hide from: a poison raised on a frame's eof
  // byte is not seen by the end-of-frame gate, which samples bad_r as
  // registered, so the 60-byte shape alone would pass MR7
  {
    struct Pad { const char *tag; uint16_t seq; size_t pad; uint64_t skew; };
    const Pad pads[] = { {"padded Sync (60)", 0x0112, 2, 555ull},
                         {"padded Sync (74)", 0x0113, 16, 999ull} };
    for (const Pad &p : pads) {
      char n[64];
      uint16_t drops = dut->dbg_rx_drop_o;
      const uint64_t TRXP = TRX2 + 1200000000ull + (uint64_t)p.seq * 1000ull;
      const uint64_t ORGP = ORIGIN2 + 1200000000ull + (uint64_t)p.seq * 1000ull
                            - p.skew;
      Frame f = ptp(0x0, p.seq, 0, 0x0208, 10);
      f.ts(0);
      for (size_t i = 0; i < p.pad; i++) f.u8(0);   // the padding
      send_frame(f.b, TRXP);
      run(2000);
      snprintf(n, sizeof n, "%s: accepted, no drop", p.tag);
      expect(n, dut->dbg_rx_drop_o, drops);
      Frame g = follow_up(p.seq, CORR_NS << 16, ORGP);
      send_frame(g.b, TRXP + 500);
      run(6000);
      const uint64_t OFFP = TRXP - (ORGP + CORR_NS + (uint64_t)pdm.d);
      snprintf(n, sizeof n, "%s pairs: offset", p.tag);
      expect(n, (uint32_t)dut->pub_offset_o, (uint32_t)OFFP);
      servo_mirror((int64_t)OFFP);
      snprintf(n, sizeof n, "%s pairs: re-bases the phc", p.tag);
      expect(n, !steps_seen.empty() && svm.stepped &&
                    steps_seen.back() == svm.step_val, 1);
    }
  }

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
    Frame g = follow_up(0x0105, CORR_NS << 16, ORG3);
    send_frame(g.b, TRX3 + 500);
    run(6000);
    servo_mirror(1000000);
    expect("step is the negation",
           !steps_seen.empty() && steps_seen.back() == svm.step_val &&
               svm.step_val == (uint64_t)(-1000000ll), 1);
    expect("step writes the bare estimate",
           adj_seen.size() == adj_before + 1 &&
               adj_seen.back() == (uint32_t)(int32_t)(-svm.intg), 1);
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
    Frame g = follow_up(0x0106, CORR_NS << 16, ORG4);
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
    int64_t intg_at_entry = svm.intg;            // phase 14's ki deposit
    uint64_t mst_base =
        phc() + 1000000ull - cyc * 500ull - cyc * 7ull / 100ull;
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
      uint64_t origin = mst_base + cyc * 500ull + cyc * 7ull / 100ull;
      uint64_t local_rx = phc() + 150;
      Frame f = ptp(0x0, sq, 0, 0x0208, 10);
      f.ts(0);
      send_frame(f.b, local_rx);
      run(1000);
      Frame g = follow_up(sq, 0, origin);
      send_frame(g.b, local_rx + 500);
      run(4000);
      if (k == 0) {
        // the one step: its addend write must be the surviving
        // integrator alone, and that integrator is nonzero here --
        // a step path that cleared it would write zero instead
        expect("integrator survives the step",
               intg_at_entry != 0 && !adj_seen.empty() &&
                   adj_seen.back() ==
                       (uint32_t)(int32_t)(-intg_at_entry), 1);
      }
      sq++;
    }
    expect("one re-base then lock", steps_seen.size(), steps_before + 1);
    int32_t final_off = (int32_t)dut->pub_offset_o;
    expect("measured offset converged",
           final_off > -200 && final_off < 200, 1);
    // ideal rate correction for +140 ppm at 2 MHz: +0.07 ns/tick
    // = +1,174,405 addend units. The target sits ABOVE half the
    // +-200 ppm integrator clamp on purpose: a clamp mutation to
    // ILIM/2 cannot carry this master and fails the lock
    int32_t final_adj = (int32_t)phc_adj;
    expect("addend carries the master's rate",
           final_adj > 1056965 && final_adj < 1291846, 1);
  }

  // ---- 16: a Follow_Up with the wrong sequenceId pairs with nothing -----
  const uint64_t TRX6 = 40000000000ull;
  {
    uint32_t off_before = dut->pub_offset_o;
    Frame f = ptp(0x0, 0x0400, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX6);
    run(2000);
    Frame g = follow_up(0x0401, 0, TRX6 - 5000);   // wrong seq
    send_frame(g.b, TRX6 + 500);
    run(6000);
    expect("mismatched seq dropped", dut->pub_offset_o, off_before);
    Frame h = follow_up(0x0400, 0, TRX6 - 5000);   // the right one
    send_frame(h.b, TRX6 + 600);
    run(6000);
    const uint64_t OFF6 = TRX6 - (TRX6 - 5000 + (uint64_t)pdm.d);
    expect("matching FU still lands", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF6);
  }

  // ---- 17: a Follow_Up from the wrong source pairs with nothing ---------
  const uint64_t IMPOSTOR = 0x00DEADFFFE000001ull;
  {
    uint32_t off_before = dut->pub_offset_o;
    Frame f = ptp(0x0, 0x0410, 0, 0x0208, 10);
    f.ts(0);
    send_frame(f.b, TRX6 + 1000000000ull);
    run(2000);
    Frame g = follow_up(0x0410, 0, TRX6 + 1000000000ull - 7000, IMPOSTOR);
    send_frame(g.b, TRX6 + 1000000500ull);
    run(6000);
    expect("impostor FU dropped", dut->pub_offset_o, off_before);
    Frame h = follow_up(0x0410, 0, TRX6 + 1000000000ull - 7000);
    send_frame(h.b, TRX6 + 1000000600ull);
    run(6000);
    const uint64_t OFF7 = 7000 - (uint64_t)pdm.d;
    expect("paired FU still lands", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF7);
  }

  // ---- 18: gmId tie -> stepsRemoved -> sourcePortIdentity ---------------
  // same GM and vector through a second announcer with a LOWER source
  // identity: the source tiebreak switches the parent; sync-ok and the
  // GM identity hold (no adoption flicker)
  const uint64_t SRC2 = 0x0011223344556677ull;
  {
    expect("sync-ok up before the switch",
           dut->pub_flags_o & FL_SYNCOK, FL_SYNCOK);
    announce(40, 100, GMID, 0, SRC2);
    expect("source tiebreak switches parent", dut->pub_parent_id_o, SRC2);
    expect("gm survives the switch", dut->pub_gm_id_o, GMID);
    expect("no flicker on the switch",
           dut->pub_flags_o & FL_SYNCOK, FL_SYNCOK);
    // a LONGER path to the same GM loses on stepsRemoved
    announce(41, 100, GMID, 1, 0x00F0F0FFFE000001ull);
    expect("longer path rejected", dut->pub_parent_id_o, SRC2);
    // and a SHORTER path wins on stepsRemoved BEFORE the source
    // tiebreak: the parent re-roots deeper, then a higher-identity
    // announcer with fewer hops takes over
    announce(46, 100, GMID, 3, SRC2);
    const uint64_t SRC5 = 0x00F1F1FFFE000009ull;
    announce(47, 100, GMID, 1, SRC5);
    expect("shorter path wins", dut->pub_parent_id_o, SRC5);
  }

  // ---- 18b: a delayed dispatch must not act on a torn bank --------------
  // a pdelay-req occupies the uCPU; a worse announce and then a Sync
  // from the CURRENT PARENT arrive zero-gap. Sync frames never write
  // the announce bank words, so the delayed announce dispatch reads
  // the announce's worse vector with the SYNC's source: without the
  // closing seq guard that torn read is a parent-update take of a
  // worse vector, our vector wins, and the plane wrongfully seizes
  // mastership (the review's R8 failure mode, made deterministic)
  {
    Frame q = ptp(0x2, 0x7777, 0, 0x0000, 20);
    q.u64(0); q.u16(0); q.ts(0);
    q.b.resize(68);
    send_frame(q.b, phc() + 150);
    Frame a = ptp(0xB, 60, 0, 0x0008, 30, 0x00A0A0FFFE000011ull);
    for (int i = 0; i < 10; i++) a.u8(0);
    a.u16(0xFFC4); a.u8(0);
    a.u8(200); a.u32(OUR_CQ); a.u8(248);
    a.u64(0x00A0A0FFFE0000AAull);
    a.u16(0); a.u8(0xA0);
    Frame sy = ptp(0x0, 0x7778, 0, 0x0208, 10, 0x00F1F1FFFE000009ull);
    sy.ts(0);
    send_frame(a.b, phc() + 300);
    send_frame(sy.b, phc() + 400);               // zero-gap, parent src
    run(20000);
    expect("no wrongful takeover", dut->pub_flags_o & FL_AMGM, 0);
    expect("gm undisturbed by the race", dut->pub_gm_id_o, GMID);
    expect("parent undisturbed by the race", dut->pub_parent_id_o,
           0x00F1F1FFFE000009ull);
  }

  // ---- 19: the parent degrades below us -> immediate takeover -----------
  // 10.3.5: a parent update replaces the best; ours now wins the
  // contest and become-master runs WITHOUT waiting any timeout
  {
    announce(42, 250, 0xAABBCCFFFE010203ull, 0, 0x00F1F1FFFE000009ull);
    expect("degraded parent yields NOW", dut->pub_flags_o & 3,
           FL_PRESENT | FL_AMGM);
    expect("gm is us again", dut->pub_gm_id_o, OUR_CID);
  }

  // ---- 20: every two-step Sync carries a zero reserved body --------------
  {
    tx_seen = txf.size();
    std::vector<uint8_t> sy = wait_tx(0x0, 800000);
    if (!sy.empty()) {
      uint8_t reserved = 0;
      for (int i = 48; i < 58; i++) reserved |= sy[i];
      expect("later sync body stays zero", reserved, 0);
    }
  }

  // ---- 21: an asCapable fall stops sync consumption ---------------------
  {
    announce(43, 100, GMID, 0, PEER_CID);        // adopt again
    expect("re-adopted", dut->pub_flags_o & 3, FL_PRESENT);
    sync_pair(0x0500, TRX6 + 5000000000ull, TRX6 + 5000000000ull - 4000);
    const uint64_t OFF_A = 4000 - (uint64_t)pdm.d;
    expect("baseline pair lands", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF_A);
    pd_mode = PD_FAR;
    {
      int base = pdm.count;
      expect("far exchange ran", wait_exchanges(base + 1, 4000000ull), 1);
      run(4000);
    }
    expect("capable fell", dut->pub_flags_o & FL_ASCAP, 0);
    size_t writes = steps_seen.size() + adj_seen.size();
    sync_pair(0x0501, TRX6 + 6000000000ull, TRX6 + 6000000000ull - 9000);
    expect("uncapable pair dropped", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF_A);
    expect("uncapable pair never steers",
           steps_seen.size() + adj_seen.size(), writes);
    pd_mode = PD_NORMAL;
    announce(44, 100, GMID, 0, PEER_CID);        // keep the GM elected
    expect("capable again", wait_flags(FL_ASCAP, FL_ASCAP, 8000000ull), 1);
    announce(45, 100, GMID, 0, PEER_CID);
    sync_pair(0x0502, TRX6 + 9000000000ull, TRX6 + 9000000000ull - 6000);
    const uint64_t OFF_C = 6000 - (uint64_t)pdm.d;
    expect("recovered pair lands", (uint32_t)dut->pub_offset_o,
           (uint32_t)OFF_C);
  }

  // ---- 21b: become resets the best record -- no ghost GM ----------------
  // announce silence rides out the receipt timeout (pdelay keeps
  // asCapable alive), the plane becomes master, and the DEAD parent's
  // record must be gone: a mediocre newcomer (worse than the ghost,
  // better than us) must be ADOPTED, not lose to a ghost
  const uint64_t NEWGM = 0x00BEEFFFFE000002ull;
  const uint64_t NEWSRC = 0x00BEEFFFFE000001ull;
  {
    expect("quiet ride to mastership",
           wait_flags(FL_AMGM, FL_AMGM, 8000000ull), 1);
    expect("gm is us after the quiet", dut->pub_gm_id_o, OUR_CID);
    announce(70, 150, NEWGM, 0, NEWSRC);
    expect("newcomer adopted, no ghost", dut->pub_gm_id_o, NEWGM);
    expect("newcomer is the parent", dut->pub_parent_id_o, NEWSRC);
  }

  // ---- 21c: the priority vector outranks the identity -------------------
  // worse pv, lower gmId: 10.3.5 compares the vector FIRST, so this
  // must be rejected -- a swapped compare order would adopt it
  {
    announce(71, 160, 0x0000000000000005ull, 0, 0x00C0FFEE00000001ull);
    expect("vector outranks identity", dut->pub_gm_id_o, NEWGM);
  }

  // ---- 21d: the second bank makes the torn case PROCESS -----------------
  // the same delayed-dispatch shape as 18b, but with a BETTER announce:
  // each frame now owns the bank its event names, so the announce's
  // words survive its successor and the plane ADOPTS instead of
  // dropping -- the v6 seq guard stays as belt-and-braces
  const uint64_t GMC = 0x00CAFEFFFE000003ull;
  {
    Frame q = ptp(0x2, 0x7779, 0, 0x0000, 20);
    q.u64(0); q.u16(0); q.ts(0);
    q.b.resize(68);
    send_frame(q.b, phc() + 150);
    Frame a = ptp(0xB, 72, 0, 0x0008, 30, 0x00CAFEFFFE000004ull);
    for (int i = 0; i < 10; i++) a.u8(0);
    a.u16(0xFFC4); a.u8(0);
    a.u8(80); a.u32(OUR_CQ); a.u8(248);
    a.u64(GMC);
    a.u16(0); a.u8(0xA0);
    Frame sy = ptp(0x0, 0x777A, 0, 0x0208, 10, NEWSRC);
    sy.ts(0);
    send_frame(a.b, phc() + 300);
    send_frame(sy.b, phc() + 400);               // zero-gap, parent src
    run(20000);
    expect("torn better announce adopts", dut->pub_gm_id_o, GMC);
    expect("its announcer is the parent", dut->pub_parent_id_o,
           0x00CAFEFFFE000004ull);
  }

  // ---- 22: negative pdelay inside the Milan floor is accepted -----------
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

  // ---- 23: over the 800 ns threshold -> asCapable falls -----------------
  pd_mode = PD_FAR;
  {
    int base = pdm.count;
    expect("far exchange ran", wait_exchanges(base + 1, 4000000ull), 1);
    run(4000);
  }
  expect("far pdelay published", dut->pub_pdelay_ns_o, (uint32_t)pdm.d);
  expect("far pdelay over thresh", pdm.d > 800, 1);
  expect("threshold clears capable", dut->pub_flags_o & FL_ASCAP, 0);

  // ---- 24: recovery takes two good exchanges again ----------------------
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

  // ---- 25: lost responses clear asCapable at the FOURTH -----------------
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

  // ---- 26: a window wider than 2^32 ns must not update the ratio --------
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

  // ---- 27: the multiple-responder cease rule (Milan 4.2.6.2.5) ----------
  // three successive requests each answered by two distinct identities
  // stop Pdelay_Req transmission and drop asCapable; the (bench-
  // shortened) resume timer restarts requests and the ladder re-earns
  {
    pd_mode = PD_NORMAL;                         // regain capable first
    expect("capable before the storm",
           wait_flags(FL_ASCAP, FL_ASCAP, 6000000ull), 1);
    pd_mode = PD_DUAL;
    expect("storm clears capable... eventually",
           wait_flags(FL_ASCAP, 0, 16000000ull), 1);
    size_t mark = txf.size();
    run_svc(5000000);                            // 2.5 s of silence?
    int reqs = 0;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2) reqs++;
    expect("ceased: no requests", reqs, 0);
    // forged Resp+Resp_FU pairs echoing our identity must not climb
    // the ladder while ceased (the completion path is gated). A real
    // forger replays against the LAST genuine request: the engine
    // computes the turnaround from its stored t1, so the forgery must
    // reuse it or self-defeat on the delay range
    uint64_t t1_last = 0;
    for (size_t i = txf.size(); i-- > 0;)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2 && txns[i]) {
        t1_last = txns[i];
        break;
      }
    expect("a genuine t1 to replay against", t1_last != 0, 1);
    for (int k = 0; k < 2; k++) {
      uint64_t t1f = t1_last, t2f = peer_ns(t1f + 300),
               t3f = t2f + 20000, t4f = t1f + 21200;
      Frame f = ptp(0x3, (uint16_t)(0x999 + k), 0, 0x0200, 20);
      f.ts(t2f); f.u64(OUR_CID); f.u16(1);
      send_frame(f.b, t4f);
      run(2000);
      Frame g = ptp(0xA, (uint16_t)(0x999 + k), 0, 0x0000, 20);
      g.ts(t3f); g.u64(OUR_CID); g.u16(1);
      send_frame(g.b, t4f + 1000);
      run(4000);
    }
    expect("forged pairs cannot climb mid-cease",
           dut->pub_flags_o & FL_ASCAP, 0);
    pd_mode = PD_NORMAL;
    size_t mark2 = txf.size();
    bool resumed = false;
    for (int k = 0; k < 40 && !resumed; k++) {
      run_svc(200000);
      for (size_t i = mark2; i < txf.size(); i++)
        if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2) resumed = true;
    }
    expect("resume timer restarts requests", resumed, 1);
    expect("the ladder re-earns",
           wait_flags(FL_ASCAP, FL_ASCAP, 8000000ull), 1);
    // duplicates from the SAME identity are not a storm (4.2.6.2.5
    // says multiple CLOCK IDENTITIES): four dup-answered intervals
    // must leave capable standing
    pd_mode = PD_DUP;
    {
      int base = pdm.count;
      expect("dup intervals ran", wait_exchanges(base + 4, 12000000ull), 1);
      run(4000);
    }
    expect("duplicates are not a storm",
           dut->pub_flags_o & FL_ASCAP, FL_ASCAP);
    pd_mode = PD_NORMAL;
  }

  // ---- 28: a warm reset during a cease still resumes ---------------------
  // scratch survives reset and the boot re-arms the cadence, so the
  // countdown completes; a timer-armed resume died with the reset and
  // stranded the cease until a bitstream reload (the review's finding)
  {
    pd_mode = PD_DUAL;
    expect("second storm ceases",
           wait_flags(FL_ASCAP, 0, 16000000ull), 1);
    run_svc(1000000);                            // eat into the countdown
    dut->rst_n = 0;
    for (int i = 0; i < 8; i++) tick();
    dut->rst_n = 1;
    pd_mode = PD_NORMAL;
    size_t mark = txf.size();
    bool resumed = false;
    for (int k = 0; k < 50 && !resumed; k++) {
      run_svc(200000);
      for (size_t i = mark; i < txf.size(); i++)
        if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2) resumed = true;
    }
    expect("the cease survives reset and resumes", resumed, 1);
  }

  // ---- 29: a chasing Follow_Up cannot steal the Resp's arrival ----------
  // resp and resp-FU sent BACK-TO-BACK (no gap): the resp's event
  // dispatches while the FU's sof is already latching -- a single
  // ingress-ts register hands the resp the FU's arrival time and skews
  // the delay by half the gap (the parent fabric bench's finding);
  // the per-bank stamp keeps each frame's own
  {
    pd_mode = PD_SKIP;
    tx_seen = txf.size();
    std::vector<uint8_t> rq = wait_tx(0x2, 4000000);
    expect("a request to chase", !rq.empty(), 1);
    uint16_t seq = rq.empty() ? 0
                 : (uint16_t)((rq[44] << 8) | rq[45]);
    size_t rqi = tx_seen - 1;
    for (int k = 0; k < 400 && txns[rqi] == 0; k++) tick();
    uint64_t t1 = txns[rqi];
    uint64_t t2 = peer_ns(t1 + 300), t3 = t2 + 20000, t4 = t1 + 21200;
    Frame f = ptp(0x3, seq, 0, 0x0200, 20);
    f.ts(t2); f.u64(OUR_CID); f.u16(1);
    Frame g = ptp(0xA, seq, 0, 0x0000, 20);
    g.ts(t3); g.u64(OUR_CID); g.u16(1);
    send_frame(f.b, t4);
    send_frame(g.b, t4 + 100000);        // the chaser, zero-gap
    run(6000);
    model_exchange(t1, t2, t3, t4);
    expect("chased resp keeps its own stamp",
           dut->pub_pdelay_ns_o, (uint32_t)pdm.d);
    pd_mode = PD_NORMAL;
  }

  // ---- 30: a runt chaser cannot poison the predecessor's stamp ----------
  // (the review's probe): a valid resp followed zero-gap by a 1-byte
  // fragment with a wild rx_ts -- the parser drops the runt without an
  // event, so its eof would land before the resp's bank flip; the
  // length-qualified commit refuses it
  {
    pd_mode = PD_SKIP;
    tx_seen = txf.size();
    std::vector<uint8_t> rq = wait_tx(0x2, 4000000);
    expect("a request for the runt test", !rq.empty(), 1);
    uint16_t seq = rq.empty() ? 0
                 : (uint16_t)((rq[44] << 8) | rq[45]);
    size_t rqi = tx_seen - 1;
    for (int k = 0; k < 400 && txns[rqi] == 0; k++) tick();
    uint64_t t1 = txns[rqi];
    uint64_t t2 = peer_ns(t1 + 300), t3 = t2 + 20000, t4 = t1 + 21200;
    Frame f = ptp(0x3, seq, 0, 0x0200, 20);
    f.ts(t2); f.u64(OUR_CID); f.u16(1);
    send_frame(f.b, t4);
    std::vector<uint8_t> runt = {0xEE, 0xEE};
    send_frame(runt, t4 + 100000);       // the poison attempt, zero-gap
    // (two bytes: a 1-byte fragment's commit would only rewrite the
    // stale staging value -- the 2-byte shape is the one that lands
    // the runt's own stamp without the length qualification)
    run(400);
    Frame g = ptp(0xA, seq, 0, 0x0000, 20);
    g.ts(t3); g.u64(OUR_CID); g.u16(1);
    send_frame(g.b, t4 + 1000);
    run(6000);
    model_exchange(t1, t2, t3, t4);
    expect("runt cannot poison the stamp",
           dut->pub_pdelay_ns_o, (uint32_t)pdm.d);
    pd_mode = PD_NORMAL;
  }

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
