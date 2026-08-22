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
// a short messageLength, a Follow_Up without its information TLV, rx_err.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>
#include <verilated.h>
#include "VKL_gptp_rx_parser.h"

static int checks = 0, fails = 0;

static void expect_eq(const char *what, uint64_t got, uint64_t exp) {
  checks++;
  if (got != exp) {
    fails++;
    printf("FAIL %-24s got %016llx exp %016llx\n", what,
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
};

struct Hdr {
  uint8_t  mtype = 0, dom = 0, logint = 0x7F, ts_field = 1, ver = 2;
  uint16_t seq = 0, flags = 0, etype = 0x88F7;
  uint64_t corr = 0, srcid = 0;
  uint16_t srcpn = 0;
};

static Frame common(const Hdr &h, uint16_t body_len) {
  Frame f;
  for (int i = 0; i < 6; i++) f.u8(0x01);            // DA
  for (int i = 0; i < 6; i++) f.u8(0x22);            // SA
  f.u16(h.etype);
  f.u8((uint8_t)((h.ts_field << 4) | (h.mtype & 0xF)));
  f.u8(h.ver);
  f.u16((uint16_t)(34 + body_len));
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

int main(int argc, char **argv) {
  Verilated::commandArgs(argc, argv);
  auto *dut = new VKL_gptp_rx_parser;

  std::map<uint32_t, uint64_t> bank;
  bool ev_seen = false;
  uint8_t ev_code = 0;
  uint16_t ev_seq = 0;

  auto tick = [&]() {
    dut->clk_i = 0; dut->eval();
    dut->clk_i = 1; dut->eval();
    if (dut->bank_we_o) bank[dut->bank_addr_o] = dut->bank_wdata_o;
    if (dut->ev_valid_o) { ev_seen = true; ev_code = dut->ev_code_o;
                           ev_seq = dut->ev_seq_o; }
  };

  auto feed = [&](const std::vector<uint8_t> &bytes, bool err_at_eof) {
    bank.clear(); ev_seen = false;
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
    for (int i = 0; i < 3; i++) tick();
  };

  // reset
  dut->rst_n = 0; dut->rx_valid_i = 0; dut->rx_sof_i = 0;
  dut->rx_eof_i = 0; dut->rx_err_i = 0; dut->rx_data_i = 0;
  for (int i = 0; i < 4; i++) tick();
  dut->rst_n = 1;
  for (int i = 0; i < 2; i++) tick();

  auto w0_of = [](const Hdr &h) {
    return ((uint64_t)(h.mtype & 0xF) << 48) | ((uint64_t)h.seq << 32) |
           ((uint64_t)h.dom << 24) | ((uint64_t)h.flags << 8) | h.logint;
  };

  // ---- Announce with a 2-hop path trace TLV -----------------------------
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
    f.u64(0x1111111111111111ull);
    f.u64(0x2222222222222222ull);
    feed(f.b, false);
    expect_eq("ann event", ev_seen ? ev_code : 0, 3);
    expect_eq("ann ev_seq", ev_seq, 0xBEEF);
    expect_eq("ann w0", bank[0], w0_of(h));
    expect_eq("ann w2 srcid", bank[2], h.srcid);
    expect_eq("ann w3 srcpn", bank[3], 2);
    expect_eq("ann w8", bank[8],
              (0xFFC4ull << 48) | (248ull << 40) |
              ((uint64_t)0xF8FE436A << 8) | 248ull);
    expect_eq("ann w9 gmid", bank[9], 0x00220FFFFE334455ull);
    expect_eq("ann w10", bank[10],
              (1ull << 48) | (0xA0ull << 40));
    expect_eq("ann w12 hops", bank[12], 2);
    expect_eq("ann w16 pt0", bank[16], 0x1111111111111111ull);
    expect_eq("ann w17 pt1", bank[17], 0x2222222222222222ull);
  }

  // ---- Sync -------------------------------------------------------------
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

  // ---- Follow_Up with information TLV -----------------------------------
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

  // ---- Pdelay_Resp ------------------------------------------------------
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

  // ---- drop arms --------------------------------------------------------
  uint16_t drops0 = dut->drop_cnt_o;
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
              (uint16_t)(d0 + 1));
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
              (uint16_t)(d0 + 1));
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
              (uint16_t)(d0 + 1));
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
              (uint16_t)(d0 + 1));
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
              (uint16_t)(d0 + 1));
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
  auto fu_frame = [&](uint16_t seq, uint16_t tlvt, uint16_t tlvl,
                      uint32_t org, uint32_t sub) {
    Hdr h; h.mtype = 0x8; h.seq = seq; h.srcid = 0xAABBCCFFFE001122ull;
    h.srcpn = 1;
    Frame f = common(h, 10 + 32);
    f.u48(0x000012345678ull); f.u32(0x2FAF0800);
    f.u16(tlvt); f.u16(tlvl);
    f.u8((uint8_t)(org >> 16)); f.u8((uint8_t)(org >> 8)); f.u8((uint8_t)org);
    f.u8((uint8_t)(sub >> 16)); f.u8((uint8_t)(sub >> 8)); f.u8((uint8_t)sub);
    f.u32(0xFFFFF000); f.u16(0x0007);
    for (int i = 0; i < 12; i++) f.u8(0);
    f.u32(0x00000123);
    return f;
  };
  const uint64_t W11 = (0xFFFFF000ull << 32) | (0x0007ull << 16);
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
              (uint16_t)(d0 + 1));
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
              (uint16_t)(d0 + 1));
  }
  {
    uint16_t d0 = dut->drop_cnt_o;
    Frame f = fu_frame(0x0F4C, 0x0003, 28, 0x0080C2, 1);
    f.b.pop_back();                                  // declared 76, cut at 75
    feed(f.b, false);
    expect_eq("cut fu drop: no event", ev_seen, 0);
    expect_eq("cut fu drop: one drop", dut->drop_cnt_o, (uint16_t)(d0 + 1));
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
    expect_eq(n, dut->drop_cnt_o, (uint16_t)(d0 + 1));
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
  expect_eq("drop count advanced", dut->drop_cnt_o, (uint16_t)(drops0 + 17));

  printf("%d checks: %d PASS, %d FAIL\n", checks, checks - fails, fails);
  delete dut;
  return fails ? 1 : 0;
}
