#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""gPTP µcode ROM image generator — v3, the grandmaster round.

v2 made the plane a correct pdelay peer and announce listener; the bench
against a real peer then demonstrated the spec's point (802.1AS-2011
5.3.1 / 10.1.2): a node that never transmits Announce never enters the
best-master contest, and a strict peer never sees a master candidate
opposite it. v3 adds Grandmaster Capability per 5.3.1 a)+c):

  * BTCA-lite (10.3): lexicographic priority-vector compare
    {priority1, clockQuality, priority2} then grandmasterIdentity,
    incoming Announce vs our own vector. stepsRemoved tie-breaks are
    deliberately out (single point-to-point link, no topology), so this
    is the two-node subset of 10.3 — the full comparison lands with the
    multi-announcer round.
  * PortAnnounceTransmit (10.3.13): when master, Announce every 1 s
    (Milan Table 4.1) with the 10.5.3 path trace TLV carrying our
    clockIdentity. Our vector: priority1 248 (Milan 4.2.6.2.1
    GM-capable), clockClass 248, clockAccuracy 0xFE, variance 0x436A,
    priority2 248.
  * ClockMasterSyncSend + PortSyncSyncSend (10.2.8/10.2.11): when
    master, two-step Sync every 125 ms + Follow_Up carrying the sync's
    egress timestamp as preciseOriginTimestamp and the 11.4.4.3
    Follow_Up information TLV.
  * Role transitions: announce receipt timeout (3 s, Milan Table 4.2)
    with no better announce -> become master; a better announce at any
    time -> become slave (adopt, cadences disarmed); a worse announce ->
    stay master. The received priority vector is published raw
    (publish word 5) so the bench UART shows what the peer claims.

Entry table (mirrored by KL_gptp_engine): 16 SYNC · 64 FOLLOWUP ·
128 ANNOUNCE · 192 PDELAY_REQ · 256 PDELAY_RESP · 320 PDELAY_RESP_FU ·
384 SIGNALING · 448 TX_TS · 512 TIMER (slot 0 init+pdelay, 1 sync TX,
2 announce receipt timeout -> become master, 3 announce TX) ·
704 TB battery · 768.. shared legs (BTCA, become-master, FU builders,
sync/announce builders).

Observe-only servo still: the PHC is never steered this round.
"""

import argparse

DEPTH = 1024
WMASK = (1 << 48) - 1

# ---- encoding (gptp_ucpu_pkg.sv) -------------------------------------------
OPS = {
    "NOP": 0, "BR": 1, "BRS": 2, "END": 3, "MOVE": 4, "CMP": 5, "MASK": 6,
    "DADDR": 7, "RDST": 8, "WRST": 9, "NRD": 10, "NWR": 11, "CPBUF": 12,
    "CHKL": 13, "CHKA": 14, "MAPV": 15, "GATH": 16, "RCTR": 17,
    "IOPEN": 18, "INEXT": 19, "APP": 20, "COMMIT": 21, "NVM": 22,
    "NTFY": 23, "SETS": 24, "SETL": 25, "BHDR": 26, "BFLD": 27,
    "SEND": 28, "ALU": 29, "MD": 30,
}
FMT_B, FMT_W, FMT_D, FMT_Q = 0, 1, 2, 3
ALU_ADD, ALU_SUB, ALU_AND, ALU_OR, ALU_XOR, ALU_SHL, ALU_SHR, ALU_SAR = \
    range(8)
MD_MULS, MD_DIVU = 0, 1
BRS_NZOK, BRS_ITER, BRS_Z, BRS_LT, BRS_OVF = range(5)

RG_BANK, RG_TS, RG_SCR, RG_PUB, RG_PHC, RG_TMR = (
    0x00000, 0x10000, 0x20000, 0x30000, 0x40000, 0x50000)

# ---- scratch map -----------------------------------------------------------
S_SYNCTS, S_HDR, S_OFFSET, S_AMGM = 0, 1, 2, 3
S_PDELAY, S_T2, S_SSEQFLY = 4, 5, 6
S_FUORG = 9                      # 0xC2000001 (info-TLV org tail)
S_MYPV = 10                      # our {p1, cq, p2, 16'0} compare vector
S_T1, S_T4, S_PEND = 16, 17, 18
S_RQCID, S_TICK, S_RQSEQ, S_RQPN, S_INIT, S_MYSEQ = 19, 20, 21, 22, 23, 24
S_CID, S_1E9, S_HDR8, S_SALO = 25, 26, 27, 28
S_SSEQ, S_ASEQ, S_ANNBODY = 29, 30, 31

# ---- our clock vector (Milan defaults) -------------------------------------
P1_C, P2_C = 248, 248
CQ_C = 0xF8FE436A               # class 248, accuracy 0xFE, variance 0x436A
UTC_OFF_C = 37

# ---- register conventions --------------------------------------------------
R0, RA, RB, RC, RD_, RT, RU, RSEC, RNS, RP = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
RV, RW = 10, 11
REV, RTS0, RTS1 = 15, 14, 13

# shared-leg entry points (768..1023), packed to measured sizes
L_BTCA, L_BECOME, L_RFU, L_SYNCFU, L_SYNCTX, L_ANNTX = (
    768, 806, 820, 862, 912, 959)


def w(op, rd=0, ra=0, rb=0, fmt=0, cnd=0, imm=0):
    assert 0 <= imm < (1 << 24), hex(imm)
    return ((OPS[op] << 43) | (rd << 39) | (ra << 35) | (rb << 31) |
            (fmt << 28) | (cnd << 24) | imm)


def splitmix48(i):
    z = (i + 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & ((1 << 64) - 1)
    return (z ^ (z >> 31)) & WMASK


class Prog:
    """Tiny two-pass assembler; local labels plus absolute targets."""

    def __init__(self, base):
        self.base = base
        self.items = []

    def emit(self, op, label=None, **kw):
        self.items.append((op, kw, label))

    def label(self, name):
        self.items.append(("label", name))

    def words(self):
        addr, labels = self.base, {}
        for it in self.items:
            if it[0] == "label":
                labels[it[1]] = addr
            else:
                addr += 1
        out = []
        for it in self.items:
            if it[0] == "label":
                continue
            op, kw, label = it
            if label is not None:
                kw = dict(kw, imm=labels[label] if isinstance(label, str)
                          else label)
            out.append(w(op, **kw))
        return out


# ---- emit helpers ----------------------------------------------------------

def e_const(p, rd, value):
    chunks = []
    v = value
    while True:
        chunks.append(v & 0xFFFFFF)
        v >>= 24
        if v == 0:
            break
    chunks.reverse()
    p.emit("MOVE", rd=rd, ra=0, imm=chunks[0])
    for c in chunks[1:]:
        p.emit("ALU", rd=rd, ra=rd, rb=0, cnd=ALU_SHL, imm=24)
        if c:
            p.emit("MOVE", rd=RT, ra=0, imm=c)
            p.emit("ALU", rd=rd, ra=rd, rb=RT, cnd=ALU_OR)


def e_guard_init(p, end_label):
    p.emit("RDST", rd=RA, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="run")
    p.emit("BR", label=end_label)
    p.label("run")


def e_hdr(p, mtype, flags, seq_reg, logint, msglen):
    """Bytes 0..47: eth + 802.1AS common header."""
    p.emit("RDST", rd=RC, imm=RG_SCR | S_HDR8, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_SALO, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_D)
    p.emit("MOVE", rd=RT, ra=0, imm=0x88F7)
    p.emit("BFLD", ra=RT, fmt=FMT_W)
    p.emit("MOVE", rd=RT, ra=0, imm=0x10 | mtype)
    p.emit("BFLD", ra=RT, fmt=FMT_B)
    p.emit("MOVE", rd=RT, ra=0, imm=0x02)
    p.emit("BFLD", ra=RT, fmt=FMT_B)
    p.emit("MOVE", rd=RT, ra=0, imm=msglen)
    p.emit("BFLD", ra=RT, fmt=FMT_W)
    p.emit("BFLD", ra=0, fmt=FMT_B)
    p.emit("BFLD", ra=0, fmt=FMT_B)
    if flags:
        p.emit("MOVE", rd=RT, ra=0, imm=flags)
        p.emit("BFLD", ra=RT, fmt=FMT_W)
    else:
        p.emit("BFLD", ra=0, fmt=FMT_W)
    p.emit("BFLD", ra=0, fmt=FMT_Q)
    p.emit("BFLD", ra=0, fmt=FMT_D)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("BFLD", ra=RT, fmt=FMT_W)
    p.emit("BFLD", ra=seq_reg, fmt=FMT_W)
    p.emit("MOVE", rd=RT, ra=0, imm=5)
    p.emit("BFLD", ra=RT, fmt=FMT_B)
    p.emit("MOVE", rd=RT, ra=0, imm=logint)
    p.emit("BFLD", ra=RT, fmt=FMT_B)


def e_ts_fields(p, ns_reg):
    p.emit("RDST", rd=RP, imm=RG_SCR | S_1E9, fmt=FMT_Q)
    p.emit("MD", rd=RSEC, ra=ns_reg, rb=RP, cnd=MD_DIVU)
    p.emit("MD", rd=RT, ra=RSEC, rb=RP, cnd=MD_MULS)
    p.emit("ALU", rd=RNS, ra=ns_reg, rb=RT, cnd=ALU_SUB)
    p.emit("ALU", rd=RU, ra=RSEC, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("BFLD", ra=RU, fmt=FMT_W)
    p.emit("BFLD", ra=RSEC, fmt=FMT_D)
    p.emit("BFLD", ra=RNS, fmt=FMT_D)


def e_full_ts(p, rd):
    p.emit("RDST", rd=RSEC, imm=RG_BANK | 4, fmt=FMT_Q)
    p.emit("RDST", rd=RP, imm=RG_SCR | S_1E9, fmt=FMT_Q)
    p.emit("MD", rd=rd, ra=RSEC, rb=RP, cnd=MD_MULS)
    p.emit("RDST", rd=RNS, imm=RG_BANK | 5, fmt=FMT_Q)
    p.emit("ALU", rd=rd, ra=rd, rb=RNS, cnd=ALU_ADD)


def e_ult64(p, ra, rb, less_label, geq_label, tag):
    """Branch to less_label when u64 rf[ra] < rf[rb]; geq on >; falls
    through on equal."""
    p.emit("ALU", rd=RT, ra=ra, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("ALU", rd=RU, ra=rb, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("CMP", ra=RT, rb=RU, fmt=FMT_D)
    p.emit("BRS", cnd=BRS_LT, label=less_label)
    p.emit("BRS", cnd=BRS_Z, label=f"lo_{tag}")
    p.emit("BR", label=geq_label)
    p.label(f"lo_{tag}")
    p.emit("CMP", ra=ra, rb=rb, fmt=FMT_D)
    p.emit("BRS", cnd=BRS_LT, label=less_label)
    p.emit("BRS", cnd=BRS_Z, label=f"eq_{tag}")
    p.emit("BR", label=geq_label)
    p.label(f"eq_{tag}")


# ---- RX handlers -----------------------------------------------------------

def prog_rx_sync(base):
    p = Prog(base)
    p.emit("WRST", ra=RTS0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_BANK | 0, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_HDR, fmt=FMT_Q)
    p.emit("END")
    return p


def prog_rx_followup(base):
    p = Prog(base)
    e_guard_init(p, "out")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_AMGM, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="slave")
    p.emit("BR", label="out")                        # masters ignore sync
    p.label("slave")
    e_full_ts(p, RA)
    p.emit("RDST", rd=RB, imm=RG_BANK | 1, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RB, rb=0, cnd=ALU_SAR, imm=16)
    p.emit("ALU", rd=RA, ra=RA, rb=RB, cnd=ALU_ADD)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=RB, cnd=ALU_ADD)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RB, rb=RA, cnd=ALU_SUB)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_OFFSET, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_PUB | 4, fmt=FMT_Q)
    p.emit("COMMIT")
    p.label("out")
    p.emit("END")
    return p


def prog_rx_announce(base):
    p = Prog(base)
    e_guard_init(p, "out")
    p.emit("RDST", rd=RA, imm=RG_BANK | 8, fmt=FMT_Q)   # their {utc,p1,cq,p2}
    p.emit("WRST", ra=RA, imm=RG_PUB | 5, fmt=FMT_Q)    # publish raw: bench
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_SHL, imm=16)  # {p1,cq,p2,0}
    p.emit("RDST", rd=RB, imm=RG_BANK | 9, fmt=FMT_Q)   # their gm identity
    p.emit("RDST", rd=RV, imm=RG_SCR | S_MYPV, fmt=FMT_Q)
    p.emit("RDST", rd=RW, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("BR", label=L_BTCA)
    p.label("out")
    p.emit("END")
    return p


def prog_rx_pdreq(base):
    p = Prog(base)
    e_guard_init(p, "out")
    p.emit("RDST", rd=RA, imm=RG_BANK | 0, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_RQSEQ, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("WRST", ra=RB, imm=RG_SCR | S_RQCID, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_BANK | 3, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_RQPN, fmt=FMT_Q)
    e_hdr(p, 0x3, 0x0200, RA, 0x7F, 54)
    e_ts_fields(p, RTS0)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_RQCID, fmt=FMT_Q)
    p.emit("BFLD", ra=RB, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_RQPN, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_W)
    p.emit("MOVE", rd=RT, ra=0, imm=2)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.label("out")
    p.emit("END")
    return p


def prog_rx_pdresp(base):
    p = Prog(base)
    e_guard_init(p, "out")
    p.emit("RDST", rd=RA, imm=RG_BANK | 6, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=RB, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="mine")
    p.emit("BR", label="out")
    p.label("mine")
    e_full_ts(p, RA)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_T2, fmt=FMT_Q)
    p.emit("WRST", ra=RTS0, imm=RG_SCR | S_T4, fmt=FMT_Q)
    p.label("out")
    p.emit("END")
    return p


def prog_rx_pdrfu(base):
    p = Prog(base)
    e_guard_init(p, "out")
    p.emit("RDST", rd=RA, imm=RG_BANK | 6, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=RB, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="mine")
    p.emit("BR", label="out")
    p.label("mine")
    e_full_ts(p, RC)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_T4, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_T1, fmt=FMT_Q)
    p.emit("ALU", rd=RD_, ra=RA, rb=RB, cnd=ALU_SUB)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_T2, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=RC, rb=RB, cnd=ALU_SUB)
    p.emit("ALU", rd=RD_, ra=RD_, rb=RC, cnd=ALU_SUB)
    p.emit("ALU", rd=RD_, ra=RD_, rb=0, cnd=ALU_SHR, imm=1)
    p.emit("WRST", ra=RD_, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)
    p.emit("WRST", ra=RD_, imm=RG_PUB | 3, fmt=FMT_Q)
    p.emit("COMMIT")
    p.label("out")
    p.emit("END")
    return p


def prog_rx_signal(base):
    p = Prog(base)
    p.emit("END")
    return p


def prog_tx_ts(base):
    p = Prog(base)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="t1")
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=2)
    p.emit("BRS", cnd=BRS_Z, label=L_RFU)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=3)
    p.emit("BRS", cnd=BRS_Z, label=L_SYNCFU)
    p.emit("END")
    p.label("t1")
    p.emit("WRST", ra=RTS0, imm=RG_SCR | S_T1, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("END")
    return p


def prog_tmr(base, mac):
    cid = ((mac >> 24) << 40) | (0xFFFE << 24) | (mac & 0xFFFFFF)
    hdr8 = (0x0180C200000E << 16) | ((mac >> 32) & 0xFFFF)
    salo = mac & 0xFFFFFFFF
    mypv = (P1_C << 56) | (CQ_C << 24) | (P2_C << 16)
    annbody = (UTC_OFF_C << 48) | (P1_C << 32) | CQ_C
    p = Prog(base)
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="slot0")
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=1)
    p.emit("BRS", cnd=BRS_Z, label=L_SYNCTX)
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=2)
    p.emit("BRS", cnd=BRS_Z, label=L_BECOME)
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=3)
    p.emit("BRS", cnd=BRS_Z, label=L_ANNTX)
    p.emit("END")
    p.label("slot0")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="cadence")
    # ---- init leg, exactly once ----
    p.emit("MOVE", rd=R0, ra=0, imm=0)
    e_const(p, RP, 1_000_000_000)
    p.emit("WRST", ra=RP, imm=RG_SCR | S_1E9, fmt=FMT_Q)
    e_const(p, RC, cid)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    e_const(p, RC, hdr8)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_HDR8, fmt=FMT_Q)
    e_const(p, RC, salo)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_SALO, fmt=FMT_Q)
    e_const(p, RC, mypv)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_MYPV, fmt=FMT_Q)
    e_const(p, RC, annbody)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_ANNBODY, fmt=FMT_Q)
    e_const(p, RC, 0xC2000001)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_FUORG, fmt=FMT_Q)
    for s in (S_SYNCTS, S_OFFSET, S_AMGM, S_PDELAY, S_T2, S_SSEQFLY,
              S_T1, S_T4, S_PEND, S_TICK, S_MYSEQ, S_SSEQ, S_ASEQ):
        p.emit("WRST", ra=0, imm=RG_SCR | s, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=3000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)   # announce receipt
    p.label("cadence")
    p.emit("MOVE", rd=RT, ra=0, imm=1000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 0, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_TICK, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_TICK, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="send")
    p.emit("END")
    p.label("send")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)
    e_hdr(p, 0x2, 0x0000, RA, 0x00, 54)
    p.emit("BFLD", ra=0, fmt=FMT_Q)
    p.emit("BFLD", ra=0, fmt=FMT_Q)
    p.emit("BFLD", ra=0, fmt=FMT_D)
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.emit("END")
    return p


def prog_tb_battery(base):
    p = Prog(base)
    for n, cnd in enumerate([ALU_ADD, ALU_SUB, ALU_AND, ALU_OR, ALU_XOR,
                             ALU_SHL, ALU_SHR, ALU_SAR]):
        p.emit("ALU", rd=1, ra=14, rb=13, cnd=cnd)
        p.emit("WRST", ra=1, imm=RG_SCR | n, fmt=FMT_Q)
    p.emit("MD", rd=1, ra=14, rb=13, cnd=MD_MULS)
    p.emit("WRST", ra=1, imm=RG_SCR | 8, fmt=FMT_Q)
    p.emit("MD", rd=1, ra=14, rb=13, cnd=MD_DIVU)
    p.emit("WRST", ra=1, imm=RG_SCR | 9, fmt=FMT_Q)
    p.emit("ALU", rd=1, ra=14, rb=0, cnd=ALU_ADD, imm=0xABC)
    p.emit("WRST", ra=1, imm=RG_SCR | 10, fmt=FMT_Q)
    p.emit("ALU", rd=1, ra=14, rb=0, cnd=ALU_SHR, imm=16)
    p.emit("WRST", ra=1, imm=RG_SCR | 11, fmt=FMT_Q)
    p.emit("END")
    return p


# ---- shared legs (768..1023) -----------------------------------------------

def prog_btca(base):
    """r1 = their vector, r2 = their gmId, r10 = ours, r11 = our CID."""
    p = Prog(base)
    e_ult64(p, RA, RV, "adopt", "reject", "pv")
    e_ult64(p, RB, RW, "adopt", "reject", "id")
    p.emit("BR", label="reject")                     # equal cannot happen
    p.label("adopt")
    p.emit("WRST", ra=0, imm=RG_SCR | S_AMGM, fmt=FMT_Q)
    p.emit("WRST", ra=RB, imm=RG_PUB | 0, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_PUB | 1, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)  # gm_present, not gm
    p.emit("WRST", ra=0, imm=RG_TMR | 1, fmt=FMT_Q)   # sync TX off
    p.emit("WRST", ra=0, imm=RG_TMR | 3, fmt=FMT_Q)   # announce TX off
    p.emit("MOVE", rd=RT, ra=0, imm=3000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)  # receipt timeout
    p.emit("COMMIT")
    p.emit("END")
    p.label("reject")                                # ours is better
    p.emit("RDST", rd=RA, imm=RG_SCR | S_AMGM, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="held")
    p.emit("BR", label=L_BECOME)
    p.label("held")
    p.emit("END")
    return p


def prog_become(base):
    p = Prog(base)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_AMGM, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_PUB | 0, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_PUB | 1, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=3)
    p.emit("WRST", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)  # present | am_gm
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_TMR | 1, fmt=FMT_Q)  # sync now
    p.emit("MOVE", rd=RT, ra=0, imm=2)
    p.emit("WRST", ra=RT, imm=RG_TMR | 3, fmt=FMT_Q)  # announce now
    p.emit("WRST", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch
    p.emit("COMMIT")
    p.emit("END")
    return p


def prog_leg_rfu(base):
    p = Prog(base)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_RQSEQ, fmt=FMT_Q)
    e_hdr(p, 0xA, 0x0000, RA, 0x7F, 54)
    e_ts_fields(p, RTS0)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_RQCID, fmt=FMT_Q)
    p.emit("BFLD", ra=RB, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_RQPN, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_W)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.emit("END")
    return p


def prog_leg_syncfu(base):
    p = Prog(base)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_SSEQFLY, fmt=FMT_Q)
    e_hdr(p, 0x8, 0x0008, RA, 0xFD, 76)
    e_ts_fields(p, RTS0)                             # preciseOrigin = t1
    p.emit("MOVE", rd=RT, ra=0, imm=0x03001C)        # TLV type 3, len 28
    p.emit("BFLD", ra=RT, fmt=FMT_D)
    p.emit("MOVE", rd=RT, ra=0, imm=0x0080)
    p.emit("BFLD", ra=RT, fmt=FMT_W)                 # org 00-80-
    p.emit("RDST", rd=RT, imm=RG_SCR | S_FUORG, fmt=FMT_Q)
    p.emit("BFLD", ra=RT, fmt=FMT_D)                 # C2 + subtype 000001
    p.emit("BFLD", ra=0, fmt=FMT_D)                  # cumScaledRateOffset
    p.emit("BFLD", ra=0, fmt=FMT_W)                  # gmTimeBaseIndicator
    p.emit("BFLD", ra=0, fmt=FMT_Q)                  # lastGmPhaseChange
    p.emit("BFLD", ra=0, fmt=FMT_D)                  #   (12 bytes)
    p.emit("BFLD", ra=0, fmt=FMT_D)                  # scaledLastGmFreqChg
    p.emit("WRST", ra=0, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.emit("END")
    return p


def prog_leg_synctx(base):
    p = Prog(base)
    p.emit("MOVE", rd=RT, ra=0, imm=125)
    p.emit("WRST", ra=RT, imm=RG_TMR | 1, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_AMGM, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="go")
    p.emit("END")
    p.label("go")
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="build")
    p.emit("END")                                    # skip this beat
    p.label("build")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_SSEQ, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_SSEQFLY, fmt=FMT_Q)
    e_hdr(p, 0x0, 0x0208, RA, 0xFD, 44)
    p.emit("BFLD", ra=0, fmt=FMT_Q)                  # originTimestamp
    p.emit("BFLD", ra=0, fmt=FMT_W)                  #   (10 bytes)
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_SSEQ, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=3)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.emit("END")
    return p


def prog_leg_anntx(base):
    p = Prog(base)
    p.emit("MOVE", rd=RT, ra=0, imm=1000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 3, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_AMGM, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="go")
    p.emit("END")
    p.label("go")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_ASEQ, fmt=FMT_Q)
    e_hdr(p, 0xB, 0x0008, RA, 0x00, 76)
    p.emit("BFLD", ra=0, fmt=FMT_Q)                  # 10 reserved bytes
    p.emit("BFLD", ra=0, fmt=FMT_W)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_ANNBODY, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)                 # utc,res,p1,cq
    p.emit("MOVE", rd=RT, ra=0, imm=P2_C)
    p.emit("BFLD", ra=RT, fmt=FMT_B)                 # priority2
    p.emit("RDST", rd=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)                 # grandmasterIdentity
    p.emit("BFLD", ra=0, fmt=FMT_W)                  # stepsRemoved
    p.emit("MOVE", rd=RT, ra=0, imm=0xA0)
    p.emit("BFLD", ra=RT, fmt=FMT_B)                 # timeSource internal
    p.emit("MOVE", rd=RT, ra=0, imm=0x080008)
    p.emit("BFLD", ra=RT, fmt=FMT_D)                 # path trace TLV hdr
    p.emit("RDST", rd=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)                 # our hop
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_ASEQ, fmt=FMT_Q)
    p.emit("SEND")
    p.emit("END")
    return p


def build(mac):
    entries = [
        (16, prog_rx_sync), (64, prog_rx_followup), (128, prog_rx_announce),
        (192, prog_rx_pdreq), (256, prog_rx_pdresp), (320, prog_rx_pdrfu),
        (384, prog_rx_signal), (448, prog_tx_ts),
        (512, lambda b: prog_tmr(b, mac)), (704, prog_tb_battery),
        (L_BTCA, prog_btca), (L_BECOME, prog_become),
        (L_RFU, prog_leg_rfu), (L_SYNCFU, prog_leg_syncfu),
        (L_SYNCTX, prog_leg_synctx), (L_ANNTX, prog_leg_anntx),
    ]
    rom = [None] * DEPTH
    used = 0
    ends = sorted(b for b, _ in entries) + [DEPTH]
    for base, fn in entries:
        words = fn(base).words()
        limit = min(e for e in ends if e > base)
        assert base + len(words) <= limit, \
            f"program at {base} is {len(words)} words, next entry at {limit}"
        for i, word in enumerate(words):
            assert rom[base + i] is None
            rom[base + i] = word
        used += len(words)
    for i in range(DEPTH):
        if rom[i] is None:
            rom[i] = splitmix48(i)
    return rom, used


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="gptp_ucode.hex")
    ap.add_argument("--mac", type=lambda s: int(s, 0), default=0x02A1B2C3D4E5)
    ap.add_argument("--p1", type=int, default=248,
                    help="our announced priority1 (lower wins BTCA)")
    args = ap.parse_args()
    global P1_C
    P1_C = args.p1
    rom, used = build(args.mac)
    with open(args.out, "w", encoding="ascii") as f:
        for word in rom:
            f.write(f"{word:012X}\n")
    print(f"{args.out}: {DEPTH} words, {used} real "
          f"({100.0 * used / DEPTH:.1f}%), mac {args.mac:012X}")


if __name__ == "__main__":
    main()
