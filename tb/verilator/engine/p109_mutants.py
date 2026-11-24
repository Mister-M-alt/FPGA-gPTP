# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The #109 controls of the engine mutation arm (`mutants.py`).

FPGA-gPTP #109: a negative computed link delay of any magnitude is a good
exchange toward asCapable (Milan v1.2 4.2.6.2.7 sets only a minimum
tolerance; 802.1AS clears asCapable only above neighborPropDelayThresh),
and, by the manager's ruling, the Sync path and the engine's publication
keep that delay signed, floored at -NPD_HI_C. The parent's public bank is
the only clamp to 0. Each control here lists, after its issue number,
every named check it must fail. `mutants.py` runs them with the rest of
the arm.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only.
"""

from receipt_mutants import GENERATOR

#: the floor of the delay the Sync path uses, D = max(D, -NPD_HI_C)
FLOOR = ("    p.emit(\"ALU\", rd=RT, ra=RD_, rb=0, cnd=ALU_ADD, imm=NPD_HI_C)\n"
         "    p.emit(\"ALU\", rd=RU, ra=RT, rb=0, cnd=ALU_SAR, imm=63)\n"
         "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_AND)\n"
         "    p.emit(\"ALU\", rd=RD_, ra=RD_, rb=RT, cnd=ALU_SUB)\n")
#: the two writes of the floored delay: the Sync path's, then the publication
USED = "    p.emit(\"WRST\", ra=RD_, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)\n"
PUB = "    p.emit(\"WRST\", ra=RD_, imm=RG_PUB | 3, fmt=FMT_Q)\n"
#: the threshold verdict: bad iff D - (NPD_HI_C + 1) is not negative
VERDICT = ("    p.emit(\"ALU\", rd=RT, ra=RD_, rb=0, cnd=ALU_SUB,"
           " imm=NPD_HI_C + 1)\n"
           "    p.emit(\"ALU\", rd=RT, ra=RT, rb=0, cnd=ALU_SHR, imm=63)\n"
           "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=0)\n"
           "    p.emit(\"BRS\", cnd=BRS_Z, label=\"bad\")"
           "            # D - 801 >= 0\n")


def kept(*ds: str) -> str:
    """The asCapable checks of the #109 trials named by `ds`."""
    return " | ".join(f"#109 {d}: asCapable kept" for d in ds)


#: the trials a floor at -80 ns, the defect #109 repairs, must fail
BELOW_80 = ("D -81", "D -263", "latency constants over-stated by 400 ns",
            "D -800", "D -801", "D -5000000",
            "the most negative delay of the wire")
EXACT = "its offset uses the delay exactly"
OVER = "#109 latency constants over-stated by 400 ns"

#: (name, file under hdl/, pattern, replacement, the checks it must fail);
#: a replacement of None makes the pattern a list of pairs
P109_MUTATIONS = [
    # word-neutral: the defect #109 repairs, a delay below -80 ns is a bad
    # exchange. (D + 80) u< 881 on the low 32 bits, as 1213ac5b judged it
    ("a delay below -80 ns is a bad exchange", GENERATOR,
     VERDICT,
     "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=0, cnd=ALU_ADD, imm=80)\n"
     "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=NPD_HI_C + 80 + 1)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=\"good\")\n"
     "    p.emit(\"BR\", label=\"bad\")\n",
     kept(*BELOW_80)),
    # the Sync path clamps a negative delay to 0; the publication stays
    # signed. Over-stated latency constants then leave their error in full
    ("the Sync path uses a negative delay as 0", GENERATOR,
     USED,
     "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=0, cnd=ALU_SAR, imm=63)\n"
     "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=RT, cnd=ALU_AND)\n"
     "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=RT, cnd=ALU_SUB)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_PDELAY, fmt=FMT_Q)\n",
     f"#109 D -3: {EXACT} | #109 D -81: {EXACT} | #109 D -263: {EXACT}"
     f" | {OVER}: {EXACT}"),
    # word-neutral: the floor at 0 instead of -800, for both writes
    ("a negative delay is floored at 0", GENERATOR,
     FLOOR,
     FLOOR.replace("imm=NPD_HI_C)", "imm=0)"),
     f"#109 D -263: the engine publishes the used delay"
     f" | #109 D -263: {EXACT} | {OVER}: {EXACT}"),
    # the floor is missing: -5 ms reaches the servo and steps the clock
    ("a negative delay has no floor", GENERATOR,
     FLOOR,
     "",
     f"#109 D -801: {EXACT} | #109 D -5000000: no PHC step"
     " | #109 the most negative delay of the wire: no PHC step"
     " | #109 the most negative delay of the wire: the engine publishes the"
     " used delay"),
    # word-neutral: the floor 1 ns short, at -799
    ("the floor is -799 ns", GENERATOR,
     FLOOR,
     FLOOR.replace("imm=NPD_HI_C)", "imm=NPD_HI_C - 1)"),
     f"#109 D -800: {EXACT} | #109 D -800: the engine publishes the used"
     " delay"),
    # word-neutral: the publication precedes the floor, so a delay below
    # -2^31 ns reaches the parent's 32-bit word with an arbitrary sign
    ("the engine publishes the unfloored delay", GENERATOR,
     FLOOR + USED + PUB,
     PUB + FLOOR + USED,
     "#109 D -5000000: the engine publishes the used delay"
     " | #109 the most negative delay of the wire: the engine publishes the"
     " used delay"),
    # word-neutral: the threshold boundary, both ways
    ("801 ns is a good exchange", GENERATOR,
     VERDICT,
     VERDICT.replace("imm=NPD_HI_C + 1)", "imm=NPD_HI_C + 2)"),
     "#109 D 801: asCapable falls | #109 D 801: the next Follow_Up is not"
     " used"),
    ("800 ns is a bad exchange", GENERATOR,
     VERDICT,
     VERDICT.replace("imm=NPD_HI_C + 1)", "imm=NPD_HI_C)"),
     kept("D 800")),
    # word-neutral: the verdict tests D - 801 >> 31 for zero, not its sign,
    # so a delay of 2^31 + 801 ns or more is a good exchange
    ("the verdict reads D - 801 from bit 31", GENERATOR,
     VERDICT,
     VERDICT.replace("cnd=ALU_SHR, imm=63)", "cnd=ALU_SHR, imm=31)"),
     "#109 the most positive delay of the wire: asCapable falls"
     " | #109 the most positive delay of the wire: the next Follow_Up is"
     " not used"),
]
