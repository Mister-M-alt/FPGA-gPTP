#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Mutation arm for the engine suite: prove its checks are load-bearing.

Why this exists. `sim_main.cpp` grades the whole plane through its wire and
publish faces, and the arms that repair FPGA-gPTP #31 - the accepted-beat
result face, the message-scoped lost arm, the retained Pdelay pairing
context and the three admission gates - are exactly the kind of behaviour a
harness can appear to check without checking. A suite whose assertions never
fail is indistinguishable from a suite that asserts nothing, and the defect
this round repairs was invisible to a green suite for that reason.

So the real engine RTL and the real micro-code generator are mutated, one
defect at a time, and the SAME harness is run against each mutant. Every
mutant must make it FAIL. The unmutated build must still PASS, without which
the arm would be satisfied by a harness that fails on everything.

"Caught" means the harness's own tally says so; see tb/mutation_verdict.py
for why a non-zero exit alone is not a catch. Everything is staged into a
temporary directory, so nothing is written into the tree.

Cost note, recorded rather than hidden: micro-code mutants reuse one build of
the unmutated RTL, because a generator change moves only the ROM image the
simulation reads at start-up. RTL mutants are built individually.

What this arm deliberately does NOT list, recorded rather than hidden,
because the value of a mutation arm is also the map of what it cannot reach.
Removing the reset-backed read gate on the pending-pair cell alone survives
every check, and that survival is a property of the design rather than a gap
in the harness: the cell is read in only two places, and a new Pdelay_Req
clears it at its commit point before any post-reset timestamp result can
match a claim. The gate is kept because it is the second half of a stated
rule that pairs it with the t1 validity beside it, whose own removal IS
caught below; it is defence in depth with no reachable arm, not a checked
behaviour. Closing that would need a reachable state, not another mutant.

The lapse hook's asCapable term is also defence in depth. Removing only
that term survives: Sync pairs cannot be consumed while incapable, and
the 375 ms Sync receipt watch clears sync-ok before capability can recover
through two good Pdelay exchanges at 1 s cadence. Only mastership disarms
that watch, and mastership retires the qualifier itself. This is a
reachability argument from the current policy, not an executed proof;
revisit it if the timer or capability recovery rules change.

A commit pairing count zero with a nonzero entry has no arm either. No
legitimate path is empty since #87 (an absent TLV keeps the previous
pathTrace), and the engine's own simulation assertion stops the run on
that pairing, so such a mutant aborts before any check can grade it, and
an abort is not a catch. The empty-sequence mutant below publishes count
zero with every entry zero, which the assertion admits and the checks
catch.

A mutant is one (pattern, replacement) pair, or, with the replacement None,
a list of pairs applied to the same file: restoring the parser's head
refusal takes three edits, as in tb/verilator/parser/mutants.py.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HDL = (HERE / "../../../hdl").resolve()
sys.path.insert(0, str((HERE / "../../").resolve()))

from mutation_verdict import TALLY, verdict  # noqa: E402

#: the RTL the suite builds, in the order the Makefile lists it
RTL_SOURCES = (
    "ucpu/gptp_ucpu_pkg.sv",
    "ucpu/KL_gptp_ucpu.sv",
    "wire/KL_gptp_rx_parser.sv",
    "wire/KL_gptp_tx_slot.sv",
    "common/KL_gptp_timer.sv",
    "top/KL_gptp_engine.sv",
)
GENERATOR = "ucode/gen_gptp_ucode.py"
#: the shipping arguments of this suite's image, as tb/verilator/engine/Makefile
GENARGS = ("--clk-hz", "2000000", "--cease-ms", "3000")
#: the Makefile's fourth pass (#82): a priority1 of 255, the self-publication
#: phases only. Its checks print with this prefix, so a control names the pass
P1_GENARGS = ("--p1", "255")
P1_PLUSARG = "+not-gm-capable"
P1_PREFIX = "p1 255 "

VFLAGS = [
    "--cc", "--exe", "--build", "-j", "4", "--top-module", "KL_gptp_engine",
    "-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL",
    "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "-Wno-UNUSEDPARAM",
    "-GUCODE_HEX_P=\"gptp_ucode.hex\"", "-GCLK_HZ_P=2000000",
]

#: #88: the parser's PathTrace header verdict and its retired variants
PT_HDR_BAD_HEAD = (
    "  assign ann_tlv_header_bad_w = ann_tlv_header_end_w &&\n"
    "      (ann_tlv_len_w[0] ||\n"
    "       ({6'd0, cnt_r} + {1'b0, ann_tlv_len_w} > {6'd0, msg_end_r}) ||\n"
    "       ((ann_tlv_type_w == 16'h0008) &&\n")
PT_HDR_BAD = PT_HDR_BAD_HEAD + "        (ann_tlv_len_w[2:0] || pt_seen_r)));\n"
#: the base's head rule, as tb/verilator/parser/mutants.py restores it
PT_HEAD_EDITS = [
    ("  logic ann_pt_byte_w;\n",
     "  logic ann_pt_byte_w;\n"
     "  logic [63:0] mut_gm_r;\n"
     "  always_ff @(posedge clk_i)\n"
     "    if (rx_valid_i && (cnt_r == 11'd74)) mut_gm_r <= acc_nxt_w;\n"
     "  wire mut_head_bad_w = ann_pt_byte_w && (pt_byte_r == 3'd7) &&\n"
     "                        (pt_cnt_r == 8'd0) && (acc_nxt_w != mut_gm_r);\n"),
    ("                    if (acc_nxt_w == local_clock_id_i)"
     " pt_self_r <= 1'b1;\n",
     "                    if (acc_nxt_w == local_clock_id_i)"
     " pt_self_r <= 1'b1;\n"
     "                    if (mut_head_bad_w) bad_r <= 1'b1;\n"),
    ("                          !ann_tlv_header_bad_w &&\n",
     "                          !ann_tlv_header_bad_w && !mut_head_bad_w &&\n"),
]
#: the engine's address-7 copy of one received entry, and its keep gate
PATH_COPY = ("                      pub_path_r[64*pk +: 64] <=\n"
             "                          ann_pub_path_r[64*pk +: 64];\n")
PATH_KEEP = "                if (ann_pub_present_r) begin\n"
PATH_APPEND = "  wire       path_append_w = (ann_pub_count_clamped_w != 4'd8);\n"

#: (name, file under hdl/, pattern, replacement, the property it should
#: break); a replacement of None makes the pattern a list of pairs
MUTATIONS = [
    # ---- #75: the policy level must cover the entire affected interval ----
    ("slew level tied low", "top/KL_gptp_engine.sv",
     "      // gather: atomic millisecond snapshot",
     "      phc_slew_active_o <= 1'b0; // injected tied-low output\n"
     "      // gather: atomic millisecond snapshot",
     "slew: policy decision starts at +101 ns"),
    ("slew clears at the first in-band pair", GENERATOR,
     "    p.emit(\"MOVE\", rd=RB, ra=0, imm=3)                       # reload, then -1",
     "    p.emit(\"MOVE\", rd=RB, ra=0, imm=2)                       # early completion",
     "slew: first in-band pair cannot clear"),
    ("slew clears before the replacement rate", "top/KL_gptp_engine.sv",
     "                if (st_wdata_w[1:0] != 2'd0)\n"
     "                  phc_slew_active_o <= 1'b1;",
     "                phc_slew_active_o <= (st_wdata_w[1:0] != 2'd0);",
     "slew: no clear precedes the replacement rate"),
    ("slew idle lapse arms qualification", "top/KL_gptp_engine.sv",
     "                if (phc_slew_active_o &&\n",
     "                if (1'b1 &&\n",
     "slew: in-band pair after idle timeout stays inactive"),
    ("slew idle asCapable loss arms qualification", "top/KL_gptp_engine.sv",
     "                if (phc_slew_active_o &&\n"
     "                    (!st_wdata_w[2] || !st_wdata_w[3]))\n",
     "                if ((phc_slew_active_o && !st_wdata_w[3]) ||\n"
     "                    !st_wdata_w[2])\n",
     "slew: in-band pair after asCapable recovery stays inactive"),
    ("slew mastership keeps qualification", "top/KL_gptp_engine.sv",
     "                phc_slew_left_r   <= 2'd0;\n"
     "                phc_slew_active_o <= 1'b0;\n",
     "                phc_slew_active_o <= 1'b0;\n",
     "slew: in-band return from GM stays inactive"),
    # ---- the result face: acceptance, and what acceptance protects -------
    ("result face always ready", "top/KL_gptp_engine.sv",
     "assign txts_ready_o  = !txts_pend_r && rst_n;",
     "assign txts_ready_o  = 1'b1;",
     "a result already owed to the micro-code cannot be replaced by a "
     "later one"),
    ("result value taken without an accepted beat", "top/KL_gptp_engine.sv",
     "if (txts_accept_w)          txts_r <= txts_ns_i;",
     "if (txts_valid_i)          txts_r <= txts_ns_i;",
     "the accepted result keeps its own timestamp until its dispatch"),
    ("result tag taken without an accepted beat", "top/KL_gptp_engine.sv",
     "if (txts_accept_w) begin",
     "if (txts_valid_i) begin",
     "the accepted result keeps its own tag and outcome until its dispatch"),
    # ---- reset-backed validity of the pairing cells ----------------------
    ("recorded t1 survives reset", "top/KL_gptp_engine.sv",
     "        else if ((st_addr_w[5:0] == 6'd37) && !t1v_valid_r)\n"
     "          st_rd_mux_w = 64'd0;\n",
     "",
     "a t1 measured before a reset cannot pair with a later Follow_Up"),
    # ---- the byte face, which decides how many frames were sent ----------
    ("byte face advances without ready", "wire/KL_gptp_tx_slot.sv",
     "      end else if (tx_ready_i) begin",
     "      end else begin",
     "a stalled byte, including the final one, waits for an accepted "
     "transfer"),
    # ---- the lost arm, and its scope -------------------------------------
    ("lost t1 fabricates a time and a companion", GENERATOR,
     "    p.label(\"t1\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n",
     "    p.label(\"t1\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"BR\", label=LB[\"TXT1OK\"])\n",
     "a lost result writes no time and completes no exchange"),
    ("lost Sync cancels the requester exchange", GENERATOR,
     "    p.label(\"sync\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"END\")                      # no SYNCFU: there is no "
     "origin time\n",
     "    p.label(\"sync\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n",
     "a lost Sync result retires the Sync claim and nothing else"),
    ("lost response cancels the requester exchange", GENERATOR,
     "    p.label(\"resp\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_RESP, fmt=FMT_Q)\n"
     "    p.emit(\"END\")                      # no RFU: there is no t3 to "
     "carry\n",
     "    p.label(\"resp\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_RESP, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n",
     "a lost Pdelay_Resp result retires the response claim and nothing "
     "else"),
    # ---- the retained pairing context -------------------------------------
    ("a later response re-arms the frozen pair", GENERATOR,
     "    p.emit(\"RDST\", rd=RU, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"CMP\", ra=RU, rb=0, fmt=FMT_D, imm=0)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"arm_go\")\n"
     "    p.emit(\"BR\", label=\"multi\")                                   "
     "# frozen\n"
     "    p.label(\"arm_go\")\n",
     "    p.label(\"arm_go\")\n",
     "a complete pair keeps its own identity and operands until its t1"),
    ("the tail runs before its own t1", GENERATOR,
     "    p.emit(\"RDST\", rd=RT, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=1)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"t1_here\")\n"
     "    p.emit(\"WRST\", ra=RC, imm=RG_SCR | S_T3, fmt=FMT_Q)\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=1)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n"
     "    p.label(\"t1_here\")\n",
     "    p.label(\"t1_here\")\n",
     "a delay is computed from this exchange's own t1, never a "
     "predecessor's"),
    ("a new request leaves the old pair live", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)\n",
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)\n",
     "a superseded exchange cannot pair with the new request's t1"),
    # ---- the three admission gates, one arm each --------------------------
    ("credit gate removed from the Pdelay_Req leg", GENERATOR,
     "    e_credit_gate(p, \"beat_off\")\n",
     "",
     "a Pdelay_Req beat is postponed while the transmit path has no "
     "credit"),
    ("credit gate removed from the Sync leg", GENERATOR,
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    e_credit_gate(p, \"skip\")\n"
     "    p.emit(\"RDST\", rd=RB, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n",
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    p.emit(\"RDST\", rd=RB, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n",
     "a Sync beat is postponed while the transmit path has no credit"),
    ("credit gate removed from the Announce leg", GENERATOR,
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    e_credit_gate(p, \"skip\")\n"
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_ASEQ, fmt=FMT_Q)\n",
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_ASEQ, fmt=FMT_Q)\n",
     "an Announce beat is postponed while the transmit path has no credit"),
    # ---- the #68 step-versus-slew policy, one arm per rule -----------------
    ("every pair uses the locked threshold", GENERATOR,
     "    p.emit(\"RDST\", rd=RB, imm=RG_SCR | S_LOCK, fmt=FMT_Q)\n",
     "    p.emit(\"MOVE\", rd=RB, ra=0,"
     " imm=STEP_LOCKED_NS_C - STEP_LINKUP_NS_C)\n",
     "a link-up pair steps over 20 us"),
    ("every pair uses the link-up threshold", GENERATOR,
     "    p.emit(\"MOVE\", rd=RT, ra=0,"
     " imm=STEP_LOCKED_NS_C - STEP_LINKUP_NS_C)\n",
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=0)\n",
     "a locked pair slews up to 100 us"),
    ("exactly the threshold steps", GENERATOR,
     "    p.emit(\"ALU\", rd=RB, ra=RB, rb=0, cnd=ALU_ADD, imm=1)\n"
     "    p.emit(\"MD\", rd=RU, ra=RW, rb=RB, cnd=MD_DIVU)\n",
     "    p.emit(\"ALU\", rd=RB, ra=RB, rb=0, cnd=ALU_ADD, imm=0)\n"
     "    p.emit(\"MD\", rd=RU, ra=RW, rb=RB, cnd=MD_DIVU)\n",
     "an offset of exactly 20 us, or 100 us once locked, slews"),
    ("the step arm is unreachable", GENERATOR,
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"sv_slew\")\n",
     "    p.emit(\"BR\", label=\"sv_slew\")\n",
     "an offset over the threshold steps"),
    # word-neutral, because the BTCA leg filled its gap when this arm was
    # written and one more word was a packing refusal, not a mutant (#82
    # has since freed words): the unlock takes the slot of the
    # Sync-cadence disarm, which disarms nothing for a plane that is
    # already a slave (18c's), and elsewhere leaves a cadence whose own
    # master gate sends nothing
    ("a grandmaster change unlocks the servo", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_TMR | 1, fmt=FMT_Q)        "
     "# sync TX off\n",
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_LOCK, fmt=FMT_Q)\n",
     "the servo stays locked across a grandmaster identity change"),
    # only an asCapable rise re-arms the link-up (the manager's ruling on
    # #68): each of these two re-adds a retired re-arm
    # word-neutral, because the packer has no gap for a longer receipt
    # timeout leg (#84): a slave's timeout as before, plus the unlock
    ("a receipt timeout unlocks the servo", GENERATOR,
     "    p.emit(\"ALU\", rd=RU, ra=RT, rb=0, cnd=ALU_SHL, imm=SYNCOK_BY_AMGM_C)\n"
     "    p.emit(\"ALU\", rd=RU, ra=RU, rb=0, cnd=ALU_OR,\n"
     "           imm=FL_PRESENT_C | FL_AMGM_C | FL_ASCAP_C)\n",
     "    p.emit(\"MOVE\", rd=RU, ra=0,"
     " imm=FL_PRESENT_C | FL_AMGM_C | FL_ASCAP_C)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_LOCK, fmt=FMT_Q)\n",
     "the servo stays locked across a Sync receipt timeout"),
    ("becoming grandmaster unlocks the servo", GENERATOR,
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_AMGM_C | FL_SYNCOK_C)\n",
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_AMGM_C | FL_SYNCOK_C)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_LOCK, fmt=FMT_Q)\n",
     "the servo stays locked across a return from mastership"),
    ("the locked threshold is 200 us", GENERATOR,
     "    p.emit(\"MOVE\", rd=RT, ra=0,"
     " imm=STEP_LOCKED_NS_C - STEP_LINKUP_NS_C)\n",
     "    p.emit(\"MOVE\", rd=RT, ra=0,"
     " imm=2 * STEP_LOCKED_NS_C - STEP_LINKUP_NS_C)\n",
     "a locked pair steps over 100 us, after a receipt timeout too"),
    ("asCapable's rise keeps the lock", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_LOCK, fmt=FMT_Q)"
     "  # rose: link-up\n",
     "",
     "the first pair after asCapable rises, or after a reset, is a link-up"),
    ("the whole trim is not clamped", GENERATOR,
     "    e_sat(p, RT, RUNTIME[\"ilim\"], \"sv_a\")                    "
     "# +-200 ppm\n",
     "",
     "the written trim never leaves +-200 ppm"),
    ("the trim clamp is one unit wider than the envelope", GENERATOR,
     "    e_sat(p, RT, RUNTIME[\"ilim\"], \"sv_a\")",
     "    e_sat(p, RT, RUNTIME[\"ilim\"] + 1, \"sv_a\")",
     "the written trim never leaves the envelope the consumer derives"),
    ("the integrator is not clamped", GENERATOR,
     "    e_sat(p, RC, RUNTIME[\"ilim\"], \"sv_i\")                    "
     "# +-ILIM\n",
     "",
     "the integrator stays within +-200 ppm"),
    # ---- #82: thisClock and {thisClock} unless a live peer is elected ----
    # Each control lists, after "#82 ", every named check it must fail.
    # -- reset publishes the self tuple, and commits it once, at once --
    ("reset leaves the grandmaster zero", "top/KL_gptp_engine.sv",
     "      pub_gm_r        <= rom_clock_id_w;\n",
     "      pub_gm_r        <= '0;\n",
     "#82 cold release: every cycle to the first beat names thisClock"
     " | #82 cold release: every cycle to the first beat has {thisClock}"
     " | #82 cold release: that commit carries thisClock and {thisClock}"
     " | #82 warm reset: it names thisClock, not the elected peer"
     " | pre-init deep Announce: GM stays thisClock"),
    ("reset keeps the elected grandmaster", "top/KL_gptp_engine.sv",
     "      pub_gm_r        <= rom_clock_id_w;\n",
     "",
     "#82 warm reset: it names thisClock, not the elected peer"),
    ("the thisClock words are read swapped", GENERATOR,
     "    for addr, word in ((ROM_CID_HI_C,\n"
     "                        (cid >> 32) | (gm_capable << ROM_GMCAP_BIT_C)),\n"
     "                       (ROM_CID_LO_C, cid & 0xFFFFFFFF)):\n",
     "    for addr, word in ((ROM_CID_LO_C,\n"
     "                        (cid >> 32) | (gm_capable << ROM_GMCAP_BIT_C)),\n"
     "                       (ROM_CID_HI_C, cid & 0xFFFFFFFF)):\n",
     "#82 cold release: every cycle to the first beat names thisClock"
     " | #82 cold release: that commit carries thisClock and {thisClock}"),
    ("reset leaves the path empty", "top/KL_gptp_engine.sv",
     "      pub_path_count_r <= 4'd1;\n"
     "      pub_path_r       <= self_path_w;\n",
     "      pub_path_count_r <= 4'd0;\n"
     "      pub_path_r       <= '0;\n",
     "#82 cold release: every cycle to the first beat has {thisClock}"
     " | #82 cold release: that commit carries thisClock and {thisClock}"
     " | #82 warm reset: its path is {thisClock} with a zero tail"),
    ("reset keeps the elected tail", "top/KL_gptp_engine.sv",
     "      pub_path_count_r <= 4'd1;\n"
     "      pub_path_r       <= self_path_w;\n",
     "      pub_path_count_r <= 4'd1;\n",
     "#82 warm reset: its path is {thisClock} with a zero tail"
     " | #82 every commit naming thisClock carries {thisClock}"),
    ("no engine commit after reset", "top/KL_gptp_engine.sv",
     "  assign pub_commit_o     = ucpu_commit_w || boot_pub_commit_r;",
     "  assign pub_commit_o     = ucpu_commit_w;",
     "#82 cold release: one commit before the first beat"
     " | #82 warm reset: one commit in the first 2 ms"),
    ("the boot commit fires twice", "top/KL_gptp_engine.sv",
     "      boot_pub_commit_r <= boot_pub_pend_r;\n"
     "      boot_pub_pend_r   <= 1'b0;\n",
     "      boot_pub_commit_r <= boot_pub_pend_r;\n"
     "      boot_pub_pend_r   <= boot_pub_pend_r && !boot_pub_commit_r;\n",
     "#82 cold release: one commit before the first beat"
     " | #82 warm reset: one commit in the first 2 ms"),
    ("the boot commit never retires", "top/KL_gptp_engine.sv",
     "      boot_pub_commit_r <= boot_pub_pend_r;\n"
     "      boot_pub_pend_r   <= 1'b0;\n",
     "      boot_pub_commit_r <= boot_pub_pend_r;\n",
     "#82 cold release: one commit before the first beat"),
    ("the boot commit waits for the timer bootstrap", "top/KL_gptp_engine.sv",
     "      boot_pub_commit_r <= boot_pub_pend_r;\n"
     "      boot_pub_pend_r   <= 1'b0;\n",
     "      boot_pub_commit_r <= boot_pub_pend_r && boot_done_r;\n"
     "      boot_pub_pend_r   <= boot_pub_pend_r && !boot_done_r;\n",
     "#82 cold release: that commit is the first edge after release"
     " | #82 warm reset: that commit is the first edge after release"
     " | pre-init deep Announce: no commit"),
    # -- only a newly received Announce competes after a reset --------------
    ("a warm reset keeps the retained best record", "top/KL_gptp_engine.sv",
     "      best_pv_valid_r    <= 1'b0;\n"
     "      best_id_valid_r    <= 1'b0;\n"
     "      best_src_valid_r   <= 1'b0;\n",
     "",
     "#82 warm reset: a worse-than-local peer leaves thisClock"
     " | #82 warm reset: the live worse peer wins, not the absent A"
     " | #82 warm reset: the live peer carries its own path"),
    ("an unwritten best record reads as the best vector",
     "top/KL_gptp_engine.sv",
     "                 ((st_addr_w[5:0] == 6'd20) && !best_src_valid_r))\n"
     "          st_rd_mux_w = '1;\n",
     "                 ((st_addr_w[5:0] == 6'd20) && !best_src_valid_r))\n"
     "          st_rd_mux_w = '0;\n",
     "#82 warm reset: a worse-than-local peer leaves thisClock"
     " | #82 warm reset: the live worse peer wins, not the absent A"),
    # -- a winning peer is published with its own path ----------------------
    ("a winning peer's grandmaster is not published", GENERATOR,
     "    p.emit(\"WRST\", ra=RW, imm=RG_PUB | 0, fmt=FMT_Q)\n",
     "",
     "#82 peer wins: its commit names the peer GM"
     " | #82 warm reset: the live worse peer wins, not the absent A"
     " | #84 the run hands mastership to a peer"
     " | #85 direct grandmaster: elected"
     " | #85 multi-hop grandmaster: elected"
     " | #85 seven received entries: elected"
     " | #85 eight received entries: elected"
     " | #85 absent path: elected"),
    ("a winning peer's path is not staged", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_PUB | 7, fmt=FMT_Q)\n",
     "",
     "#82 peer wins: its commit carries the peer path"
     " | #82 warm reset: the live peer carries its own path"),
    # -- a departed peer returns the self tuple, by either departure --------
    ("the self publication keeps the departed grandmaster", GENERATOR,
     "    p.emit(\"WRST\", ra=RC, imm=RG_PUB | 0, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=RC, imm=RG_PUB | 1, fmt=FMT_Q)\n",
     "    p.emit(\"WRST\", ra=RC, imm=RG_PUB | 1, fmt=FMT_Q)\n",
     "#82 peer leaves: the mastership commit names thisClock"
     " | #82 Pdelay loss: thisClock is committed within 2 ms of the fall"
     " | #82 Pdelay loss: that mastership names thisClock, {thisClock}"
     " | #85 direct grandmaster: the degraded grandmaster yields"
     " | #85 multi-hop grandmaster: the degraded grandmaster yields"
     " | #85 seven received entries: the degraded grandmaster yields"
     " | #85 eight received entries: the degraded grandmaster yields"
     " | #85 absent path: the degraded grandmaster yields"),
    ("the self publication keeps the departed path", GENERATOR,
     "    p.emit(\"WRST\", ra=RT, imm=RG_PUB | 6, fmt=FMT_Q)",
     "    p.emit(\"WRST\", ra=0, imm=RG_PUB | 6, fmt=FMT_Q)",
     "#82 peer leaves: the mastership commit path is {thisClock}"
     " | #82 Pdelay loss: that commit carries {thisClock}"
     " | #82 Pdelay loss: that mastership names thisClock, {thisClock}"
     " | #82 every commit naming thisClock carries {thisClock}"),
    ("the self publication keeps the departed record", GENERATOR,
     "    p.emit(\"RDST\", rd=RT, imm=RG_SCR | S_MYPV, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_BESTPV, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=RC, imm=RG_SCR | S_BESTID, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=RC, imm=RG_SCR | S_BESTSRC, fmt=FMT_Q)\n",
     "",
     "#82 Pdelay loss: once capable, a live peer worse than D wins"),
    ("an asCapable fall leaves the receipt watch running",
     "top/KL_gptp_engine.sv",
     "                if (pub_flags_r[2] && !st_wdata_w[2]) begin\n"
     "                  tmr_arm_we_w    <= 1'b1;\n"
     "                  tmr_arm_slot_w  <= 3'd2;\n"
     "                  tmr_arm_delta_w <= 32'd1;\n"
     "                end\n",
     "",
     "#82 Pdelay loss: thisClock is committed within 2 ms of the fall"),
    ("an incapable receipt timeout keeps the elected peer", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"BR\", label=LB[\"SELF\"])\n",
     "",
     "#82 Pdelay loss: thisClock is committed within 2 ms of the fall"
     " | #82 Pdelay loss: that commit carries {thisClock}"
     " | #82 Pdelay loss: Announces from the incapable port elect nothing"),
    ("an incapable port's Announces still compete", GENERATOR,
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"out\")\n",
     "",
     "#82 Pdelay loss: Announces from the incapable port elect nothing"),
    ("the asCapable drop keeps the flags word", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"BR\", label=LB[\"SELF\"])\n",
     "    p.emit(\"BR\", label=LB[\"SELF\"])\n",
     "#82 Pdelay loss: the drop commit's flags are gmPresent alone"
     " | p1 255 #82 Pdelay loss: the drop commit's flags are gmPresent alone"),
    ("an incapable port's receipt watch is not re-armed", GENERATOR,
     "    p.emit(\"MOVE\", rd=RU, ra=0, imm=3000)\n"
     "    p.emit(\"WRST\", ra=RU, imm=RG_TMR | 2, fmt=FMT_Q)  # keep watching\n",
     "",
     "#82 Pdelay loss: once capable, with no Announce, master in 3 s"
     " | #82 Pdelay loss: that mastership names thisClock, {thisClock}"
     " | p1 255 #82 Pdelay loss: once capable, with no Announce, master in 3 s"),
    # -- every self publication carries gmPresent (10.3.13.2.4 g) ----------
    ("the published flags leave gmPresent to the microcode",
     "top/KL_gptp_engine.sv",
     "  assign pub_flags_o     = {pub_flags_r[31:1],\n"
     "                            pub_flags_r[0] | rom_gm_capable_w};\n",
     "  assign pub_flags_o     = pub_flags_r;\n",
     "#82 cold release: every cycle to the first beat has gmPresent"
     " | #82 cold release: that commit's flags are gmPresent alone"
     " | #82 warm reset: its flags are gmPresent alone"
     " | #82 peer leaves: the mastership commit has gmPresent"
     " | #82 Pdelay loss: the drop commit's flags are gmPresent alone"
     " | #82 Pdelay loss: that mastership commit has gmPresent"),
    ("the image does not mark thisClock grandmaster-capable", GENERATOR,
     "    gm_capable = RUNTIME[\"p1\"] < 255\n",
     "    gm_capable = False\n",
     "#82 cold release: every cycle to the first beat has gmPresent"
     " | #82 cold release: that commit's flags are gmPresent alone"
     " | #82 warm reset: its flags are gmPresent alone"
     " | #82 peer leaves: the mastership commit has gmPresent"
     " | #82 Pdelay loss: the drop commit's flags are gmPresent alone"
     " | #82 Pdelay loss: that mastership commit has gmPresent"),
    ("the capability mark ignores priority1", GENERATOR,
     "    gm_capable = RUNTIME[\"p1\"] < 255\n",
     "    gm_capable = True\n",
     "p1 255 #82 cold release: every cycle to the first beat has gmPresent"
     " | p1 255 #82 cold release: that commit's flags are gmPresent alone"
     " | p1 255 #82 Pdelay loss: the drop commit's flags are gmPresent alone"
     " | p1 255 #82 Pdelay loss: that mastership commit has gmPresent"),
    ("mastership sets the microcode's presence bit", GENERATOR,
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_AMGM_C | FL_SYNCOK_C)\n",
     "    e_flags(p, andm=FL_ASCAP_C,"
     " orm=FL_PRESENT_C | FL_AMGM_C | FL_SYNCOK_C)\n",
     "p1 255 #82 Pdelay loss: that mastership commit has gmPresent"),
    # ---- #84: the master role is synchronised ----------------------------
    # Each control lists, after "#84 ", every named check it must fail.
    ("becoming grandmaster clears sync-ok", GENERATOR,
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_AMGM_C | FL_SYNCOK_C)\n",
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_AMGM_C)\n",
     "#84 first mastership: the master flags carry sync-ok"
     " | #84 takeover: its commit names thisClock with sync-ok"
     " | #84 every master cycle publishes sync-ok"
     " | p1 255 #84 first mastership: the master flags carry sync-ok"
     " | p1 255 #84 every master cycle publishes sync-ok"),
    ("a queued receipt timeout clears a master's sync-ok", GENERATOR,
     "    p.emit(\"ALU\", rd=RU, ra=RT, rb=0, cnd=ALU_SHL,"
     " imm=SYNCOK_BY_AMGM_C)\n",
     "    p.emit(\"MOVE\", rd=RU, ra=0, imm=0)\n",
     "#84 takeover: a queued receipt timeout keeps sync-ok"
     " | #84 every master cycle publishes sync-ok"),
    ("the receipt timeout publishes nothing", GENERATOR,
     "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_AND)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)\n"
     "    p.emit(\"COMMIT\")\n",
     "    p.emit(\"ALU\", rd=RT, ra=RT, rb=RU, cnd=ALU_AND)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_PUB | 2, fmt=FMT_Q)\n",
     "#84 takeover: the queued receipt timeout commits after it"),
    ("dispatch ignores a busy serializer", "top/KL_gptp_engine.sv",
     "                 disp_ready_w && ser_idle_w && !disp_valid_r;",
     "                 disp_ready_w && !disp_valid_r;",
     "#84 takeover: nothing commits while dispatch is held"),
    ("mastership never publishes the master bit", GENERATOR,
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_AMGM_C | FL_SYNCOK_C)\n",
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_SYNCOK_C)\n",
     "#84 master cycles were graded"
     " | p1 255 #84 master cycles were graded"),
    ("a handover to a peer keeps sync-ok", GENERATOR,
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_PRESENT_C)\n",
     "    e_flags(p, andm=FL_ASCAP_C | FL_SYNCOK_C, orm=FL_PRESENT_C)\n",
     "#84 every handover to a peer grandmaster clears sync-ok"
     " | p1 255 #84 every handover to a peer grandmaster clears sync-ok"),
    # ---- #85: the received pathSequence plus thisClock --------------------
    # Each control lists, after "#85 ", every named check it must fail.
    ("the received path is published without thisClock",
     "top/KL_gptp_engine.sv", PATH_APPEND,
     "  wire       path_append_w = 1'b0;\n",
     "#85 direct grandmaster: count"
     " | #85 direct grandmaster: tail 1"
     " | #85 direct grandmaster: its commit names the grandmaster and path"
     " | #85 multi-hop grandmaster: count"
     " | #85 multi-hop grandmaster: tail 5"
     " | #85 multi-hop grandmaster: its commit names the grandmaster and path"
     " | #85 seven received entries: count"
     " | #85 seven received entries: tail 7"
     " | #85 seven received entries: its commit names the grandmaster and"
     " path"
     " | #85 every peer path ends with thisClock"
     " | p1 255 #85 every peer path ends with thisClock"
     " | #82 peer wins: its commit carries the peer path"
     " | #82 warm reset: the live peer carries its own path"
     " | #82 Pdelay loss: once capable, a live peer worse than D wins"
     " | adopt appends thisClock as path tail 4"
     " | worse announce retains path A tail 4"
     " | worse TLV-less announce retains path A tail 4"
     " | parent refresh appends thisClock"
     " | unknown before path current parent: tail 3"
     " | post-release C appends thisClock"
     " | #88 empty path: count"
     " | #88 empty path from the parent: count"),
    ("eight received entries take a ninth", "top/KL_gptp_engine.sv",
     PATH_APPEND,
     "  wire       path_append_w = 1'b1;\n",
     "#85 eight received entries: count"
     " | #85 eight received entries: its commit names the grandmaster and"
     " path"),
    ("seven received entries leave thisClock out", "top/KL_gptp_engine.sv",
     PATH_APPEND,
     "  wire       path_append_w = (ann_pub_count_clamped_w < 4'd7);\n",
     "#85 seven received entries: count"
     " | #85 seven received entries: tail 7"),
    # #88: 802.1AS-2020 10.3.13.2.4 f) 5)'s rule, which appends thisClock
    # only to a nonempty sequence; 2011's d) appends it to an empty one too
    ("an empty path takes no thisClock", "top/KL_gptp_engine.sv",
     PATH_APPEND,
     "  wire       path_append_w = (ann_pub_count_clamped_w != 4'd0) &&\n"
     "                             (ann_pub_count_clamped_w != 4'd8);\n",
     "#88 empty path: count"
     " | #88 empty path: head"
     " | #88 empty path: its commit names the grandmaster and path"
     " | #88 empty path from the parent: count"
     " | #88 empty path from the parent: head"
     " | #88 empty path from the parent: its commit names the grandmaster"
     " and path"),
    ("thisClock lands one slot early", "top/KL_gptp_engine.sv",
     "                             (4'(pk) == ann_pub_count_clamped_w))\n",
     "                             (4'(pk + 1) == ann_pub_count_clamped_w))\n",
     "#85 direct grandmaster: tail 1"
     " | #85 multi-hop grandmaster: tail 5"
     " | #85 every peer path ends with thisClock"
     " | #88 empty path: head"),
    ("thisClock fills every later slot", "top/KL_gptp_engine.sv",
     "                             (4'(pk) == ann_pub_count_clamped_w))\n",
     "                             (4'(pk) >= ann_pub_count_clamped_w))\n",
     "#85 direct grandmaster: tail 2"
     " | #85 direct grandmaster: tail 3"
     " | #85 direct grandmaster: tail 4"
     " | #85 direct grandmaster: tail 5"
     " | #85 direct grandmaster: tail 6"
     " | #85 direct grandmaster: tail 7"
     " | #85 multi-hop grandmaster: tail 6"
     " | #85 multi-hop grandmaster: tail 7"
     " | #88 issue shape: tail 2"
     " | #88 issue shape: tail 3"
     " | #88 issue shape: tail 4"
     " | #88 issue shape: tail 5"
     " | #88 issue shape: tail 6"
     " | #88 issue shape: tail 7"
     " | #88 two entries, stepsRemoved 5: tail 3"
     " | #88 two entries, stepsRemoved 5: tail 4"
     " | #88 two entries, stepsRemoved 5: tail 5"
     " | #88 two entries, stepsRemoved 5: tail 6"
     " | #88 two entries, stepsRemoved 5: tail 7"
     " | #88 three entries, stepsRemoved 0: tail 4"
     " | #88 three entries, stepsRemoved 0: tail 5"
     " | #88 three entries, stepsRemoved 0: tail 6"
     " | #88 three entries, stepsRemoved 0: tail 7"
     " | #88 head not the grandmaster: tail 3"
     " | #88 head not the grandmaster: tail 7"
     " | #88 empty path: tail 1"
     " | #88 empty path: tail 7"),
    ("the appended entry is the announcing source", "top/KL_gptp_engine.sv",
     "                      pub_path_r[64*pk +: 64] <= rom_clock_id_w;\n",
     "                      pub_path_r[64*pk +: 64] <= frame_cid_r;\n",
     "#85 direct grandmaster: tail 1"
     " | #85 multi-hop grandmaster: tail 5"
     " | #85 every peer path ends with thisClock"),
    ("the received entries are not copied", "top/KL_gptp_engine.sv",
     PATH_COPY,
     "                      pub_path_r[64*pk +: 64] <= 64'd0;\n",
     "#85 direct grandmaster: head"
     " | #85 multi-hop grandmaster: head"
     " | #85 multi-hop grandmaster: tail 1"
     " | #85 multi-hop grandmaster: tail 2"
     " | #85 multi-hop grandmaster: tail 3"
     " | #85 multi-hop grandmaster: tail 4"
     " | #85 seven received entries: tail 1"
     " | #85 seven received entries: tail 2"
     " | #85 seven received entries: tail 3"
     " | #85 seven received entries: tail 4"
     " | #85 seven received entries: tail 5"
     " | #85 seven received entries: tail 6"
     " | #85 eight received entries: tail 1"
     " | #85 eight received entries: tail 2"
     " | #85 eight received entries: tail 3"
     " | #85 eight received entries: tail 4"
     " | #85 eight received entries: tail 5"
     " | #85 eight received entries: tail 6"
     " | #85 eight received entries: tail 7"),
    ("every received path is published as {thisClock}",
     "top/KL_gptp_engine.sv",
     "  wire [3:0] ann_pub_count_clamped_w = (ann_pub_count_r > 8'd8)\n"
     "      ? 4'd8 : ann_pub_count_r[3:0];\n",
     "  wire [3:0] ann_pub_count_clamped_w = 4'd0;\n",
     "#85 direct grandmaster: count"
     " | #85 multi-hop grandmaster: count"
     " | #85 eight received entries: count"
     " | #88 issue shape: count"
     " | #87 G1 elected: count"),
    # ---- #88: a)-c) are the only Announce disqualifications ---------------
    # The base's lengthField/8 == stepsRemoved+1 refusal, restored beside
    # the stepsRemoved capture (frame index 76) it needs.
    ("the path-count refusal restored", "wire/KL_gptp_rx_parser.sv",
     PT_HDR_BAD,
     "  logic [15:0] mut_steps_r;\n"
     "  always_ff @(posedge clk_i)\n"
     "    if (rx_valid_i && (cnt_r == 11'd76)) mut_steps_r <= acc_nxt_w[15:0];\n"
     + PT_HDR_BAD_HEAD +
     "        (ann_tlv_len_w[2:0] || pt_seen_r ||\n"
     "         ({1'b0, ann_tlv_len_w[15:3]} != ({1'b0, mut_steps_r} + 17'd1)))));\n",
     "#88 issue shape: elected"
     " | #88 issue shape: no longer master"
     " | #88 issue shape: count"
     " | #88 issue shape: no Announce for one interval"
     " | #88 two entries, stepsRemoved 5: elected"
     " | #88 three entries, stepsRemoved 0: elected"
     " | #88 own source, one entry, stepsRemoved 3: parser-drop policy"
     " | #88 stepsRemoved 255, one entry: parser-drop policy"
     " | #88 short loop, stepsRemoved 5: parser-drop policy"),
    # The base's head refusal: the first entry compared with
    # grandmasterIdentity, the whole Announce refused on a mismatch
    ("the path-head refusal restored", "wire/KL_gptp_rx_parser.sv",
     PT_HEAD_EDITS, None,
     "#88 head not the grandmaster: elected"
     " | #88 head not the grandmaster: no longer master"
     " | #88 head not the grandmaster: entry 0 is the received head"
     " | #88 head not the grandmaster: no Announce for one interval"
     " | #88 head not the grandmaster: parser accepts"
     " | #88 current parent's path headed elsewhere: one commit"
     " | #88 current parent's path headed elsewhere: entry 0 is the received"
     " head"
     " | #88 current parent's path headed elsewhere: parser accepts"
     " | #88 parent path headed elsewhere: head"
     " | #88 parent path headed elsewhere: parser accepts"),
    # The base's nonzero rule: an empty pathSequence refused
    ("the empty-path refusal restored", "wire/KL_gptp_rx_parser.sv",
     PT_HDR_BAD,
     PT_HDR_BAD_HEAD +
     "        ((ann_tlv_len_w == 16'd0) || ann_tlv_len_w[2:0] || pt_seen_r)));\n",
     "#88 empty path: elected"
     " | #88 empty path: its commit names the grandmaster and path"
     " | #88 empty path from the parent: count"
     " | #88 empty path from the parent: parser accepts"),
    # The {grandmasterIdentity, tail} sequence no peer sent: entry 0 taken
    # from the frozen Announce's grandmasterIdentity, not its received head
    ("the received head replaced by the grandmaster", "top/KL_gptp_engine.sv",
     PATH_COPY,
     "                      pub_path_r[64*pk +: 64] <= (pk == 0) ?\n"
     "                          ann_ctx_r[9] : ann_pub_path_r[64*pk +: 64];\n",
     "#88 head not the grandmaster: entry 0 is the received head"
     " | #88 head not the grandmaster: its commit names the grandmaster and"
     " path"
     " | #88 current parent's path headed elsewhere: entry 0 is the received"
     " head"
     " | #88 parent path headed elsewhere: head"
     " | #87 parent refresh without a TLV: head"),
    ("the received head is not published", "top/KL_gptp_engine.sv",
     PATH_COPY,
     "                      pub_path_r[64*pk +: 64] <= (pk == 0) ?\n"
     "                          64'd0 : ann_pub_path_r[64*pk +: 64];\n",
     "#85 direct grandmaster: head"
     " | #88 issue shape: entry 0 is the received head"
     " | adopt publishes path head"
     " | worse announce retains path A head"
     " | worse TLV-less announce retains path A head"
     " | deep path retains its head"
     " | parent refresh publishes path C head"
     " | unknown-only current parent: keeps the previous head"
     " | unknown before path current parent: head"
     " | full path before raw empty: head"
     " | TLV-less current parent: keeps the previous head"
     " | frozen queued A head coherent"
     " | post-release C head coherent"
     " | boundary-clean announce: raw path head"
     " | #87 G1 elected: head"),
    # ---- #87: no TLV keeps the previous pathTrace ------------------------
    # 802.1AS-2020's empty sequence for a TLV-less Announce
    ("the empty sequence published without a TLV", "top/KL_gptp_engine.sv",
     PATH_KEEP,
     "                if (!ann_pub_present_r) begin\n"
     "                  pub_path_count_r <= 4'd0;\n"
     "                  pub_path_r       <= '0;\n"
     "                end else begin\n",
     "#87 G1 to G2 without a TLV: count"
     " | #87 G1 to G2 without a TLV: its commit names the grandmaster and"
     " path"
     " | #87 parent refresh without a TLV: count"
     " | #85 absent path: count"
     " | TLV-less competition control: raw path count"
     " | #87 post-warm-reset TLV-less count"
     " | #87 post-warm-reset TLV-less selection commits {thisClock}"
     " | TLV-less current parent: keeps the previous count"
     " | unknown-only current parent: keeps the previous count"
     " | out-of-message fake PathTrace: keeps the previous count"
     " | #87 raw-empty overload: frozen A keeps C's path"
     " | #85 every peer path ends with thisClock"),
    # an absent TLV staged as an empty one, which publishes {thisClock}
    ("a TLV-less Announce publishes {thisClock}", "top/KL_gptp_engine.sv",
     PATH_KEEP,
     "                if (1'b1) begin\n",
     "#87 G1 to G2 without a TLV: count"
     " | #87 G1 to G2 without a TLV: head"
     " | #87 parent refresh without a TLV: head"
     " | TLV-less current parent: keeps the previous count"
     " | unknown-only current parent: keeps the previous head"
     " | out-of-message fake PathTrace: keeps tail 7"
     " | #87 raw-empty overload: frozen A keeps C's path"),
    # ---- #82: {thisClock} is thisClock at entry 0 -------------------------
    ("the self path leaves entry 0 empty", "top/KL_gptp_engine.sv",
     "  wire [8*64-1:0] self_path_w = {{7*64{1'b0}}, rom_clock_id_w};\n",
     "  wire [8*64-1:0] self_path_w = '0;\n",
     "#82 cold release: every cycle to the first beat has {thisClock}"
     " | #82 cold release: that commit carries thisClock and {thisClock}"
     " | self path entry 0 is thisClock"
     " | own-GM transition publishes thisClock at entry 0"
     " | #87 post-warm-reset TLV-less head"
     " | #87 the degraded G2 yields with {thisClock}"
     " | #82 every commit naming thisClock carries {thisClock}"
     " | p1 255 self path entry 0 is thisClock"
     " | p1 255 #82 every commit naming thisClock carries {thisClock}"),
    # a), b) and c) themselves, each removed from qualifyAnnounce: the #88
    # probes carry a count other than stepsRemoved+1, so only the microcode
    # refusal can hold the plane's mastership
    ("(a) the own-source refusal removed", GENERATOR,
     "    p.emit(\"CMP\", ra=RD_, rb=RT, fmt=FMT_Q)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"out\")\n"
     "    # (b) stepsRemoved >= 255",
     "    p.emit(\"CMP\", ra=RD_, rb=RT, fmt=FMT_Q)\n"
     "    # (b) stepsRemoved >= 255",
     "#88 own source, one entry, stepsRemoved 3: still master"
     " | #88 own source, one entry, stepsRemoved 3: gm still us"
     " | #88 own source, one entry, stepsRemoved 3: flags untouched"
     " | #88 own source, one entry, stepsRemoved 3: raw vector never published"),
    ("(b) the stepsRemoved refusal removed", GENERATOR,
     "    p.emit(\"BRS\", cnd=BRS_LT, label=\"steps_ok\")\n"
     "    p.emit(\"BR\", label=\"out\")\n"
     "    p.label(\"steps_ok\")\n",
     "    p.emit(\"BRS\", cnd=BRS_LT, label=\"steps_ok\")\n"
     "    p.label(\"steps_ok\")\n",
     "#88 stepsRemoved 255, one entry: still master"
     " | #88 stepsRemoved 255, one entry: gm still us"
     " | #88 stepsRemoved 255, one entry: parent still us"
     " | #88 stepsRemoved 255, one entry: flags untouched"
     " | #88 stepsRemoved 255, one entry: raw vector never published"),
    ("(c) the PathTrace loop refusal removed", GENERATOR,
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"qualified\")\n"
     "    p.emit(\"BR\", label=\"out\")\n"
     "    p.label(\"qualified\")\n",
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"qualified\")\n"
     "    p.label(\"qualified\")\n",
     "#88 short loop, stepsRemoved 5: still master"
     " | #88 short loop, stepsRemoved 5: gm still us"
     " | #88 short loop, stepsRemoved 5: parent still us"
     " | #88 short loop, stepsRemoved 5: flags untouched"
     " | #88 short loop, stepsRemoved 5: raw vector never published"),
    # 10.3.5: the current parent's own Announce replaces the best record
    # unconditionally; made to compete instead, a degraded parent keeps it
    ("a parent update must beat the best", GENERATOR,
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"take\")"
     "                 # parent update\n",
     "",
     "#88 issue shape: the degraded grandmaster yields"
     " | #88 two entries, stepsRemoved 5: the degraded grandmaster yields"
     " | #88 three entries, stepsRemoved 0: the degraded grandmaster yields"),
]


def edits_of(pattern, replacement) -> list[tuple[str, str]]:
    """A mutant's (pattern, replacement) pairs: one pair, or, with the
    replacement None, the list of pairs the pattern holds."""
    return list(pattern) if replacement is None else [(pattern, replacement)]


def stage(work: Path, tag: str,
          mutate: tuple[str, list[tuple[str, str]]] | None = None) -> Path:
    """A directory holding the RTL and the generator, with at most one
    file mutated by its edits. Nothing outside the returned directory is
    written."""
    srcdir = work / f"src_{tag}"
    for name in RTL_SOURCES + (GENERATOR,):
        target = srcdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (HDL / name).read_text(encoding="utf-8")
        if mutate is not None and mutate[0] == name:
            for pattern, replacement in mutate[1]:
                text = text.replace(pattern, replacement)
        target.write_text(text, encoding="utf-8")
    return srcdir


def generate_image(srcdir: Path, rundir: Path) -> bool:
    """Write the suite's ROM images from `srcdir`'s generator: the shipping
    one in `rundir`, the fourth pass's in `rundir`/p1run. False when the
    generator refuses, which for a packing failure is a real answer."""
    for d, extra in ((rundir, ()), (rundir / "p1run", P1_GENARGS)):
        d.mkdir(parents=True, exist_ok=True)
        out = subprocess.run(
            [sys.executable, str(srcdir / GENERATOR), *GENARGS, *extra,
             "-o", str(d / "gptp_ucode.hex")],
            capture_output=True, text=True)
        if out.returncode != 0 or not (d / "gptp_ucode.hex").is_file():
            return False
    return True


def build(srcdir: Path, work: Path, tag: str) -> Path | None:
    """Build the harness against the RTL in `srcdir`; the exe, or None."""
    mdir = work / f"obj_{tag}"
    exe_name = f"Vengine_{tag}"
    out = subprocess.run(
        ["verilator", *VFLAGS, "--Mdir", str(mdir),
         "-CFLAGS", f"-std=c++17 -O2 -I{HERE} -Wall -Wextra",
         *[str(srcdir / s) for s in RTL_SOURCES],
         str(HERE / "sim_main.cpp"), "-o", exe_name],
        capture_output=True, text=True)
    exe = mdir / exe_name
    if out.returncode != 0 or not exe.is_file():
        return None
    return exe


def run_harness(exe: Path, rundir: Path) -> tuple[int, str]:
    """(rc, output) of one harness run, reading its image from `rundir`,
    followed by the fourth pass from `rundir`/p1run.

    The two tallies become one, so a failure in either pass is a failure of
    the run. A pass that printed no tally keeps both runs' raw output with
    no tally, and verdict() then names the abort rather than a catch.

    No host deadline: every wait in sim_main.cpp is bounded in DUT cycles and
    reports its own timeout as a failed check, so a mutant that wedges the
    plane still returns a verdict.
    """
    runs = [subprocess.run([str(exe), *arg], cwd=str(d),
                           capture_output=True, text=True)
            for d, arg in ((rundir, ()), (rundir / "p1run", (P1_PLUSARG,)))]
    rc = next((r.returncode for r in runs if r.returncode), 0)
    outs = [r.stdout + r.stderr for r in runs]
    tallies = [TALLY.search(o) for o in outs]
    body = "".join(TALLY.sub("", o) for o in outs)
    if not all(tallies):
        return rc, body
    total = sum(int(m.group(1)) for m in tallies)
    failed = sum(int(m.group(3)) for m in tallies)
    return rc, f"{body}{total} checks: {total - failed} PASS, {failed} FAIL\n"


def _named_failure(failed: list[str], want: str) -> str | None:
    """The first of the `failed` lines that names the check `want`, from the
    pass `want` names: one with the `P1_PREFIX` matches only fourth-pass
    failures, any other name only shipping-pass failures. None if absent."""
    pass_tag = "FAIL " + P1_PREFIX
    mine = want.startswith(P1_PREFIX)
    return next((line for line in failed
                 if want in line
                 and line.startswith(pass_tag) == mine),
                None)


def named_verdict(answer: str, breaks: str, output: str) -> str:
    """`answer`, unless a caught control missed a check its `breaks` names.

    Prints the failed line of each named check it finds. Any other answer,
    and a control that names no check, is returned unchanged.
    """
    # #75 controls must fail their specific behavioral check; an
    # unrelated existing failure cannot stand in for that evidence.
    if breaks.startswith("slew:") and answer == "caught":
        named = [line for line in output.splitlines()
                 if line.startswith("FAIL ") and breaks in line
                 and not line.startswith("FAIL " + P1_PREFIX)]
        if not named:
            answer = "missed its named check"
        else:
            print(named[0])
    # #82, #84, #85 and #88 controls must fail every check they name, for
    # the same reason: each of those checks needs its own failing defect.
    if breaks.startswith(("#82 ", "#84 ", "#85 ", "#88 ", P1_PREFIX)) and \
            answer == "caught":
        failed = [line for line in output.splitlines()
                  if line.startswith("FAIL ")]
        missed = [want for want in breaks.split(" | ")
                  if _named_failure(failed, want) is None]
        if missed:
            answer = ("missed its named check(s): "
                      + "; ".join(missed))
        else:
            for want in breaks.split(" | "):
                print(_named_failure(failed, want))
    return answer


def run_mutant(work: Path, clean_exe: Path,
               mutation: tuple) -> bool:
    """Plant one of the `MUTATIONS` under `work` and print its verdict.

    True when the harness catches it, through every check it names; False,
    with the reason printed, when it survived, did not build, its image was
    refused, or its pattern no longer appears exactly once.
    """
    name, fname, pattern, replacement, breaks = mutation
    edits = edits_of(pattern, replacement)
    src = (HDL / fname).read_text(encoding="utf-8")
    for pat, _ in edits:
        if src.count(pat) != 1:
            print(f"[FAIL] mutation {name!r}: its pattern appears "
                  f"{src.count(pat)} time(s) in {fname}, expected "
                  f"exactly 1. The source moved and this mutant is no "
                  f"longer mutating anything - fix the pattern, do not "
                  f"delete the arm.")
            return False
    tag = "".join(c if c.isalnum() else "_" for c in name)
    srcdir = stage(work, tag, (fname, edits))
    rundir = work / f"run_{tag}"
    if not generate_image(srcdir, rundir):
        print(f"[FAIL] mutation {name!r}: the generator refused its "
              f"image, so this mutant proves nothing about the "
              f"harness")
        return False
    if fname == GENERATOR:
        exe = clean_exe          # only the ROM image differs
    else:
        exe = build(srcdir, work, tag)
    if exe is None:
        print(f"[FAIL] mutation {name!r} did not build; a mutant that "
              f"cannot build proves nothing about the harness")
        return False
    rc, output = run_harness(exe, rundir)
    answer = named_verdict(verdict(rc, output), breaks, output)
    if answer == "caught":
        print(f"[PASS] mutant caught: {name} - breaks \"{breaks}\"")
        return True
    if answer == "pass":
        print(f"[FAIL] mutant SURVIVED: {name}. The harness does not "
              f"prove \"{breaks}\".")
    else:
        print(f"[FAIL] mutant {name!r} {answer}")
    return False


def main() -> int:
    """Run the control and every mutant, and report the arm's exit status.

    0 when the unmutated sources pass and every mutant is caught; 1 when any
    mutant survived, failed to build, or no longer matches its pattern, each
    printed with the property it was defending.
    """
    passes = fails = 0
    with tempfile.TemporaryDirectory(prefix="engine-mutants-") as td:
        work = Path(td)

        # -- positive control: the real sources must still pass -------------
        clean_src = stage(work, "clean")
        clean_run = work / "run_clean"
        clean_exe = build(clean_src, work, "clean")
        if clean_exe is None or not generate_image(clean_src, clean_run):
            print("[FAIL] the unmutated sources did not build; every mutant "
                  "result below would be meaningless")
            return 1
        answer = verdict(*run_harness(clean_exe, clean_run))
        if answer == "pass":
            passes += 1
            print("[PASS] the unmutated engine still passes the harness")
        else:
            fails += 1
            print(f"[FAIL] the unmutated engine does NOT pass ({answer}) - "
                  f"every mutant result below is meaningless")

        # -- each mutant must be caught --------------------------------------
        for mutation in MUTATIONS:
            if run_mutant(work, clean_exe, mutation):
                passes += 1
            else:
                fails += 1

    total = passes + fails
    print(f"\n{total} checks: {passes} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
