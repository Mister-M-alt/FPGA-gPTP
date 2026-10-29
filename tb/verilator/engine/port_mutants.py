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

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet. It is data only.
"""

from receipt_mutants import GENERATOR

#: the engine top, under hdl/, which the RTL controls mutate
ENGINE = "top/KL_gptp_engine.sv"

#: the edge test of the portEnabled block
EDGE = "      if (port_seen_r && (port_enabled_i != port_en_r)) begin\n"

#: (name, file under hdl/, pattern, replacement, the checks it must fail)
PORT_MUTATIONS = [
    # ---- #94: the NOT_ENABLED leg (timer slot 6) ---------------------------
    ("a portEnabled edge keeps the cease", GENERATOR,
     "    for s in (S_CEASE, S_CEASECNT, S_MULTI):\n",
     "    for s in (S_CEASECNT, S_MULTI):\n",
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
     "      if (port_seen_r && port_enabled_i && !port_en_r) begin\n",
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
    ("a frame built across the fall is sent", ENGINE,
     "      .send_i     (resp_send_w && port_en_r),\n",
     "      .send_i     (resp_send_w),\n",
     "#94 built across the fall: the response is not sent"
     " | #94 link loss: nothing is transmitted while the port is disabled"),
    # both transmit gates at once: either alone keeps a ceased port silent
    ("a disabled port keeps its credit and its SEND", ENGINE,
     [("          st_rd_mux_w = {63'd0, tx_credit_i && port_en_r};\n",
       "          st_rd_mux_w = {63'd0, tx_credit_i};\n"),
      ("      .send_i     (resp_send_w && port_en_r),\n",
       "      .send_i     (resp_send_w),\n")],
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
    # the boot cadence serves the first enable since reset, so an edge there
    # adds a commit to the one every reset release makes (#82)
    ("the first enable since reset raises events", ENGINE,
     EDGE,
     "      if (port_enabled_i != port_en_r) begin\n",
     "#82 cold release: one commit before the first beat"
     " | #82 warm reset: one commit in the first 2 ms"
     " | p1 255 #82 cold release: one commit before the first beat"),
]
