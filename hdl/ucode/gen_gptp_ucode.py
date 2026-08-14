#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""gPTP µcode ROM image generator.

Emits 1024 lines of 12 hex digits for KL_gptp_ucpu's $readmemh. Entry
points are fixed and mirrored by KL_gptp_engine's dispatch table:

    16   EV_RX_SYNC       two-step sync receive: latch ingress ts + header
    64   EV_RX_FOLLOWUP   offset = local - (origin + correction + pdelay),
                          first-cut P servo -> PHC rate addend
    128  EV_RX_ANNOUNCE   first-cut master adopt: publish GM + parent,
                          re-arm the announce receipt timeout
    192  EV_RX_PDREQ      build + send a Pdelay_Resp skeleton (exercises
                          the full build path incl. ns -> sec/ns DIVU)
    256  EV_RX_PDRESP     latch t2/t4 leg
    320  EV_RX_PDRFU      meanLinkDelay = ((t4-t1)-(t3-t2))/2 -> publish
    384  EV_RX_SIGNAL     accept and end
    448  EV_TX_TS         latch egress timestamp (t1/t3 capture)
    512  EV_TMR           cadence bookkeeping + self re-arm
    768  TB battery       arithmetic battery used by tb/verilator/ucpu

Every handler is a REAL first cut, not a placeholder: together they use
ADD/SUB/AND/OR/XOR/SHL/SHR/SAR, MULS, DIVU, so no arithmetic datapath can
constant-fold out of the OOC synthesis. Unused ROM words carry a
deterministic non-degenerate fill (splitmix64 masked to 48 bits) for the
same reason, the base generator's rule.

Handlers are the resource skeleton's semantics, not the 802.1AS state
machines of record — BTCA, asCapable and the receipt-timeout ladder land
as µcode revisions on this same ROM.
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

# state-port regions (KL_gptp_engine)
RG_BANK, RG_TS, RG_SCR, RG_PUB, RG_PHC, RG_TMR = (
    0x00000, 0x10000, 0x20000, 0x30000, 0x40000, 0x50000)


def w(op, rd=0, ra=0, rb=0, fmt=0, cnd=0, imm=0):
    assert 0 <= imm < (1 << 24), hex(imm)
    return ((OPS[op] << 43) | (rd << 39) | (ra << 35) | (rb << 31) |
            (fmt << 28) | (cnd << 24) | imm)


def splitmix48(i):
    z = (i + 0x9E3779B97F4A7C15) & ((1 << 64) - 1)
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & ((1 << 64) - 1)
    return (z ^ (z >> 31)) & WMASK


# ---- handlers --------------------------------------------------------------
# dispatch preloads: r15 = {code, seq, aux}, r14 = ts0, r13 = ts1

def prog_rx_sync():
    return [
        w("RDST", rd=1, imm=RG_BANK | 0, fmt=FMT_Q),      # header word
        w("WRST", ra=14, imm=RG_SCR | 0, fmt=FMT_Q),      # sync ingress ts
        w("WRST", ra=1, imm=RG_SCR | 1, fmt=FMT_Q),       # header snapshot
        w("END"),
    ]


def prog_rx_followup():
    return [
        w("RDST", rd=1, imm=RG_BANK | 5, fmt=FMT_Q),      # origin ns
        w("RDST", rd=2, imm=RG_BANK | 1, fmt=FMT_Q),      # correctionField
        w("ALU", rd=2, ra=2, cnd=ALU_SHR, imm=16),        # scaled-ns -> ns
        w("ALU", rd=3, ra=1, rb=2, cnd=ALU_ADD),          # origin + corr
        w("RDST", rd=4, imm=RG_SCR | 0, fmt=FMT_Q),       # sync ingress ts
        w("RDST", rd=5, imm=RG_SCR | 4, fmt=FMT_Q),       # meanLinkDelay
        w("ALU", rd=3, ra=3, rb=5, cnd=ALU_ADD),          # gm @ ingress
        w("ALU", rd=6, ra=4, rb=3, cnd=ALU_SUB),          # offset
        w("WRST", ra=6, imm=RG_SCR | 2, fmt=FMT_Q),
        w("MOVE", rd=8, imm=205),                         # Kp (Q8-ish)
        w("MD", rd=7, ra=6, rb=8, cnd=MD_MULS),           # P term
        w("ALU", rd=7, ra=7, cnd=ALU_SAR, imm=8),
        w("WRST", ra=7, imm=RG_PHC | 0, fmt=FMT_D),       # rate addend
        w("COMMIT"),
        w("END"),
    ]


def prog_rx_announce():
    return [
        w("RDST", rd=1, imm=RG_BANK | 8, fmt=FMT_Q),      # priority vector
        w("WRST", ra=1, imm=RG_SCR | 8, fmt=FMT_Q),
        w("RDST", rd=2, imm=RG_BANK | 9, fmt=FMT_Q),      # gm identity
        w("WRST", ra=2, imm=RG_PUB | 0, fmt=FMT_Q),
        w("RDST", rd=3, imm=RG_BANK | 2, fmt=FMT_Q),      # parent clock id
        w("WRST", ra=3, imm=RG_PUB | 1, fmt=FMT_Q),
        w("MOVE", rd=4, imm=3000),                        # announce timeout
        w("WRST", ra=4, imm=RG_TMR | 2, fmt=FMT_D),
        w("COMMIT"),
        w("END"),
    ]


def prog_rx_pdreq():
    # Pdelay_Resp skeleton build: eth header + PTP header + t2 as sec/ns.
    # Exercises SET_LENGTH, BUILD_FLD B/W/D/Q, SHL, DIVU, MULS, SUB, SEND.
    p = [
        w("MOVE", rd=0, imm=0),                           # r0 = 0 convention
        w("SETL", imm=68),                                # 14 + 54
        w("MOVE", rd=1, imm=0x0180C2),
        w("ALU", rd=1, ra=1, cnd=ALU_SHL, imm=24),
        w("MOVE", rd=2, imm=0x00000E),
        w("ALU", rd=1, ra=1, rb=2, cnd=ALU_OR),           # DA 01-80-C2-..-0E
        w("ALU", rd=1, ra=1, cnd=ALU_SHL, imm=16),
        w("BFLD", ra=1, fmt=FMT_Q),                       # DA + SA[47:32]=0
        w("BFLD", ra=0, fmt=FMT_D),                       # SA[31:0] = 0
        w("MOVE", rd=3, imm=0x88F7),
        w("BFLD", ra=3, fmt=FMT_W),                       # EtherType
        w("MOVE", rd=4, imm=0x13),
        w("BFLD", ra=4, fmt=FMT_B),                       # ts=1, type=3
        w("MOVE", rd=4, imm=0x02),
        w("BFLD", ra=4, fmt=FMT_B),                       # version 2
        w("MOVE", rd=4, imm=54),
        w("BFLD", ra=4, fmt=FMT_W),                       # messageLength
        w("BFLD", ra=0, fmt=FMT_W),                       # domain + reserved
        w("BFLD", ra=0, fmt=FMT_W),                       # flags
        w("BFLD", ra=0, fmt=FMT_Q),                       # correctionField
        w("BFLD", ra=0, fmt=FMT_D),                       # reserved
        w("BFLD", ra=0, fmt=FMT_Q),                       # srcPortIdentity
        w("BFLD", ra=0, fmt=FMT_W),                       #   .portNumber
        w("RDST", rd=5, imm=RG_BANK | 0, fmt=FMT_Q),      # echo sequenceId
        w("BFLD", ra=5, fmt=FMT_W),                       #  (low 16 of w0…)
        w("MOVE", rd=4, imm=0x05),
        w("BFLD", ra=4, fmt=FMT_B),                       # control
        w("MOVE", rd=4, imm=0x7F),
        w("BFLD", ra=4, fmt=FMT_B),                       # logMessageInterval
        # t2 = r14 (ingress ns) -> 48-bit seconds + 32-bit ns
        w("MOVE", rd=6, imm=0x3B9ACA),
        w("ALU", rd=6, ra=6, cnd=ALU_SHL, imm=8),         # 1e9
        w("MD", rd=7, ra=14, rb=6, cnd=MD_DIVU),          # seconds
        w("MD", rd=8, ra=7, rb=6, cnd=MD_MULS),           # sec * 1e9
        w("ALU", rd=9, ra=14, rb=8, cnd=ALU_SUB),         # ns remainder
        w("BFLD", ra=7, fmt=FMT_W),                       # sec[47:32] (lo16)
        w("BFLD", ra=7, fmt=FMT_D),                       # sec[31:0]
        w("BFLD", ra=9, fmt=FMT_D),                       # nanoseconds
        w("BFLD", ra=0, fmt=FMT_Q),                       # reqPortIdentity
        w("BFLD", ra=0, fmt=FMT_W),                       #   .portNumber
        w("SEND"),
        w("END"),
    ]
    return p


def prog_rx_pdresp():
    return [
        w("RDST", rd=1, imm=RG_BANK | 5, fmt=FMT_Q),      # t2 ns (receipt)
        w("WRST", ra=1, imm=RG_SCR | 5, fmt=FMT_Q),
        w("WRST", ra=14, imm=RG_SCR | 17, fmt=FMT_Q),     # t4 (ingress)
        w("END"),
    ]


def prog_rx_pdrfu():
    return [
        w("RDST", rd=1, imm=RG_SCR | 16, fmt=FMT_Q),      # t1 (egress)
        w("RDST", rd=2, imm=RG_SCR | 17, fmt=FMT_Q),      # t4
        w("RDST", rd=3, imm=RG_BANK | 5, fmt=FMT_Q),      # t3 ns
        w("RDST", rd=4, imm=RG_SCR | 5, fmt=FMT_Q),       # t2
        w("ALU", rd=5, ra=2, rb=1, cnd=ALU_SUB),          # t4 - t1
        w("ALU", rd=6, ra=3, rb=4, cnd=ALU_SUB),          # t3 - t2
        w("ALU", rd=7, ra=5, rb=6, cnd=ALU_SUB),
        w("ALU", rd=7, ra=7, cnd=ALU_SHR, imm=1),         # /2
        w("WRST", ra=7, imm=RG_SCR | 4, fmt=FMT_Q),       # meanLinkDelay
        w("WRST", ra=7, imm=RG_PUB | 3, fmt=FMT_D),
        w("COMMIT"),
        w("END"),
    ]


def prog_rx_signal():
    return [w("END")]


def prog_tx_ts():
    return [
        w("WRST", ra=14, imm=RG_SCR | 16, fmt=FMT_Q),     # t1/t3 capture
        w("END"),
    ]


def prog_tmr():
    return [
        w("RDST", rd=1, imm=RG_SCR | 20, fmt=FMT_Q),
        w("ALU", rd=1, ra=1, cnd=ALU_ADD, imm=1),         # cadence count
        w("WRST", ra=1, imm=RG_SCR | 20, fmt=FMT_Q),
        w("MOVE", rd=2, imm=1000),
        w("WRST", ra=2, imm=RG_TMR | 0, fmt=FMT_D),       # re-arm 1 s
        w("END"),
    ]


def prog_tb_battery():
    """r14 = A, r13 = B; writes 12 results to scratch 0..11 (tb/ucpu)."""
    p = []
    for n, cnd in enumerate([ALU_ADD, ALU_SUB, ALU_AND, ALU_OR, ALU_XOR,
                             ALU_SHL, ALU_SHR, ALU_SAR]):
        p.append(w("ALU", rd=1, ra=14, rb=13, cnd=cnd))
        p.append(w("WRST", ra=1, imm=RG_SCR | n, fmt=FMT_Q))
    p.append(w("MD", rd=1, ra=14, rb=13, cnd=MD_MULS))
    p.append(w("WRST", ra=1, imm=RG_SCR | 8, fmt=FMT_Q))
    p.append(w("MD", rd=1, ra=14, rb=13, cnd=MD_DIVU))
    p.append(w("WRST", ra=1, imm=RG_SCR | 9, fmt=FMT_Q))
    p.append(w("ALU", rd=1, ra=14, cnd=ALU_ADD, imm=0xABC))
    p.append(w("WRST", ra=1, imm=RG_SCR | 10, fmt=FMT_Q))
    p.append(w("ALU", rd=1, ra=14, cnd=ALU_SHR, imm=16))
    p.append(w("WRST", ra=1, imm=RG_SCR | 11, fmt=FMT_Q))
    p.append(w("END"))
    return p


ENTRIES = [
    (16, prog_rx_sync), (64, prog_rx_followup), (128, prog_rx_announce),
    (192, prog_rx_pdreq), (256, prog_rx_pdresp), (320, prog_rx_pdrfu),
    (384, prog_rx_signal), (448, prog_tx_ts), (512, prog_tmr),
    (768, prog_tb_battery),
]


def build():
    rom = [None] * DEPTH
    used = 0
    for base, fn in ENTRIES:
        words = fn()
        assert base + len(words) <= DEPTH
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
    args = ap.parse_args()
    rom, used = build()
    with open(args.out, "w", encoding="ascii") as f:
        for word in rom:
            f.write(f"{word:012X}\n")
    print(f"{args.out}: {DEPTH} words, {used} real "
          f"({100.0 * used / DEPTH:.1f}%), rest deterministic fill")


if __name__ == "__main__":
    main()
