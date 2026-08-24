// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_engine protocol round-trip -- v5, the servo round.
//
//  1..4   pdelay bring-up: byte-exact both roles, asCapable at the
//         second good exchange and not the first (Milan 4.2.6.2.4)
//  1a     a Pdelay_Req sourced from OUR OWN clockIdentity, arriving
//         while the boot request waits for its egress timestamp, draws
//         no frame and cannot steal that timestamp (1588-2008 9.5.2.2,
//         #26)
//  1c     equal-sequence Pdelay_Req/Pdelay_Resp claims are separated by
//         messageType; a stamped unclaimed Resp_FU cannot consume either
//         claim, and the true request stamp still produces 600 ns (#28)
//  3a     a requester differing from us in only one half of its
//         clockIdentity is a neighbour and is still answered, so a
//         compare narrowed to either half goes red (#26)
//  1b     a Follow_Up for the boot request (sequence 0) ahead of any
//         Resp, from the zero identity a never-armed pairing holds, is
//         ignored: "armed with sequence 0" is not "nothing armed" (#8)
//  2b     a Pdelay_Resp (and its Follow_Up) sourced from OUR OWN
//         clockIdentity, answering the outstanding request, is ignored:
//         it neither moves the delay nor climbs the ladder (IEEE
//         1588-2008 9.5.2.2, 802.1AS-2011 Figure 11-8, #23)
//  3b     a foreign-domain Pdelay_Req draws no frame and counts one drop;
//         a domain-0 request right after it is answered (8.1, #6)
//  3c     a header-only and a cut Pdelay_Req draw no frame and count one
//         drop each; the complete request after them is answered (#12)
//  3d     an unlisted messageType (0x1, 0xD, 0xF) with a valid header
//         draws no frame at all and counts one drop each, and the flags
//         do not move (Table 11-3's NOTE: not used in this standard, #22)
//  5..9   grandmaster life: timeout become (asCapable-gated), Announce/
//         Sync/Follow_Up byte-exact, BTCA both directions, adoption;
//         phase 7 holds an equal-sequence Sync and Pdelay_Resp, returns
//         the response stamp first, stamps its unclaimed Resp_FU, then
//         proves the Sync still receives its own timestamp (#28)
//  7b     802.1AS-2011 11.2.15.3: a Pdelay_Resp_Follow_Up pairs with one
//         Pdelay_Resp for the outstanding request only -- before any
//         Resp, with a stale sequenceId, behind a stale Resp (0xEEEE,
//         and the outstanding sequence with its high byte flipped),
//         from another responder, duplicated, or for a superseded
//         request it leaves the delay and asCapable unmoved; the paired
//         one and the next exchange still compute (#8)
//  26b    a completed exchange cannot be completed again: the identical
//         pair replayed is not a second exchange (asCapable holds down),
//         a skewed replay cannot move the delay (Figure 11-8, Cor2) (#8)
//  27b    a second identity answering AFTER the first responder's
//         Follow_Up still counts for the Milan 4.2.6.2.5 cease: the
//         completed exchange's post-completion path reaches the identity
//         bookkeeping (cease, silence, resume, re-earn) (#8)
//  8b     a better Announce in a foreign domain never reaches BTCA: GM,
//         parent, flags and the raw published vector hold (8.1, #6)
//  8c..8m 802.1AS-2011 10.3.10.2.1 qualifyAnnounce: a better Announce
//         from our own clock identity, with stepsRemoved 255 / 0x0100 /
//         0xFFFF, or with our identity in its path trace (second hop,
//         eighth hop, fourth of twelve, FIRST hop of two, the only hop)
//         is refused before any state moves and is not a parser drop;
//         the boundary control (stepsRemoved 254, a one-hop trace
//         without us, in a bank whose upper hop words still hold our
//         identity) and two half-identity controls (source and first
//         hop differing from ours in one 32-bit half) adopt, and a
//         degrade hands mastership back each time (#7)
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
// 31      reset after a Pdelay_Req, Pdelay_Resp or Sync SEND but before its
//         boundary return invalidates the volatile owner; request, response
//         and master Sync cadence each recover autonomously (#41)
// 32      start, middle, one-cycle and long TX backpressure preserve bytes;
//         two peer requests wait behind one response claim and each gets
//         its own response Follow_Up after its own boundary stamp (#40/#33)
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
//! an identity that shares OUR clockIdentity's low 32 bits and differs
//! above them, used by two rounds: as the second responder of the Milan
//! 4.2.6.2.5 probes, which the 1588-2008 9.5.2.2 compare must admit
//! (FPGA-gPTP #23), and as a genuine requester the responder must answer
//! (#26). A compare narrowed to the low half refuses it, which is how
//! both rounds catch that narrowing.
//!
//! DERIVED from OUR_CID, never hand-copied. A literal keeps the halves it
//! was written with, and --mac moves OUR_CID: measured on this suite, one
//! byte of difference in the high-half fixture and the high-half
//! narrowing mutation escapes silently at 340/340, where the derived form
//! gives 336/340. The static_asserts below are the second lock, so the
//! shared halves cannot drift without the build saying so
static const uint64_t NEAR_CID =
    0x0077770000000000ull | (OUR_CID & 0xFFFFFFFFull);
//! its mirror: a requester sharing our HIGH 32 bits and differing below,
//! so a compare narrowed to the high half refuses this one instead (#26)
static const uint64_t REQ_HI_CID =
    (OUR_CID & 0xFFFFFFFF00000000ull) | 0x00112233ull;
static_assert((NEAR_CID & 0xFFFFFFFFull) == (OUR_CID & 0xFFFFFFFFull),
              "NEAR_CID must share OUR_CID's low half");
static_assert((NEAR_CID >> 32) != (OUR_CID >> 32),
              "NEAR_CID must differ from OUR_CID above the halfway line");
static_assert((REQ_HI_CID >> 32) == (OUR_CID >> 32),
              "REQ_HI_CID must share OUR_CID's high half");
static_assert((REQ_HI_CID & 0xFFFFFFFFull) != (OUR_CID & 0xFFFFFFFFull),
              "REQ_HI_CID must differ from OUR_CID below the halfway line");
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
//! the sequenceId a boundary stamper reads out of the frame it stamps
//! (PTP header offset 30, frame offset 44)
static uint16_t seq_of(const std::vector<uint8_t> &f) {
  return f.size() > 45 ? (uint16_t)((f[44] << 8) | f[45]) : 0;
}
//! the messageType nibble the parent boundary stamper returns beside it
static uint8_t type_of(const std::vector<uint8_t> &f) {
  return f.size() > 14 ? (uint8_t)(f[14] & 0xF) : 0;
}

static uint64_t cyc = 0;

// ---- TX backpressure ------------------------------------------------------
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
    dut->txts_seq_i = seq_of(txf[auto_pend]);
    dut->txts_type_i = type_of(txf[auto_pend]);
    txns[auto_pend] = ns;
    auto_pend = -1;
  }
  dut->clk_i = 0; dut->eval();
  const bool tx_fire = dut->tx_valid_o && dut->tx_ready_i;
  const uint8_t tx_data = dut->tx_data_o;
  const bool tx_sof = dut->tx_sof_o;
  const bool tx_eof = dut->tx_eof_o;
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
  if (tx_fire) {
    if (tx_sof) { cur.clear(); in_tx = true; }
    if (in_tx) cur.push_back(tx_data);
    if (tx_eof && in_tx) {
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

//! stamp one CHOSEN transmitted frame, reporting its own header identity
//! the way KL_gptp_txstamp does
static void txts_idx(size_t idx, uint64_t ns) {
  dut->txts_valid_i = 1; dut->txts_ns_i = ns;
  dut->txts_seq_i = idx < txf.size() ? seq_of(txf[idx]) : 0;
  dut->txts_type_i = idx < txf.size() ? type_of(txf[idx]) : 0;
  tick();
  dut->txts_valid_i = 0;
}

//! stamp the frame last sent, the common case
static void txts(uint64_t ns) {
  txts_idx(txf.empty() ? 0 : txf.size() - 1, ns);
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
enum PdMode { PD_OFF, PD_NORMAL, PD_NEG, PD_FAR, PD_SKIP, PD_SELF, PD_DUAL,
              PD_DUP, PD_DUAL_LATE };
static PdMode pd_mode = PD_SKIP;         // SKIP: consume silently
static size_t pd_seen = 0;
static int pd_self_sent = 0;             // PD_SELF pairs actually sent

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
    if (pd_mode == PD_SELF) {
      // our own request reflected back at us: the pair answers the
      // outstanding sequenceId with our requestingPortIdentity, so every
      // other gate admits it and only the sourcePortIdentity compare can
      // refuse it. Its residency is 19,800, a delay near 700 rather than
      // the 600 of a genuine exchange, so an accepted pair MOVES the
      // published delay (still under the 800 ns threshold, which must
      // not be what refuses it). No model_exchange: it never happened
      Frame f = ptp(0x3, seq, 0, 0x0200, 20, OUR_CID);
      f.ts(t2); f.u64(OUR_CID); f.u16(1);
      send_frame(f.b, t1 + 21200);
      run(400);
      Frame g = ptp(0xA, seq, 0, 0x0000, 20, OUR_CID);
      g.ts(t2 + 19800); g.u64(OUR_CID); g.u16(1);
      send_frame(g.b, t1 + 21200 + 1000);
      run(400);
      pd_self_sent++;
      continue;
    }
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
      uint64_t src2 = (pd_mode == PD_DUAL) ? NEAR_CID
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
    if (pd_mode == PD_DUAL_LATE) {
      // the second identity answers AFTER the first responder's
      // Follow_Up: the exchange has completed, so this response takes
      // the handler's post-completion path, which must still reach the
      // Milan 4.2.6.2.5 identity bookkeeping
      Frame d = ptp(0x3, seq, 0, 0x0200, 20, NEAR_CID);
      d.ts(t2 + 40); d.u64(OUR_CID); d.u16(1);
      send_frame(d.b, t4 + 2000);
      run(400);
    }
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

// an announce carrying {p1, gmid, steps} from `src` with a path trace TLV
// (802.1AS-2011 10.5.3.3: tlvType 0x0008, one clockIdentity per hop);
// an empty path omits the TLV
static void send_announce(uint16_t seq, uint8_t p1, uint64_t gmid,
                          uint16_t steps, uint64_t src,
                          const std::vector<uint64_t> &path, uint64_t rx_ts) {
  uint16_t tlv = path.empty() ? 0 : (uint16_t)(4 + 8 * path.size());
  Frame a = ptp(0xB, seq, 0, 0x0008, (uint16_t)(30 + tlv), src);
  for (int i = 0; i < 10; i++) a.u8(0);
  a.u16(0xFFC4); a.u8(0);
  a.u8(p1); a.u32(OUR_CQ); a.u8(248);
  a.u64(gmid);
  a.u16(steps); a.u8(0xA0);
  if (!path.empty()) {
    a.u16(0x0008); a.u16((uint16_t)(8 * path.size()));
    for (uint64_t hop : path) a.u64(hop);
  }
  send_frame(a.b, rx_ts);
  run_svc(6000);
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
  dut->txts_type_i = 0;
  dut->phc_ns_i = 0;
  for (int i = 0; i < 8; i++) tick();
  dut->rst_n = 1;

  // ---- 1: our Pdelay_Req; asCapable must start low ----------------------
  std::vector<uint8_t> req = wait_tx(0x2, 3200000);
  const size_t our_req_idx = txf.empty() ? 0 : txf.size() - 1;
  if (!req.empty()) {
    check_common("pdreq", req, 0x2, 0x0000, 54, 0x00);
    uint64_t z = 0;
    for (int i = 48; i < 68; i++) z |= req[i];
    expect("pdreq body zero", z, 0);
  }
  expect("asCapable low at boot", dut->pub_flags_o & FL_ASCAP, 0);
  const uint64_t T1 = 1000000ull;

  // ---- 1a: a self-sourced Pdelay_Req draws nothing -----------------------
  // IEEE 1588-2008 9.5.2.2: "A message received at the same port that
  // issued the message shall be ignored", compared on sourcePortIdentity
  // against the port's own portIdentity (its Table 17). 802.1AS-2011
  // Figure 11-9 (MDPdelayResp) carries no such condition, so 9.5.2.2 is
  // the whole mandate on this side (#26). The window is chosen, not
  // incidental: the boot Pdelay_Req is still waiting for its egress
  // timestamp, which is exactly when a reflection of it arrives, and
  // answering steals that timestamp through the shared S_PEND cell
  // (#28), so phase 2's published delay below is this phase's real
  // oracle: 600 if the request was ignored, 500,600 if it was answered.
  // No counter moves, because the refusal is in the ucode and
  // dbg_rx_drop_o counts what the parser refused
  {
    size_t mark = txf.size();
    uint16_t drops = dut->dbg_rx_drop_o;
    uint32_t flags0 = dut->pub_flags_o;
    Frame q = ptp(0x2, 0x9901, 0, 0x0000, 20, OUR_CID);
    q.u64(0); q.u16(0); q.ts(0);
    q.b.resize(68);
    send_frame(q.b, T1 - 1000);
    run(8000);
    int resps = 0;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x3) resps++;
    expect("self-sourced request: no Pdelay_Resp", resps, 0);
    expect("self-sourced request: no frame at all", txf.size(), mark);
    expect("self-sourced request: not a parser drop", dut->dbg_rx_drop_o,
           drops);
    expect("self-sourced request: flags unmoved", dut->pub_flags_o, flags0);
  }
  // ---- 1c: peer requests inside our own request's outstanding interval --
  // Our Pdelay_Req is out and its egress timestamp has not come back, so
  // the plane owes itself a stamp for the whole of this interval. A peer
  // running its own cadence sends into that interval, we answer, and the
  // answer must not divert the stamp our request is waiting for
  // (FPGA-gPTP #28). The leads are spread across the interval rather
  // than bunched at its edge, because the interval is not a few cycles:
  // the steal was measured at leads from 0 to 1,000,000 cycles, so a
  // single near-boundary case would look the same whether a fix closed
  // the whole interval or only its last cycles.
  //
  // The last response's stamp is then returned BEFORE our request's,
  // which is the discriminating case: positional matching, crediting
  // stamps in hand-over order, gives that stamp to our request and this
  // phase goes red. Matching by the sequenceId the stamper reports does
  // not care what order they arrive in.
  uint16_t drops_1c = 0;
  const uint64_t P3_TS = 850000ull, P4_TS = 870000ull, P5_TS = 890000ull;
  size_t p3_idx = 0, p4_idx = 0, p5_idx = 0;
  uint16_t p3_seq = 0;
  {
    const long leads[] = {10, 2000, 200000};
    const uint64_t response_ts[] = {810000ull, 830000ull, P3_TS};
    size_t mark = txf.size();
    drops_1c = dut->dbg_rx_drop_o;
    int n = 0;
    for (long lead : leads) {
      run((uint64_t)lead);
      p3_seq = (uint16_t)(0x9900 + n);
      size_t response_mark = txf.size();
      Frame q = ptp(0x2, p3_seq, 0, 0x0000, 20, PEER_CID);
      q.u64(0); q.u16(0); q.ts(0);
      q.b.resize(68);
      send_frame(q.b, 900000 + 1000 * n);
      run(4000);
      bool seen = false;
      for (size_t i = response_mark; i < txf.size(); i++)
        if (type_of(txf[i]) == 0x3 && seq_of(txf[i]) == p3_seq) {
          p3_idx = i;
          seen = true;
        }
      expect("peer request across our window: response sent",
             seen ? 1 : 0, 1);
      // One response context is intentionally live at a time. Retire the
      // first two before presenting the next request; the third remains
      // outstanding for the response-before-request-stamp ordering below.
      if (seen && n < 2) {
        size_t fu_mark = txf.size();
        txts_idx(p3_idx, response_ts[n]);
        run(8000);
        bool fu_seen = false;
        for (size_t i = fu_mark; i < txf.size(); i++)
          if (type_of(txf[i]) == 0xA && seq_of(txf[i]) == p3_seq)
            fu_seen = true;
        expect("peer request across our window: Follow_Up sent",
               fu_seen ? 1 : 0, 1);
      }
      n++;
    }
    int resps = 0;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x3) {
        resps++;
        p3_idx = i;
      }
    // Three requests still draw three Pdelay_Resps, but a later request is
    // not allowed to overwrite live response context: the first two claims
    // are retired above and the last remains pending for the ordering probe.
    expect("peer requests across our window: three Pdelay_Resps", resps, 3);
    expect("peer requests across our window: none was a parser drop",
           dut->dbg_rx_drop_o, drops_1c);
  }
  {
    size_t mark = txf.size();
    txts_idx(p3_idx, P3_TS);            // the RESPONSE's stamp, returned
    run(8000);                          // before our own request's
    std::vector<uint8_t> u;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0xA) u = txf[i];
    expect("out-of-order stamp: the Resp_FU is built", u.empty() ? 0 : 1, 1);
    if (!u.empty()) {
      expect("out-of-order stamp: it pairs its own request",
             fld16(u, 44), p3_seq);
      expect("out-of-order stamp: it carries its own timestamp",
             fld48(u, 48) * 1000000000ull + fld32(u, 54), P3_TS);
    }
  }
  {
    // two claims outstanding whose tags differ ONLY in the high byte of
    // the sequenceId: ours is 0 and this request's is 0x0100. A compare
    // narrowed to the low 8 bits reads them as equal, gives this
    // response's stamp to our request and never builds the Resp_FU, and
    // every other tag pair in this suite differs in the low byte, so
    // without this case that narrowing survives untouched. It is the
    // same blindness the pinned txts_seq_i had: a field nothing varies
    // is a field nothing tests
    size_t mark = txf.size();
    Frame q = ptp(0x2, 0x0100, 0, 0x0000, 20, PEER_CID);
    q.u64(0); q.u16(0); q.ts(0);
    q.b.resize(68);
    send_frame(q.b, 904000);
    run(4000);
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x3) p5_idx = i;
    mark = txf.size();
    txts_idx(p5_idx, P5_TS);
    run(8000);
    std::vector<uint8_t> u;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0xA) u = txf[i];
    expect("high-byte-only difference: the Resp_FU is built",
           u.empty() ? 0 : 1, 1);
    if (!u.empty()) {
      expect("high-byte-only difference: it pairs its own request",
             fld16(u, 44), 0x0100);
      expect("high-byte-only difference: it carries its own timestamp",
             fld48(u, 48) * 1000000000ull + fld32(u, 54), P5_TS);
    }
  }
  size_t p4_rfu_idx = 0;
  bool p4_rfu_seen = false;
  {
    // Both ends start their independent request counters at zero, so the
    // peer's request and our outstanding request have the SAME sequenceId.
    // Return the response's stamp first: sequenceId-only credit gives it
    // to our request, while {messageType, sequenceId} must build this
    // response's own Follow_Up and leave our request claim intact (#28).
    size_t mark = txf.size();
    Frame q = ptp(0x2, 0, 0, 0x0000, 20, PEER_CID);
    q.u64(0); q.u16(0); q.ts(0);
    q.b.resize(68);
    send_frame(q.b, 906000);
    run(4000);
    bool p4_seen = false;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x3) {
        p4_idx = i;
        p4_seen = true;
      }
    expect("equal sequences: the request is still answered",
           p4_seen ? 1 : 0, 1);
    if (p4_seen)
      expect("equal sequences: its response carries our own sequence",
             fld16(txf[p4_idx], 44), 0);
    if (p4_seen) txts_idx(p4_idx, P4_TS);
    run(8000);
    std::vector<uint8_t> u;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0xA) {
        u = txf[i];
        p4_rfu_idx = i;
        p4_rfu_seen = true;
      }
    expect("equal sequences: response-first stamp builds the Resp_FU",
           u.empty() ? 0 : 1, 1);
    if (!u.empty()) {
      expect("equal sequences: Resp_FU carries the response stamp",
             fld48(u, 48) * 1000000000ull + fld32(u, 54), P4_TS);
    }
  }
  // A Resp_FU itself leaves no claim, but the boundary still stamps it.
  // Its sequence is also zero. That unclaimed type must not consume the
  // still-outstanding request claim. Phase 2's 600 ns result below is the
  // end-to-end oracle: sequence-only credit moves it far from 600 ns.
  if (p4_rfu_seen) {
    txts_idx(p4_rfu_idx, T1 + 110000);
    run(2000);                         // separate this from open #31
  }
  txts_idx(our_req_idx, T1);
  run(2000);
  tx_seen = txf.size();          // this phase's frames are accounted for

  // ---- 1b: a Follow_Up for the boot request ahead of any Resp ----------
  // sequence 0 is the first request the plane sends (and recurs every
  // 65,536 requests): "armed with sequence 0" must differ from "nothing
  // armed". A never-armed pairing holds a zero responder identity, so
  // the forged frame carries exactly that identity: only the armed bit
  // can refuse it (FPGA-gPTP #8)
  {
    Frame g = ptp(0xA, 0, 0, 0x0000, 20, 0);
    g.ts(T1 + 20000); g.u64(OUR_CID); g.u16(1);
    send_frame(g.b, T1 + 22200);
    run(6000);
    expect("boot Follow_Up before any Resp: pdelay unmoved",
           dut->pub_pdelay_ns_o, 0);
    expect("boot Follow_Up before any Resp: asCapable unmoved",
           dut->pub_flags_o & FL_ASCAP, 0);
  }

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

  // ---- 2b: a Pdelay_Resp sourced from OUR clockIdentity is ignored ------
  // IEEE 1588-2008 9.5.2.2: "A message received at the same port that
  // issued the message shall be ignored", identified by comparing the
  // received sourcePortIdentity with the port's own portIdentity (its
  // Table 17). 802.1AS-2011 Figure 11-8 carries the same condition into
  // the MDPdelayReq machine, where asCapable is set only if
  // rcvdPdelayRespPtr->sourcePortIdentity.clockIdentity != thisClock. A
  // loop or a misconfigured bridge reflecting our own Pdelay_Req back at
  // us is not a neighbour, and one exchange has already completed here,
  // so an accepted pair would be the SECOND and would raise asCapable
  // (FPGA-gPTP #23). The pair is refused by nothing else: it answers the
  // outstanding sequenceId, carries our requestingPortIdentity, and its
  // delay lands near 700 ns, under the threshold
  {
    uint32_t fl0 = dut->pub_flags_o, d0 = dut->pub_pdelay_ns_o;
    int c0 = pdm.count;
    uint16_t dr0 = dut->dbg_rx_drop_o;
    pd_seen = txf.size();
    pd_mode = PD_SELF;
    pd_self_sent = 0;
    auto_txts = true;                  // the cadence request needs its t1
    run_svc(2600000);
    expect("self-sourced pair: one was answered", pd_self_sent >= 1, 1);
    // sent is not the same as admitted: without this the three checks
    // below would pass vacuously if the frame were ever refused at the
    // parser instead, which is where it must NOT be refused, the parser
    // holding no identity of its own. The refusal is in the ucode, so
    // the parser's counter must not move
    expect("self-sourced pair: not a parser drop", dut->dbg_rx_drop_o, dr0);
    expect("self-sourced pair: asCapable unmoved",
           dut->pub_flags_o & FL_ASCAP, fl0 & FL_ASCAP);
    expect("self-sourced pair: pdelay unmoved", dut->pub_pdelay_ns_o, d0);
    expect("self-sourced pair: no exchange modelled", pdm.count, c0);
    pd_mode = PD_SKIP;
    pd_seen = txf.size();
    auto_txts = false;                 // phase 3 feeds its own timestamps
  }

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

  // ---- 3a: a requester whose identity nearly matches ours is answered ---
  // the refusal above compares all 64 bits of the clockIdentity. These
  // two requesters differ from ours in only one half each, so a compare
  // narrowed to the low half refuses the first and one narrowed to the
  // high half refuses the second: either way a genuine neighbour loses
  // its Pdelay_Resp and this phase goes red.
  //
  // Only FMT_D is a symmetric narrowing here. The ISA masks operand A
  // alone (KL_gptp_ucpu.sv:188-194; b_or_imm_w keeps all 64 bits), so
  // FMT_W and FMT_B make the compare unsatisfiable rather than narrow:
  // nothing is ever refused, this phase stays green, and the loss shows
  // in phase 1a instead, where the self-sourced request is answered
  {
    struct Near { const char *tag; uint64_t cid; uint16_t seq; uint64_t rx, tx; };
    const Near near[] = {
      {"low-half", NEAR_CID, 0x55B1, T2R + 20000, T3R + 20000},
      {"high-half", REQ_HI_CID, 0x55B2, T2R + 40000, T3R + 40000},
    };
    for (const Near &n : near) {
      Frame f = ptp(0x2, n.seq, 0, 0x0000, 20, n.cid);
      f.u64(0); f.u16(0); f.ts(0);
      f.b.resize(68);
      send_frame(f.b, n.rx);
      std::vector<uint8_t> r = wait_tx(0x3, 400000);
      char nm[80];
      snprintf(nm, sizeof nm, "%s requester: answered", n.tag);
      expect(nm, r.empty() ? 0 : 1, 1);
      if (!r.empty()) {
        snprintf(nm, sizeof nm, "%s requester: its sequence", n.tag);
        expect(nm, fld16(r, 44), n.seq);
        snprintf(nm, sizeof nm, "%s requester: its reqCID", n.tag);
        expect(nm, fld64(r, 58), n.cid);
      }
      txts(n.tx);
      std::vector<uint8_t> u = wait_tx(0xA, 400000);
      snprintf(nm, sizeof nm, "%s requester: Resp_FU pairs", n.tag);
      expect(nm, u.empty() ? 0 : (uint64_t)fld16(u, 44), n.seq);
    }
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

  // ---- 3d: an unlisted messageType draws nothing and is counted --------
  // 802.1AS-2011 Tables 10-5 and 11-3 name the seven messageType values
  // a gPTP port carries, and the NOTE under Table 11-3 says the others
  // "are not used in this standard": IEEE 1588-2008 Table 19 assigns
  // three of them to Delay_Req, Delay_Resp and Management and reserves
  // the rest. None has a handler here. Until
  // #22 the parser admitted any of them with a valid header and the
  // engine's entry table sent the resulting code-0 event to the timer
  // program at 512, whose slot came from the descriptor's low bits: slot
  // 0 is the cadence leg, so a type-0x1 frame drew a Pdelay_Req off the
  // 11.5.2.2 interval and walked the lost-response count, and as master
  // slot 1 emitted a Sync. The three shapes the issue names, each an
  // otherwise valid 44-octet frame: the window is proven quiet first, no
  // frame at all leaves the lane after them, each counts one drop, and
  // the flags do not move. Phase 4 then earns asCapable as before, so
  // the refusals cannot pass by having deafened the plane.
  {
    size_t pre = txf.size();
    run(4000);
    expect("unlisted types: the window starts quiet", txf.size(), pre);
    size_t mark = txf.size();
    uint16_t drops = dut->dbg_rx_drop_o;
    uint32_t flags0 = dut->pub_flags_o;
    const uint8_t unlisted[] = {0x1, 0xD, 0xF};
    for (uint8_t mt : unlisted) {
      Frame f = ptp(mt, (uint16_t)(0x56A0 + mt), 0, 0x0000, 10);
      f.ts(0);
      send_frame(f.b, T2R + 450000);
      run(4000);
    }
    expect("unlisted types: no frame transmitted", txf.size(), mark);
    expect("unlisted types: dropped and counted", dut->dbg_rx_drop_o,
           (uint16_t)(drops + 3));
    expect("unlisted types: flags unmoved", dut->pub_flags_o, flags0);
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
  // wait_tx returns on the frame's EOF, one tick before the automatic
  // boundary-stamp helper would return its stamp. Hold this Sync claim,
  // then make a peer request with the SAME sequenceId. The response's
  // stamp arrives first and must build a Resp_FU, not a Sync Follow_Up.
  expect("sync collision: stamp is pending", auto_pend, (int)sidx);
  auto_txts = false;
  auto_pend = -1;
  size_t collision_mark = txf.size();
  Frame same = ptp(0x2, sseq, 0, 0x0000, 20, PEER_CID);
  same.u64(0); same.u16(0); same.ts(0);
  same.b.resize(68);
  send_frame(same.b, phc() + 1000);
  run(8000);
  size_t collision_resp_idx = 0;
  bool collision_resp_seen = false;
  for (size_t i = collision_mark; i < txf.size(); i++)
    if (type_of(txf[i]) == 0x3) {
      collision_resp_idx = i;
      collision_resp_seen = true;
    }
  expect("sync collision: equal-sequence request answered",
         collision_resp_seen ? 1 : 0, 1);

  const uint64_t RESP_COLLISION_TS = 7110000ull;
  size_t response_stamp_mark = txf.size();
  if (collision_resp_seen)
    txts_idx(collision_resp_idx, RESP_COLLISION_TS);
  run(8000);
  size_t collision_rfu_idx = 0;
  bool collision_rfu_seen = false;
  int premature_sync_fu = 0;
  for (size_t i = response_stamp_mark; i < txf.size(); i++) {
    if (type_of(txf[i]) == 0xA) {
      collision_rfu_idx = i;
      collision_rfu_seen = true;
      expect("sync collision: Resp_FU carries response stamp",
             fld48(txf[i], 48) * 1000000000ull + fld32(txf[i], 54),
             RESP_COLLISION_TS);
    }
    if (type_of(txf[i]) == 0x8) premature_sync_fu++;
  }
  expect("sync collision: response stamp builds Resp_FU",
         collision_rfu_seen ? 1 : 0, 1);
  expect("sync collision: response stamp does not build Sync FU",
         premature_sync_fu, 0);

  // The emitted Resp_FU is stamped too, but leaves no claim. Its type-A
  // stamp shares the sequenceId and must not consume the pending Sync.
  if (collision_rfu_seen) {
    txts_idx(collision_rfu_idx, RESP_COLLISION_TS + 1000);
    run(2000);                                // avoid open buffering #31
  }
  const uint64_t SYNC_COLLISION_TS = 7220000ull;
  size_t sync_stamp_mark = txf.size();
  if (!sy.empty()) txts_idx(sidx, SYNC_COLLISION_TS);
  run(8000);
  std::vector<uint8_t> fu;
  for (size_t i = sync_stamp_mark; i < txf.size(); i++)
    if (type_of(txf[i]) == 0x8) fu = txf[i];
  expect("sync collision: own stamp still builds Sync FU",
         fu.empty() ? 0 : 1, 1);
  if (!fu.empty()) {
    check_common("syncfu", fu, 0x8, 0x0008, 76, 0xFD);
    expect("syncfu seq", fld16(fu, 44), sseq);
    expect("syncfu origin", fld48(fu, 48) * 1000000000ull + fld32(fu, 54),
           SYNC_COLLISION_TS);
    expect("syncfu tlv", fld32(fu, 58), 0x0003001C);
    expect("syncfu org", fld48(fu, 62), 0x0080C2000001ull);
  }
  auto_txts = true;
  pd_seen = txf.size();

  // ---- 7b: a Pdelay_Resp_Follow_Up pairs with one Pdelay_Resp only ------
  // 802.1AS-2011 11.2.15.3 (Figure 11-8): a Pdelay_Resp is taken only
  // when it answers the OUTSTANDING request (its sequenceId, our
  // requestingPortIdentity), and a Pdelay_Resp_Follow_Up only when it
  // carries that sequenceId and comes from that responder; everything
  // else is ignored and neither neighborPropDelay nor the ladder moves.
  // The auto-peer is silenced so every frame is hand-built against the
  // DUT's own request; a wrongly consumed Follow_Up carries a t3 skewed
  // +2 us, so the published delay would move by -1 us and the verdict
  // would fall below the Milan floor (FPGA-gPTP #8)
  {
    const uint64_t STRANGER = 0x00BAD0FFFE000002ull;
    pd_mode = PD_SKIP;
    tx_seen = txf.size();
    std::vector<uint8_t> rq = wait_tx(0x2, 4000000);
    expect("7b: a request to pair against", !rq.empty(), 1);
    uint16_t seq = rq.empty() ? 0 : fld16(rq, 44);
    size_t rqi = tx_seen - 1;
    for (int k = 0; k < 400 && txns[rqi] == 0; k++) tick();
    uint64_t t1 = txns[rqi];
    uint64_t t2 = peer_ns(t1 + 300), t3 = t2 + 20000, t4 = t1 + 21200;
    uint32_t pd0 = dut->pub_pdelay_ns_o;
    uint32_t fl0 = dut->pub_flags_o;
    auto resp = [&](uint16_t s, uint64_t src, uint64_t t2v, uint64_t rx) {
      Frame f = ptp(0x3, s, 0, 0x0200, 20, src);
      f.ts(t2v); f.u64(OUR_CID); f.u16(1);
      send_frame(f.b, rx);
      run(2000);
    };
    auto rfu = [&](uint16_t s, uint64_t src, uint64_t t3v, uint64_t rx) {
      Frame g = ptp(0xA, s, 0, 0x0000, 20, src);
      g.ts(t3v); g.u64(OUR_CID); g.u16(1);
      send_frame(g.b, rx);
      run(6000);
    };
    // the completion path can only touch asCapable (the ladder and the
    // threshold verdict), so that is the bit pinned; the role bits are
    // the announce machinery's and move on their own cadence
    auto unmoved = [&](const char *tag) {
      char n[96];
      snprintf(n, 96, "%s: pdelay unmoved", tag);
      expect(n, dut->pub_pdelay_ns_o, pd0);
      snprintf(n, 96, "%s: asCapable unmoved", tag);
      expect(n, dut->pub_flags_o & FL_ASCAP, fl0 & FL_ASCAP);
    };
    // (i) a Follow_Up before any Pdelay_Resp: nothing is armed
    rfu(seq, PEER_CID, t3 + 2000, t4 + 1000);
    unmoved("Follow_Up before any Resp");
    // (ii) the parent campaign's probe: a stale sequenceId, our identity
    rfu(0xEEEE, PEER_CID, 1000, t4 + 1100);
    unmoved("stale-sequence Follow_Up");
    // (iii) a stale Resp + Follow_Up pair: the Resp answers nothing
    // outstanding, so it must not arm the pairing either
    resp(0xEEEE, PEER_CID, t2, t4);
    rfu(0xEEEE, PEER_CID, t3 + 2000, t4 + 1200);
    unmoved("stale-sequence Resp + Follow_Up pair");
    // (iii-b) a stale pair whose sequenceId differs from the outstanding
    // one in the HIGH byte only: a byte-wide sequence compare would arm
    resp((uint16_t)(seq ^ 0x0100), PEER_CID, t2, t4);
    rfu((uint16_t)(seq ^ 0x0100), PEER_CID, t3 + 2000, t4 + 1250);
    unmoved("high-byte-stale Resp + Follow_Up pair");
    // (iv) the legitimate Resp arms the pairing; a Follow_Up with the
    // right sequenceId and our identity from ANOTHER source is not it
    resp(seq, PEER_CID, t2, t4);
    rfu(seq, STRANGER, t3 + 2000, t4 + 1300);
    unmoved("Follow_Up from another responder");
    // (v) the paired Follow_Up still computes
    rfu(seq, PEER_CID, t3, t4 + 1400);
    model_exchange(t1, t2, t3, t4);
    expect("the paired Follow_Up computes", dut->pub_pdelay_ns_o,
           (uint32_t)pdm.d);
    expect("the paired Follow_Up keeps capable",
           dut->pub_flags_o & FL_ASCAP, FL_ASCAP);
    pd0 = dut->pub_pdelay_ns_o;
    fl0 = dut->pub_flags_o;
    // (vi) a duplicate Follow_Up: the pairing was consumed, one per Resp
    rfu(seq, PEER_CID, t3 + 2000, t4 + 1500);
    unmoved("duplicate Follow_Up");
    // (vii) a Follow_Up for a superseded request: its Resp did arrive,
    // but the next request owns the pairing now, so it must not compute
    // against the new request's t1
    tx_seen = txf.size();
    std::vector<uint8_t> rq2 = wait_tx(0x2, 4000000);
    expect("7b: a second request", !rq2.empty(), 1);
    uint16_t seq2 = rq2.empty() ? 0 : fld16(rq2, 44);
    size_t rq2i = tx_seen - 1;
    for (int k = 0; k < 400 && txns[rq2i] == 0; k++) tick();
    uint64_t t1b = txns[rq2i];
    uint64_t t2b = peer_ns(t1b + 300), t3b = t2b + 20000, t4b = t1b + 21200;
    resp(seq2, PEER_CID, t2b, t4b);               // and no Follow_Up
    tx_seen = txf.size();
    std::vector<uint8_t> rq3 = wait_tx(0x2, 4000000);
    expect("7b: a third request", !rq3.empty(), 1);
    uint16_t seq3 = rq3.empty() ? 0 : fld16(rq3, 44);
    size_t rq3i = tx_seen - 1;
    for (int k = 0; k < 400 && txns[rq3i] == 0; k++) tick();
    uint64_t t1c = txns[rq3i];
    uint64_t t2c = peer_ns(t1c + 300), t3c = t2c + 20000, t4c = t1c + 21200;
    rfu(seq2, PEER_CID, t3b, t4c + 1000);
    unmoved("Follow_Up for a superseded request");
    resp(seq3, PEER_CID, t2c, t4c);
    rfu(seq3, PEER_CID, t3c, t4c + 1100);
    model_exchange(t1c, t2c, t3c, t4c);
    expect("the next exchange computes", dut->pub_pdelay_ns_o,
           (uint32_t)pdm.d);
    expect("still capable after the probes",
           dut->pub_flags_o & FL_ASCAP, FL_ASCAP);
    pd_seen = txf.size();                  // the peer answers fresh ones only
    pd_mode = PD_NORMAL;
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

  // ---- 8c..8m: 802.1AS-2011 10.3.10.2.1 qualifyAnnounce -----------------
  // every probe carries priority1 1, which wins BTCA outright (phase 9
  // adopts priority1 100), so the only way the plane stays master is the
  // qualification refusing the frame before the compare. The handler's
  // first write is the raw vector publish, so pub_annq_o holding proves
  // nothing moved; the parser accepted every frame, so the drop counter
  // must NOT move either. The order is deliberate: accepted frames
  // alternate between the two message banks, and the boundary control
  // lands two frames after the [foreign, OUR_CID] probe, in the bank
  // whose word 17 still holds our identity: only a walk reading past
  // the hop count can see it (FPGA-gPTP #7)
  {
    const uint64_t PEER2 = 0x0080E1FFFE445566ull;
    auto refuse_probe = [&](const char *tag, uint16_t seq, uint64_t gm,
                            uint16_t steps, uint64_t src,
                            const std::vector<uint64_t> &path, uint64_t rx) {
      uint32_t flags0 = dut->pub_flags_o;
      uint64_t annq0 = dut->pub_annq_o;
      uint16_t drops0 = dut->dbg_rx_drop_o;
      send_announce(seq, 1, gm, steps, src, path, rx);
      char n[96];
      snprintf(n, 96, "%s: still master", tag);
      expect(n, dut->pub_flags_o & FL_AMGM, FL_AMGM);
      snprintf(n, 96, "%s: gm still us", tag);
      expect(n, dut->pub_gm_id_o, OUR_CID);
      snprintf(n, 96, "%s: parent still us", tag);
      expect(n, dut->pub_parent_id_o, OUR_CID);
      snprintf(n, 96, "%s: flags untouched", tag);
      expect(n, dut->pub_flags_o, flags0);
      snprintf(n, 96, "%s: raw vector never published", tag);
      expect(n, dut->pub_annq_o, annq0);
      snprintf(n, 96, "%s: not a parser drop", tag);
      expect(n, dut->dbg_rx_drop_o, drops0);
    };
    // an adopt-control: a priority1-1 announce that MUST be adopted, then
    // the same announcer degrades below us, a parent update our own
    // vector then wins (10.3.5), and mastership returns at once
    auto adopt_control = [&](const char *tag, uint16_t seq, uint64_t gm,
                             uint16_t steps, uint64_t src,
                             const std::vector<uint64_t> &path, uint64_t rx) {
      char n[96];
      send_announce(seq, 1, gm, steps, src, path, rx);
      snprintf(n, 96, "%s: adopted", tag);
      expect(n, dut->pub_gm_id_o, gm);
      snprintf(n, 96, "%s: announcer is the parent", tag);
      expect(n, dut->pub_parent_id_o, src);
      snprintf(n, 96, "%s: no longer master", tag);
      expect(n, dut->pub_flags_o & FL_AMGM, 0);
      send_announce((uint16_t)(seq + 1), 250, gm, steps, src, path,
                    rx + 100000);
      snprintf(n, 96, "%s: degraded parent yields", tag);
      expect(n, dut->pub_flags_o & 3, FL_PRESENT | FL_AMGM);
      snprintf(n, 96, "%s: gm is us again", tag);
      expect(n, dut->pub_gm_id_o, OUR_CID);
    };
    // 8c: (a) sent by this time-aware system: our own clockIdentity as
    // the source, a foreign MAC (a reflected or forged frame)
    refuse_probe("own-source announce", 12, 0x0000000000002222ull, 0,
                 OUR_CID, {}, 5600000);
    // 8d: (b) stepsRemoved 255 (IEEE 1588-2008 9.3.2.5 d)
    refuse_probe("stepsRemoved-255 announce", 13, 0x0000000000002222ull, 255,
                 PEER2, {}, 5700000);
    // 8g: (c) beyond the cap: twelve hops, ours the fourth; the count
    // reports twelve, the bank holds eight, the walk must still see it
    {
      std::vector<uint64_t> path;
      for (int i = 0; i < 12; i++) path.push_back(0x6000 + i);
      path[3] = OUR_CID;
      refuse_probe("deep-trace loop announce", 16, 0x0000000000006000ull, 11,
                   PEER2, path, 5800000);
    }
    // 8f: (c) at the bank's cap: eight hops, ours the eighth
    {
      std::vector<uint64_t> path;
      for (int i = 0; i < 7; i++) path.push_back(0x5000 + i);
      path.push_back(OUR_CID);
      refuse_probe("eighth-hop loop announce", 15, 0x0000000000005000ull, 7,
                   PEER2, path, 5900000);
    }
    // 8i: (c) at the FIRST hop, the one loop an end station meets without
    // forgery: our own Announce as grandmaster returned through a bridge
    // (the bridge's source identity, so (a) does not fire; pathSequence[0]
    // is us, the bridge behind it). A walk reading the next bank word
    // would miss it
    refuse_probe("first-hop loop announce", 19, 0x0000000000007777ull, 1,
                 PEER2, {OUR_CID, 0x0000000000007777ull}, 6000000);
    // 8j: (c) a single-hop trace that is us, the grandmaster field ours too
    refuse_probe("single-hop loop announce", 20, OUR_CID, 0, PEER2,
                 {OUR_CID}, 6100000);
    // 8e: (c) our identity as the second hop of a two-hop path trace
    // (the parent campaign's probe shape); this frame leaves our
    // identity in word 17 of its bank for the boundary control below
    refuse_probe("path-trace-loop announce", 14, 0x0000000000003333ull, 1,
                 PEER2, {0x0000000000003333ull, OUR_CID}, 6200000);
    // 8m: (b) above 255: 0x0100, which a byte-wide compare would admit
    refuse_probe("stepsRemoved-0x0100 announce", 21, 0x0000000000002222ull,
                 0x0100, PEER2, {}, 6300000);
    // 8h: the boundary control ADOPTS: stepsRemoved 254, a one-hop path
    // trace without us, landing in the bank whose word 17 still holds
    // our identity from 8e: a walk not gated by the hop count, or one
    // hop past it, would refuse it
    const uint64_t GMQ = 0x00D1D1FFFE000004ull, SRCQ = 0x00D1D1FFFE000005ull;
    adopt_control("boundary-clean announce", 17, GMQ, 254, SRCQ, {GMQ},
                  6400000);
    // 8m: (b) the field's maximum
    refuse_probe("stepsRemoved-0xFFFF announce", 22, 0x0000000000002222ull,
                 0xFFFF, PEER2, {}, 6600000);
    // 8k, 8l: the identity compares are 64 bits wide. Two adopt-controls
    // whose source clockIdentity and whose first hop each differ from
    // ours in ONE 32-bit half only (8k: the source in the high half, the
    // hop in the low half; 8l: the other way round): a compare narrowed
    // to either half would refuse a legitimate master
    adopt_control("half-identity control A", 23, 0x00D2D2FFFE000006ull, 0,
                  OUR_CID ^ (1ull << 40), {OUR_CID ^ 1ull}, 6700000);
    adopt_control("half-identity control B", 25, 0x00D3D3FFFE000007ull, 0,
                  OUR_CID ^ 1ull, {OUR_CID ^ (1ull << 40)}, 6900000);
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

  // ---- 26b: a completed exchange cannot be completed again --------------
  // Figure 11-8 (Cor2-2015): after the pair, only the interval timer
  // leaves WAITING_FOR_PDELAY_INTERVAL_TIMER; a replayed Pdelay_Resp +
  // Follow_Up for the same sequenceId is not an exchange. asCapable is
  // down (phase 25) with ONE exchange in (phase 26), so a second
  // completion in this interval would raise it a request early (Milan
  // 4.2.6.2.4); a skewed replay (t4 + 2000: D 600 -> 1600) would
  // overwrite the genuine delay and clear the ladder (FPGA-gPTP #8)
  {
    pd_mode = PD_SKIP;
    size_t rqi = 0;
    bool found = false;
    for (size_t i = txf.size(); i-- > 0;)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2 && txns[i]) {
        rqi = i;
        found = true;
        break;
      }
    expect("26b: the request phase 26 answered", found, 1);
    uint16_t seq = found ? fld16(txf[rqi], 44) : 0;
    uint64_t t1 = found ? txns[rqi] : 0;
    uint64_t t2 = peer_ns(t1 + 300), t3 = t2 + 20000, t4 = t1 + 21200;
    uint32_t pd0 = dut->pub_pdelay_ns_o;
    expect("26b: asCapable down, one exchange in",
           dut->pub_flags_o & FL_ASCAP, 0);
    for (int k = 0; k < 2; k++) {
      uint64_t skew = k ? 2000 : 0;          // the identical pair, then skewed
      Frame f = ptp(0x3, seq, 0, 0x0200, 20);
      f.ts(t2); f.u64(OUR_CID); f.u16(1);
      send_frame(f.b, t4 + skew);
      run(2000);
      Frame g = ptp(0xA, seq, 0, 0x0000, 20);
      g.ts(t3); g.u64(OUR_CID); g.u16(1);
      send_frame(g.b, t4 + skew + 1000);
      run(6000);
      const char *tag = k ? "skewed replay" : "replayed identical pair";
      char n[96];
      snprintf(n, 96, "%s: not a second exchange", tag);
      expect(n, dut->pub_flags_o & FL_ASCAP, 0);
      snprintf(n, 96, "%s: pdelay unmoved", tag);
      expect(n, dut->pub_pdelay_ns_o, pd0);
    }
    pd_seen = txf.size();
    pd_mode = PD_NORMAL;
  }

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
    // forger replays against the LAST genuine request: the engine pairs
    // on its sequenceId (11.2.15.3) and computes the turnaround from its
    // stored t1, so the forgery must reuse both or self-defeat before
    // the gate it is here to probe. The pair's t3 is skewed +2 us: a
    // completion behind a missing gate would publish -400 ns (once
    // completed, the request admits no second pair, so the delay is the
    // observable, not a second climb)
    uint64_t t1_last = 0;
    uint16_t seq_last = 0;
    for (size_t i = txf.size(); i-- > 0;)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2 && txns[i]) {
        t1_last = txns[i];
        seq_last = fld16(txf[i], 44);
        break;
      }
    expect("a genuine t1 to replay against", t1_last != 0, 1);
    uint32_t pd_cease = dut->pub_pdelay_ns_o;
    for (int k = 0; k < 2; k++) {
      uint64_t t1f = t1_last, t2f = peer_ns(t1f + 300),
               t3f = t2f + 20000 + 2000, t4f = t1f + 21200;
      Frame f = ptp(0x3, seq_last, 0, 0x0200, 20);
      f.ts(t2f); f.u64(OUR_CID); f.u16(1);
      send_frame(f.b, t4f);
      run(2000);
      Frame g = ptp(0xA, seq_last, 0, 0x0000, 20);
      g.ts(t3f); g.u64(OUR_CID); g.u16(1);
      send_frame(g.b, t4f + 1000);
      run(4000);
    }
    expect("forged pairs cannot climb mid-cease",
           dut->pub_flags_o & FL_ASCAP, 0);
    expect("forged pairs cannot publish mid-cease",
           dut->pub_pdelay_ns_o, pd_cease);
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

  // ---- 27b: a late second identity still ceases --------------------------
  // the second identity answers AFTER the first responder's Follow_Up,
  // so the exchange has already completed when its Pdelay_Resp arrives:
  // the handler refuses to re-arm (26b) but must still count the
  // identity for the Milan 4.2.6.2.5 rule. Three such intervals cease
  // Pdelay_Req and drop asCapable, the countdown resumes them, the
  // ladder re-earns (the review's probe; a completed path sent to END
  // instead of the bookkeeping passes phase 27, whose second identity
  // answers before the Follow_Up, and fails here)
  {
    pd_mode = PD_NORMAL;
    expect("27b: capable before the late-second storm",
           wait_flags(FL_ASCAP, FL_ASCAP, 6000000ull), 1);
    pd_mode = PD_DUAL_LATE;
    expect("27b: a late second identity still ceases",
           wait_flags(FL_ASCAP, 0, 16000000ull), 1);
    size_t mark = txf.size();
    run_svc(5000000);                            // 2.5 s of silence?
    int reqs = 0;
    for (size_t i = mark; i < txf.size(); i++)
      if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2) reqs++;
    expect("27b: ceased, no requests", reqs, 0);
    pd_mode = PD_NORMAL;
    size_t mark2 = txf.size();
    bool resumed = false;
    for (int k = 0; k < 40 && !resumed; k++) {
      run_svc(200000);
      for (size_t i = mark2; i < txf.size(); i++)
        if (txf[i].size() > 14 && (txf[i][14] & 0xF) == 0x2) resumed = true;
    }
    expect("27b: the countdown resumes requests", resumed, 1);
    expect("27b: the ladder re-earns",
           wait_flags(FL_ASCAP, FL_ASCAP, 8000000ull), 1);
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

  // ---- 31: reset cannot strand a pre-reset egress claim -----------------
  // Scratch deliberately survives warm reset for the Milan cease countdown,
  // but the frame/event pipelines do not. A request whose boundary return is
  // lost across reset must not leave S_TXQ_TMR suppressing every later Req
  // and Sync. The resettable validity beside the LUTRAM claim makes the old
  // word read as empty until a post-reset transmitter writes a new one.
  {
    pd_mode = PD_SKIP;
    while (auto_pend >= 0) tick();
    auto_txts = true;
    tx_seen = txf.size();
    size_t pre_reset_idx = 0;
    std::vector<uint8_t> pre_reset_req =
        wait_tx(0x2, 4000000, &pre_reset_idx);
    auto_txts = false;
    auto_pend = -1;
    expect("reset claim: request sent", pre_reset_req.empty() ? 0 : 1, 1);
    if (!pre_reset_req.empty())
      expect("reset claim: stamp withheld", txns[pre_reset_idx], 0);

    dut->rst_n = 0;
    for (int i = 0; i < 8; i++) tick();
    dut->rst_n = 1;
    dut->tx_ready_i = 1;
    auto_txts = true;
    tx_seen = txf.size();
    std::vector<uint8_t> post_reset_req = wait_tx(0x2, 4000000);
    expect("reset claim: cadence restarts", post_reset_req.empty() ? 0 : 1, 1);
    while (auto_pend >= 0) tick();

    // The responder claim/context is the other reset-surviving scratch word.
    // Lose one response's return across reset, then require a fresh request
    // to produce a complete response pair instead of waiting behind the
    // orphaned pre-reset owner.
    const uint16_t RQ1 = 0x31A1, RQ2 = 0x31A2;
    auto_txts = false;
    Frame reset_q1 = ptp(0x2, RQ1, 0, 0x0000, 20, NEAR_CID);
    reset_q1.u64(0); reset_q1.u16(0); reset_q1.ts(0);
    reset_q1.b.resize(68);
    size_t reset_resp_mark = txf.size();
    send_frame(reset_q1.b, phc() + 1000);
    int pre_reset_resp = -1;
    for (int k = 0; k < 200000 && pre_reset_resp < 0; k++) {
      tick();
      for (size_t i = reset_resp_mark; i < txf.size(); i++)
        if (type_of(txf[i]) == 0x3 && seq_of(txf[i]) == RQ1)
          pre_reset_resp = (int)i;
    }
    expect("reset response claim: response sent",
           pre_reset_resp >= 0 ? 1 : 0, 1);
    if (pre_reset_resp >= 0)
      expect("reset response claim: stamp withheld", txns[pre_reset_resp], 0);

    dut->rst_n = 0;
    for (int i = 0; i < 8; i++) tick();
    dut->rst_n = 1;
    dut->tx_ready_i = 1;
    auto_txts = true;
    Frame reset_q2 = ptp(0x2, RQ2, 0, 0x0000, 20, NEAR_CID);
    reset_q2.u64(0); reset_q2.u16(0); reset_q2.ts(0);
    reset_q2.b.resize(68);
    reset_resp_mark = txf.size();
    send_frame(reset_q2.b, phc() + 2000);
    int post_reset_resp = -1, post_reset_fu = -1;
    for (int k = 0; k < 300000 && post_reset_fu < 0; k++) {
      tick();
      for (size_t i = reset_resp_mark; i < txf.size(); i++) {
        if (type_of(txf[i]) == 0x3 && seq_of(txf[i]) == RQ2)
          post_reset_resp = (int)i;
        if (type_of(txf[i]) == 0xA && seq_of(txf[i]) == RQ2)
          post_reset_fu = (int)i;
      }
    }
    expect("reset response claim: fresh response sent",
           post_reset_resp >= 0 ? 1 : 0, 1);
    expect("reset response claim: fresh Follow_Up sent",
           post_reset_fu >= 0 ? 1 : 0, 1);
    while (auto_pend >= 0) tick();

    // Exercise the other producer of S_TXQ_TMR independently. Re-earn
    // asCapable and mastership, then lose a Sync's boundary return across
    // reset. A later request proves that the shared cadence claim recovered.
    pd_seen = txf.size();
    pd_mode = PD_NORMAL;
    expect("reset Sync claim: capable setup",
           wait_flags(FL_ASCAP, FL_ASCAP, 8000000ull), 1);
    expect("reset Sync claim: master setup",
           wait_flags(FL_AMGM, FL_AMGM, 12000000ull), 1);
    while (auto_pend >= 0) tick();
    auto_txts = true;
    size_t pre_reset_sync_idx = 0;
    std::vector<uint8_t> pre_reset_sync =
        wait_tx(0x0, 1000000, &pre_reset_sync_idx);
    auto_txts = false;
    auto_pend = -1;
    expect("reset Sync claim: Sync sent", pre_reset_sync.empty() ? 0 : 1, 1);
    if (!pre_reset_sync.empty())
      expect("reset Sync claim: stamp withheld", txns[pre_reset_sync_idx], 0);

    dut->rst_n = 0;
    for (int i = 0; i < 8; i++) tick();
    dut->rst_n = 1;
    dut->tx_ready_i = 1;
    auto_txts = true;
    pd_mode = PD_SKIP;
    tx_seen = txf.size();
    std::vector<uint8_t> post_sync_reset_req = wait_tx(0x2, 4000000);
    expect("reset Sync claim: cadence restarts",
           post_sync_reset_req.empty() ? 0 : 1, 1);
    while (auto_pend >= 0) tick();
  }

  // ---- 32: two response claims survive downstream backpressure ----------
  // The parent can commit complete frames into its TX FIFO while the lane is
  // stopped. Request 2 therefore reaches the donor before response 1's real
  // boundary stamp. Hold it at the event-queue head; the stamp has a direct
  // priority dispatch path, clears claim/context 1, builds Resp_FU 1, and
  // only then may request 2 overwrite the scratch context. This also drives
  // tx_ready low at a frame's first byte, in its body, for one cycle and for
  // many cycles; only valid/ready handshakes enter the captured frame.
  {
    pd_mode = PD_SKIP;
    while (auto_pend >= 0) tick();
    auto_txts = false;
    for (int k = 0; k < 20000 && (dut->dbg_busy_o || dut->tx_valid_o); k++)
      tick();

    const uint16_t Q1 = 0x1111, Q2 = 0x2222;
    const uint64_t C1 = PEER_CID, C2 = NEAR_CID;
    const uint16_t P1 = 1, P2 = 2;
    const uint64_t TS1 = 8100111ull, TS2 = 8200222ull;
    Frame q1 = ptp(0x2, Q1, 0, 0x0000, 20, C1);
    q1.u64(0); q1.u16(0); q1.ts(0); q1.b.resize(68);
    Frame q2 = ptp(0x2, Q2, 0, 0x0000, 20, C2);
    q2.b[42] = (uint8_t)(P2 >> 8); q2.b[43] = (uint8_t)P2;
    q2.u64(0); q2.u16(0); q2.ts(0); q2.b.resize(68);

    const size_t mark = txf.size();
    const uint16_t evdrop0 = dut->dbg_ev_drop_o;
    dut->tx_ready_i = 0;
    const uint64_t Q1_RX = phc() + 1000;
    send_frame(q1.b, Q1_RX);
    const uint64_t Q2_RX = phc() + 2000;
    send_frame(q2.b, Q2_RX);
    // Two accepted chasers consume both ping-pong banks while request 2 is
    // held behind response 1's claim. Its event-queue snapshot, not either
    // live bank, must still feed the second response and Follow_Up.
    Frame chase1 = ptp(0xC, 0xD00D, 0, 0x0000, 0);
    Frame chase2 = ptp(0xC, 0xBEEF, 0, 0x0000, 0);
    send_frame(chase1.b, phc() + 3000);
    send_frame(chase2.b, phc() + 4000);
    for (int k = 0; k < 20000 && !(dut->tx_valid_o && dut->tx_sof_o); k++)
      tick();
    expect("backpressure: first byte presented",
           (dut->tx_valid_o && dut->tx_sof_o) ? 1 : 0, 1);
    uint8_t start_data = dut->tx_data_o;
    size_t start_frames = txf.size();
    run(32);
    expect("backpressure: start valid holds", dut->tx_valid_o, 1);
    expect("backpressure: start sof holds", dut->tx_sof_o, 1);
    expect("backpressure: start byte holds", dut->tx_data_o, start_data);
    expect("backpressure: start accepts none", txf.size(), start_frames);

    dut->tx_ready_i = 1;
    for (int k = 0; k < 20000 && !(in_tx && cur.size() >= 12); k++) tick();
    expect("backpressure: body advances", (in_tx && cur.size() >= 12) ? 1 : 0,
           1);
    dut->tx_ready_i = 0;
    uint8_t mid_data = dut->tx_data_o;
    uint8_t mid_sof = dut->tx_sof_o;
    uint8_t mid_eof = dut->tx_eof_o;
    size_t mid_size = cur.size();
    run(32);
    expect("backpressure: mid valid holds", dut->tx_valid_o, 1);
    expect("backpressure: mid byte holds", dut->tx_data_o, mid_data);
    expect("backpressure: mid sof holds", dut->tx_sof_o, mid_sof);
    expect("backpressure: mid eof holds", dut->tx_eof_o, mid_eof);
    expect("backpressure: mid accepts none", cur.size(), mid_size);
    dut->tx_ready_i = 1;

    auto find_frame = [&](uint8_t mt, uint16_t seq) -> int {
      for (size_t i = mark; i < txf.size(); i++)
        if (type_of(txf[i]) == mt && seq_of(txf[i]) == seq) return (int)i;
      return -1;
    };

    int resp1 = -1;
    for (int k = 0; k < 200000 && resp1 < 0; k++) {
      tick();
      resp1 = find_frame(0x3, Q1);
    }
    expect("backpressure: response 1 sent", resp1 >= 0 ? 1 : 0, 1);
    if (resp1 >= 0) {
      expect("backpressure: response 1 requestReceiptTimestamp",
             fld48(txf[resp1], 48) * 1000000000ull +
                 fld32(txf[resp1], 54),
             Q1_RX);
      expect("backpressure: response 1 requester", fld64(txf[resp1], 58), C1);
      expect("backpressure: response 1 port", fld16(txf[resp1], 66), P1);
    }
    run(2000);
    expect("backpressure: response 2 waits", find_frame(0x3, Q2) < 0 ? 1 : 0,
           1);

    if (resp1 >= 0) txts_idx((size_t)resp1, TS1);
    for (int k = 0; k < 20000 && !dut->tx_valid_o; k++) tick();
    expect("backpressure: post-stamp frame starts", dut->tx_valid_o, 1);
    if (dut->tx_valid_o) {
      uint8_t one_data = dut->tx_data_o;
      uint8_t one_sof = dut->tx_sof_o;
      uint8_t one_eof = dut->tx_eof_o;
      dut->tx_ready_i = 0;
      tick();
      expect("backpressure: one-cycle byte holds", dut->tx_data_o, one_data);
      expect("backpressure: one-cycle sof holds", dut->tx_sof_o, one_sof);
      expect("backpressure: one-cycle eof holds", dut->tx_eof_o, one_eof);
      dut->tx_ready_i = 1;
    }

    int fu1 = -1, resp2 = -1;
    for (int k = 0; k < 300000 && (fu1 < 0 || resp2 < 0); k++) {
      tick();
      fu1 = find_frame(0xA, Q1);
      resp2 = find_frame(0x3, Q2);
    }
    expect("backpressure: Follow_Up 1 sent", fu1 >= 0 ? 1 : 0, 1);
    expect("backpressure: response 2 sent", resp2 >= 0 ? 1 : 0, 1);
    if (fu1 >= 0) {
      expect("backpressure: Follow_Up 1 timestamp",
             fld48(txf[fu1], 48) * 1000000000ull + fld32(txf[fu1], 54), TS1);
      expect("backpressure: Follow_Up 1 requester", fld64(txf[fu1], 58), C1);
      expect("backpressure: Follow_Up 1 port", fld16(txf[fu1], 66), P1);
    }
    if (resp2 >= 0) {
      expect("backpressure: response 2 requestReceiptTimestamp",
             fld48(txf[resp2], 48) * 1000000000ull +
                 fld32(txf[resp2], 54),
             Q2_RX);
      expect("backpressure: response 2 requester", fld64(txf[resp2], 58), C2);
      expect("backpressure: response 2 port", fld16(txf[resp2], 66), P2);
      txts_idx((size_t)resp2, TS2);
    }

    int fu2 = -1;
    for (int k = 0; k < 200000 && fu2 < 0; k++) {
      tick();
      fu2 = find_frame(0xA, Q2);
    }
    expect("backpressure: Follow_Up 2 sent", fu2 >= 0 ? 1 : 0, 1);
    if (fu2 >= 0) {
      expect("backpressure: Follow_Up 2 timestamp",
             fld48(txf[fu2], 48) * 1000000000ull + fld32(txf[fu2], 54), TS2);
      expect("backpressure: Follow_Up 2 requester", fld64(txf[fu2], 58), C2);
      expect("backpressure: Follow_Up 2 port", fld16(txf[fu2], 66), P2);
    }
    expect("backpressure: event queue keeps both", dut->dbg_ev_drop_o, evdrop0);
    dut->tx_ready_i = 1;
    auto_txts = true;
    pd_mode = PD_NORMAL;
  }

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
