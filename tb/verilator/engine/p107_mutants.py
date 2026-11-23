# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The #107 controls of the engine mutation arm (`mutants.py`).

FPGA-gPTP #107: this plane follows grandmasters up to +-100 ppm from this
oscillator, and a mastership runs on this oscillator (802.1AS-2020
10.1.2.1, 10.2.4.14). BECOME's PHC word-3 write carries rate 0 in its
low word, which the engine always applies, and the integrator in its
high word, which is the frequency change scaledLastGmFreqChange sends
(11.4.4.3.9). Each control here lists, after its issue number, every
named check it must fail. `mutants.py` runs them with the rest of the
arm.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only.
"""

from p100_mutants import ENGINE, TLV_DLT
from receipt_mutants import GENERATOR

#: BECOME's word-3 operand: the integrator moved to the high word
BECOME_SHL = ("    p.emit(\"ALU\", rd=RT, ra=RT, rb=0, cnd=ALU_SHL, imm=32)\n")
#: the engine's word-3 rate write
WORD3 = ("                phc_addend_we_o <= 1'b1;\n"
         "                phc_addend_o    <= st_wdata_w[31:0];\n"
         "                phc_slew_left_r   <= 2'd0;\n")
#: mastership clears the slave rate seen
UNSEEN = "      else if (tlv_become_w) slave_rate_seen_r <= 1'b0;\n"
#: the trim limit, which is the follow range against this oscillator
RATE = "RATE_PPM_C = 200                # the rate envelope"
#: one trim unit in the TLV's 2^41 scale
TLV_K = "      ((64'(CLK_HZ_P) << 33) + 64'd500_000_000)"

TAKEOVER = ("#107 takeover: one rate write, this oscillator's within one trim"
            " unit")
OSC = "slew: mastership runs on this oscillator"
SETTLED_RATE = "#100 TLV settled: BECOME writes rate 0, this oscillator"
IDLE_RATE = "slew: idle timeout writes only mastership's rate 0"
FREQ = ": scaledLastGmFreqChange is rate 0 less the estimate"
SETTLED = "#100 TLV settled"
SLEWING = "#100 TLV slewing"
UNFOLLOWED = "#107 TLV unfollowed"
TLV61 = ": scaledLastGmFreqChange is the change of the time base"
PLUS10 = "#107 TLV after a grandmaster +10 ppm"
MINUS10 = "#107 TLV after a grandmaster -10 ppm"
FOLLOW = ": the trim settles within 0.2 ppm of it"
NEAR = ": its offset stays within 1 us"

#: (name, file under hdl/, pattern, replacement, the checks it must fail)
P107_MUTATIONS = [
    # ---- #107: the rate of a mastership -----------------------------------
    # the defect #107 repairs: BECOME as 1616fc8f had it, the time base
    # keeping the slave's estimate, wound or not
    ("a mastership keeps the slave's rate", GENERATOR,
     BECOME_SHL,
     "    p.emit(\"ALU\", rd=RT, ra=R0, rb=RT, cnd=ALU_SUB)\n",
     f"{TAKEOVER} | {OSC} | {SETTLED_RATE}"),
    # the 1616fc8f engine: word 3 applied only while a slew was active
    ("word 3 applies only during a slew", ENGINE,
     WORD3,
     "                if (phc_slew_active_o) begin\n"
     "                  phc_addend_we_o <= 1'b1;\n"
     "                  phc_addend_o    <= st_wdata_w[31:0];\n"
     "                end\n"
     "                phc_slew_left_r   <= 2'd0;\n",
     f"{SETTLED_RATE} | {IDLE_RATE}"
     f" | {UNFOLLOWED}: BECOME writes rate 0, and only it"),
    # ---- #107: scaledLastGmFreqChange -------------------------------------
    ("scaledLastGmFreqChange has its sign inverted", ENGINE,
     TLV_DLT,
     TLV_DLT.replace("25'(st_wdata_w[63:32])",
                     "25'(-$signed(st_wdata_w[63:32]))"),
     f"{SETTLED}{FREQ} | {SLEWING}{FREQ} | {PLUS10}{TLV61}"
     f" | {MINUS10}{TLV61}"),
    # the trim the PHC kept, proportional term and all, not the estimate
    ("scaledLastGmFreqChange is the last trim's", ENGINE,
     TLV_DLT,
     TLV_DLT.replace("25'(st_wdata_w[63:32])", "25'(-phc_addend_o)"),
     f"{SETTLED}{FREQ} | {SLEWING}{FREQ}"),
    # a quarter of the change, which the qual's 50 % grading must refuse
    ("scaledLastGmFreqChange is scaled by 2^39", ENGINE,
     TLV_K,
     TLV_K.replace("<< 33", "<< 31"),
     f"{SETTLED}{FREQ} | {PLUS10}{TLV61} | {MINUS10}{TLV61}"),
    # a mastership with no slave rate since the last one reports the stale
    # estimate, though the time base never left this oscillator
    ("a mastership leaves the slave rate seen", ENGINE,
     UNSEEN,
     "",
     f"{UNFOLLOWED}{FREQ}"),
    # ---- #107: the follow range (phase 59) --------------------------------
    # a trim short of 802.1AS-2020 B.1.1's two 100 ppm LocalClocks
    ("the trim stops short of a grandmaster 100 ppm away", GENERATOR,
     RATE,
     RATE.replace("= 200 ", "= 99  "),
     "#107 a grandmaster +100 ppm" + FOLLOW
     + " | #107 a grandmaster +100 ppm" + NEAR
     + " | #107 a grandmaster -100 ppm" + FOLLOW
     + " | #107 a grandmaster -100 ppm" + NEAR),
]
