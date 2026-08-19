#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""gPTP µcode ROM image generator -- v7, the cease-rule round.

The round that deliberately ends the zero-RTL era: the engine grows a
SECOND message bank (each accepted frame lands in the bank its event
names, retiring the torn-read window the v6 announce guard could only
narrow) and the scratch doubles to 64 words. On that room, the last
missing Milan v1.2 4.2.6 behavior lands:

  * The multiple-responder cease rule (4.2.6.2.5): a Pdelay_Req
    answered by responses from MORE THAN ONE clock identity, for three
    successive requests, stops Pdelay_Req transmission (the storm
    guard for daisy-chained non-AVB switches). Entering the cease
    clears asCapable and the ladder, and the pdelay COMPLETION path is
    gated too -- a forged or late exchange cannot climb the ladder
    while ceased. The resume is a CADENCE COUNTDOWN in scratch (the
    --cease-ms argument, 5 minutes by default, in 1 s cadence beats):
    scratch survives a warm reset and the engine's boot re-arms the
    cadence, so a reset during a cease still completes it -- a
    timer-armed resume would die with the reset and strand the cease
    until a bitstream reload (the review's stranded-cease finding).
    Duplicate responses from the SAME identity are not a storm.

--- v6, the full-compare round ---

v5 closed the loop; v6 completes the receive-side state machines of
802.1AS-2011 that the two-node bench let v3 defer:

  * Full BTCA (10.3.4/10.3.5): the plane keeps a BEST-VECTOR record
    {p1, cq, p2 | stepsRemoved+1, gmIdentity, sourcePortIdentity} --
    initialized to our own vector, replaced by any better announce,
    refreshed unconditionally by the CURRENT parent's announces (a
    parent update, including degradation). The compare is the spec's
    lexicographic order: priority vector, then grandmasterIdentity,
    then stepsRemoved (receiver-side +1), then sourcePortIdentity.
    After every processed announce our own vector contests the best:
    losing adopts (with the sync-ok verdict cleared ONLY on a GM
    change -- v5 cleared it on every parent refresh, a 1 Hz flicker
    this round retires), winning becomes master, and become resets
    the best record to ourselves.
  * Sync/Follow_Up pairing (11.4.4): the Follow_Up must match the
    pending Sync's sequenceId AND sourcePortIdentity, or it pairs with
    nothing. The source is held in the master-role slot 6 alias (a
    slave never runs the sync-TX builder), voided at adoption.
  * asCapable gates consumption (10.2.4.1): a fall while slave stops
    Sync/Follow_Up processing -- the servo no longer steers on a link
    whose delay verdict is dead. Pdelay keeps running; it is how the
    verdict is earned back.
  * The Sync originTimestamp carries the live PHC (11.4.3 approximate
    origin; GATH sel 0 -- the first functional consumer of phc_ns_i,
    which makes a mis-wired clock snapshot observable on the wire).

Identity scope: "sourcePortIdentity" in the pairing and the BTCA
tiebreak is the clockIdentity alone; the 16-bit portNumber (bank w3)
never joins a compare -- honest for single-port end stations, revisit
with any multi-port work.

Still deliberately out (the scratch-widen round that follows): the
multiple-responder cease rule of Milan 4.2.6.2.5, which needs more
per-interval state than the 32-word scratch has left, and the second
message bank in the engine that retires the torn-read window the
announce seq guard narrows.

--- v5, the servo round ---

v4 gave the plane its verdicts; v5 makes it act on them: the PHC servo
lands and observe-only retires. On every accepted Sync + Follow_Up as
slave, the measured offset drives the parent `timestamp_counter`'s two
knobs through the engine's PHC region:

  * |offset| > 20 us (the linuxptp first_step_threshold default):
    STEP -- one adjtime write of -offset re-bases the clock at once,
    and the addend is rewritten to the bare integrator: the rate
    estimate survives the step while the stale proportional term (moot
    after a re-base) is dropped. This is the DLL policy of the GM-loss
    design (the parent's GM_LOSS_RECOVERY.md): a running ptp4l slews a
    60 s cliff for 40 minutes; the fabric servo re-bases in one write.
  * otherwise: SLEW -- a PI controller in Q8.24 addend units. The loop
    gain is CLOCK-AWARE: the generator computes the ns-to-addend factor
    from --clk-hz (an addend unit is worth clk/8/2^24 ns of phase per
    125 ms sync interval), so kp = 3/4 and ki = 1/4 of the normalized
    gain hold at any clock and the closed loop is (z - 1/2)^2,
    critically damped. The integrator clamps at +-200 ppm so a
    pathological peer cannot wind it up.

The addend sign: offset is local minus master, so the correction is its
negation. A frequency-offset master converges to zero phase error (the
integrator carries the rate); the engine suite proves it closed-loop
against a +140 ppm master, deliberately above half the clamp.

--- v4, the asCapable round ---

v3 made the plane a bilateral BMCA participant and a transmitting
grandmaster; the bench interop round then listed what still separated it
from the 802.1AS state machines of record. v4 lands three of those as
ROM words on the same engine (zero RTL change):

  * The asCapable ladder (802.1AS-2011 10.2.4.1 with the Milan v1.2
    profile): asCapable rises after 2 successful Pdelay Resp + Resp_FU
    exchanges (Milan 4.2.6.2.4 bounds it in [2, 5]); it falls when the
    count of consecutive unanswered Pdelay_Reqs EXCEEDS
    allowedLostResponses = 3 (802.1AS-2011 11.2.12.4: at the fourth)
    or when the measured neighborPropDelay exceeds
    neighborPropDelayThresh = 800 ns (Milan 4.2.6.1.1, copper), with the
    Milan 4.2.6.2.7 floor: negative delays down to -80 ns do NOT clear
    it. asCapable is publish-flags bit 2, and it gates what the spec
    says it gates: Announce processing, the master TX cadences, and the
    become-master transition. Both Pdelay roles keep running regardless
    (they are how asCapable is EARNED back).
  * The receipt timeouts of Milan Table 4.2 beyond announce (v3):
    syncReceiptTimeout 375 ms (timer slot 4) clears the sync-ok verdict
    (flags bit 3, set on each completed Sync+Follow_Up as slave);
    followUpReceiptTimeout 125 ms (timer slot 5) invalidates a Sync
    whose Follow_Up never came, so a late Follow_Up is discarded
    instead of pairing with a stale ingress timestamp.
  * neighborRateRatio (802.1AS-2011 11.2.15.3, successive-response
    form): nrr = (t3_n - t3_prev) / (t4_n - t4_prev) as a Q2.30
    fixed-point ratio (OP_MULDIV earns its LUTs here), and the link
    delay becomes D = (nrr*(t4-t1) - (t3-t2)) / 2. Windows wider than
    2^32 ns (a silent peer) skip the update rather than divide stale.

Publish flags: bit0 gm_present, bit1 am_gm, bit2 asCapable, bit3
sync_ok. Every writer read-modify-writes so the verdicts compose.

Fixed entry table (mirrored by KL_gptp_engine): 16 SYNC · 64 FOLLOWUP ·
128 ANNOUNCE · 192 PDELAY_REQ · 256 PDELAY_RESP · 320 PDELAY_RESP_FU ·
384 SIGNALING · 448 TX_TS · 512 TIMER (slot 0 init+pdelay, 1 sync TX,
2 announce receipt, 3 announce TX, 4 sync receipt, 5 FU receipt) ·
704 TB battery. Shared legs are auto-packed into the free gaps by a
two-pass assembler (sizes first, then bases), so a leg outgrowing the
768.. tail is a solved problem instead of a manual repack.

Still deliberately out (each a later round): stepsRemoved tie-breaks
(two-node link), the multiple-responder cease rule of Milan 4.2.6.2.5,
and sourcePortIdentity matching on Sync.
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
# v6 reclaimed three write-only slots (the old S_OFFSET/S_AMGM/S_TICK:
# pub word 4 is the offset record, flags bit 1 is the role, the tick
# counter had no reader) for the BTCA best-vector record, and slot 6 is
# role-exclusive: sync-seq-in-flight while master, the pending Sync's
# sourcePortIdentity while slave (adopt clears it at the role change).
S_SYNCTS, S_HDR, S_BESTPV, S_BESTID = 0, 1, 2, 3
S_PDELAY, S_T2, S_SSEQFLY = 4, 5, 6
S_SYNCSRC = S_SSEQFLY                    # the slave-role alias
S_PDOK, S_PDLOST = 7, 8                  # asCapable ladder counters
S_FUORG = 9                              # 0xC2000001 (info-TLV org tail)
S_MYPV = 10                              # our {p1, cq, p2, 16'0} vector
S_PDGOT = 11                             # exchange seen since last req
S_NR3, S_NR4, S_NRR = 12, 13, 14         # nrr window + Q2.30 ratio
S_INTG = 15                              # servo integrator, addend units
S_T1, S_T4, S_PEND = 16, 17, 18
S_RQCID, S_BESTSRC, S_RQSEQ, S_RQPN, S_INIT, S_MYSEQ = 19, 20, 21, 22, 23, 24
S_CID, S_1E9, S_HDR8, S_SALO = 25, 26, 27, 28
S_SSEQ, S_ASEQ, S_ANNBODY = 29, 30, 31
# the widened half (the engine's 64-word scratch, v7)
S_RSP1, S_IVMULTI, S_MULTI, S_CEASE = 32, 33, 34, 35
S_CEASECNT = 36                          # cadence beats to resume
# S_BESTPV holds {p1, cq, p2} in [63:16] and stepsRemoved+1 in [15:0]
# (steps ranks BELOW the identity in 10.3.5, so it never joins the
# packed compare -- the pv compare masks the low 16 first)

# ---- our clock vector (Milan defaults) -------------------------------------
P1_C, P2_C = 248, 248
CQ_C = 0xF8FE436A               # class 248, accuracy 0xFE, variance 0x436A
UTC_OFF_C = 37

# ---- Milan v1.2 profile numbers --------------------------------------------
NPD_HI_C = 800                  # neighborPropDelayThresh ns, 4.2.6.1.1
NPD_LO_C = 80                   # negative-delay floor ns, 4.2.6.2.7
ASCAP_UP_C = 2                  # exchanges to asCapable, 4.2.6.2.4 in [2,5]
LOST_N_C = 3                    # allowedLostResponses, 802.1AS-2011 10.2.4.1
SYNC_RTO_MS_C = 375             # syncReceiptTimeout, Table 4.2
FU_RTO_MS_C = 125               # followUpReceiptTimeout, Table 4.2
CEASE_N_C = 3                   # successive multi-answered reqs, 4.2.6.2.5
CEASE_MS_C = 300_000            # resume after 5 min (--cease-ms overrides)
                                # counted down in 1 s cadence beats

# ---- servo constants (clock-aware, set by set_servo_gains) -----------------
STEP_NS_C = 20000               # linuxptp first_step_threshold default, ns
GAIN_S_C = 6                    # ns -> addend units: (off * GAIN_M) >> 6
GAIN_M_C = 86                   # for the 100 MHz default; see set_servo_gains
ILIM_C = 33554                  # integrator clamp = +-200 ppm at that clock


def set_servo_gains(clk_hz):
    """An addend unit adds 2^-24 ns per tick; one 125 ms sync interval is
    clk/8 ticks, so one unit is clk/8/2^24 ns of phase per interval. The
    PI shifts assume normalized gain, hence M/2^6 = 2^24/(clk/8)."""
    global GAIN_M_C, ILIM_C
    GAIN_M_C = round((1 << 24) * 64 * 8 / clk_hz)
    ILIM_C = round(200 * (1 << 24) * 1000 / clk_hz)
    assert 0 < GAIN_M_C < (1 << 24), GAIN_M_C
    assert 2 * ILIM_C + 1 < (1 << 24), ILIM_C

# publish flags bits
FL_PRESENT_C, FL_AMGM_C, FL_ASCAP_C, FL_SYNCOK_C = 1, 2, 4, 8

# ---- register conventions --------------------------------------------------
R0, RA, RB, RC, RD_, RT, RU, RSEC, RNS, RP = 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
RV, RW = 10, 11
REV, RTS0, RTS1 = 15, 14, 13

# shared-leg bases: filled by the packing pass, referenced through LB[]
LB = {}


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


def e_flags(p, andm=None, orm=None):
    """Read-modify-write the publish flags word (clobbers RT)."""
    p.emit("RDST", rd=RT, imm=RG_PUB | 2, fmt=FMT_Q)
    if andm is not None:
        p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_AND, imm=andm)
    if orm:
        p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_OR, imm=orm)
    p.emit("WRST", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)


def e_flag_gate(p, mask, want, tag, out_label):
    """Fall through when (flags & mask) == want, else branch out."""
    p.emit("RDST", rd=RT, imm=RG_PUB | 2, fmt=FMT_Q)
    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_AND, imm=mask)
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=want)
    p.emit("BRS", cnd=BRS_Z, label=f"fg_{tag}")
    p.emit("BR", label=out_label)
    p.label(f"fg_{tag}")


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
    # gate FIRST: a rogue Sync heard while master must not touch the
    # slot-6 alias (it holds OUR in-flight FU sequence in that role)
    e_flag_gate(p, FL_PRESENT_C | FL_AMGM_C | FL_ASCAP_C,
                FL_PRESENT_C | FL_ASCAP_C, "sl", "out")
    p.emit("WRST", ra=RTS0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_BANK | 0, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_HDR, fmt=FMT_Q)
    p.emit("RDST", rd=RA, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_SYNCSRC, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=FU_RTO_MS_C)
    p.emit("WRST", ra=RT, imm=RG_TMR | 5, fmt=FMT_Q)
    p.label("out")
    p.emit("END")
    return p


def prog_rx_followup(base):
    p = Prog(base)
    e_guard_init(p, "out")
    # an asCapable fall stops consumption: the servo must not steer on
    # a link whose delay verdict is dead (802.1AS-2011 10.2.4.1)
    e_flag_gate(p, FL_PRESENT_C | FL_AMGM_C | FL_ASCAP_C,
                FL_PRESENT_C | FL_ASCAP_C, "sl", "out")
    # a Sync must be pending and valid: the FU-receipt timeout zeroes it,
    # so a Follow_Up later than 125 ms pairs with nothing and is dropped
    p.emit("RDST", rd=RD_, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
    p.emit("CMP", ra=RD_, rb=0, fmt=FMT_Q, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="out")
    # 11.4.4 pairing: the FU must match the pending Sync's sequenceId
    # and sourcePortIdentity, or it pairs with nothing
    p.emit("RDST", rd=RT, imm=RG_SCR | S_HDR, fmt=FMT_Q)
    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("RDST", rd=RU, imm=RG_BANK | 0, fmt=FMT_Q)
    p.emit("ALU", rd=RU, ra=RU, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("ALU", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=0xFFFF)
    p.emit("CMP", ra=RT, rb=RU, fmt=FMT_W)
    p.emit("BRS", cnd=BRS_Z, label="srcck")
    p.emit("BR", label="out")
    p.label("srcck")
    p.emit("RDST", rd=RT, imm=RG_SCR | S_SYNCSRC, fmt=FMT_Q)
    p.emit("RDST", rd=RU, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("CMP", ra=RT, rb=RU, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="paired")
    p.emit("BR", label="out")
    p.label("paired")
    e_full_ts(p, RA)
    p.emit("RDST", rd=RB, imm=RG_BANK | 1, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RB, rb=0, cnd=ALU_SAR, imm=16)
    p.emit("ALU", rd=RA, ra=RA, rb=RB, cnd=ALU_ADD)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)
    p.emit("ALU", rd=RA, ra=RA, rb=RB, cnd=ALU_ADD)
    p.emit("ALU", rd=RA, ra=RD_, rb=RA, cnd=ALU_SUB)
    p.emit("WRST", ra=RA, imm=RG_PUB | 4, fmt=FMT_Q)
    p.emit("BR", label=LB["SERVO"])
    p.label("out")
    p.emit("END")
    return p


def prog_leg_servo(base):
    """Accepted Sync+FU as slave; RA = offset (local minus master).
    Step-vs-slew into the PHC region, then the receipt-timeout tail."""
    p = Prog(base)
    # ---- the servo: offset is local minus master, correction negates --
    # step when |offset| > 20 us, i.e. (offset + 20000) u> 40000
    p.emit("ALU", rd=RT, ra=RA, rb=0, cnd=ALU_ADD, imm=STEP_NS_C)
    p.emit("ALU", rd=RU, ra=RT, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("CMP", ra=RU, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="sv_lo")
    p.emit("BR", label="sv_step")
    p.label("sv_lo")
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=2 * STEP_NS_C + 1)
    p.emit("BRS", cnd=BRS_LT, label="sv_slew")
    p.label("sv_step")
    p.emit("ALU", rd=RB, ra=R0, rb=RA, cnd=ALU_SUB)          # -offset
    p.emit("WRST", ra=RB, imm=RG_PHC | 1, fmt=FMT_Q)         # adjtime
    # the rate estimate survives the step AND becomes the whole addend:
    # the re-base just made the stale proportional term moot
    p.emit("RDST", rd=RC, imm=RG_SCR | S_INTG, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=R0, rb=RC, cnd=ALU_SUB)
    p.emit("WRST", ra=RC, imm=RG_PHC | 0, fmt=FMT_Q)
    p.emit("BR", label="sv_done")
    p.label("sv_slew")
    p.emit("MOVE", rd=RB, ra=0, imm=GAIN_M_C)
    p.emit("MD", rd=RT, ra=RA, rb=RB, cnd=MD_MULS)           # off * M
    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_SAR, imm=GAIN_S_C)
    p.emit("ALU", rd=RB, ra=RT, rb=0, cnd=ALU_SAR, imm=2)    # ki term
    p.emit("RDST", rd=RC, imm=RG_SCR | S_INTG, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=RC, rb=RB, cnd=ALU_ADD)
    # clamp the integrator to +-ILIM: (I + ILIM) u<= 2*ILIM
    p.emit("MOVE", rd=RU, ra=0, imm=ILIM_C)
    p.emit("ALU", rd=RB, ra=RC, rb=RU, cnd=ALU_ADD)
    p.emit("ALU", rd=RW, ra=RB, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("CMP", ra=RW, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="sv_cl")
    p.emit("BR", label="sv_sat")
    p.label("sv_cl")
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=2 * ILIM_C + 1)
    p.emit("BRS", cnd=BRS_LT, label="sv_iok")
    p.label("sv_sat")
    p.emit("ALU", rd=RW, ra=RC, rb=0, cnd=ALU_SHR, imm=63)
    p.emit("CMP", ra=RW, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="sv_neg")
    p.emit("MOVE", rd=RC, ra=0, imm=ILIM_C)
    p.emit("BR", label="sv_iok")
    p.label("sv_neg")
    p.emit("ALU", rd=RC, ra=R0, rb=RU, cnd=ALU_SUB)          # -ILIM
    p.label("sv_iok")
    p.emit("WRST", ra=RC, imm=RG_SCR | S_INTG, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RT, rb=0, cnd=ALU_SAR, imm=2)
    p.emit("ALU", rd=RT, ra=RT, rb=RB, cnd=ALU_SUB)          # kp = 3/4
    p.emit("ALU", rd=RT, ra=RT, rb=RC, cnd=ALU_ADD)          # + I
    p.emit("ALU", rd=RT, ra=R0, rb=RT, cnd=ALU_SUB)          # negate
    p.emit("WRST", ra=RT, imm=RG_PHC | 0, fmt=FMT_Q)         # adjfine
    p.label("sv_done")
    p.emit("WRST", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)   # consumed
    p.emit("MOVE", rd=RT, ra=0, imm=SYNC_RTO_MS_C)
    p.emit("WRST", ra=RT, imm=RG_TMR | 4, fmt=FMT_Q)         # sync watch
    p.emit("WRST", ra=0, imm=RG_TMR | 5, fmt=FMT_Q)          # FU watch off
    e_flags(p, orm=FL_SYNCOK_C)
    p.emit("COMMIT")
    p.emit("END")
    return p


def prog_rx_announce(base):
    p = Prog(base)
    e_guard_init(p, "out")
    # 802.1AS: a port that is not asCapable does not enter the contest
    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, "ac", "out")
    p.emit("RDST", rd=RA, imm=RG_BANK | 8, fmt=FMT_Q)   # their {utc,p1,cq,p2}
    p.emit("WRST", ra=RA, imm=RG_PUB | 5, fmt=FMT_Q)    # publish raw: bench
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_SHL, imm=16)  # {p1,cq,p2,0}
    p.emit("RDST", rd=RB, imm=RG_BANK | 9, fmt=FMT_Q)   # their gm identity
    # snapshot the rest of the announce NOW: the single message bank
    # belongs to the NEXT frame the moment it arrives, and this handler
    # is long (the deferred double-bank engine revision retires this)
    p.emit("RDST", rd=RC, imm=RG_BANK | 10, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=RC, rb=0, cnd=ALU_SHR, imm=48)
    p.emit("ALU", rd=RC, ra=RC, rb=0, cnd=ALU_ADD, imm=1)  # steps+1
    p.emit("ALU", rd=RC, ra=RC, rb=0, cnd=ALU_AND, imm=0xFFFF)
    p.emit("RDST", rd=RD_, imm=RG_BANK | 2, fmt=FMT_Q)     # their source
    # the snapshot closes by proving the bank still belongs to THIS
    # event: a delayed dispatch behind a busy handler would otherwise
    # read the NEXT frame and hand its source a parent-update take
    # (the wrongful-takeover race). The event word carries the seq;
    # a mismatch drops the announce -- the 1 Hz cadence resends. The
    # ~6-tick torn window between the bank's src and seq writes stands
    # until the second message bank lands in the engine.
    p.emit("RDST", rd=RT, imm=RG_BANK | 0, fmt=FMT_Q)
    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_AND, imm=0xFFFF)
    p.emit("ALU", rd=RU, ra=REV, rb=0, cnd=ALU_SHR, imm=16)
    p.emit("ALU", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=0xFFFF)
    p.emit("CMP", ra=RT, rb=RU, fmt=FMT_W)
    p.emit("BRS", cnd=BRS_Z, label="mine")
    p.emit("BR", label="out")
    p.label("mine")
    p.emit("BR", label=LB["BTCA"])
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
    # 4.2.6.2.5 bookkeeping: a SECOND distinct responder identity in
    # one request interval marks it multi (duplicates are not a storm)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_RSP1, fmt=FMT_Q)
    p.emit("RDST", rd=RC, imm=RG_BANK | 2, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_Q, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="rsp1")
    p.emit("CMP", ra=RB, rb=RC, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="out")
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_IVMULTI, fmt=FMT_Q)
    p.emit("BR", label="out")
    p.label("rsp1")
    p.emit("WRST", ra=RC, imm=RG_SCR | S_RSP1, fmt=FMT_Q)
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
    e_full_ts(p, RC)                                    # RC = t3
    p.emit("BR", label=LB["PDPOST"])
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
    p.emit("BRS", cnd=BRS_Z, label=LB["RFU"])
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=3)
    p.emit("BRS", cnd=BRS_Z, label=LB["SYNCFU"])
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
    p.emit("BRS", cnd=BRS_Z, label=LB["SYNCTX"])
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=2)
    p.emit("BRS", cnd=BRS_Z, label=LB["BECGATE"])
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=3)
    p.emit("BRS", cnd=BRS_Z, label=LB["ANNTX"])
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=4)
    p.emit("BRS", cnd=BRS_Z, label=LB["SRTO"])
    p.emit("CMP", ra=REV, rb=0, fmt=FMT_W, imm=5)
    p.emit("BRS", cnd=BRS_Z, label=LB["FUTO"])
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
    p.emit("WRST", ra=RC, imm=RG_SCR | S_BESTID, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)
    e_const(p, RC, hdr8)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_HDR8, fmt=FMT_Q)
    e_const(p, RC, salo)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_SALO, fmt=FMT_Q)
    e_const(p, RC, mypv)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_MYPV, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)  # steps 0: us
    e_const(p, RC, annbody)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_ANNBODY, fmt=FMT_Q)
    e_const(p, RC, 0xC2000001)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_FUORG, fmt=FMT_Q)
    for s in (S_SYNCTS, S_PDELAY, S_T2, S_SSEQFLY,
              S_PDOK, S_PDLOST, S_PDGOT, S_NR3, S_NR4, S_NRR, S_INTG,
              S_T1, S_T4, S_PEND, S_MYSEQ, S_SSEQ, S_ASEQ,
              S_RSP1, S_IVMULTI, S_MULTI, S_CEASE, S_CEASECNT):
        p.emit("WRST", ra=0, imm=RG_SCR | s, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_INIT, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=3000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)   # announce receipt
    p.label("cadence")
    p.emit("MOVE", rd=RT, ra=0, imm=1000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 0, fmt=FMT_Q)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="send")
    p.emit("END")
    p.label("send")
    # ---- the cease rule (Milan 4.2.6.2.5): while ceased, no requests
    p.emit("RDST", rd=RA, imm=RG_SCR | S_CEASE, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="quiet")
    p.emit("BR", label="storm_ck")
    p.label("quiet")
    # the countdown to resume: reset-proof (scratch survives, the boot
    # re-arms this cadence), one beat per second
    p.emit("RDST", rd=RB, imm=RG_SCR | S_CEASECNT, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RB, rb=0, cnd=ALU_SUB, imm=1)
    p.emit("WRST", ra=RB, imm=RG_SCR | S_CEASECNT, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="resume")
    p.emit("END")
    p.label("resume")
    p.emit("BR", label=LB["RESUME"])
    p.label("storm_ck")
    p.emit("RDST", rd=RB, imm=RG_SCR | S_IVMULTI, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=1)
    p.emit("BRS", cnd=BRS_Z, label="was_multi")
    p.emit("WRST", ra=0, imm=RG_SCR | S_MULTI, fmt=FMT_Q)   # streak over
    p.emit("BR", label="iv_clear")
    p.label("was_multi")
    p.emit("RDST", rd=RC, imm=RG_SCR | S_MULTI, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=RC, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_MULTI, fmt=FMT_Q)
    p.emit("CMP", ra=RC, rb=0, fmt=FMT_D, imm=CEASE_N_C)
    p.emit("BRS", cnd=BRS_LT, label="iv_clear")
    # cease: stop requesting, drop the verdict, load the countdown
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_CEASE, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=max(1, CEASE_MS_C // 1000))
    p.emit("WRST", ra=RT, imm=RG_SCR | S_CEASECNT, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDOK, fmt=FMT_Q)
    e_flags(p, andm=FL_PRESENT_C | FL_AMGM_C | FL_SYNCOK_C)
    p.emit("COMMIT")
    p.emit("WRST", ra=0, imm=RG_SCR | S_IVMULTI, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_RSP1, fmt=FMT_Q)
    p.emit("END")
    p.label("iv_clear")
    p.emit("WRST", ra=0, imm=RG_SCR | S_IVMULTI, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_RSP1, fmt=FMT_Q)
    # ---- lost-response accounting (802.1AS-2011 10.2.4.1): before each
    # new request, judge the last one; skip until a first was ever sent
    p.emit("RDST", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="pd_go")
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PDGOT, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="pd_lost")
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDLOST, fmt=FMT_Q)
    p.emit("BR", label="pd_go")
    p.label("pd_lost")
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PDLOST, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RB, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RB, imm=RG_SCR | S_PDLOST, fmt=FMT_Q)
    # 802.1AS-2011 11.2.12.4: the verdict falls when the count EXCEEDS
    # allowedLostResponses -- at the fourth, not the third
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=LOST_N_C + 1)
    p.emit("BRS", cnd=BRS_LT, label="pd_go")
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDOK, fmt=FMT_Q)
    e_flags(p, andm=FL_PRESENT_C | FL_AMGM_C | FL_SYNCOK_C)
    p.emit("COMMIT")
    p.label("pd_go")
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDGOT, fmt=FMT_Q)
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


# ---- shared legs (auto-packed) ---------------------------------------------

def prog_btca(base):
    """RA = their {p1,cq,p2,16'0}, RB = their gmId; the bank still holds
    the announce. 10.3.4/10.3.5: a parent update replaces the best
    unconditionally; anything else must beat it lexicographically --
    pv, then gmId, then stepsRemoved(+1), then sourcePortIdentity.
    Afterwards our own vector contests whatever the best now is."""
    p = Prog(base)
    p.emit("RDST", rd=RT, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)
    p.emit("CMP", ra=RD_, rb=RT, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="take")                 # parent update
    p.emit("RDST", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)
    p.emit("ALU", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=16)
    p.emit("ALU", rd=RV, ra=RV, rb=0, cnd=ALU_SHL, imm=16)  # steps out
    p.emit("RDST", rd=RW, imm=RG_SCR | S_BESTID, fmt=FMT_Q)
    e_ult64(p, RA, RV, "take", "ours", "pv")
    e_ult64(p, RB, RW, "take", "ours", "id")
    p.emit("RDST", rd=RU, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)
    p.emit("ALU", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=0xFFFF)
    p.emit("CMP", ra=RC, rb=RU, fmt=FMT_W)                 # steps low16
    p.emit("BRS", cnd=BRS_LT, label="take")
    p.emit("BRS", cnd=BRS_Z, label="srctie")
    p.emit("BR", label="ours")
    p.label("srctie")
    # NEVER hand RT/RU to e_ult64: they are its scratch registers
    p.emit("RDST", rd=RW, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)
    e_ult64(p, RD_, RW, "take", "ours", "sp")
    p.emit("BR", label="take")                             # identical
    p.label("take")
    p.emit("ALU", rd=RU, ra=RA, rb=RC, cnd=ALU_OR)         # pv | steps
    p.emit("WRST", ra=RU, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)
    p.emit("WRST", ra=RB, imm=RG_SCR | S_BESTID, fmt=FMT_Q)
    p.emit("WRST", ra=RD_, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)
    p.label("ours")
    # the contest: {mypv, our cid, steps 0} vs the (updated) best
    p.emit("RDST", rd=RA, imm=RG_SCR | S_MYPV, fmt=FMT_Q)
    p.emit("RDST", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)
    p.emit("ALU", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=16)
    p.emit("ALU", rd=RV, ra=RV, rb=0, cnd=ALU_SHL, imm=16)
    p.emit("RDST", rd=RB, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("RDST", rd=RW, imm=RG_SCR | S_BESTID, fmt=FMT_Q)
    e_ult64(p, RA, RV, "we_win", "they_win", "opv")
    e_ult64(p, RB, RW, "we_win", "they_win", "oid")
    p.emit("RDST", rd=RU, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)
    p.emit("CMP", ra=RU, rb=0, fmt=FMT_W, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="we_win")     # stored steps 0 = us
    p.label("they_win")
    p.emit("RDST", rd=RC, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_PUB | 1, fmt=FMT_Q)       # parent
    p.emit("RDST", rd=RT, imm=RG_PUB | 0, fmt=FMT_Q)
    p.emit("CMP", ra=RT, rb=RW, fmt=FMT_Q)
    p.emit("BRS", cnd=BRS_Z, label="same_gm")
    # a GM change is the full adoption; a refresh must NOT clear the
    # sync-ok verdict (v5 flickered it at the parent's announce rate)
    p.emit("WRST", ra=RW, imm=RG_PUB | 0, fmt=FMT_Q)
    e_flags(p, andm=FL_ASCAP_C, orm=FL_PRESENT_C)
    p.emit("WRST", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_SYNCSRC, fmt=FMT_Q)
    p.emit("RDST", rd=RT, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=3)
    p.emit("BRS", cnd=BRS_Z, label="vfu")
    p.emit("BR", label="pk")
    p.label("vfu")
    p.emit("WRST", ra=0, imm=RG_SCR | S_PEND, fmt=FMT_Q)   # FU build void
    p.label("pk")
    p.emit("WRST", ra=0, imm=RG_TMR | 1, fmt=FMT_Q)        # sync TX off
    p.emit("WRST", ra=0, imm=RG_TMR | 3, fmt=FMT_Q)        # ann TX off
    p.label("same_gm")
    p.emit("MOVE", rd=RT, ra=0, imm=3000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)       # receipt watch
    p.emit("COMMIT")
    p.emit("END")
    p.label("we_win")
    e_flag_gate(p, FL_AMGM_C, 0, "nm", "held")             # already GM?
    p.emit("BR", label=LB["BECOME"])
    p.label("held")
    p.emit("END")
    return p


def prog_becgate(base):
    """Announce receipt expiry: only an asCapable port may become master."""
    p = Prog(base)
    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, "bg", "held")
    p.emit("BR", label=LB["BECOME"])
    p.label("held")
    p.emit("MOVE", rd=RT, ra=0, imm=3000)
    p.emit("WRST", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)  # keep watching
    p.emit("END")
    return p


def prog_become(base):
    p = Prog(base)
    p.emit("RDST", rd=RC, imm=RG_SCR | S_CID, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_PUB | 0, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_PUB | 1, fmt=FMT_Q)
    # the best-vector record returns to ourselves: a dead parent's
    # claim expires with the receipt timeout that brought us here
    p.emit("RDST", rd=RT, imm=RG_SCR | S_MYPV, fmt=FMT_Q)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_BESTID, fmt=FMT_Q)
    p.emit("WRST", ra=RC, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)
    e_flags(p, andm=FL_ASCAP_C, orm=FL_PRESENT_C | FL_AMGM_C)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_TMR | 1, fmt=FMT_Q)  # sync now
    p.emit("MOVE", rd=RT, ra=0, imm=2)
    p.emit("WRST", ra=RT, imm=RG_TMR | 3, fmt=FMT_Q)  # announce now
    p.emit("WRST", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch
    p.emit("WRST", ra=0, imm=RG_TMR | 4, fmt=FMT_Q)   # a master expects
    p.emit("WRST", ra=0, imm=RG_TMR | 5, fmt=FMT_Q)   #   no sync
    p.emit("COMMIT")
    p.emit("END")
    return p


def prog_leg_pdpost(base):
    """Pdelay exchange complete; RC = t3. neighborRateRatio, corrected
    link delay, the threshold verdict and the asCapable ladder."""
    p = Prog(base)
    # ceased: no exchange may climb the ladder (a forged or straggling
    # response pair must not re-raise asCapable mid-cease)
    p.emit("RDST", rd=RT, imm=RG_SCR | S_CEASE, fmt=FMT_Q)
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="live")
    p.emit("END")
    p.label("live")
    p.emit("RDST", rd=RD_, imm=RG_SCR | S_T4, fmt=FMT_Q)
    # ---- nrr window (802.1AS-2011 11.2.15.3) ----
    p.emit("RDST", rd=RA, imm=RG_SCR | S_NR3, fmt=FMT_Q)
    p.emit("CMP", ra=RA, rb=0, fmt=FMT_Q, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="save")           # first exchange
    p.emit("ALU", rd=RA, ra=RC, rb=RA, cnd=ALU_SUB)  # num = t3 - prev3
    p.emit("RDST", rd=RB, imm=RG_SCR | S_NR4, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RD_, rb=RB, cnd=ALU_SUB)  # den = t4 - prev4
    p.emit("ALU", rd=RT, ra=RB, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="den32")
    p.emit("BR", label="save")                       # stale window: skip
    p.label("den32")
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="save")           # zero window
    p.emit("ALU", rd=RA, ra=RA, rb=0, cnd=ALU_SHL, imm=30)
    p.emit("MD", rd=RV, ra=RA, rb=RB, cnd=MD_DIVU)   # Q2.30 ratio
    p.emit("WRST", ra=RV, imm=RG_SCR | S_NRR, fmt=FMT_Q)
    p.label("save")
    p.emit("WRST", ra=RC, imm=RG_SCR | S_NR3, fmt=FMT_Q)
    p.emit("WRST", ra=RD_, imm=RG_SCR | S_NR4, fmt=FMT_Q)
    # ---- corrected D = (nrr*(t4-t1) - (t3-t2)) / 2 ----
    p.emit("RDST", rd=RB, imm=RG_SCR | S_T1, fmt=FMT_Q)
    p.emit("ALU", rd=RB, ra=RD_, rb=RB, cnd=ALU_SUB)  # turn = t4 - t1
    p.emit("RDST", rd=RV, imm=RG_SCR | S_NRR, fmt=FMT_Q)
    p.emit("CMP", ra=RV, rb=0, fmt=FMT_Q, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="uncorr")         # no ratio yet
    p.emit("MD", rd=RB, ra=RV, rb=RB, cnd=MD_MULS)
    p.emit("ALU", rd=RB, ra=RB, rb=0, cnd=ALU_SHR, imm=30)
    p.label("uncorr")
    p.emit("RDST", rd=RT, imm=RG_SCR | S_T2, fmt=FMT_Q)
    p.emit("ALU", rd=RC, ra=RC, rb=RT, cnd=ALU_SUB)  # resid = t3 - t2
    p.emit("ALU", rd=RD_, ra=RB, rb=RC, cnd=ALU_SUB)
    p.emit("ALU", rd=RD_, ra=RD_, rb=0, cnd=ALU_SAR, imm=1)
    p.emit("WRST", ra=RD_, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)
    p.emit("WRST", ra=RD_, imm=RG_PUB | 3, fmt=FMT_Q)
    # ---- verdict: good iff -80 <= D <= 800, i.e. (D + 80) u<= 880 ----
    p.emit("ALU", rd=RT, ra=RD_, rb=0, cnd=ALU_ADD, imm=NPD_LO_C)
    p.emit("ALU", rd=RU, ra=RT, rb=0, cnd=ALU_SHR, imm=32)
    p.emit("CMP", ra=RU, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="lowck")
    p.emit("BR", label="bad")
    p.label("lowck")
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=NPD_HI_C + NPD_LO_C + 1)
    p.emit("BRS", cnd=BRS_LT, label="good")
    p.emit("BR", label="bad")
    p.label("good")
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PDGOT, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDLOST, fmt=FMT_Q)
    p.emit("RDST", rd=RT, imm=RG_SCR | S_PDOK, fmt=FMT_Q)
    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_ADD, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PDOK, fmt=FMT_Q)
    p.emit("CMP", ra=RT, rb=0, fmt=FMT_D, imm=ASCAP_UP_C)
    p.emit("BRS", cnd=BRS_LT, label="done")          # Milan: not before 2
    e_flags(p, orm=FL_ASCAP_C)
    p.emit("BR", label="done")
    p.label("bad")
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PDGOT, fmt=FMT_Q)  # it DID answer
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDOK, fmt=FMT_Q)
    e_flags(p, andm=FL_PRESENT_C | FL_AMGM_C | FL_SYNCOK_C)
    p.label("done")
    p.emit("COMMIT")
    p.emit("END")
    return p


def prog_leg_resume(base):
    """The cease countdown reached zero: requests resume; asCapable
    re-earns through the ladder as ever (PDGOT set: no phantom lost)."""
    p = Prog(base)
    p.emit("WRST", ra=0, imm=RG_SCR | S_CEASE, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_MULTI, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_IVMULTI, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_RSP1, fmt=FMT_Q)
    p.emit("WRST", ra=0, imm=RG_SCR | S_PDLOST, fmt=FMT_Q)
    p.emit("MOVE", rd=RT, ra=0, imm=1)
    p.emit("WRST", ra=RT, imm=RG_SCR | S_PDGOT, fmt=FMT_Q)
    p.emit("END")
    return p


def prog_leg_srto(base):
    """Sync receipt timeout (375 ms): the sync-ok verdict falls."""
    p = Prog(base)
    e_flags(p, andm=FL_PRESENT_C | FL_AMGM_C | FL_ASCAP_C)
    p.emit("COMMIT")
    p.emit("END")
    return p


def prog_leg_futo(base):
    """Follow_Up receipt timeout (125 ms): the pending Sync is void."""
    p = Prog(base)
    p.emit("WRST", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)
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
    e_flag_gate(p, FL_AMGM_C, FL_AMGM_C, "gm", "skip")
    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, "ac", "skip")
    p.emit("RDST", rd=RB, imm=RG_SCR | S_PEND, fmt=FMT_Q)
    p.emit("CMP", ra=RB, rb=0, fmt=FMT_D, imm=0)
    p.emit("BRS", cnd=BRS_Z, label="build")
    p.label("skip")
    p.emit("END")                                    # skip this beat
    p.label("build")
    p.emit("RDST", rd=RA, imm=RG_SCR | S_SSEQ, fmt=FMT_Q)
    p.emit("WRST", ra=RA, imm=RG_SCR | S_SSEQFLY, fmt=FMT_Q)
    e_hdr(p, 0x0, 0x0208, RA, 0xFD, 44)
    # 11.4.3: the two-step Sync's originTimestamp is the approximate
    # egress time -- the live PHC via gather sel 0 (the first
    # functional consumer of phc_ns_i)
    p.emit("GATH", rd=RB, imm=0)
    e_ts_fields(p, RB)
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
    e_flag_gate(p, FL_AMGM_C, FL_AMGM_C, "gm", "skip")
    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, "ac", "skip")
    p.emit("BR", label="go")
    p.label("skip")
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


# ---- build: fixed entries + auto-packed shared legs ------------------------

LEG_FNS = [
    ("BTCA", prog_btca), ("BECOME", prog_become), ("BECGATE", prog_becgate),
    ("RFU", prog_leg_rfu), ("SYNCFU", prog_leg_syncfu),
    ("SYNCTX", prog_leg_synctx), ("ANNTX", prog_leg_anntx),
    ("PDPOST", prog_leg_pdpost), ("SRTO", prog_leg_srto),
    ("FUTO", prog_leg_futo), ("SERVO", prog_leg_servo),
    ("RESUME", prog_leg_resume),
]


def build(mac):
    fixed = [
        (16, prog_rx_sync), (64, prog_rx_followup), (128, prog_rx_announce),
        (192, prog_rx_pdreq), (256, prog_rx_pdresp), (320, prog_rx_pdrfu),
        (384, prog_rx_signal), (448, prog_tx_ts),
        (512, lambda b: prog_tmr(b, mac)), (704, prog_tb_battery),
    ]

    # pass 1: measure (word counts are independent of branch targets)
    for name, _ in LEG_FNS:
        LB[name] = 0
    fixed_sz = [(b, len(fn(b).words())) for b, fn in fixed]
    leg_sz = [(name, len(fn(0).words())) for name, fn in LEG_FNS]

    # a fixed program must not run into the next fixed entry
    fbases = sorted(b for b, _ in fixed) + [DEPTH]
    for b, sz in fixed_sz:
        nxt = min(x for x in fbases if x > b)
        assert b + sz <= nxt, f"fixed {b} is {sz} words, next entry {nxt}"

    # free gaps between fixed programs (µPC 0..15 stays clear)
    gaps = []
    prev_end = 16
    for b, sz in sorted(fixed_sz):
        if b > prev_end:
            gaps.append([prev_end, b])
        prev_end = b + sz
    if prev_end < DEPTH:
        gaps.append([prev_end, DEPTH])

    # first-fit decreasing; every leg must land
    for name, sz in sorted(leg_sz, key=lambda x: -x[1]):
        for g in gaps:
            if g[1] - g[0] >= sz:
                LB[name] = g[0]
                g[0] += sz
                break
        else:
            raise AssertionError(f"leg {name} ({sz} words) does not fit")

    # pass 2: emit with real bases
    rom = [None] * DEPTH
    used = 0
    progs = fixed + [(LB[name], fn) for name, fn in LEG_FNS]
    for base, fn in progs:
        words = fn(base).words()
        for i, word in enumerate(words):
            assert rom[base + i] is None, f"overlap at {base + i}"
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
    ap.add_argument("--clk-hz", type=int, default=100_000_000,
                    help="engine clock; sets the servo's ns-to-addend gain")
    ap.add_argument("--cease-ms", type=int, default=300_000,
                    help="cease-rule resume delay (Milan: 5 minutes)")
    args = ap.parse_args()
    global CEASE_MS_C
    CEASE_MS_C = args.cease_ms
    assert 0 < CEASE_MS_C < (1 << 24), CEASE_MS_C
    global P1_C
    P1_C = args.p1
    set_servo_gains(args.clk_hz)
    rom, used = build(args.mac)
    with open(args.out, "w", encoding="ascii") as f:
        for word in rom:
            f.write(f"{word:012X}\n")
    legs = " ".join(f"{n}@{LB[n]}" for n, _ in LEG_FNS)
    print(f"{args.out}: {DEPTH} words, {used} real "
          f"({100.0 * used / DEPTH:.1f}%), mac {args.mac:012X}")
    print(f"legs: {legs}")


if __name__ == "__main__":
    main()
