# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""The pathTrace and Announce-qualification controls of the engine
mutation arm (`mutants.py`).

FPGA-gPTP #85 publishes the received pathSequence with thisClock appended,
#87 keeps the previous pathTrace when an Announce carries no TLV, and #88
leaves a), b) and c) of qualifyAnnounce as the only Announce
disqualifications. Each control here lists, after its issue number, every
named check it must fail. The three PathTrace refusals #88 retired are the
parser arm's own edits, taken from tb/verilator/parser/mutants.py by name,
so both suites plant one defect. `mutants.py` runs these controls last, in
this order.

The table lives in its own module so that the arm stays under the parent
repository's module length ratchet (#104). It is data only.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from receipt_mutants import GENERATOR

HERE = Path(__file__).resolve().parent

#: #88: the parser arm's planted PathTrace refusals, by its own names
_PARSER_SPEC = importlib.util.spec_from_file_location(
    "parser_mutants", HERE / "../parser/mutants.py")
_PARSER_ARM = importlib.util.module_from_spec(_PARSER_SPEC)
_PARSER_SPEC.loader.exec_module(_PARSER_ARM)
PARSER_EDITS = {name: edits for name, edits, _ in _PARSER_ARM.MUTATIONS}
#: the engine's address-7 copy of one received entry, and its keep gate
PATH_COPY = ("                      pub_path_r[64*pk +: 64] <=\n"
             "                          ann_pub_path_r[64*pk +: 64];\n")
PATH_KEEP = "                if (ann_pub_present_r) begin\n"
PATH_APPEND = "  wire       path_append_w = (ann_pub_count_clamped_w != 4'd8);\n"


def tails(tag: str, first: int, last: int = 7) -> str:
    """The named checks `tag: tail k` for k = first..last, " | "-joined."""
    return " | ".join(f"{tag}: tail {k}" for k in range(first, last + 1))


#: (name, file under hdl/, pattern, replacement, the property it should
#: break), in the arm's order; a replacement of None makes the pattern a
#: list of pairs
PATH_MUTATIONS = [
    # ---- #85: the received pathSequence plus thisClock --------------------
    # Each control lists, after "#85 ", every named check it must fail.
    ("the received path is published without thisClock",
     "top/KL_gptp_engine.sv", PATH_APPEND,
     "  wire       path_append_w = 1'b0;\n",
     "#85 direct grandmaster: count | #85 direct grandmaster: tail 1"
     " | #85 direct grandmaster: its commit names the grandmaster and path"
     " | #85 multi-hop grandmaster: count | #85 multi-hop grandmaster: tail 5"
     " | #85 multi-hop grandmaster: its commit names the grandmaster and path"
     " | #85 seven received entries: count"
     " | #85 seven received entries: tail 7"
     " | #85 seven received entries: its commit names the grandmaster and path"
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
     " | #88 empty path: count | #88 empty path from the parent: count"),
    ("eight received entries take a ninth", "top/KL_gptp_engine.sv",
     PATH_APPEND,
     "  wire       path_append_w = 1'b1;\n",
     "#85 eight received entries: count"
     " | #85 eight received entries: its commit names the grandmaster and"
     " path"),
    ("seven received entries leave thisClock out", "top/KL_gptp_engine.sv",
     PATH_APPEND,
     "  wire       path_append_w = (ann_pub_count_clamped_w < 4'd7);\n",
     "#85 seven received entries: count | #85 seven received entries: tail 7"),
    # #88: 802.1AS-2020 10.3.13.2.4 f) 5)'s rule, which appends thisClock
    # only to a nonempty sequence; 2011's d) appends it to an empty one too
    ("an empty path takes no thisClock", "top/KL_gptp_engine.sv",
     PATH_APPEND,
     "  wire       path_append_w = (ann_pub_count_clamped_w != 4'd0) &&\n"
     "                             (ann_pub_count_clamped_w != 4'd8);\n",
     "#88 empty path: count | #88 empty path: head"
     " | #88 empty path: its commit names the grandmaster and path"
     " | #88 empty path from the parent: count"
     " | #88 empty path from the parent: head"
     " | #88 empty path from the parent: its commit names the grandmaster"
     " and path"),
    ("thisClock lands one slot early", "top/KL_gptp_engine.sv",
     "                             (4'(pk) == ann_pub_count_clamped_w))\n",
     "                             (4'(pk + 1) == ann_pub_count_clamped_w))\n",
     "#85 direct grandmaster: tail 1 | #85 multi-hop grandmaster: tail 5"
     " | #85 every peer path ends with thisClock | #88 empty path: head"),
    ("thisClock fills every later slot", "top/KL_gptp_engine.sv",
     "                             (4'(pk) == ann_pub_count_clamped_w))\n",
     "                             (4'(pk) >= ann_pub_count_clamped_w))\n",
     " | ".join([tails("#85 direct grandmaster", 2),
                 tails("#85 multi-hop grandmaster", 6),
                 tails("#88 issue shape", 2),
                 tails("#88 two entries, stepsRemoved 5", 3),
                 tails("#88 three entries, stepsRemoved 0", 4),
                 "#88 head not the grandmaster: tail 3",
                 "#88 head not the grandmaster: tail 7",
                 "#88 empty path: tail 1", "#88 empty path: tail 7"])),
    ("the appended entry is the announcing source", "top/KL_gptp_engine.sv",
     "                      pub_path_r[64*pk +: 64] <= rom_clock_id_w;\n",
     "                      pub_path_r[64*pk +: 64] <= frame_cid_r;\n",
     "#85 direct grandmaster: tail 1 | #85 multi-hop grandmaster: tail 5"
     " | #85 every peer path ends with thisClock"),
    ("the received entries are not copied", "top/KL_gptp_engine.sv",
     PATH_COPY,
     "                      pub_path_r[64*pk +: 64] <= 64'd0;\n",
     " | ".join(["#85 direct grandmaster: head",
                 "#85 multi-hop grandmaster: head",
                 tails("#85 multi-hop grandmaster", 1, 4),
                 tails("#85 seven received entries", 1, 6),
                 tails("#85 eight received entries", 1)])),
    ("every received path is published as {thisClock}",
     "top/KL_gptp_engine.sv",
     "  wire [3:0] ann_pub_count_clamped_w = (ann_pub_count_r > 8'd8)\n"
     "      ? 4'd8 : ann_pub_count_r[3:0];\n",
     "  wire [3:0] ann_pub_count_clamped_w = 4'd0;\n",
     "#85 direct grandmaster: count | #85 multi-hop grandmaster: count"
     " | #85 eight received entries: count | #88 issue shape: count"
     " | #87 G1 elected: count"),
    # ---- #88: a)-c) are the only Announce disqualifications ---------------
    # The base's lengthField/8 == stepsRemoved+1 refusal, restored beside
    # the stepsRemoved capture (frame index 76) it needs.
    ("the path-count refusal restored", "wire/KL_gptp_rx_parser.sv",
     PARSER_EDITS["the path-count refusal restored (#88)"], None,
     "#88 issue shape: elected | #88 issue shape: no longer master"
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
     PARSER_EDITS["the path-head refusal restored (#88)"], None,
     "#88 head not the grandmaster: elected"
     " | #88 head not the grandmaster: no longer master"
     " | #88 head not the grandmaster: entry 0 is the received head"
     " | #88 head not the grandmaster: no Announce for one interval"
     " | #88 head not the grandmaster: parser accepts"
     " | #88 current parent's path headed elsewhere: one commit"
     " | #88 current parent's path headed elsewhere: entry 0 is the received"
     " head | #88 current parent's path headed elsewhere: parser accepts"
     " | #88 parent path headed elsewhere: head"
     " | #88 parent path headed elsewhere: parser accepts"),
    # The base's nonzero rule: an empty pathSequence refused
    ("the empty-path refusal restored", "wire/KL_gptp_rx_parser.sv",
     PARSER_EDITS["the empty-path refusal restored (#88)"], None,
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
     " path | #88 current parent's path headed elsewhere: entry 0 is the"
     " received head | #88 parent path headed elsewhere: head"
     " | #87 parent refresh without a TLV: head"),
    ("the received head is not published", "top/KL_gptp_engine.sv",
     PATH_COPY,
     "                      pub_path_r[64*pk +: 64] <= (pk == 0) ?\n"
     "                          64'd0 : ann_pub_path_r[64*pk +: 64];\n",
     "#85 direct grandmaster: head"
     " | #88 issue shape: entry 0 is the received head"
     " | adopt publishes path head | worse announce retains path A head"
     " | worse TLV-less announce retains path A head"
     " | deep path retains its head | parent refresh publishes path C head"
     " | unknown-only current parent: keeps the previous head"
     " | unknown before path current parent: head"
     " | full path before raw empty: head"
     " | TLV-less current parent: keeps the previous head"
     " | frozen queued A head coherent | post-release C head coherent"
     " | boundary-clean announce: raw path head | #87 G1 elected: head"),
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
     " path | #87 parent refresh without a TLV: count"
     " | #85 absent path: count | TLV-less competition control: raw path count"
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
     "#87 G1 to G2 without a TLV: count | #87 G1 to G2 without a TLV: head"
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
