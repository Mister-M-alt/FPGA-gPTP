# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The #100 controls of the engine mutation arm (`mutants.py`).

FPGA-gPTP #100 fills the Follow_Up information TLV of this plane's
mastership (802.1AS-2011 10.2.8.2.1 j) to l), 10.2.9, 11.4.4.3), times the
announce receipt watch from the received logMessageInterval (10.3.9.1),
and takes three stricter readings: an Announce at the timeout instant ages
the port, a Pdelay_Resp later than the Milan v1.2 4.2.6.2.6 bound is a lost
response, and the default clockAccuracy is 0x22 (8.6.2.3). Each control
here lists, after its issue number, every named check it must fail.
`mutants.py` runs them with the rest of the arm.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only.
"""

from receipt_mutants import GENERATOR

#: the engine top, under hdl/, which the RTL controls mutate
ENGINE = "top/KL_gptp_engine.sv"

#: the Follow_Up leg's reads of the three TLV words
TLV_TX = ("        p.emit(\"RDST\", rd=RT, imm=RG_TLV | word, fmt=FMT_Q)\n"
          "        p.emit(\"BFLD\", ra=RT, fmt=fmt)\n")
#: the late-response branch of the Pdelay tail
LATE_END = ("    p.emit(\"END\")                                    "
            "# late: lost\n")
#: the late-response bound's three guards
LATE_PPM = ("                  * (1_000_000 + LOCAL_CLOCK_PPM_C"
            " + RATE_PPM_C)\n")
LATE_LINK = "(PD_TURNAROUND_MAX_NS_C + 2 * NPD_HI_C)"
LATE_GRAIN = "                + 2 * LOCAL_CLOCK_GRAIN_NS_C)\n"
#: the frequency change's operands, taken at BECOME's PHC word-3 write
TLV_DLT = ("        tlv_dlt_r <= (phc_slew_active_o || !phc_rate_seen_r)"
           " ? 25'sd0\n"
           "                   : 25'(phc_addend_o - st_wdata_w[31:0]);\n")
#: the Announce handler's slot-2 arm, anchored at its Announce
ARM = ("            tmr_arm_delta_w <= tmr_wr_delta_w;\n"
       "            //! #100: an Announce's watch, anchored at its arrival\n"
       "            tmr_arm_anchor_r    <= ann_anchor_w;\n")
LATE_ANN = ("  wire        w2_late_w = w2_armed_r &&\n"
            "                          ($signed(ann_arr_ms_r - w2_dl_r)"
            " >= 0);\n")
#: phase 54's trials that the engine must age through its forced expiry
FORCED = ("#100 3.0 s apart, a clock after the tick: the port is aged"
          " | #100 3.0 s apart, two clocks after the tick: the port is aged")
STALLED = ("#100 a stalled handler: an Announce received before the deadline"
           " refreshes the watch")
SETTLED = "#100 TLV settled"
SLEWING = "#100 TLV slewing"
TBI = ": gmTimeBaseIndicator increments"
PHASE = ": lastGmPhaseChange is the last offset"
FREQ = ": scaledLastGmFreqChange is the kept trim less the estimate"

#: (name, file under hdl/, pattern, replacement, the checks it must fail)
P100_MUTATIONS = [
    # ---- #100: the Follow_Up information TLV -------------------------------
    # word-neutral: the defect #100 repairs, every field sent zero
    ("the Follow_Up TLV is sent zero", GENERATOR,
     TLV_TX,
     TLV_TX.replace("ra=RT, fmt=fmt", "ra=0, fmt=fmt"),
     "#100 TLV: the first mastership's Follow_Up carries indicator 1"
     f" | {SETTLED}{TBI} | {SETTLED}{PHASE} | {SETTLED}{FREQ}"
     f" | {SLEWING}{TBI} | {SLEWING}{PHASE}"),
    ("gmTimeBaseIndicator does not count mastership", ENGINE,
     "    if (tlv_become_w) tlv_tbi_r <= tlv_tbi_r + 16'd1;\n",
     "",
     "#100 TLV: the first mastership's Follow_Up carries indicator 1"
     f" | {SETTLED}{TBI} | {SLEWING}{TBI}"),
    ("lastGmPhaseChange is zero", ENGINE,
     "  wire  [95:0] tlv_phase_w = {{16{tlv_off_w[63]}}, tlv_off_w, 16'd0};\n",
     "  wire  [95:0] tlv_phase_w = 96'd0;\n",
     f"{SETTLED}{PHASE} | {SLEWING}{PHASE}"),
    ("lastGmPhaseChange is not ScaledNs", ENGINE,
     "  wire  [95:0] tlv_phase_w = {{16{tlv_off_w[63]}}, tlv_off_w, 16'd0};\n",
     "  wire  [95:0] tlv_phase_w = {{32{tlv_off_w[63]}}, tlv_off_w};\n",
     f"{SETTLED}{PHASE} | {SLEWING}{PHASE}"),
    ("lastGmPhaseChange drops the offset's high word", ENGINE,
     "        pub_offset_hi_r <= st_wdata_w[63:32];\n",
     "        pub_offset_hi_r <= 32'd0;\n",
     f"{SLEWING}{PHASE}"),
    ("scaledLastGmFreqChange is zero", ENGINE,
     "      if (tlv_mul_r) tlv_freq_r <= 32'(tlv_prod_w >>> 16);\n",
     "",
     f"{SETTLED}{FREQ}"),
    ("scaledLastGmFreqChange is the rate estimate", ENGINE,
     TLV_DLT,
     TLV_DLT.replace("25'(phc_addend_o - st_wdata_w[31:0])",
                     "25'(st_wdata_w[31:0])"),
     f"{SETTLED}{FREQ}"),
    ("a slewing mastership reports its last trim", ENGINE,
     TLV_DLT,
     TLV_DLT.replace("(phc_slew_active_o || !phc_rate_seen_r)",
                     "(!phc_rate_seen_r)"),
     f"{SLEWING}{FREQ}"),
    ("a rate unknown since reset is taken as zero", ENGINE,
     TLV_DLT,
     TLV_DLT.replace("(phc_slew_active_o || !phc_rate_seen_r)",
                     "(phc_slew_active_o)"),
     "#100 TLV: a mastership after a warm reset, no rate written since,"
     " carries no phase or frequency change"),
    # ---- #100: the announce receipt watch (10.3.9.1, Figure 10-13) ---------
    ("the watch ignores the received interval", ENGINE,
     "  wire [31:0] ann_dl_w  = ann_arr_ms_r + ann_rto_ms(ann_log_r);\n",
     "  wire [31:0] ann_dl_w  = ann_arr_ms_r + ANN_RTO_MS_C;\n",
     "#100 logAnnounceInterval 1: still slave 5998 ms after the Announce"
     " | #100 logAnnounceInterval -1: master within 1502 ms of the Announce"),
    ("a negative interval lengthens the watch", ENGINE,
     "      ann_rto_ms = ANN_RTO_MS_C >> (5'(-$signed(lg)));\n",
     "      ann_rto_ms = ANN_RTO_MS_C << (5'(-$signed(lg)));\n",
     "#100 logAnnounceInterval -1: master within 1502 ms of the Announce"),
    ("the watch counts from the handler", ENGINE,
     ARM,
     ARM.replace("tmr_arm_delta_w <= tmr_wr_delta_w",
                 "tmr_arm_delta_w <= st_wdata_w[31:0]")
        .replace("tmr_arm_anchor_r    <= ann_anchor_w",
                 "tmr_arm_anchor_r    <= 1'b0"),
     "#100 3.0 s apart, nine clocks before a tick: the port is aged"
     " | #100 logAnnounceInterval 1: still slave 5998 ms after the Announce"),
    ("a late Announce runs before the expiry", ENGINE,
     "  wire ann_force_w = !evq_empty_w &&\n"
     "                     (ev_head_w[39:32] == EV_RX_ANNOUNCE_C)"
     " && w2_late_w;\n",
     "  wire ann_force_w = 1'b0;\n",
     FORCED),
    ("an Announce at the instant refreshes the port", ENGINE,
     LATE_ANN,
     LATE_ANN.replace(">= 0);", "> 0);"),
     FORCED),
    ("lateness is judged at dispatch", ENGINE,
     LATE_ANN,
     LATE_ANN.replace("ann_arr_ms_r - w2_dl_r", "ms_now_w - w2_dl_r"),
     STALLED),
    # a dispatched expiry takes its watch. An expiry leg that leaves slot 2
    # alone (a master's) would otherwise keep the watch due, so every later
    # Announce would wait behind expiries forever and the plane wedge
    ("a dispatched expiry leaves its watch armed", ENGINE,
     "  assign t2_take_w  = t2_force_w ||"
     " (pop_w && head_t2_w && !t2_stale_w);\n",
     "  assign t2_take_w  = 1'b0;\n",
     "#90 no response: runs from a capable plane"
     " | #90 no response: request 1 goes out"),
    ("a stale expiry dispatches", ENGINE,
     "  wire t2_stale_w  = head_t2_w && !w2_due_w;\n",
     "  wire t2_stale_w  = 1'b0;\n",
     STALLED),
    # ---- #100: late Pdelay responses (Milan v1.2 4.2.6.2.6) ----------------
    ("a late response completes its exchange", GENERATOR,
     LATE_END,
     "",
     "#100 late responses: the fifth clears asCapable"
     " | #100 late responses: none moves the delay"),
    ("the late bound is one nanosecond short", GENERATOR,
     "imm=PD_LATE_NS_C + 1)",
     "imm=PD_LATE_NS_C)",
     "#100 responses at the bound: six keep asCapable"
     " | #100 responses at the bound: the delay is published"),
    ("the late bound leaves out the clock tolerance", GENERATOR,
     LATE_PPM,
     "                  * 1_000_000\n",
     "#100 responses at the bound: six keep asCapable"),
    ("the late bound leaves out the link", GENERATOR,
     LATE_LINK,
     "(PD_TURNAROUND_MAX_NS_C)",
     "#100 responses at the bound: six keep asCapable"),
    ("the late bound leaves out the timestamp granules", GENERATOR,
     LATE_GRAIN,
     "                )\n",
     "#100 responses at the bound: six keep asCapable"),
    # ---- #100: clockAccuracy (802.1AS-2011 8.6.2.3) ------------------------
    ("the default clockAccuracy is unknown", GENERATOR,
     "CQ_C = 0xF822436A ",
     "CQ_C = 0xF8FE436A ",
     "#100 the default image announces clockAccuracy 0x22"),
    ("--clock-accuracy is ignored", GENERATOR,
     "    RUNTIME[\"cq\"] = (CQ_C & ~mask)"
     " | (accuracy << CQ_ACCURACY_SHIFT_C)\n",
     "    RUNTIME[\"cq\"] = CQ_C\n",
     "p1 255 #100 a --clock-accuracy 0xFE image announces 0xFE"),
]
