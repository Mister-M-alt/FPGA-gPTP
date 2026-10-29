# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The portEnabled controls of the engine mutation arm (`mutants.py`).

FPGA-gPTP #94 gives the engine portEnabled (802.1AS-2011 10.2.4.11). Its
edges leave NOT_ENABLED through INITIAL_SEND_PDELAY_REQ (Figure 11-8, Cor1
and Cor2) and end the Milan v1.2 4.2.6.2.5 cease; a disabled port sends
nothing. Each control here lists, after its issue number, every named check
it must fail. `mutants.py` runs them with the rest of the arm.

Two writes of the NOT_ENABLED leg have no control, recorded rather than
hidden. S_CEASECNT is read only behind S_CEASE, which the same leg clears,
so its zero write is the cell's documented invariant, not a behaviour. The
S_MULTI write matters only when a second responder's Pdelay_Resp lands
between the leg and the request beat queued right behind it; the interval
clear the leg also makes otherwise restarts the streak at that beat.

Three disable paths have controls of their own: a frame stalled on the
byte face (withdrawn before its first byte, completed after it, and never
holding NOT_ENABLED back), an exchange still armed or queued at the fall,
and a warm reset released with the port disabled.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only.
"""

from receipt_mutants import GENERATOR

#: the engine top, under hdl/, which the RTL controls mutate
ENGINE = "top/KL_gptp_engine.sv"

#: the edge test of the portEnabled block
EDGE = "      if (port_ref_r && (port_enabled_i != port_en_r)) begin\n"
#: the serializer, whose unstarted frame a disabled port withdraws
TXSLOT = "wire/KL_gptp_tx_slot.sv"
DROP = "  assign ser_drop_w = cancel_i && ser_sof_r;\n"
#: the engine's withdrawal input to it
CANCEL = "      .cancel_i   (!port_en_r),\n"
#: NOT_ENABLED's own dispatch, ahead of the result and the queue
PE_POP = "  assign pe_pop_w   = pe_noten_r && disp_ready_w && !disp_valid_r;\n"
#: the checks every stalled byte position of phase 49 makes
STALL_K = (1, 34, 67)


def at_each_stall(check: str) -> str:
    """`check` of phase 49, named at each of its byte positions."""
    return " | ".join(f"#94 stalled at byte {k}: {check}" for k in STALL_K)


#: (name, file under hdl/, pattern, replacement, the checks it must fail)
PORT_MUTATIONS = [
    # ---- #94: the NOT_ENABLED leg (timer slot 6) ---------------------------
    ("a portEnabled edge keeps the cease", GENERATOR,
     "    for s in (S_CEASE, S_CEASECNT, S_MULTI, S_RSPSEQ):\n",
     "    for s in (S_CEASECNT, S_MULTI, S_RSPSEQ):\n",
     "#94 toggle: the first request comes within one interval of the rise"
     " | #94 toggle: the first request goes out at once after the rise"
     " | #94 toggle: then one request every interval"),
    ("slot 6 runs no NOT_ENABLED leg", GENERATOR,
     "    p.emit(\"BR\", label=LB[\"NOTEN\"])\n",
     "    p.emit(\"END\")\n",
     "#94 toggle: the first request goes out at once after the rise"
     " | #94 link loss: asCapable falls at the falling edge"),
    # word-neutral: the leg and the cease entry skip S_PDOK's clear
    ("a portEnabled edge keeps the ladder", GENERATOR,
     "    p.emit(\"BR\", label=LB[\"PDBAD\"])\n",
     "    p.emit(\"BR\", label=LB[\"PDBAD\"] + 1)\n",
     "#94 link loss: one exchange after the rise leaves asCapable clear"),
    ("a portEnabled edge leaves the interval unanswered", GENERATOR,
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=1)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_PDGOT, fmt=FMT_Q)\n"
     "    p.label(\"tail\")\n",
     "    p.label(\"tail\")\n",
     "#94 toggle: lostResponses starts at zero: four losses commit nothing"),
    # ---- #94: the cease entry that now ends in NOTEN's tail ----------------
    ("the countdown loads one beat less", GENERATOR,
     "    p.emit(\"MOVE\", rd=RT, ra=0,"
     " imm=max(1, RUNTIME[\"cease_ms\"] // 1000))\n",
     "    p.emit(\"MOVE\", rd=RT, ra=0,"
     " imm=max(1, RUNTIME[\"cease_ms\"] // 1000 - 1))\n",
     "#94 countdown: the first request after the cease follows the last by"
     " the countdown and two beats"),
    ("the cease entry ends the cease at once", GENERATOR,
     "    p.emit(\"BR\", label=LB[\"NOTENTAIL\"])\n",
     "    p.emit(\"BR\", label=LB[\"NOTEN\"])\n",
     "#94 toggle: the cease sends no request"
     " | #94 countdown: the first request after the cease follows the last by"
     " the countdown and two beats"),
    # word-neutral: the cease holds, but nothing drops the verdict, and with
    # no request there is no loss to drop it later
    ("the cease entry keeps asCapable", GENERATOR,
     "    p.emit(\"BR\", label=LB[\"NOTENTAIL\"])\n",
     "    p.emit(\"END\")\n",
     "#94 toggle: three multi-answered requests cease"
     " | #94 countdown: three multi-answered requests cease"),
    # ---- Milan v1.2 4.2.6.2.4, which every #94 rise re-earns ----------------
    ("the ladder raises asCapable at the first exchange", GENERATOR,
     "ASCAP_UP_C = 2  ",
     "ASCAP_UP_C = 1  ",
     "#94 toggle: one exchange after the rise leaves asCapable clear"
     " | #94 link loss: one exchange after the rise leaves asCapable clear"),
    # ---- #94: the engine's portEnabled block --------------------------------
    ("the falling edge raises no event", ENGINE,
     EDGE,
     "      if (port_ref_r && port_enabled_i && !port_en_r) begin\n",
     "#94 link loss: asCapable falls at the falling edge"),
    ("a rise sends no request at once", ENGINE,
     "        pe_beat_r  <= port_enabled_i;\n",
     "        pe_beat_r  <= 1'b0;\n",
     "#94 toggle: the first request goes out at once after the rise"
     " | #94 link loss: the first request goes out at once after the rise"),
    ("a disabled port keeps its transmit credit", ENGINE,
     "          st_rd_mux_w = {63'd0, tx_credit_i && port_en_r};\n",
     "          st_rd_mux_w = {63'd0, tx_credit_i};\n",
     "#94 link loss: the publication holds while the port is disabled"),
    # a SEND issued while disabled is withdrawn like a stalled frame, so
    # this one tie stands for both
    ("a disabled port starts an unstarted frame", ENGINE,
     CANCEL,
     "      .cancel_i   (1'b0),\n",
     "#94 built across the fall: the response is not sent"
     " | #94 link loss: nothing is transmitted while the port is disabled"
     " | #94 stalled first byte: the frame is withdrawn"
     " | #94 stalled first byte: no frame starts while the port is"
     " disabled"),
    # both transmit gates at once: either alone keeps a ceased port silent
    ("a disabled port keeps its credit and starts its frames", ENGINE,
     [("          st_rd_mux_w = {63'd0, tx_credit_i && port_en_r};\n",
       "          st_rd_mux_w = {63'd0, tx_credit_i};\n"),
      (CANCEL, "      .cancel_i   (1'b0),\n")],
     None,
     "#94 toggle: nothing is transmitted while the port is disabled"
     " | #94 link loss: nothing is transmitted while the port is disabled"),
    ("egress claims survive the fall", ENGINE,
     "      if (!port_en_r) begin\n"
     "        tmr_claim_valid_r  <= 1'b0;\n"
     "        resp_claim_valid_r <= 1'b0;\n"
     "      end\n",
     "",
     "#94 built across the fall: a request after the rise is answered at"
     " once"),
    # the request's own claim alone: a frozen pair's late t1 still finds it
    ("the request claim survives the fall", ENGINE,
     "      if (!port_en_r) begin\n"
     "        tmr_claim_valid_r  <= 1'b0;\n",
     "      if (!port_en_r) begin\n",
     "#94 t1 after the fall: nothing commits after NOT_ENABLED"
     " | #94 t1 after the fall: the delay holds"),
    # the boot cadence serves the first enable since reset, so an edge there
    # adds a commit to the one every reset release makes (#82)
    ("the first enable since reset raises events", ENGINE,
     EDGE,
     "      if (port_enabled_i != port_en_r) begin\n",
     "#82 cold release: one commit before the first beat"
     " | #82 warm reset: one commit in the first 2 ms"
     " | p1 255 #82 cold release: one commit before the first beat"),
    # ---- #94: a frame stalled on the byte face -----------------------------
    # valid stays up for the cycle that withdraws the frame, so a ready
    # downstream takes one byte of a frame that never ends
    ("the withdrawn frame stays offered for a cycle", TXSLOT,
     "  assign tx_valid_o = ser_run_r && !ser_drop_w;\n",
     "  assign tx_valid_o = ser_run_r;\n",
     "#94 link loss: nothing is transmitted while the port is disabled"),
    ("a disabled port tears a started frame", TXSLOT,
     DROP,
     "  assign ser_drop_w = cancel_i && ser_run_r;\n",
     at_each_stall("the started frame keeps its place") + " | "
     + at_each_stall("the started frame completes whole")),
    ("NOT_ENABLED waits for the serializer", ENGINE,
     PE_POP,
     "  assign pe_pop_w   = pe_noten_r && disp_ready_w && ser_idle_w &&\n"
     "                      !disp_valid_r;\n",
     at_each_stall("asCapable falls within 2 ms of the fall")),
    # both: the frame stays offered and NOT_ENABLED waits for it, a
    # serializer with no withdrawal
    ("a stalled frame holds NOT_ENABLED back", ENGINE,
     [(PE_POP,
       "  assign pe_pop_w   = pe_noten_r && disp_ready_w && ser_idle_w &&\n"
       "                      !disp_valid_r;\n"),
      (CANCEL, "      .cancel_i   (1'b0),\n")],
     None,
     "#94 stalled first byte: asCapable falls within 2 ms of the fall"),
    # ---- #94: an exchange armed or queued at the fall ----------------------
    ("NOT_ENABLED keeps the armed response", GENERATOR,
     "    for s in (S_CEASE, S_CEASECNT, S_MULTI, S_RSPSEQ):\n",
     "    for s in (S_CEASE, S_CEASECNT, S_MULTI):\n",
     "#94 Follow_Up after the fall: nothing commits after NOT_ENABLED"
     " | #94 Follow_Up after the fall: the delay holds"
     " | #94 Follow_Up queued before the fall: nothing commits after"
     " NOT_ENABLED"
     " | #94 Follow_Up queued before the fall: the delay holds"),
    # NOT_ENABLED dispatches last, behind the result and the queue
    ("NOT_ENABLED queues behind earlier events", ENGINE,
     [(PE_POP,
       "  assign pe_pop_w   = pe_noten_r && !txts_pend_r && evq_empty_w &&\n"
       "                      disp_ready_w && !disp_valid_r;\n"),
      ("  assign txts_pop_w = txts_pend_r && !pe_noten_r && disp_ready_w &&\n",
       "  assign txts_pop_w = txts_pend_r && disp_ready_w &&\n"),
      ("  assign pop_w = !txts_pend_r && !pe_noten_r && !evq_empty_w &&\n",
       "  assign pop_w = !txts_pend_r && !evq_empty_w &&\n")],
     None,
     "#94 Follow_Up queued before the fall: the delay holds"),
    # ---- #94: a warm reset released with the port disabled -----------------
    # only a sample with the port enabled arms the edges
    ("the first rise after a disabled release raises nothing", ENGINE,
     "      port_ref_r  <= 1'b1;\n",
     "      port_ref_r  <= port_ref_r || port_en_r;\n",
     "#94 disabled warm reset: the first request comes within one interval"
     " of the rise"
     " | #94 disabled warm reset: the first request goes out at once after"
     " the rise"),
]
