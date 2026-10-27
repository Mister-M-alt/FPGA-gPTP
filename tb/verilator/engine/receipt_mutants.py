# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The receipt-rule controls of the engine mutation arm (`mutants.py`).

FPGA-gPTP #89, #90 and #91 are the receipt rules of 802.1AS-2011 as
corrected by Cor1 and Cor2: the sync receipt timeout that ages the port
(10.3.11, Figure 10-13), the lost-response count of Figure 11-8 RESET, and
the duplicate-response reset of WAITING_FOR_PDELAY_RESP_FOLLOW_UP. Every
control here mutates the generator only, and each one lists, after its
issue number, every named check it must fail. `mutants.py` runs them with
the rest of the arm, in the order listed.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only: staging, building
and grading stay in `mutants.py`.
"""

#: the micro-code generator, under hdl/, which every control here mutates
GENERATOR = "ucode/gen_gptp_ucode.py"

#: (name, file under hdl/, pattern, replacement, the checks it must fail)
RECEIPT_MUTATIONS = [
    # ---- #89: sync receipt timeout ages the port ---------------------------
    # word-neutral: the presence term is dropped and the expiry goes straight
    # to BECOME, so a timeout queued behind mastership runs it a second time
    ("a queued receipt timeout ages a master", GENERATOR,
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_SUB, imm=FL_PRESENT_C)\n"
     "    p.emit(\"RDST\", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=40)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n"
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=LB[\"BECGATE\"])\n",
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=0)\n"
     "    p.emit(\"RDST\", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=40)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n"
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=LB[\"BECOME\"])\n",
     "#89 takeover: the queued receipt timeout ages nothing"),
    # the leg as main 55680bff shipped it, seven words, which its gap holds:
    # sync-ok falls unless mastership stands, and nothing is aged
    ("a sync receipt timeout only clears sync-ok", GENERATOR,
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=SRTO_PASSED_C)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_SRTO, fmt=FMT_Q)\n"
     "    p.emit(\"RDST\", rd=RU, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=FL_PRESENT_C)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_SUB, imm=FL_PRESENT_C)\n"
     "    p.emit(\"RDST\", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=40)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n"
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=LB[\"BECGATE\"])\n"
     "    p.emit(\"END\")\n",
     "    p.emit(\"RDST\", rd=RT, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RT, rb=0, cnd=ALU_SHL, imm=2)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_OR, imm=7)\n"
     "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_AND)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"COMMIT\")\n    p.emit(\"END\")\n",
     "#89 Sync stops: the plane takes mastership"
     " | #89 never usable: the grandmaster is aged"
     " | #89 no Follow_Up: the plane takes mastership within"
     " | #89 Follow_Up after the next Sync: the plane takes mastership within"
     " | #89 Follow_Up with the next sequenceId: the plane takes mastership"
     " within"),
    # the round-1 rule, one word longer: only an expiry that ages an elected
    # peer leaves the mark, so one found in the master role is forgotten
    ("only an expiry that ages a slave marks the port", GENERATOR,
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_SRTO, fmt=FMT_Q)\n"
     "    p.emit(\"RDST\", rd=RU, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=FL_PRESENT_C)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_SUB, imm=FL_PRESENT_C)\n"
     "    p.emit(\"RDST\", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=40)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n"
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=LB[\"BECGATE\"])\n"
     "    p.emit(\"END\")\n",
     "    p.emit(\"RDST\", rd=RU, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_AND, imm=FL_PRESENT_C)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_SUB, imm=FL_PRESENT_C)\n"
     "    p.emit(\"RDST\", rd=RV, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=40)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n"
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=\"aged\")\n"
     "    p.emit(\"END\")\n"
     "    p.label(\"aged\")\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_SRTO, fmt=FMT_Q)\n"
     "    p.emit(\"BR\", label=LB[\"BECGATE\"])\n",
     "#89 takeover: the queued receipt timeout leaves the port aged"
     " | #89 a lone pair heard as master: a later Announce elects nothing"
     " | #89 Announce lapse: a sync receipt timeout after mastership ages"
     " the next Announce"),
    # word-neutral: the elected grandmaster's priority1 is read as zero, so a
    # priority1 255 grandmaster is aged as if gmPresent were TRUE
    ("sync receipt ageing ignores gmPresent", GENERATOR,
     "    p.emit(\"ALU\", rd=RV, ra=RV, rb=0, cnd=ALU_SHR, imm=40)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n",
     "    p.emit(\"MOVE\", rd=RV, ra=0, imm=0)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=RV, cnd=ALU_OR)\n",
     "p1 255 #89 gmPresent: a priority1 255 grandmaster without Sync stays"
     " elected"),
    ("adoption leaves the Sync receipt watch off", GENERATOR,
     "    # A parent refresh (same_gm) restarts nothing\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=SYNC_RTO_MS_C)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_TMR | 4, fmt=FMT_Q)       "
     "# sync watch\n",
     "    # A parent refresh (same_gm) restarts nothing\n",
     "#89 never usable: the grandmaster is aged"
     " | #89 never usable: within syncReceiptTimeout of its adoption"),
    ("an aged port takes Announces", GENERATOR,
     "    p.emit(\"ALU\", rd=RU, ra=RA, rb=0, cnd=ALU_SHR, imm=40)  "
     "# {p1,class,acc}\n"
     "    p.emit(\"RDST\", rd=RT, imm=RG_SCR | S_SRTO, fmt=FMT_Q)\n"
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=LB[\"BECGATE\"])\n",
     "",
     "#89 never usable: the aged port stays master while Announces continue"
     " | #89 Sync stops: the aged port stays master"
     " | #89 no Follow_Up: the aged port stays master"
     " | #89 Follow_Up after the next Sync: the aged port stays master"
     " | #89 Follow_Up with the next sequenceId: the aged port stays master"
     " | p1 255 #89 gmPresent: a priority1 1 Announce on the aged port"
     " elects nothing"),
    # word-neutral: the Announce's priority1 is read as zero, so the aged
    # port refuses a priority1 255 grandmaster as if gmPresent were TRUE
    ("an aged port refuses a priority1 255 grandmaster", GENERATOR,
     "    p.emit(\"ALU\", rd=RU, ra=RA, rb=0, cnd=ALU_SHR, imm=40)  "
     "# {p1,class,acc}\n",
     "    p.emit(\"MOVE\", rd=RU, ra=0, imm=0)\n",
     "p1 255 #89 gmPresent: the aged port elects a priority1 255 grandmaster"),
    # word-neutral: the aged Announce is dropped, so a slave of a priority1
    # 255 grandmaster stays elected instead of becoming master at once
    ("an aged Announce is dropped rather than aged", GENERATOR,
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=LB[\"BECGATE\"])\n"
     "    p.emit(\"RDST\", rd=RB, imm=RG_BANK | 9, fmt=FMT_Q)",
     "    p.emit(\"CMP\", ra=RU, rb=RT, fmt=FMT_D)\n"
     "    p.emit(\"BRS\", cnd=BRS_LT, label=\"out\")\n"
     "    p.emit(\"RDST\", rd=RB, imm=RG_BANK | 9, fmt=FMT_Q)",
     "p1 255 #89 gmPresent: a priority1 1 Announce on the aged port makes"
     " this plane master"),
    # BECOME as round 1 shipped it: one word longer each, which the ROM holds
    ("mastership stops the Sync receipt watch", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch\n",
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 4, fmt=FMT_Q)\n",
     "#89 Announce lapse: a sync receipt timeout after mastership ages the"
     " next Announce"),
    ("mastership stops the Follow_Up watch", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch\n",
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 5, fmt=FMT_Q)\n",
     "#89 parked Sync: a Follow_Up 200 ms after it pairs with nothing"),
    ("mastership voids the parked Sync", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch\n",
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 2, fmt=FMT_Q)   # stop the watch\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)\n",
     "#89 parked Sync: a Follow_Up 60 ms after it, after the takeover, is"
     " heard"),
    ("a master steers on its aged peer's Sync", GENERATOR,
     "    p.emit(\"CMP\", ra=RC, rb=0, fmt=FMT_D,"
     " imm=ROLE_MASTER_C - ROLE_SLAVE_C)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=LB[\"SRWATCH\"])\n",
     "",
     "#89 first grandmaster: Sync recovery is heard as master and steers"
     " nothing"
     " | #89 Sync stops: Sync recovery is heard as master and steers nothing"
     " | #89 no Follow_Up: Sync recovery is heard as master and steers"
     " nothing"),
    # word-neutral: the Follow_Up handler's role gate admits the slave alone
    ("a master hears no Sync", GENERATOR,
     "           imm=ROLE_MASTER_C - ROLE_SLAVE_C + 1)\n",
     "           imm=ROLE_MASTER_C - ROLE_SLAVE_C)\n",
     "#89 first grandmaster: the next Announce elects the grandmaster"
     " | #89 Sync stops: the next Announce elects the grandmaster"
     " | #89 no Follow_Up: the next Announce elects the grandmaster"
     " | #89 a lone pair heard as master: an Announce inside its watch"
     " elects the grandmaster"),
    # the watch a usable pair restarts, too short and too long
    ("the Sync receipt watch is 100 ms", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)   "
     "# consumed\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=SYNC_RTO_MS_C)\n",
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)   "
     "# consumed\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=100)\n",
     "#89 Sync stops: within syncReceiptTimeout and one BMCA pass"
     " | #89 first grandmaster: usable Sync keeps it elected"
     " | #89 Sync every 250 ms keeps the plane deferring"),
    ("the Sync receipt watch is 500 ms", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)   "
     "# consumed\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=SYNC_RTO_MS_C)\n",
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_SYNCTS, fmt=FMT_Q)   "
     "# consumed\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=500)\n",
     "#89 Sync stops: within syncReceiptTimeout and one BMCA pass"
     " | #89 no Follow_Up: the plane takes mastership within"
     " | #89 Follow_Up with the next sequenceId: the plane takes mastership"
     " within"),
    # word-neutral: a refresh expires the Sync watch, not the Announce one
    ("a parent refresh expires the Sync watch", GENERATOR,
     "    p.label(\"same_gm\")\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=3000)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_TMR | 2, fmt=FMT_Q)       "
     "# receipt watch\n",
     "    p.label(\"same_gm\")\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=1)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_TMR | 4, fmt=FMT_Q)\n",
     "#89 Sync stops: the Announce leaves the grandmaster elected"),
    ("the adoption watch is 100 ms", GENERATOR,
     "    # A parent refresh (same_gm) restarts nothing\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=SYNC_RTO_MS_C)\n",
     "    # A parent refresh (same_gm) restarts nothing\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=100)\n",
     "#89 never usable: within syncReceiptTimeout of its adoption"
     " | still slave inside the Sync receipt watch"),
    # word-saving: the Follow_Up pairs on its source alone
    ("a Follow_Up pairs whatever its sequenceId", GENERATOR,
     "    p.emit(\"CMP\", ra=RT, rb=RU, fmt=FMT_W)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"srcck\")\n"
     "    p.emit(\"BR\", label=\"out\")\n",
     "    p.emit(\"BR\", label=\"srcck\")\n",
     "#89 Follow_Up after the next Sync: no unusable pair is consumed"
     " | #89 Follow_Up with the next sequenceId: no unusable pair is"
     " consumed"),
    ("the Follow_Up watch is 50 ms", GENERATOR,
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=FU_RTO_MS_C)\n",
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=50)\n",
     "#89 a Follow_Up 60 ms after its Sync is used"),
    # ---- #90 and #91: Figure 11-8 RESET and lostResponses -----------------
    ("lost responses clear asCapable at the first", GENERATOR,
     "LOST_CLEARS_AT_C = LOST_N_C + 2\n",
     "LOST_CLEARS_AT_C = 1\n",
     "#90 no response: one loss keeps asCapable"
     " | #90 no follow-up: one loss keeps asCapable"
     " | #91 duplicated response: one loss keeps asCapable"
     " | #91 three responses: one loss keeps asCapable"),
    # one word more, which its gap holds: the clearing beat sends nothing
    ("the fifth loss stops the requests", GENERATOR,
     "    p.emit(\"COMMIT\")\n"
     "    p.label(\"pd_go\")\n",
     "    p.emit(\"COMMIT\")\n"
     "    p.emit(\"END\")\n"
     "    p.label(\"pd_go\")\n",
     "#90 no response: request 6 goes out"
     " | #90 no follow-up: runs from a capable plane"
     " | #90 no follow-up: runs from a completed exchange"),
    ("same-identity duplicates are a storm", GENERATOR,
     "    p.emit(\"CMP\", ra=RB, rb=RC, fmt=FMT_Q)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"out\")\n",
     "",
     "#91 duplicates are not a storm: requests keep going out"),
    ("lost responses clear asCapable at the fourth", GENERATOR,
     "LOST_CLEARS_AT_C = LOST_N_C + 2\n",
     "LOST_CLEARS_AT_C = LOST_N_C + 1\n",
     "#90 no response: four losses keep asCapable"
     " | #90 no follow-up: four losses keep asCapable"
     " | #91 duplicated response: four losses keep asCapable"
     " | #91 three responses: four losses keep asCapable"),
    ("lost responses clear asCapable at the sixth", GENERATOR,
     "LOST_CLEARS_AT_C = LOST_N_C + 2\n",
     "LOST_CLEARS_AT_C = LOST_N_C + 3\n",
     "#90 no response: the fifth loss clears asCapable"
     " | #90 no follow-up: the fifth loss clears asCapable"
     " | #91 duplicated response: the fifth loss clears asCapable"
     " | #91 three responses: the fifth loss clears asCapable"),
    # the arm as main 55680bff shipped it: every response overwrites it
    ("a second response re-arms the pairing", GENERATOR,
     "    p.emit(\"RDST\", rd=RU, imm=RG_SCR | S_RSPSEQ, fmt=FMT_Q)\n"
     "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_ADD)\n",
     "",
     "#91 duplicated response: the fifth loss clears asCapable"
     " | #91 duplicated response: no exchange completes"
     " | #91 three responses: the fifth loss clears asCapable"
     " | #91 three responses: no exchange completes"),
    # word-neutral: the second response disarms, the third arms again
    ("a third response re-arms the reset exchange", GENERATOR,
     "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_ADD)\n",
     "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_XOR)\n",
     "#91 three responses: the fifth loss clears asCapable"
     " | #91 three responses: no exchange completes"),
]
