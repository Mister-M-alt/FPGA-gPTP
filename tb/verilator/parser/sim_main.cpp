// SPDX-FileCopyrightText: 2026 Kebag Logic
// SPDX-License-Identifier: CERN-OHL-W-2.0
//
// KL_gptp_rx_parser field-extraction checks.
//
// Builds 802.1AS-2011 frames byte-by-byte in C++ (an independent
// re-implementation of the wire layout — never derived from the RTL),
// streams them into the parser, records every message-bank write and the
// end-of-frame event, and compares against independently packed expected
// words. Also proves the drop arms: wrong EtherType, wrong
// transportSpecific, wrong PTP version, foreign domainNumber, truncation,
// a short messageLength (one arm per type the per-type table names), a
// Follow_Up without its information TLV, a Pdelay_Req shorter than its
// two reserved fields, rx_err; and that a Sync padded to the 60-byte
// Ethernet minimum is accepted.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>
#include <verilated.h>
#include "VKL_gptp_rx_parser.h"
#include "../../common/verilator_harness.hpp"

constexpr uint64_t LOCAL_CID = 0x02A1B2FFFEC3D4E5ull;

//! Cycles held in reset, and cycles idled after it before the first frame.
constexpr int kResetTicks = 4;
constexpr int kPostResetTicks = 2;
//! Idle cycles after a feed, so a deferred end-of-frame resolves before the
//! next feed clears the recorded bank and event state.
constexpr int kDrainTicks = 3;


struct Frame {
  std::vector<uint8_t> b;
  void u8(uint8_t v) { b.push_back(v); }
  void u16(uint16_t v) { u8(v >> 8); u8(v & 0xFF); }
  void u32(uint32_t v) { u16(v >> 16); u16(v & 0xFFFF); }
  void u48(uint64_t v) { u16((v >> 32) & 0xFFFF); u32(v & 0xFFFFFFFF); }
  void u64(uint64_t v) { u32(v >> 32); u32(v & 0xFFFFFFFF); }
};

struct Hdr {
  uint8_t  mtype = 0;
  uint8_t  dom = 0;
  uint8_t  logint = 0x7F;
  uint8_t  ts_field = 1;
  uint8_t  ver = 2;
  uint16_t seq = 0;
  uint16_t flags = 0;
  uint16_t etype = 0x88F7;
  uint64_t corr = 0;
  uint64_t srcid = 0;
  uint16_t srcpn = 0;
};

static Frame common(const Hdr &h, uint16_t body_len) {
  Frame f;
  for (int i = 0; i < 6; i++) f.u8(0x01);            // DA
  for (int i = 0; i < 6; i++) f.u8(0x22);            // SA
  f.u16(h.etype);
  f.u8(static_cast<uint8_t>((h.ts_field << 4) | (h.mtype & 0xF)));
  f.u8(h.ver);
  f.u16(static_cast<uint16_t>(34 + body_len));
  f.u8(h.dom);
  f.u8(0);
  f.u16(h.flags);
  f.u64(h.corr);
  f.u32(0);                                          // reserved
  f.u64(h.srcid);
  f.u16(h.srcpn);
  f.u16(h.seq);
  f.u8(0x05);                                        // control
  f.u8(h.logint);
  return f;
}

static uint64_t w0_of(const Hdr &h) {
  return (static_cast<uint64_t>(h.mtype & 0xF) << 48) |
         (static_cast<uint64_t>(h.seq) << 32) |
         (static_cast<uint64_t>(h.dom) << 24) |
         (static_cast<uint64_t>(h.flags) << 8) | h.logint;
}

static Frame announce_frame(uint16_t seq, uint64_t gm, uint16_t steps,
                            uint64_t src,
                            const std::vector<uint64_t> &path) {
  Hdr h; h.mtype = 0xB; h.seq = seq; h.flags = 0x0008;
  h.srcid = src; h.srcpn = 1;
  const uint16_t suffix = path.empty() ? 0 :
                          static_cast<uint16_t>(4 + 8 * path.size());
  Frame f = common(h, static_cast<uint16_t>(30 + suffix));
  for (int i = 0; i < 10; i++) f.u8(0);
  f.u16(0xFFC4); f.u8(0);
  f.u8(100); f.u32(0xF8FE436A); f.u8(248);
  f.u64(gm); f.u16(steps); f.u8(0xA0);
  if (!path.empty()) {
    f.u16(0x0008); f.u16(static_cast<uint16_t>(8 * path.size()));
    for (uint64_t hop : path) f.u64(hop);
  }
  return f;
}

static void set_declared_to_physical(Frame &f) {
  const uint16_t n = static_cast<uint16_t>(f.b.size() - 14);
  f.b[16] = static_cast<uint8_t>(n >> 8);
  f.b[17] = static_cast<uint8_t>(n);
}

static void append_tlv(Frame &f, uint16_t type,
                       const std::vector<uint8_t> &value) {
  f.u16(type); f.u16(static_cast<uint16_t>(value.size()));
  for (uint8_t b : value) f.u8(b);
  set_declared_to_physical(f);
}

static void append_path_tlv(Frame &f, const std::vector<uint64_t> &path) {
  f.u16(0x0008); f.u16(static_cast<uint16_t>(8 * path.size()));
  for (uint64_t hop : path) f.u64(hop);
  set_declared_to_physical(f);
}

// The Announce identities the declared-length probes are built from.
constexpr uint64_t AGM = 0x001122FFFE334455ull;
constexpr uint64_t ASRC = 0x001122FFFE556677ull;

namespace {

//! The parser, the message bank it writes, the per-feed event record and
//! the tally in one object. `checks`/`fails` were file-scope mutables (I.2)
//! and every probe below lived in one 994-line `main` (F.3).
class RxParserHarness {
 public:
  int run();

 private:
  void expect_eq(const char *what, uint64_t got, uint64_t exp);
  void tick();
  void feed(const std::vector<uint8_t> &bytes, bool err_at_eof);
  void feed_gap(const std::vector<uint8_t> &a,
                const std::vector<uint8_t> &b, int gap);
  void reset_the_parser();
  void check_announce_with_a_two_hop_path_trace();
  void check_a_declared_suffix_binds_parsing_to_the_message();
  void check_unknown_tlvs_are_skipped_around_the_path_tlv();
  void check_an_incomplete_declared_chain_is_refused();
  void check_a_duplicate_path_tlv_is_refused();
  void check_declared_path_boundaries_and_padding();
  void check_sync();
  void check_follow_up_with_information_tlv();
  void check_pdelay_resp();
  void check_header_level_drop_arms();
  void check_foreign_domain_is_refused_for_every_type();
  void check_follow_up_minimum_and_tlv_arms();
  void check_message_length_minimum_per_type();
  void check_a_padded_sync_is_accepted();
  void check_pdelay_req_minimum_arms();
  void check_unlisted_message_types_are_refused();
  void check_adjacent_refusals_are_each_counted();
  void check_the_drop_count_advanced();
  int report();

  const milan::tb::Model<VKL_gptp_rx_parser> model;
  VKL_gptp_rx_parser *const dut = model.get();

  std::map<uint32_t, uint64_t> bank;
  //! every event in a feed, with the word-0 the frame that raised it left
  //! behind: a two-frame feed needs both, and one `ev_seen` cannot say
  //! whether the second frame dispatched or only the first did twice
  int ev_count = 0;
  std::vector<uint64_t> ev_w0;
  bool ev_seen = false;
  uint8_t ev_code = 0;
  uint16_t ev_seq = 0;

  //! the drop count before the drop arms, so the last check can assert the
  //! total every arm between them added
  uint16_t drops0 = 0;

  int checks = 0;
  int fails = 0;
};

void RxParserHarness::expect_eq(const char *what, uint64_t got, uint64_t exp) {
  checks++;
  if (got != exp) {
    fails++;
    printf("FAIL %-24s got %016llx exp %016llx\n", what,
           static_cast<unsigned long long>(got),
           static_cast<unsigned long long>(exp));
  }
}

void RxParserHarness::tick() {
  dut->clk_i = 0; dut->eval();
  dut->clk_i = 1; dut->eval();
  if (dut->bank_we_o) bank[dut->bank_addr_o] = dut->bank_wdata_o;
  if (dut->ev_valid_o) {
    ev_seen = true;
    ev_code = dut->ev_code_o;
    ev_seq = dut->ev_seq_o;
    ev_count++;
    ev_w0.push_back(bank.count(0) ? bank[0] : 0);
  }
}

void RxParserHarness::feed(const std::vector<uint8_t> &bytes, bool err_at_eof) {
  bank.clear(); ev_seen = false; ev_count = 0; ev_w0.clear();
  for (size_t i = 0; i < bytes.size(); i++) {
    dut->rx_valid_i = 1;
    dut->rx_data_i  = bytes[i];
    dut->rx_sof_i   = (i == 0);
    dut->rx_eof_i   = (i + 1 == bytes.size());
    dut->rx_err_i   = err_at_eof && (i + 1 == bytes.size());
    tick();
  }
  dut->rx_valid_i = 0; dut->rx_sof_i = 0; dut->rx_eof_i = 0;
  dut->rx_err_i = 0;
  for (int i = 0; i < kDrainTicks; i++) tick();
}

//! stream two frames with an exact inter-frame gap, so a frame can start
//! in the cycle a predecessor's deferred end-of-frame is still settling
void RxParserHarness::feed_gap(const std::vector<uint8_t> &a,
                               const std::vector<uint8_t> &b, int gap) {
  bank.clear(); ev_seen = false; ev_count = 0; ev_w0.clear();
  for (const std::vector<uint8_t> *f : {&a, &b}) {
    for (size_t i = 0; i < f->size(); i++) {
      dut->rx_valid_i = 1;
      dut->rx_data_i  = (*f)[i];
      dut->rx_sof_i   = (i == 0);
      dut->rx_eof_i   = (i + 1 == f->size());
      dut->rx_err_i   = 0;         //! driven, not inherited from feed
      tick();
    }
    dut->rx_valid_i = 0; dut->rx_sof_i = 0; dut->rx_eof_i = 0;
    if (f == &a) for (int i = 0; i < gap; i++) tick();
  }
  for (int i = 0; i < kDrainTicks; i++) tick();
}

// reset
void RxParserHarness::reset_the_parser() {
  dut->rst_n = 0; dut->rx_valid_i = 0; dut->rx_sof_i = 0;
  dut->rx_eof_i = 0; dut->rx_err_i = 0; dut->rx_data_i = 0;
  dut->local_clock_id_i = LOCAL_CID;
  dut->local_clock_valid_i = 1;
  for (int i = 0; i < kResetTicks; i++) tick();
  dut->rst_n = 1;
  for (int i = 0; i < kPostResetTicks; i++) tick();
}

// ---- Announce with a 2-hop path trace TLV -----------------------------
void RxParserHarness::check_announce_with_a_two_hop_path_trace() {
  {
    Hdr h; h.mtype = 0xB; h.seq = 0xBEEF; h.dom = 0; h.flags = 0x0008;
    h.corr = 0; h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 30 + 4 + 16);
    for (int i = 0; i < 10; i++) f.u8(0);            // reserved ts
    f.u16(0xFFC4);                                   // currentUtcOffset -60
    f.u8(0);
    f.u8(248);                                       // gmPriority1
    f.u32(0xF8FE436A);                               // gmClockQuality
    f.u8(248);                                       // gmPriority2
    f.u64(0x00220FFFFE334455ull);                    // gmIdentity
    f.u16(1);                                        // stepsRemoved
    f.u8(0xA0);                                      // timeSource
    f.u16(0x0008); f.u16(16);                        // path trace TLV
    f.u64(0x00220FFFFE334455ull);
    f.u64(0x2222222222222222ull);
    feed(f.b, false);
    expect_eq("ann event", ev_seen ? ev_code : 0, 3);
    expect_eq("ann ev_seq", ev_seq, 0xBEEF);
    expect_eq("ann w0", bank[0], w0_of(h));
    expect_eq("ann w2 srcid", bank[2], h.srcid);
    expect_eq("ann w3 srcpn", bank[3], 2);
    expect_eq("ann w8", bank[8],
              (0xFFC4ull << 48) | (248ull << 40) |
              (static_cast<uint64_t>(0xF8FE436A) << 8) | 248ull);
    expect_eq("ann w9 gmid", bank[9], 0x00220FFFFE334455ull);
    expect_eq("ann w10", bank[10],
              (1ull << 48) | (0xA0ull << 40));
    expect_eq("ann w12 hops", bank[12], 2);
    expect_eq("ann w16 pt0", bank[16], 0x00220FFFFE334455ull);
    expect_eq("ann w17 pt1", bank[17], 0x2222222222222222ull);
  }
}

// ---- Announce declared-length and complete-PathTrace boundary --------
// A fixed 64-octet Announce without PathTrace is qualified and reported
// honestly as count zero. If a declared suffix is present, 10.5.3.3 makes
// PathTrace lengthField 8N and N=stepsRemoved+1. These probes bind parsing
// to the PTP message rather than physical Ethernet padding and bite
// independently on an invalid declared suffix, overrun, truncation,
// misalignment, and count mismatch. A valid message may still have
// arbitrary physical padding after its declared end.
void RxParserHarness::check_a_declared_suffix_binds_parsing_to_the_message() {
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA001, AGM, 0, ASRC, {});
    feed(f.b, false);                               // declared/exact 64
    expect_eq("TLV-less ann: event", ev_seen ? ev_code : 0, 3);
    expect_eq("TLV-less ann: zero count and loop", bank[12], 0);
    expect_eq("TLV-less ann: no retained identity", bank.count(16), 0);
    expect_eq("TLV-less ann: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA002, AGM, 1, ASRC, {});
    // Keep messageLength 64, but append bytes whose physical shape used to
    // be mistaken for an in-message PathTrace.
    f.u16(0x0008); f.u16(16); f.u64(AGM); f.u64(LOCAL_CID);
    feed(f.b, false);
    expect_eq("out-of-message path: event", ev_seen ? ev_code : 0, 3);
    expect_eq("out-of-message path: zero count and loop", bank[12], 0);
    expect_eq("out-of-message path: no retained identity", bank.count(16), 0);
    expect_eq("out-of-message path: no drop", dut->drop_cnt_o, d0);
  }
  // IEEE 1588-2008 14.1: a complete unknown TLV is ignored and the next TLV
  // is attempted. Generic lengthField is even (5.3.8); zero is permitted.
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA010, AGM, 0, ASRC, {});
    append_tlv(f, 0x1234, {0xAA, 0x55});
    feed(f.b, false);
    expect_eq("unknown-only ann: event", ev_seen ? ev_code : 0, 3);
    expect_eq("unknown-only ann: zero count", bank[12], 0);
    expect_eq("unknown-only ann: no identity", bank.count(16), 0);
    expect_eq("unknown-only ann: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA016, AGM, 0, ASRC, {});
    //! Structurally valid ORGANIZATION_EXTENSION, but neither this OUI nor
    //! subtype is recognized here: IEEE 1588-2008 14.1 says skip it.
    append_tlv(f, 0x0003, {0x12, 0x34, 0x56, 0xAB, 0xCD, 0xEF});
    feed(f.b, false);
    expect_eq("unknown organization TLV: event", ev_seen ? ev_code : 0, 3);
    expect_eq("unknown organization TLV: zero count", bank[12], 0);
    expect_eq("unknown organization TLV: no identity", bank.count(16), 0);
    expect_eq("unknown organization TLV: no drop", dut->drop_cnt_o, d0);
  }
}

void RxParserHarness::check_unknown_tlvs_are_skipped_around_the_path_tlv() {
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA011, AGM, 0, ASRC, {});
    append_tlv(f, 0x1234, {});
    feed(f.b, false);
    expect_eq("zero-length unknown ann: event", ev_seen ? ev_code : 0, 3);
    expect_eq("zero-length unknown ann: zero count", bank[12], 0);
    expect_eq("zero-length unknown ann: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA012, AGM, 0, ASRC, {});
    append_tlv(f, 0x1111, {});
    append_tlv(f, 0x2222, {1, 2, 3, 4});
    feed(f.b, false);
    expect_eq("two unknown TLVs: event", ev_seen ? ev_code : 0, 3);
    expect_eq("two unknown TLVs: zero count", bank[12], 0);
    expect_eq("two unknown TLVs: no identity", bank.count(16), 0);
    expect_eq("two unknown TLVs: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA013, AGM, 1, ASRC, {});
    append_tlv(f, 0x1111, {0xA1, 0xA2});
    append_path_tlv(f, {AGM, ASRC});
    feed(f.b, false);
    expect_eq("unknown before path: event", ev_seen ? ev_code : 0, 3);
    expect_eq("unknown before path: count", bank[12], 2);
    expect_eq("unknown before path: head", bank[16], AGM);
    expect_eq("unknown before path: tail", bank[17], ASRC);
    expect_eq("unknown before path: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA014, AGM, 1, ASRC, {});
    append_path_tlv(f, {AGM, ASRC});
    append_tlv(f, 0x2222, {0xB1, 0xB2});
    feed(f.b, false);
    expect_eq("unknown after path: event", ev_seen ? ev_code : 0, 3);
    expect_eq("unknown after path: count", bank[12], 2);
    expect_eq("unknown after path: head", bank[16], AGM);
    expect_eq("unknown after path: tail", bank[17], ASRC);
    expect_eq("unknown after path: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA015, AGM, 1, ASRC, {});
    append_tlv(f, 0x1111, {});
    append_tlv(f, 0x2222, {0xC1, 0xC2});
    append_path_tlv(f, {AGM, ASRC});
    append_tlv(f, 0x3333, {1, 2, 3, 4});
    feed(f.b, false);
    expect_eq("unknowns around path: event", ev_seen ? ev_code : 0, 3);
    expect_eq("unknowns around path: count", bank[12], 2);
    expect_eq("unknowns around path: head", bank[16], AGM);
    expect_eq("unknowns around path: tail", bank[17], ASRC);
    expect_eq("unknowns around path: no drop", dut->drop_cnt_o, d0);
  }
}

// A declared suffix must be a complete chain. Trailing 1..3 header bytes,
// odd generic values, length overflow and physical truncation are refused.
void RxParserHarness::check_an_incomplete_declared_chain_is_refused() {
  for (unsigned partial = 1; partial <= 3; partial++) {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(static_cast<uint16_t>(0xA020 + partial), AGM, 0,
                             ASRC, {});
    for (unsigned i = 0; i < partial; i++) f.u8(static_cast<uint8_t>(0xD0 + i));
    set_declared_to_physical(f);
    feed(f.b, false);
    char n[80];
    snprintf(n, sizeof n, "partial TLV header %u: no event", partial);
    expect_eq(n, ev_seen, 0);
    snprintf(n, sizeof n, "partial TLV header %u: no w12", partial);
    expect_eq(n, bank.count(12), 0);
    snprintf(n, sizeof n, "partial TLV header %u: one drop", partial);
    expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA024, AGM, 0, ASRC, {});
    append_tlv(f, 0x1234, {0xEE});                  // odd lengthField
    feed(f.b, false);
    expect_eq("odd unknown length: no event", ev_seen, 0);
    expect_eq("odd unknown length: no w12", bank.count(12), 0);
    expect_eq("odd unknown length: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA025, AGM, 0, ASRC, {});
    f.u16(0x1234); f.u16(0xFFFE);                   // must not wrap containment
    set_declared_to_physical(f);
    feed(f.b, false);
    expect_eq("huge unknown length: no event", ev_seen, 0);
    expect_eq("huge unknown length: no w12", bank.count(12), 0);
    expect_eq("huge unknown length: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA026, AGM, 0, ASRC, {});
    f.u16(0x1234); f.u16(4); f.u16(0xCAFE);         // declares value overrun
    set_declared_to_physical(f);
    feed(f.b, false);
    expect_eq("unknown crosses declaration: no event", ev_seen, 0);
    expect_eq("unknown crosses declaration: no w12", bank.count(12), 0);
    expect_eq("unknown crosses declaration: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA027, AGM, 0, ASRC, {});
    append_tlv(f, 0x1234, {1, 2, 3, 4});
    f.b.resize(f.b.size() - 2);                     // declaration stays longer
    feed(f.b, false);
    expect_eq("physically truncated unknown: no event", ev_seen, 0);
    expect_eq("physically truncated unknown: no w12", bank.count(12), 0);
    expect_eq("physically truncated unknown: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA028, AGM, 0, ASRC, {});
    append_path_tlv(f, {AGM});
    f.u16(0x1234);                                  // partial TLV after path
    set_declared_to_physical(f);
    feed(f.b, false);
    expect_eq("malformed after valid path: no event", ev_seen, 0);
    expect_eq("malformed after valid path: no w12", bank.count(12), 0);
    expect_eq("malformed after valid path: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
}

// Only one PATH_TRACE is defined for an Announce. Reject duplicates before
// a second value can overwrite the selected count, hide a conflict or hide
// a local-identity loop.
void RxParserHarness::check_a_duplicate_path_tlv_is_refused() {
  for (unsigned duplicate = 0; duplicate < 3; duplicate++) {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(static_cast<uint16_t>(0xA030 + duplicate), AGM, 0,
                             ASRC, {});
    append_path_tlv(f, {AGM});
    const uint64_t hop = duplicate == 0 ? AGM
                       : duplicate == 1 ? 0x00BAD0FFFE000001ull : LOCAL_CID;
    append_path_tlv(f, {hop});
    feed(f.b, false);
    char n[88];
    snprintf(n, sizeof n, "duplicate path %u: no event", duplicate);
    expect_eq(n, ev_seen, 0);
    snprintf(n, sizeof n, "duplicate path %u: no w12", duplicate);
    expect_eq(n, bank.count(12), 0);
    snprintf(n, sizeof n, "duplicate path %u: one drop", duplicate);
    expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA040, AGM, 0, ASRC, {});
    append_tlv(f, 0x1234, std::vector<uint8_t>(1432, 0x5A));
    feed(f.b, false);                               // messageLength == 1500
    expect_eq("maximum unknown TLV: event", ev_seen ? ev_code : 0, 3);
    expect_eq("maximum unknown TLV: zero count", bank[12], 0);
    expect_eq("maximum unknown TLV: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA009, AGM, 0, ASRC, {});
    f.b[16] = 0; f.b[17] = 68;                      // declares a suffix
    f.u32(0xDEADBEEF);                              // but no complete TLV
    feed(f.b, false);
    expect_eq("declared suffix without path: no event", ev_seen, 0);
    expect_eq("declared suffix without path: no w12", bank.count(12), 0);
    expect_eq("declared suffix without path: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA003, AGM, 1, ASRC, {AGM, ASRC});
    f.b.resize(f.b.size() - 8);                     // declared 2, got 1
    feed(f.b, false);
    expect_eq("truncated path: no event", ev_seen, 0);
    expect_eq("truncated path: no w12", bank.count(12), 0);
    expect_eq("truncated path: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
}

void RxParserHarness::check_declared_path_boundaries_and_padding() {
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA008, AGM, 1, ASRC, {AGM, ASRC});
    f.b[16] = 0; f.b[17] = 76;                      // declares only 1 hop
    feed(f.b, false);                               // physical 2nd is padding
    expect_eq("declared path overrun: no event", ev_seen, 0);
    expect_eq("declared path overrun: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA004, AGM, 0, ASRC, {AGM});
    f.b[81] = 9;                                    // lengthField 9
    f.b[16] = 0; f.b[17] = 77;                      // contains all 9 bytes
    f.u8(0xEE);
    feed(f.b, false);
    expect_eq("misaligned path: no event", ev_seen, 0);
    expect_eq("misaligned path: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA005, AGM, 2, ASRC, {AGM, ASRC});
    feed(f.b, false);                               // N=2, steps+1=3
    expect_eq("path-count mismatch: no event", ev_seen, 0);
    expect_eq("path-count mismatch: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = announce_frame(0xA006, AGM, 0, ASRC, {AGM});
    f.u16(0x0008); f.u16(8); f.u64(LOCAL_CID);      // physical padding
    feed(f.b, false);
    expect_eq("valid ann with padding: event", ev_seen ? ev_code : 0, 3);
    expect_eq("valid ann with padding: count", bank[12], 1);
    expect_eq("valid ann with padding: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    std::vector<uint64_t> path;
    path.push_back(AGM);
    for (unsigned i = 1; i < 8; i++) path.push_back(0x7000 + i);
    path.push_back(LOCAL_CID);                       // ninth, beyond storage
    Frame f = announce_frame(0xA007, AGM, 8, ASRC, path);
    feed(f.b, false);
    expect_eq("deep self path: event", ev_seen ? ev_code : 0, 3);
    expect_eq("deep self path: full count+loop", bank[12], 0x109);
    expect_eq("deep self path: first retained", bank[16], AGM);
    expect_eq("deep self path: eighth retained", bank[23], 0x7007);
    expect_eq("deep self path: no drop", dut->drop_cnt_o, d0);
  }
}

// ---- Sync -------------------------------------------------------------
void RxParserHarness::check_sync() {
  {
    Hdr h; h.mtype = 0x0; h.seq = 0x0102; h.flags = 0x0208;
    h.corr = 0x0000001234560000ull; h.srcid = 0xAABBCCFFFE001122ull;
    h.srcpn = 1; h.logint = 0xFD;
    Frame f = common(h, 10);
    f.u48(0x000012345678ull);                        // seconds
    f.u32(0x1DCD6500);                               // nanoseconds
    feed(f.b, false);
    expect_eq("sync event", ev_seen ? ev_code : 0, 1);
    expect_eq("sync w0", bank[0], w0_of(h));
    expect_eq("sync w1 corr", bank[1], h.corr);
    expect_eq("sync w4 sec", bank[4], 0x000012345678ull);
    expect_eq("sync w5 ns", bank[5], 0x1DCD6500ull);
  }
}

// ---- Follow_Up with information TLV -----------------------------------
void RxParserHarness::check_follow_up_with_information_tlv() {
  {
    Hdr h; h.mtype = 0x8; h.seq = 0x0102; h.srcid = 0xAABBCCFFFE001122ull;
    Frame f = common(h, 10 + 32);
    f.u48(0x000012345678ull);
    f.u32(0x2FAF0800);
    f.u16(0x0003); f.u16(28);                        // info TLV
    f.u8(0x00); f.u8(0x80); f.u8(0xC2);              // orgId
    f.u8(0); f.u8(0); f.u8(1);                       // orgSubType
    f.u32(0xFFFFF000);                               // cumScaledRateOffset
    f.u16(0x0007);                                   // gmTimeBaseIndicator
    for (int i = 0; i < 12; i++) f.u8(0);            // lastGmPhaseChange
    f.u32(0x00000123);                               // scaledLastGmFreq
    feed(f.b, false);
    expect_eq("fu event", ev_seen ? ev_code : 0, 2);
    expect_eq("fu w4 sec", bank[4], 0x000012345678ull);
    expect_eq("fu w5 ns", bank[5], 0x2FAF0800ull);
    expect_eq("fu w11", bank[11],
              (0xFFFFF000ull << 32) | (0x0007ull << 16));
  }
}

// ---- Pdelay_Resp ------------------------------------------------------
void RxParserHarness::check_pdelay_resp() {
  {
    Hdr h; h.mtype = 0x3; h.seq = 0x77AA; h.flags = 0x0200;
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 20);
    f.u48(0x00000000ABCDull);                        // requestReceipt sec
    f.u32(0x075BCD15);                               // requestReceipt ns
    f.u64(0xDEADBEEFCAFEF00Dull);                    // requestingPortId
    f.u16(1);
    feed(f.b, false);
    expect_eq("pdresp event", ev_seen ? ev_code : 0, 5);
    expect_eq("pdresp w4", bank[4], 0x00000000ABCDull);
    expect_eq("pdresp w5", bank[5], 0x075BCD15ull);
    expect_eq("pdresp w6", bank[6], 0xDEADBEEFCAFEF00Dull);
    expect_eq("pdresp w7", bank[7], 1);
  }
}

// ---- drop arms --------------------------------------------------------
void RxParserHarness::check_header_level_drop_arms() {
  drops0 = dut->drop_cnt_o;
  {
    Hdr h; h.mtype = 0x0; h.etype = 0x0800;          // not 88F7
    Frame f = common(h, 10);
    for (int i = 0; i < 10; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("etype drop: no event", ev_seen, 0);
  }
  {
    Hdr h; h.mtype = 0x0; h.ver = 1;                 // bad PTP version
    Frame f = common(h, 10);
    for (int i = 0; i < 10; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("version drop: no event", ev_seen, 0);
  }
  {
    Hdr h; h.mtype = 0x0; h.ts_field = 0;            // transportSpecific 0
    Frame f = common(h, 10);
    for (int i = 0; i < 10; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("tspec drop: no event", ev_seen, 0);
  }
  {
    Hdr h; h.mtype = 0xB;                            // truncated announce
    Frame f = common(h, 10);
    for (int i = 0; i < 10; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("truncated drop: no event", ev_seen, 0);
  }
  {
    Hdr h; h.mtype = 0x0;                            // rx_err at eof
    Frame f = common(h, 10);
    f.u48(1); f.u32(2);
    feed(f.b, true);
    expect_eq("rx_err drop: no event", ev_seen, 0);
  }
}

// 802.1AS-2011 8.1: the domain number of a gPTP domain shall be 0, and
// IEEE 1588-2008 9.5.1 accepts only messages whose domainNumber matches
// the local domain. The arm sits at header byte 4, ahead of every bank
// write, so a foreign-domain frame of ANY type leaves no event and no
// bank word for a handler to read: BTCA (Announce), the servo (Sync,
// Follow_Up) and both Pdelay roles are covered by the one compare
// (FPGA-gPTP #6). Five shapes, otherwise valid: a Sync in domain 5, a
// better-priority Announce in domain 1, a Pdelay_Resp in domain 255,
// and the two header-only types whose min_ok_r is set regardless of
// bad_r, so that the end-of-frame gate's !bad_r term is their only
// barrier: a Pdelay_Req in domain 0x10 and a Signaling in domain 0x80,
// the zero-low-nibble values that pin the compare's full width. Each
// arm counts exactly one drop; the header-only types first prove their
// domain-0 shape dispatches, so the refusals cannot pass vacuously.
void RxParserHarness::check_foreign_domain_is_refused_for_every_type() {
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x0; h.dom = 5; h.seq = 0x0D05; h.flags = 0x0208;
    h.srcid = 0xAABBCCFFFE001122ull; h.srcpn = 1; h.logint = 0xFD;
    Frame f = common(h, 10);
    f.u48(0x000012345678ull); f.u32(0x1DCD6500);
    feed(f.b, false);
    expect_eq("domain 5 sync drop: no event", ev_seen, 0);
    expect_eq("domain 5 sync drop: no bank write", bank.size(), 0);
    expect_eq("domain 5 sync drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0xB; h.dom = 1; h.seq = 0x0D01; h.flags = 0x0008;
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 30);
    for (int i = 0; i < 10; i++) f.u8(0);
    f.u16(0xFFC4); f.u8(0);
    f.u8(1); f.u32(0xF8FE436A); f.u8(248);            // priority1 1: wins
    f.u64(0x00220FFFFE334455ull);
    f.u16(0); f.u8(0xA0);
    feed(f.b, false);
    expect_eq("domain 1 announce drop: no event", ev_seen, 0);
    expect_eq("domain 1 announce drop: no bank write", bank.size(), 0);
    expect_eq("domain 1 announce drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x3; h.dom = 0xFF; h.seq = 0x0DFF; h.flags = 0x0200;
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 20);
    f.u48(0x00000000ABCDull); f.u32(0x075BCD15);
    f.u64(0xDEADBEEFCAFEF00Dull); f.u16(1);
    feed(f.b, false);
    expect_eq("domain 255 pdresp drop: no event", ev_seen, 0);
    expect_eq("domain 255 pdresp drop: no bank write", bank.size(), 0);
    expect_eq("domain 255 pdresp drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    Hdr h; h.mtype = 0x2; h.seq = 0x0C02; h.srcid = 0x00220FFFFE334455ull;
    h.srcpn = 2;
    Frame f = common(h, 20);
    for (int i = 0; i < 20; i++) f.u8(0);            // two reserved fields
    feed(f.b, false);
    expect_eq("pdreq event", ev_seen ? ev_code : 0, 4);
    expect_eq("pdreq w0", bank[0], w0_of(h));
    expect_eq("pdreq w2 srcid", bank[2], h.srcid);
  }
  {
    Hdr h; h.mtype = 0xC; h.seq = 0x0C0C; h.flags = 0x0008;
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 10);
    f.u64(0xFFFFFFFFFFFFFFFFull); f.u16(0xFFFF);     // targetPortIdentity
    feed(f.b, false);
    expect_eq("sig event", ev_seen ? ev_code : 0, 7);
    expect_eq("sig w0", bank[0], w0_of(h));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x2; h.dom = 0x10; h.seq = 0x0D10;
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 20);
    for (int i = 0; i < 20; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("domain 0x10 pdreq drop: no event", ev_seen, 0);
    expect_eq("domain 0x10 pdreq drop: no bank write", bank.size(), 0);
    expect_eq("domain 0x10 pdreq drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0xC; h.dom = 0x80; h.seq = 0x0D80; h.flags = 0x0008;
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    Frame f = common(h, 10);
    f.u64(0xFFFFFFFFFFFFFFFFull); f.u16(0xFFFF);
    feed(f.b, false);
    expect_eq("domain 0x80 sig drop: no event", ev_seen, 0);
    expect_eq("domain 0x80 sig drop: no bank write", bank.size(), 0);
    expect_eq("domain 0x80 sig drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
}

static Frame fu_frame(uint16_t seq, uint16_t tlvt, uint16_t tlvl,
                      uint32_t org, uint32_t sub) {
  Hdr h; h.mtype = 0x8; h.seq = seq; h.srcid = 0xAABBCCFFFE001122ull;
  h.srcpn = 1;
  Frame f = common(h, 10 + 32);
  f.u48(0x000012345678ull); f.u32(0x2FAF0800);
  f.u16(tlvt); f.u16(tlvl);
  f.u8(static_cast<uint8_t>(org >> 16));
  f.u8(static_cast<uint8_t>(org >> 8));
  f.u8(static_cast<uint8_t>(org));
  f.u8(static_cast<uint8_t>(sub >> 16));
  f.u8(static_cast<uint8_t>(sub >> 8));
  f.u8(static_cast<uint8_t>(sub));
  f.u32(0xFFFFF000); f.u16(0x0007);
  for (int i = 0; i < 12; i++) f.u8(0);
  f.u32(0x00000123);
  return f;
}

// 802.1AS-2011 Table 11-9: a Follow_Up is 76 octets, the header, the
// preciseOriginTimestamp and the Follow_Up information TLV, which
// 11.4.4.3 makes a field of the message (tlvType 0x3, lengthField 28,
// organizationId 00-80-C2, organizationSubType 1: 11.4.4.3.2 to
// 11.4.4.3.5) and 11.4.4.2.2 places first; 10.5.2.2.4 counts exactly
// those 76 octets in messageLength. Until #11 the parser's Follow_Up
// minimum was the 44-octet header-and-timestamp shape and a TLV type
// mismatch only withheld bank word 11, so a TLV-less Follow_Up
// dispatched and steered. Arms: the issue's 44-octet shape and a
// declared length of 75, each refused at the messageLength byte with
// no event, no bank write and one counted drop; a declared 76 cut at
// 75 octets, refused at the end-of-frame gate (no event, one drop);
// then a TLV header wrong in exactly one field (tlvType 0x0008,
// lengthField 27, organizationId 00-1B-19, organizationSubType 2),
// each refused at the TLV arm with no event, no word-11 write and one
// drop. Controls: the complete Follow_Up dispatches with its word 11
// after the arms as it did before them, and a Follow_Up with a second
// TLV appended after the information TLV (messageLength 88) is
// accepted: 11.4.1 has a receiver skip a TLV it does not parse.
void RxParserHarness::check_follow_up_minimum_and_tlv_arms() {
  constexpr uint64_t W11 = (0xFFFFF000ull << 32) | (0x0007ull << 16);
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x8; h.seq = 0x0F44; h.srcid = 0xAABBCCFFFE001122ull;
    h.srcpn = 1;
    Frame f = common(h, 10);                         // messageLength 44
    f.u48(0x000012345678ull); f.u32(0x2FAF0800);     // and no TLV
    feed(f.b, false);
    expect_eq("TLV-less fu drop: no event", ev_seen, 0);
    expect_eq("TLV-less fu drop: no bank write", bank.size(), 0);
    expect_eq("TLV-less fu drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = fu_frame(0x0F4B, 0x0003, 28, 0x0080C2, 1);
    f.b[16] = 0; f.b[17] = 75;                       // messageLength 75
    f.b.pop_back();                                  // in 75 octets
    feed(f.b, false);
    expect_eq("75-octet fu drop: no event", ev_seen, 0);
    expect_eq("75-octet fu drop: no bank write", bank.size(), 0);
    expect_eq("75-octet fu drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = fu_frame(0x0F4C, 0x0003, 28, 0x0080C2, 1);
    f.b.pop_back();                                  // declared 76, cut at 75
    feed(f.b, false);
    expect_eq("cut fu drop: no event", ev_seen, 0);
    expect_eq("cut fu drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  struct BadTlv { const char *tag; uint16_t tlvt, tlvl; uint32_t org, sub; };
  const BadTlv bad_tlv[] = {
    {"fu tlvType 0x0008 drop", 0x0008, 28, 0x0080C2, 1},
    {"fu lengthField 27 drop", 0x0003, 27, 0x0080C2, 1},
    {"fu orgId 00-1B-19 drop", 0x0003, 28, 0x001B19, 1},
    {"fu orgSubType 2 drop", 0x0003, 28, 0x0080C2, 2},
  };
  for (const BadTlv &t : bad_tlv) {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = fu_frame(0x0F50, t.tlvt, t.tlvl, t.org, t.sub);
    feed(f.b, false);
    char n[64];
    snprintf(n, sizeof n, "%s: no event", t.tag);
    expect_eq(n, ev_seen, 0);
    snprintf(n, sizeof n, "%s: no w11 write", t.tag);
    expect_eq(n, bank.count(11), 0);
    snprintf(n, sizeof n, "%s: one drop", t.tag);
    expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = fu_frame(0x0F76, 0x0003, 28, 0x0080C2, 1);
    feed(f.b, false);
    expect_eq("complete fu after the arms: event", ev_seen ? ev_code : 0, 2);
    expect_eq("complete fu after the arms: ev_seq", ev_seq, 0x0F76);
    expect_eq("complete fu after the arms: w11", bank[11], W11);
    expect_eq("complete fu after the arms: no drop", dut->drop_cnt_o, d0);
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = fu_frame(0x0F88, 0x0003, 28, 0x0080C2, 1);
    f.b[16] = 0; f.b[17] = 88;                       // messageLength 88:
    f.u16(0x0008); f.u16(8);                         // a path trace TLV
    f.u64(0x3333333333333333ull);                    // after the info TLV
    feed(f.b, false);
    expect_eq("fu with a trailing TLV: event", ev_seen ? ev_code : 0, 2);
    expect_eq("fu with a trailing TLV: w11", bank[11], W11);
    expect_eq("fu with a trailing TLV: no drop", dut->drop_cnt_o, d0);
  }
}

// The messageLength arm is one compare against the per-type table, so
// it must hold for every type the table names, not only the Follow_Up
// that motivated it (the #18 review's MR8, the arm narrowed to
// Follow_Up, passed both suites). For each of Sync (44, Table 11-8),
// Pdelay_Resp and Pdelay_Resp_Follow_Up
// (54, Tables 11-12 / 11-13), Pdelay_Req (54, Table 11-11, #12) and
// Signaling (34, the header alone): a physically complete frame
// declaring one octet below the minimum is refused at the
// messageLength byte with no event, no bank write and one drop, and
// the same frame declaring the exact minimum dispatches with no drop.
void RxParserHarness::check_message_length_minimum_per_type() {
  struct LenArm { const char *tag; uint8_t mtype; uint16_t minlen; uint8_t ev; };
  const LenArm len_arms[] = {
    {"sync", 0x0, 44, 1}, {"pdresp", 0x3, 54, 5},
    {"pdrfu", 0xA, 54, 6}, {"pdreq", 0x2, 54, 4}, {"signaling", 0xC, 34, 7},
  };
  for (const LenArm &a : len_arms) {
    char n[64];
    Hdr h; h.mtype = a.mtype; h.seq = static_cast<uint16_t>(0x0B00 | a.minlen);
    h.srcid = 0x00220FFFFE334455ull; h.srcpn = 2;
    uint16_t d0 = dut->drop_cnt_o;
    // the full message
    Frame f = common(h, static_cast<uint16_t>(a.minlen - 34));
    for (int i = 34; i < a.minlen; i++) f.u8(0);
    f.b[16] = static_cast<uint8_t>((a.minlen - 1) >> 8);      // declaring one
    f.b[17] = static_cast<uint8_t>((a.minlen - 1) & 0xFF);    // octet fewer
    feed(f.b, false);
    snprintf(n, sizeof n, "%s declared %u drop: no event", a.tag,
             static_cast<unsigned>(a.minlen - 1));
    expect_eq(n, ev_seen, 0);
    snprintf(n, sizeof n, "%s declared %u drop: no bank write", a.tag,
             static_cast<unsigned>(a.minlen - 1));
    expect_eq(n, bank.size(), 0);
    snprintf(n, sizeof n, "%s declared %u drop: one drop", a.tag,
             static_cast<unsigned>(a.minlen - 1));
    expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 1));
    d0 = dut->drop_cnt_o;
    // the exact minimum
    Frame g = common(h, static_cast<uint16_t>(a.minlen - 34));
    for (int i = 34; i < a.minlen; i++) g.u8(0);
    feed(g.b, false);
    snprintf(n, sizeof n, "%s declared %u control: event", a.tag,
             static_cast<unsigned>(a.minlen));
    expect_eq(n, ev_seen ? ev_code : 0, a.ev);
    snprintf(n, sizeof n, "%s declared %u control: no drop", a.tag,
             static_cast<unsigned>(a.minlen));
    expect_eq(n, dut->drop_cnt_o, d0);
  }
}

// A 44-octet Sync is a 58-byte frame and leaves the transmitting MAC
// padded to the 60-byte Ethernet minimum (IEEE 1588-2008 13.3.2.4
// NOTE: messageLength excludes the padding), so octets 58..59 exist on
// every Sync a real link delivers and the receiver ignores them. The
// #18 review's MR7, the TLV arms applied to Sync as well, passed both
// suites because no suite sent a padded Sync: the arm at byte 59 was
// never reached. Four padded Syncs, each accepted with its event, its
// six bank words and no drop: zero padding, padding shaped like the
// information TLV's tlvType (0x0003), padding 0x0008 (a path trace
// TLV's type), and a Sync padded to 74 bytes, the span of the whole
// TLV header arm.
void RxParserHarness::check_a_padded_sync_is_accepted() {
  {
    struct Pad { const char *tag; std::vector<uint8_t> pad; };
    const Pad pads[] = {
      {"sync padded to 60 (zero)", {0x00, 0x00}},
      {"sync padded to 60 (TLV-shaped)", {0x00, 0x03}},
      {"sync padded to 60 (0x0008)", {0x00, 0x08}},
      {"sync padded to 74", std::vector<uint8_t>(16, 0x00)},
    };
    for (const Pad &p : pads) {
      char n[64];
      uint16_t d0 = dut->drop_cnt_o;
      Hdr h; h.mtype = 0x0; h.seq = 0x0A60; h.flags = 0x0208;
      h.srcid = 0xAABBCCFFFE001122ull; h.srcpn = 1; h.logint = 0xFD;
      Frame f = common(h, 10);                       // messageLength 44
      f.u48(0x000012345678ull); f.u32(0x1DCD6500);
      for (uint8_t b : p.pad) f.u8(b);               // the MAC's padding
      feed(f.b, false);
      snprintf(n, sizeof n, "%s: event", p.tag);
      expect_eq(n, ev_seen ? ev_code : 0, 1);
      snprintf(n, sizeof n, "%s: six words", p.tag);
      expect_eq(n, bank.size(), 6);
      snprintf(n, sizeof n, "%s: w5 ns", p.tag);
      expect_eq(n, bank[5], 0x1DCD6500ull);
      snprintf(n, sizeof n, "%s: no drop", p.tag);
      expect_eq(n, dut->drop_cnt_o, d0);
    }
  }
}

// 802.1AS-2011 11.4.5 / Table 11-11: a Pdelay_Req is 54 octets, the
// header and two reserved 10-octet fields (IEEE 1588-2008 13.9 NOTE:
// the second reserved field gives the request the response's length).
// Until #12 the parser's minimum was the 34-octet header, so a
// header-only request dispatched and the responder answered it. Arms:
// the issue's header-only shape (messageLength 34, a 48-byte frame),
// messageLength 44 and messageLength 53, each refused at the
// messageLength byte with no event, no bank write and one drop; a
// declared 54 cut at 53 octets, refused at the end-of-frame gate (no
// event, one drop). Control: the complete 54-octet request dispatches
// after the arms as the domain-0 control did before them. The declared
// 53 in a complete 54-octet frame is the Pdelay_Req row of the
// per-type table above.
void RxParserHarness::check_pdelay_req_minimum_arms() {
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x2; h.seq = 0x0E22; h.srcid = 0x00220FFFFE334455ull;
    h.srcpn = 2;
    Frame f = common(h, 0);                          // messageLength 34
    feed(f.b, false);
    expect_eq("header-only pdreq drop: no event", ev_seen, 0);
    expect_eq("header-only pdreq drop: no bank write", bank.size(), 0);
    expect_eq("header-only pdreq drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x2; h.seq = 0x0E2C; h.srcid = 0x00220FFFFE334455ull;
    h.srcpn = 2;
    Frame f = common(h, 10);                         // messageLength 44
    for (int i = 0; i < 10; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("44-octet pdreq drop: no event", ev_seen, 0);
    expect_eq("44-octet pdreq drop: no bank write", bank.size(), 0);
    expect_eq("44-octet pdreq drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x2; h.seq = 0x0E35; h.srcid = 0x00220FFFFE334455ull;
    h.srcpn = 2;
    Frame f = common(h, 19);                         // messageLength 53
    for (int i = 0; i < 19; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("53-octet pdreq drop: no event", ev_seen, 0);
    expect_eq("53-octet pdreq drop: no bank write", bank.size(), 0);
    expect_eq("53-octet pdreq drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x2; h.seq = 0x0E36; h.srcid = 0x00220FFFFE334455ull;
    h.srcpn = 2;
    Frame f = common(h, 20);                         // declared 54,
    for (int i = 0; i < 19; i++) f.u8(0);            // cut at 53
    feed(f.b, false);
    expect_eq("cut pdreq drop: no event", ev_seen, 0);
    expect_eq("cut pdreq drop: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d0 + 1));
  }
}

// IEEE 1588-2008 13.3.2.2 and its Table 19 define the messageType
// values; a gPTP port carries only the seven of 802.1AS-2011 Clause 10
// and 11 (Sync 0x0, Pdelay_Req 0x2, Pdelay_Resp 0x3, Follow_Up 0x8,
// Pdelay_Resp_Follow_Up 0xA, Announce 0xB, Signaling 0xC) and has no
// handler for the rest. The arm sits at the type byte beside the
// transportSpecific compare, ahead of every bank write, so an unlisted
// type leaves no event, no bank word and one counted drop instead of
// dispatching with the event code no handler claims (FPGA-gPTP #22).
// All nine unlisted values, each in an otherwise valid 44-octet frame
// that every other arm admits: without this compare each one dispatches
// (measured before the fix: events=1 ev_code=0 bank_writes=4 drops=+0).
void RxParserHarness::check_unlisted_message_types_are_refused() {
  const uint8_t unlisted[] = {0x1, 0x4, 0x5, 0x6, 0x7,
                              0x9, 0xD, 0xE, 0xF};
  for (uint8_t mt : unlisted) {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = mt; h.seq = static_cast<uint16_t>(0x0E60 + mt);
    h.flags = 0x0208;
    h.srcid = 0xAABBCCFFFE001122ull; h.srcpn = 1; h.logint = 0xFD;
    Frame f = common(h, 10);
    f.u48(0x000012345678ull); f.u32(0x1DCD6500);
    feed(f.b, false);
    char n[64];
    snprintf(n, sizeof n, "type 0x%X drop: no event", mt);
    expect_eq(n, ev_seen, 0);
    snprintf(n, sizeof n, "type 0x%X drop: no bank write", mt);
    expect_eq(n, bank.size(), 0);
    snprintf(n, sizeof n, "type 0x%X drop: one drop", mt);
    expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Hdr h; h.mtype = 0x2; h.seq = 0x0E54; h.srcid = 0x00220FFFFE334455ull;
    h.srcpn = 2;
    Frame f = common(h, 20);                         // the complete request
    for (int i = 0; i < 20; i++) f.u8(0);
    feed(f.b, false);
    expect_eq("complete pdreq after the arms: event", ev_seen ? ev_code : 0, 4);
    expect_eq("complete pdreq after the arms: ev_seq", ev_seq, 0x0E54);
    expect_eq("complete pdreq after the arms: w0", bank[0], w0_of(h));
    expect_eq("complete pdreq after the arms: w2 srcid", bank[2], h.srcid);
    expect_eq("complete pdreq after the arms: no drop", dut->drop_cnt_o, d0);
  }
}

// Two refusals can resolve on one clock edge: the deferred
// end-of-frame of a dropped frame, and a one-byte frame arriving in
// that same cycle. They are different frames and both must be counted,
// and as two increments of one register only one survived
// (FPGA-gPTP #27). `dbg_rx_drop_o` is the oracle the parent's
// conformance probes read, so a lost increment weakens every probe
// that asserts a counted refusal. Both orderings and both gaps: only
// drop-then-runt at zero gap ever collided, and the reverse never did,
// because a runt resolves on its own edge while the frame behind it
// finalizes two cycles later
void RxParserHarness::check_adjacent_refusals_are_each_counted() {
  {
    Hdr h; h.mtype = 0x0; h.dom = 5;                 // a foreign-domain Sync
    Frame f = common(h, 10);
    f.u48(1); f.u32(2);
    const std::vector<uint8_t> runt = {0x01};
    for (int gap : {0, 1}) {
      char n[64];
      uint16_t d0 = dut->drop_cnt_o;
      feed_gap(f.b, runt, gap);
      snprintf(n, sizeof n, "drop then %d-gap runt: two drops", gap);
      expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 2));
      d0 = dut->drop_cnt_o;
      feed_gap(runt, f.b, gap);
      snprintf(n, sizeof n, "runt then %d-gap drop: two drops", gap);
      expect_eq(n, dut->drop_cnt_o, static_cast<uint16_t>(d0 + 2));
    }
    // and the accepted path is untouched: a good frame arriving in the
    // cycle a dropped frame finalizes still dispatches with a clean bank
    // word, which is one drop and one event, never both for one frame
    Hdr g; g.mtype = 0x0; g.seq = 0x0777; g.flags = 0x0208;
    g.srcid = 0xAABBCCFFFE001122ull; g.srcpn = 1; g.logint = 0xFD;
    Frame good = common(g, 10);
    good.u48(0x000012345678ull); good.u32(0x1DCD6500);
    uint16_t d1 = dut->drop_cnt_o;
    feed_gap(f.b, good.b, 0);
    expect_eq("drop then zero-gap sync: one drop", dut->drop_cnt_o,
              static_cast<uint16_t>(d1 + 1));
    expect_eq("drop then zero-gap sync: event", ev_seen ? ev_code : 0, 1);
    expect_eq("drop then zero-gap sync: w0", bank[0], w0_of(g));

    // the mirror of that adjacency, which the drop case cannot cover: a
    // good frame whose own finalize cycle IS a successor's sof. Both must
    // dispatch, so the check is two events with each frame's own word 0;
    // a deferred dispatch suppressed by a zero-gap successor passes every
    // one-event check and fails here
    Hdr g2 = g; g2.seq = 0x0778;
    Frame good2 = common(g2, 10);
    good2.u48(0x000012345678ull); good2.u32(0x1DCD6500);
    uint16_t d2 = dut->drop_cnt_o;
    feed_gap(good.b, good2.b, 0);
    expect_eq("good then zero-gap good: two events", ev_count, 2);
    expect_eq("good then zero-gap good: no drop", dut->drop_cnt_o, d2);
    expect_eq("good then zero-gap good: first w0",
              ev_w0.size() > 0 ? ev_w0[0] : 0, w0_of(g));
    expect_eq("good then zero-gap good: second w0",
              ev_w0.size() > 1 ? ev_w0[1] : 0, w0_of(g2));

    // sof and eof raised with rx_valid_i LOW is not a frame. At base the
    // runt increment sat inside `if (rx_valid_i)`, so that qualifier could
    // not be deleted; as a term of runt_drop_w it can, and nothing else in
    // this bench ever pulses the two flags without valid
    uint16_t d3 = dut->drop_cnt_o;
    dut->rx_valid_i = 0; dut->rx_sof_i = 1; dut->rx_eof_i = 1;
    dut->rx_data_i = 0x01;
    for (int i = 0; i < 4; i++) tick();
    dut->rx_sof_i = 0; dut->rx_eof_i = 0;
    for (int i = 0; i < kDrainTicks; i++) tick();
    expect_eq("sof and eof without valid: not a frame", dut->drop_cnt_o, d3);
  }
}

void RxParserHarness::check_the_drop_count_advanced() {
  expect_eq("drop count advanced", dut->drop_cnt_o,
            static_cast<uint16_t>(drops0 + 44));
}

int RxParserHarness::report() {
  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  return fails ? 1 : 0;
}

int RxParserHarness::run() {
  reset_the_parser();
  check_announce_with_a_two_hop_path_trace();
  check_a_declared_suffix_binds_parsing_to_the_message();
  check_unknown_tlvs_are_skipped_around_the_path_tlv();
  check_an_incomplete_declared_chain_is_refused();
  check_a_duplicate_path_tlv_is_refused();
  check_declared_path_boundaries_and_padding();
  check_sync();
  check_follow_up_with_information_tlv();
  check_pdelay_resp();
  check_header_level_drop_arms();
  check_foreign_domain_is_refused_for_every_type();
  check_follow_up_minimum_and_tlv_arms();
  check_message_length_minimum_per_type();
  check_a_padded_sync_is_accepted();
  check_pdelay_req_minimum_arms();
  check_unlisted_message_types_are_refused();
  check_adjacent_refusals_are_each_counted();
  check_the_drop_count_advanced();
  return report();
}

}  // namespace

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  RxParserHarness harness;
  return harness.run();
}
