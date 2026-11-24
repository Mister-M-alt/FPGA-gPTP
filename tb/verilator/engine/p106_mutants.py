# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The #106 controls of the engine mutation arm (`mutants.py`).

FPGA-gPTP #106: a master announcement must reach the wire after the
announce receipt timeout instant, even when an Announce is already queued
behind the expiry, and on regaining the grandmaster role the Announces go
out at once and then 1 s apart (802.1AS-2011 Figure 10-15). BECOME arms no
Announce beat: SELF, where it ends, continues into ANNTX, which sends the
first Announce in the same handler and arms the cadence from it. Each
control here lists, after its issue number, every named check it must
fail. `mutants.py` runs them with the rest of the arm.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only.
"""

from receipt_mutants import GENERATOR

#: SELF's tail, which continues into ANNTX since #106
SELF_TAIL = ("    p.emit(\"COMMIT\")\n"
             "    p.emit(\"BR\", label=LB[\"ANNTX\"])\n")
#: BECOME's Sync arm, behind which 1616fc8f also armed the Announce beat
BECOME_SYNC = ("    p.emit(\"WRST\", ra=RT, imm=RG_TMR | 1, fmt=FMT_Q)"
               "  # sync now\n")
#: the checks the deferred first Announce fails
INSTANT = ("#106 3.0 s, a clock after the tick: a master Announce on the wire"
           " after the instant")
TIE = "#106 3.00006 s, the lab's tie: a master Announce on the wire after the instant"
NEAR = "#106 3.001 s: a master Announce on the wire after the instant"
AT_ONCE = "#106 regain: the first master Announce leaves at once"
RACE = ("#106 regain race: one master Announce leaves before the better one"
        " is taken")
CADENCE = ("#106 regain: four more master Announces, each 1 s after the one"
           " before")

#: (name, file under hdl/, pattern, replacement, the checks it must fail);
#: a replacement of None makes the pattern a list of pairs
P106_MUTATIONS = [
    # the defect #106 repairs: the first Announce waits 2 ms for a beat, so
    # an Announce queued behind the role change disarms it first
    ("the first master Announce waits for a beat", GENERATOR,
     [(SELF_TAIL, "    p.emit(\"COMMIT\")\n    p.emit(\"END\")\n"),
      (BECOME_SYNC,
       BECOME_SYNC + "    p.emit(\"MOVE\", rd=RT, ra=0, imm=2)\n"
                     "    p.emit(\"WRST\", ra=RT, imm=RG_TMR | 3, fmt=FMT_Q)\n")],
     None,
     f"{INSTANT} | {TIE} | {NEAR} | {AT_ONCE} | {RACE}"),
    # the first Announce leaves at once but arms nothing, so no cadence
    # follows it
    ("the first master Announce starts no cadence", GENERATOR,
     SELF_TAIL,
     SELF_TAIL.replace("label=LB[\"ANNTX\"]", "label=LB[\"ANNTX\"] + 2"),
     CADENCE),
]
