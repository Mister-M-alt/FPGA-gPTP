#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""gPTP µcode ROM image generator — v2, the first protocol round.

v1 (the resource skeleton) proved the datapaths; v2 makes the plane speak
802.1AS-2011 on a real wire, aimed at the Arty-vs-STM32 bench:

  * a COMPLETE two-step Pdelay responder: Pdelay_Resp built with the
    requester's sequenceId and requestingPortIdentity echoed, twoStep
    flag set, t2 from the ingress timestamp; Pdelay_Resp_Follow_Up sent
    on the egress-timestamp return with t3;
  * a Pdelay INITIATOR on the timer cadence (1 s): Pdelay_Req out,
    t1 captured from the egress return, meanLinkDelay computed from the
    four timestamps on Resp + Resp_Follow_Up and published;
  * Announce adoption (last announcer wins — BTCA is a later µcode
    round): GM identity + parent published, a 3 s receipt timeout armed
    that clears gm_present on expiry;
  * Sync/Follow_Up: offset = t_rx − (preciseOrigin + correction>>16 +
    meanLinkDelay), published. OBSERVE-ONLY this round: the PHC is not
    steered, so the bench can watch raw drift honestly.

Entry table (mirrored by KL_gptp_engine's dispatcher):
  16 SYNC · 64 FOLLOWUP · 128 ANNOUNCE · 192 PDELAY_REQ · 256 PDELAY_RESP
  · 320 PDELAY_RESP_FU · 384 SIGNALING · 448 TX_TS · 512 TIMER (slot 0 =
  init + pdelay cadence, slot 2 = announce receipt timeout) · 768 TB
  battery (unchanged from v1).

Station identity is compile-time (bench): --mac sets the source MAC;
clockIdentity is its EUI-64 (FF:FE inserted), portNumber 1.

RX handlers that depend on init-built constants guard on the init flag,
so a chatty peer in the first ~1.2 s (before the engine's boot-armed
timer runs the init leg) is ignored rather than answered with garbage.
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
S_SYNCTS, S_HDR, S_OFFSET = 0, 1, 2
S_PDELAY, S_T2 = 4, 5
S_T1, S_T4, S_PEND = 16, 17, 18
S_RQCID, S_TICK, S_RQSEQ, S_RQPN, S_INIT, S_MYSEQ = 19, 20, 21, 22, 23, 24
S_CID, S_1E9, S_HDR8, S_SALO = 25, 26, 27, 28

# ---- register conventions --------------------------------------------------
# r0 zero (init-owned) · r1/r2/r4/r10 caller data · r3/r5/r6/r7/r8/r9 temps
R0, RA, RB, RC, RD_, RT, RU, RSEC, RNS, RP = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
REV, RTS0, RTS1 = 15, 14, 13


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
    """Tiny two-pass assembler: ops + labels at a fixed base µPC."""

    def __init__(self, base):
        self.base = base
        self.items = []          # ints or ("label", name) or (op, kw, label)

    def emit(self, op, label=None, **kw):
        self.items.append((op, kw, label))

    def label(self, name):
        self.items.append(("label", name))

    def words(self):
        # pass 1: resolve label addresses
        addr, labels = self.base, {}
        for it in self.items:
            if it[0] == "label":
                labels[it[1]] = addr
            else:
                addr += 1
        # pass 2: encode
        out = []
        for it in self.items:
            if it[0] == "label":
                continue
            op, kw, label = it
            if label is not None:
                kw = dict(kw, imm=labels[label])
            out.append(w(op, **kw))
        return out


# ---- emit helpers ----------------------------------------------------------

def e_const(p, rd, value):
    """Load an up-to-64-bit constant via MOVE/SHL/OR chains."""
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
    """Skip the handler until the init leg has built the constants."""
    p.emit("RDST", rd=RA, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="run")
    p.emit("BR", label=end_label)
    p.label("run")


def e_hdr(p, mtype, flags, seq_reg, logint, msglen):
    """Bytes 0..47: eth header + 802.1AS common header. Cursor ends at 48."""
    p.emit("RDST", rd=RC, imm=RG_SCR | S_HDR8, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)                 # DA + SA[47:32]
    p.emit("RDST", rd=RC, imm=RG_SCR | S_SALO, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_D)                 # SA[31:0]
    p.emit("MOVE", rd=RT, ra=0, imm=0x88F7)
    p.emit("BFLD", ra=RT, fmt=FMT_W)                 # EtherType
    p.emit("MOVE", rd=RT, ra=0, imm=0x10 | mtype)
    p.emit("BFLD", ra=RT, fmt=FMT_B)                 # transportSpecific|type
    p.emit("MOVE", rd=RT, ra=0, imm=0x02)
    p.emit("BFLD", ra=RT, fmt=FMT_B)                 # versionPTP
    p.emit("MOVE", rd=RT, ra=0, imm=msglen)
    p.emit("BFLD", ra=RT, fmt=FMT_W)                 # messageLength
    p.emit("BFLD", ra=0, fmt=FMT_B)                  # domainNumber 0
    p.emit("BFLD", ra=0, fmt=FMT_B)                  # reserved
    if flags:
        p.emit("MOVE", rd=RT, ra=0, imm=flags)
        p.emit("BFLD", ra=RT, fmt=FMT_W)             # flags
    else:
        p.emit("BFLD", ra=0, fmt=FMT_W)
    p.emit("BFLD", ra=0, fmt=FMT_Q)                  # correctionField
    p.emit("BFLD", ra=0, fmt=FMT_D)                  # reserved
    p.emit("RDST", rd=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_Q)                 # srcPortId.clockIdentity
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("BFLD", ra=RT, fmt=FMT_W)                 # srcPortId.portNumber
    p.emit("BFLD", ra=seq_reg, fmt=FMT_W)            # sequenceId
    p.emit("MOVE", rd=RT, ra=0, imm=5)
    p.emit("BFLD", ra=RT, fmt=FMT_B)                 # control
    p.emit("MOVE", rd=RT, ra=0, imm=logint)
    p.emit("BFLD", ra=RT, fmt=FMT_B)                 # logMessageInterval


def e_ts_fields(p, ns_reg):
    """Emit a 1588 Timestamp (sec48 + ns32) from a 64-bit ns register."""
    p.emit("RDST", rd=RP, imm=RG_SCR | S_1E9, fmt=FMT_Q)
    p.emit("MD", rd=RSEC, ra=ns_reg, rb=RP, cnd=MD_DIVU)
    p.emit("MD", rd=RT, ra=RSEC, rb=RP, cnd=MD_MULS)
    p.emit("ALU", rd=RNS, ra=ns_reg, rb=RT, cnd=ALU_SUB)
    p.emit("ALU", rd=RU, ra=RSEC, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("BFLD", ra=RU, fmt=FMT_W)                 # seconds[47:32]
    p.emit("BFLD", ra=RSEC, fmt=FMT_D)               # seconds[31:0]
    p.emit("BFLD", ra=RNS, fmt=FMT_D)                # nanoseconds


def e_full_ts(p, rd):
    """rd = bank w4 * 1e9 + bank w5 (their sec/ns to a 64-bit ns)."""
    p.emit("RDST", rd=RSEC, imm=RG_BANK | 4, fmt=FMT_Q)
    p.emit("RDST", rd=RP, imm=RG_SCR | S_1E9, fmt=FMT_Q)
    p.emit("MD", rd=rd, ra=RSEC, rb=RP, cnd=MD_MULS)
    p.emit("RDST", rd=RNS, imm=RG_BANK | 5, fmt=FMT_Q)
    p.emit("ALU", rd=rd, ra=rd, rb=RNS, cnd=ALU_ADD)


# ---- programs --------------------------------------------------------------

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
    e_full_ts(p, RA)                                  # preciseOrigin ns
    p.emit("RDST", rd=RB, imm=RG_BANK | 1, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RB, rb=0, cnd=ALU_SAR, imm=16)
    p.emit("ALU", rd=RA, ra=RA, rb=RB, cnd=ALU_ADD)   # + correction ns
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=RB, cnd=ALU_ADD)   # + meanLinkDelay
    p.emit("RDST", rd=RB, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RB, rb=RA, cnd=ALU_SUB)   # offset = trx - gm
    p.emit("WRST", ra=RA, imm=RG_SCR | S_OFFSET, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_PUB | 4, fmt=FMT_Q)
    p.emit("COMMIT")
    p.label("out")
    p.emit("END")
    return p


def prog_rx_announce(base):
    p = Prog(base)
    p.emit("RDST", rd=RA, imm=RG_BANK | 9, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_PUB | 0, fmt=FMT_Q)  # gm identity
    p.emit("RDST", rd=RB, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("WRST", ra=RB, imm=RG_PUB | 1, fmt=FMT_Q)  # parent clock id
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)  # gm_present
    p.emit("MOVE", rd=RT, ra=0, imm=3000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)  # receipt timeout
    p.emit("COMMIT")
    p.emit("END")
    return p


def prog_rx_pdreq(base):
    p = Prog(base)
    e_guard_init(p, "out")
    p.emit("RDST", rd=RA, imm=RG_BANK | 0, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_SHR, imm=32)   # their seq
    p.emit("WRST", ra=RA, imm=RG_SCR | S_RQSEQ, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("WRST", ra=RB, imm=RG_SCR | S_RQCID, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_BANK | 3, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_RQPN, fmt=FMT_Q)
    e_hdr(p, 0x3, 0x0200, RA, 0x7F, 54)               # Pdelay_Resp, twoStep
    e_ts_fields(p, RTS0)                              # t2 = ingress ts
    p.emit("RDST", rd=RB, imm=RG_SCR | S_RQCID, fmt=FMT_Q)
    p.emit("BFLD", ra=RB, fmt=FMT_Q)                  # requesting cid
    p.emit("RDST", rd=RC, imm=RG_SCR | S_RQPN, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_W)                  # requesting port
    p.emit("MOVE", rd=RT, ra=0, imm=2)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.label("out")
    p.emit("END")
    return p


def prog_rx_pdresp(base):
    p = Prog(base)
    e_guard_init(p, "out")
    # ours? requestingPortIdentity.clockIdentity must be our CID
    p.emit("RDST", rd=RA, imm=RG_BANK | 6, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=RB, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="mine")
    p.emit("BR", label="out")
    p.label("mine")
    e_full_ts(p, RA)                                  # t2 (their receipt)
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
    e_full_ts(p, RC)                                  # t3 (their origin)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_T4, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_T1, fmt=FMT_Q)
    p.emit("ALU", rd=RD_, ra=RA, rb=RB, cnd=ALU_SUB)  # t4 - t1
    p.emit("RDST", rd=RB, imm=RG_SCR | S_T2, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=RC, rb=RB, cnd=ALU_SUB)   # t3 - t2
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
    p.emit("BRS", cnd=BRS_Z, label="fu")
    p.emit("END")
    p.label("t1")                                     # our Pdelay_Req left
    p.emit("WRST", ra=RTS0, imm=RG_SCR | S_T1, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("END")
    p.label("fu")                                     # our Pdelay_Resp left
    p.emit("RDST", rd=RA, imm=RG_SCR | S_RQSEQ, fmt=FMT_Q)
    e_hdr(p, 0xA, 0x0000, RA, 0x7F, 54)               # Pdelay_Resp_FU
    e_ts_fields(p, RTS0)                              # t3 = egress ts
    p.emit("RDST", rd=RB, imm=RG_SCR | S_RQCID, fmt=FMT_Q)
    p.emit("BFLD", ra=RB, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_RQPN, fmt=FMT_Q)
    p.emit("BFLD", ra=RC, fmt=FMT_W)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("SEND")
    p.emit("END")
    return p


def prog_tmr(base, mac):
    cid = ((mac >> 24) << 40) | (0xFFFE << 24) | (mac & 0xFFFFFF)
    hdr8 = (0x0180C200000E << 16) | ((mac >> 32) & 0xFFFF)
    salo = mac & 0xFFFFFFFF
    p = Prog(base)
    # which slot fired? aux is r15 low16
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="slot0")
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=2)
    p.emit("BRS", cnd=BRS_Z, label="anntmo")
    p.emit("END")
    p.label("anntmo")                                 # announce timed out
    p.emit("WRST", ra=0, imm=RG_PUB | 2, fmt=FMT_Q)
    p.emit("COMMIT")
    p.emit("END")
    p.label("slot0")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="run")
    # ---- init leg: constants + state zero, runs exactly once ----
    p.emit("MOVE", rd=R0, ra=0, imm=0)                # r0 = 0 convention
    e_const(p, RP, 1_000_000_000)
    p.emit("WRST", ra=RP, imm=RG_SCR | S_1E9, fmt=FMT_Q)
    e_const(p, RC, cid)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    e_const(p, RC, hdr8)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_HDR8, fmt=FMT_Q)
    e_const(p, RC, salo)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_SALO, fmt=FMT_Q)
    for s in (S_SYNCTS, S_OFFSET, S_PDELAY, S_T2, S_T1, S_T4, S_PEND,
              S_TICK, S_MYSEQ):
        p.emit("WRST", ra=0, imm=RG_SCR | s, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.label("run")
    p.emit("MOVE", rd=RT, ra=0, imm=1000)             # own cadence re-arm
    p.emit("WRST", ra=RT, imm=RG_TMR | 0, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_SCR | S_TICK, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_TICK, fmt=FMT_Q)
    # send Pdelay_Req unless an egress timestamp is still owed
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="send")
    p.emit("END")
    p.label("send")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)
    e_hdr(p, 0x2, 0x0000, RA, 0x00, 54)               # Pdelay_Req
    p.emit("BFLD", ra=0, fmt=FMT_Q)                   # 20 reserved bytes
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
    """r14 = A, r13 = B; writes 12 results to scratch 0..11 (tb/ucpu)."""
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


def build(mac):
    entries = [
        (16, prog_rx_sync), (64, prog_rx_followup), (128, prog_rx_announce),
        (192, prog_rx_pdreq), (256, prog_rx_pdresp), (320, prog_rx_pdrfu),
        (384, prog_rx_signal), (448, prog_tx_ts),
        (512, lambda b: prog_tmr(b, mac)), (768, prog_tb_battery),
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
    ap.add_argument("--mac", type=lambda s: int(s, 0), default=0x02A1B2C3D4E5,
                    help="station source MAC (48-bit)")
    args = ap.parse_args()
    rom, used = build(args.mac)
    with open(args.out, "w", encoding="ascii") as f:
        for word in rom:
            f.write(f"{word:012X}\n")
    print(f"{args.out}: {DEPTH} words, {used} real "
          f"({100.0 * used / DEPTH:.1f}%), mac {args.mac:012X}")


if __name__ == "__main__":
    main()
