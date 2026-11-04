#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Mutation arm for the parser suite: prove its rx_err_i checks are load-bearing.

Why this exists. FPGA-gPTP #35: `rx_err_i` was read only in the end-of-frame
branch, so a flag on any earlier byte was ignored and the frame dispatched,
and the suite stayed green because it only ever raised the flag with the
last byte. The repair latches the flag on any byte, and `sim_main.cpp` now
raises it at every byte position of four message types, and splits every
bank write of a flagged frame into those before, on and after the flagged
byte, none allowed after it (the ruling in #35). Checks that never
fail are indistinguishable from checks that assert nothing, so each defect
below is planted in the real parser RTL, one at a time, and the SAME harness
must fail on it. The unmutated build must still pass, without which the arm
would be satisfied by a harness that fails on everything.

"Caught" is stricter here than a red tally: every check a mutant names must
appear in a FAIL line, so an unrelated failure cannot stand in for the
evidence. See tb/mutation_verdict.py for why a non-zero exit alone is not a
catch. Everything is staged into a temporary directory, so nothing is
written into the tree.

The first mutant is the planted control the issue asks for: it deletes the
latch and so restores exactly the end-of-frame-only read the base shipped.
The eighth is the defect the ruling in #35 asks for: a refused frame's words
may stay in the write bank, so a clean frame behind it that skips one field
write would hand its event the refused frame's word.

Six belong to #87 and #88. Two restore PathTrace refusals #88
retired, a hop count other than stepsRemoved+1 and a first entry other than
grandmasterIdentity: each refused the whole Announce, which 802.1AS-2011
10.3.10.2.1 does not allow. One reports grandmasterIdentity in place of the
received head, the sequence the head refusal existed to prevent, and one
restores the refusal of an empty pathSequence. The other three lose or
fabricate the TLV's presence, which 10.3.10.2.1 d) needs to tell an empty
path from no path (#87).

The last nineteen belong to #98, the Follow_Up TLV walk (802.1AS-2011
11.4.1). The first restores the defect: a TLV ahead of the information TLV
refuses the Follow_Up. One reads word 11 at the fixed octets again, and
one two octets late. Each refusal the walk keeps loses its own term: the
missing information TLV; a value past messageLength, once in the walk and
once in the end-of-frame gate; an odd lengthField; a header messageLength
cuts; and the refusal latch itself, which only a malformed header ahead
of a well-formed information TLV can show. Others read padding as a
header, read a second information TLV, end the walk at a zero-length TLV,
or name the information TLV without one of its four header values, or
with any lengthField of at least 28. The last three refuse a well-formed
chain that ends on a header at messageLength: a complete header read as
cut, a zero-length TLV after the information TLV, and a last declared
octet not walked.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HDL = (HERE / "../../../hdl").resolve()
sys.path.insert(0, str((HERE / "../../").resolve()))

from mutation_verdict import verdict  # noqa: E402

#: the RTL the suite builds, in the order the Makefile lists it
RTL_SOURCES = ("ucpu/gptp_ucpu_pkg.sv", "wire/KL_gptp_rx_parser.sv")
PARSER = "wire/KL_gptp_rx_parser.sv"

VFLAGS = [
    "--cc", "--exe", "--build", "-j", "0", "--top-module", "KL_gptp_rx_parser",
    "-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL",
    "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "-Wno-UNUSEDPARAM",
]

LATCH = "        if (rx_err_i) bad_r <= 1'b1;\n"
EOF_TERM = "fin_ok_r <= !bad_r && !rx_err_i && (cnt_r >= min_end_w) &&"
TYPES = ("sync", "fu", "pdreq", "pdresp")
#: the before/on/after oracle adds an Announce, whose deferred hop-count
#: word is the one write that can land after an eof
ORACLE_TYPES = TYPES + ("ann",)


def each(check: str, types: tuple[str, ...] = TYPES) -> tuple[str, ...]:
    """The named check, once per message type the sweep covers."""
    return tuple(f"{t} {check}" for t in types)


def oracle(check: str) -> tuple[str, ...]:
    """The named first/middle/eof oracle check, once per type it covers."""
    return each(f"rx_err at first, middle, eof: {check}", ORACLE_TYPES)


#: #88: the PathTrace TLV header verdict, and the same verdict with the
#: retired lengthField/8 == stepsRemoved+1 rule restored beside the
#: stepsRemoved capture it needs (octets 75..76, frame index 76)
PT_HDR_BAD_HEAD = (
    "  assign ann_tlv_header_bad_w = ann_tlv_header_end_w &&\n"
    "      (ann_tlv_len_w[0] ||\n"
    "       ({6'd0, cnt_r} + {1'b0, ann_tlv_len_w} > {6'd0, msg_end_r}) ||\n"
    "       ((ann_tlv_type_w == 16'h0008) &&\n")
PT_HDR_BAD = (
    PT_HDR_BAD_HEAD +
    "        (ann_tlv_len_w[2:0] || pt_seen_r)));\n")
PT_HDR_BAD_WITH_COUNT = (
    "  logic [15:0] mut_steps_r;\n"
    "  always_ff @(posedge clk_i)\n"
    "    if (rx_valid_i && (cnt_r == 11'd76)) mut_steps_r <= acc_nxt_w[15:0];\n"
    + PT_HDR_BAD_HEAD +
    "        (ann_tlv_len_w[2:0] || pt_seen_r ||\n"
    "         ({1'b0, ann_tlv_len_w[15:3]} != ({1'b0, mut_steps_r} + 17'd1)))));\n")
#: the base's nonzero rule: an empty pathSequence refused the Announce
PT_HDR_BAD_WITH_NONZERO = (
    PT_HDR_BAD_HEAD +
    "        ((ann_tlv_len_w == 16'd0) || ann_tlv_len_w[2:0] || pt_seen_r)));\n")
#: the base's head rule: grandmasterIdentity captured at its last octet
#: (frame index 74), compared with the first entry both on the edge that
#: completes it and at an EOF that same byte ends
PT_DECLS = "  logic ann_pt_byte_w;\n"
PT_DECLS_WITH_HEAD = (
    PT_DECLS +
    "  logic [63:0] mut_gm_r;\n"
    "  always_ff @(posedge clk_i)\n"
    "    if (rx_valid_i && (cnt_r == 11'd74)) mut_gm_r <= acc_nxt_w;\n"
    "  wire mut_head_bad_w = ann_pt_byte_w && (pt_byte_r == 3'd7) &&\n"
    "                        (pt_cnt_r == 8'd0) && (acc_nxt_w != mut_gm_r);\n")
PT_SELF = ("                    if (acc_nxt_w == local_clock_id_i)"
           " pt_self_r <= 1'b1;\n")
PT_WRITE = ("                      bank_addr_o  <= 5'd16 + 5'(pt_cnt_r[2:0]);\n"
            "                      bank_wdata_o <= acc_nxt_w;\n")
PT_FIN = "                          !ann_tlv_header_bad_w &&\n"
#: the zero-length arm's presence mark and the deferred word 12
PT_EMPTY_SEEN = ("                    if (ann_tlv_type_w == 16'h0008)"
                 " pt_seen_r <= 1'b1;\n")
W12 = "            bank_wdata_o <= {pt_seen_r, 54'd0, pt_self_r, pt_cnt_r};\n"
#: the #88 probes, each graded on its event and its drop count
COUNT_PROBES = ("#88 one entry, stepsRemoved 3",
                "#88 two entries, stepsRemoved 2",
                "#88 three entries, stepsRemoved 0",
                "#88 short loop, stepsRemoved 5")
HEAD_PROBES = ("#88 head not the grandmaster, two entries",
               "#88 head not the grandmaster, one entry",
               "#88 head is thisClock")
EMPTY_PROBES = ("#88 empty path", "#88 empty path between unknowns")

#: #98: the Follow_Up walk's terms, as the parser spells them
FU_DECLS = "  logic fu_tlv_header_bad_w, fu_tlv_cut_after_w;\n"
FU_LATCH = "                  if (fu_tlv_header_bad_w) begin\n"
FU_CUT = ("  assign fu_tlv_cut_after_w = tlv_hdr_run_r &&\n"
          "      (fu_tlv_header_byte_w ? !fu_tlv_header_end_w\n")
FU_ODD = ("      (acc_nxt_w[0] ||\n"
          "       ({6'd0, cnt_r} + {1'b0, acc_nxt_w[15:0]} > {6'd0, msg_end_r}));\n")
FU_FIN = ("                         (fu_found_r && !fu_tlv_header_bad_w &&\n"
          "                          !fu_tlv_cut_after_w));\n")
FU_HDR_BYTE = (
    "  assign fu_tlv_header_byte_w = (mtype_r == MT_FU_C) && tlv_hdr_run_r &&\n"
    "                                (cnt_r <= msg_end_r);\n")
FU_SKIP = ("                  end else if (acc_nxt_w[15:0] != 16'd0) begin\n"
           "                    tlv_hdr_run_r <= 1'b0;\n")
FU_MATCH = ("                if (fu_info_r && (tlv_left_r == FU_LEFT_AT_SUB_C) &&\n"
            "                    (acc_nxt_w[47:0] == FU_TLV_ORG_C)) fu_found_r <= 1'b1;\n")
FU_W11 = ("                if (fu_info_r && fu_found_r &&\n"
          "                    (tlv_left_r == FU_LEFT_AT_TBI_C)) begin\n")
FU_TYPE = "                               (acc_nxt_w[31:16] == FU_TLV_TYPE_C) &&\n"
FU_LEN = "                               (acc_nxt_w[15:0] == FU_TLV_LEN_C);\n"
FU_TBI = "  localparam logic [15:0] FU_LEFT_AT_TBI_C = 16'd17;\n"
#: the walk's accepting shapes and their named words
FU_FIRST = ("#98 unknown TLV first", "#98 three unknown TLVs first",
            "#98 unknown TLV first, padded", "#98 second information TLV",
            "#98 identifiers at octet 6")
FU_CUTS = tuple(f"#98 header cut after {k} octet(s){p}: no event"
                for k in (1, 2, 3) for p in ("", ", padded"))
#: the well-formed chain that ends on a zero-length header at messageLength
FU_AFTER = ("#98 unknown TLVs after: event", "#98 unknown TLVs after: no drop")


def refused(tag: str, no_w11: bool = False) -> tuple[str, ...]:
    """The named refusal checks of one #98 or #11 Follow_Up row."""
    return ((f"{tag}: no event", f"{tag}: one drop")
            + ((f"{tag}: no w11 write",) if no_w11 else ()))


#: (clean, refused) pairs of the stale-word check
PAIRS = (("sync", "sync"), ("sync", "pdresp"), ("fu", "fu"), ("fu", "pdresp"),
         ("pdreq", "pdreq"), ("pdreq", "sync"), ("pdresp", "pdresp"),
         ("pdresp", "fu"))


def pairs(check: str) -> tuple[str, ...]:
    """The named stale-word check, once per pair it covers."""
    return tuple(f"{c} after a refused {r}: {check}" for c, r in PAIRS)


#: (name, [(pattern, replacement), ...] in the parser, checks that must FAIL)
MUTATIONS = [
    ("rx_err read only at eof (the planted control)",
     [(LATCH, "")],
     each("rx_err at every byte: one drop") +
     each("rx_err at every byte: no event") +
     each("rx_err at every byte: no later write") +
     oracle("one drop") + oracle("no event") + oracle("no write after")),
    ("a first-byte flag lost to the sof clear",
     [(LATCH, ""),
      ("      if (rx_valid_i) begin\n        if (rx_sof_i) begin\n",
       "      if (rx_valid_i) begin\n" + LATCH + "        if (rx_sof_i) begin\n")],
     each("rx_err at every byte: one drop") + oracle("one drop")),
    ("the eof byte's own flag ignored",
     [(EOF_TERM, "fin_ok_r <= !bad_r && (cnt_r >= min_end_w) &&")],
     each("rx_err at every byte: one drop") +
     each("rx_err at every byte: no event") +
     oracle("one drop") + oracle("no event") +
     ("ann rx_err at first, middle, eof: no write after",)),
    ("every flagged byte counts a drop",
     [(LATCH, "        if (rx_err_i) begin\n"
              "          bad_r <= 1'b1;\n"
              "          drop_cnt_r <= drop_cnt_r + 16'd1;\n"
              "        end\n")],
     each("rx_err held from byte 20 to eof: one drop")),
    ("rx_err ignored on every byte",
     [(LATCH, ""),
      (EOF_TERM, "fin_ok_r <= !bad_r && (cnt_r >= min_end_w) &&")],
     each("rx_err held from byte 20 to eof: no event")),
    ("the refusal outlives its frame",
     [("          bad_r    <= 1'b0;\n", "")],
     each("control after the errors: event") +
     each("control after the errors: no drop") +
     pairs("one drop") + pairs("event")),
    ("rx_err sampled between bytes",
     [(LATCH + "      end\n", "      end\n      if (rx_err_i) bad_r <= 1'b1;\n")],
     ("rx_err in every gap between bytes: sync event",
      "rx_err in every gap between bytes: no drop")),
    # the planted defect the ruling in #35 asks for: the clean frame behind
    # a refused one skips its source-identity write, so the refused frame's
    # w2 is what its event would read
    ("a refusal skips the next frame's w2 write",
     [("  logic        bad_r;          //! poisoned: consume to eof, then drop\n",
       "  logic        bad_r;          //! poisoned: consume to eof, then drop\n"
       "  logic        was_bad_r;\n"),
      ("      bad_r       <= 1'b0;\n",
       "      bad_r       <= 1'b0;\n      was_bad_r   <= 1'b0;\n"),
      ("          bad_r    <= 1'b0;\n",
       "          bad_r    <= 1'b0;\n          was_bad_r <= bad_r;\n"),
      ("              bank_we_o    <= !bad_r;\n              bank_addr_o  <= 5'd2;\n",
       "              bank_we_o    <= !bad_r && !was_bad_r;\n"
       "              bank_addr_o  <= 5'd2;\n")],
     pairs("every word is this frame's")),
    # #88: the hop count compared with stepsRemoved again, as the base did
    ("the path-count refusal restored (#88)",
     [(PT_HDR_BAD, PT_HDR_BAD_WITH_COUNT)],
     tuple(f"{p}: event" for p in COUNT_PROBES) +
     tuple(f"{p}: no drop" for p in COUNT_PROBES)),
    # #88: the first entry compared with grandmasterIdentity again
    ("the path-head refusal restored (#88)",
     [(PT_DECLS, PT_DECLS_WITH_HEAD),
      (PT_SELF, PT_SELF + "                    if (mut_head_bad_w)"
                          " bad_r <= 1'b1;\n"),
      (PT_FIN, "                          !ann_tlv_header_bad_w &&"
               " !mut_head_bad_w &&\n")],
     tuple(f"{p}: event" for p in HEAD_PROBES) +
     tuple(f"{p}: no drop" for p in HEAD_PROBES)),
    # #88: the received head replaced by grandmasterIdentity, the
    # {grandmasterIdentity, tail} sequence no peer sent
    ("the head is replaced by grandmasterIdentity (#88)",
     [(PT_DECLS, PT_DECLS_WITH_HEAD),
      (PT_WRITE, "                      bank_addr_o  <= 5'd16 +"
                 " 5'(pt_cnt_r[2:0]);\n"
                 "                      bank_wdata_o <= (pt_cnt_r == 8'd0)"
                 " ? mut_gm_r : acc_nxt_w;\n")],
     tuple(f"{p}: identity 0" for p in HEAD_PROBES)),
    # #88: an empty pathSequence refused again, as the base did
    ("the empty-path refusal restored (#88)",
     [(PT_HDR_BAD, PT_HDR_BAD_WITH_NONZERO)],
     tuple(f"{p}: event" for p in EMPTY_PROBES) +
     tuple(f"{p}: no drop" for p in EMPTY_PROBES)),
    # #87: an empty TLV reported as no TLV, and not counted as the one
    # PathTrace a second must not follow
    ("an empty path is not marked present (#87)",
     [(PT_EMPTY_SEEN, "")],
     ("#88 empty path: present, count zero",
      "#88 empty path between unknowns: present, count zero",
      "#88 path after an empty path: no event",
      "#88 path after an empty path: no w12",
      "#88 path after an empty path: one drop")),
    # #87: word 12 without its presence bit, so no TLV and an empty TLV
    # look alike
    ("word 12 drops the presence bit (#87)",
     [(W12, "            bank_wdata_o <= {55'd0, pt_self_r, pt_cnt_r};\n")],
     ("ann w12 hops", "#88 empty path: present, count zero",
      "#88 one entry, stepsRemoved 3: presence, count and loop",
      "#88 head not the grandmaster, one entry: presence, count and loop")),
    # #87: word 12 marks every Announce present, so no TLV looks like an
    # empty one
    ("word 12 marks a TLV-less Announce present (#87)",
     [(W12, "            bank_wdata_o <= {1'b1, 54'd0, pt_self_r,"
            " pt_cnt_r};\n")],
     ("TLV-less ann: absent, zero count and loop",
      "out-of-message path: absent, zero count and loop",
      "unknown-only ann: zero count")),
    # #98: the defect restored, every TLV ahead of the information TLV
    # refuses the Follow_Up, as the fixed octet-44 arm did
    ("a TLV ahead of the information TLV refuses the Follow_Up (#98)",
     [(FU_LATCH,
       "                  if (fu_tlv_header_bad_w || !(fu_found_r ||\n"
       "                      ((acc_nxt_w[31:16] == FU_TLV_TYPE_C) &&\n"
       "                       (acc_nxt_w[15:0] == FU_TLV_LEN_C)))) begin\n")],
     tuple(f"{t}: event" for t in FU_FIRST) + ("#98 unknown TLV first: no drop",)),
    # #98: word 11 read at the information TLV's octets 68..73 when it is
    # first, wherever it really is
    ("word 11 read at the fixed octets 68..73 (#98)",
     [(FU_W11, "                if (cnt_r == 11'd73) begin\n")],
     ("#98 unknown TLV first: w11 as the plain case",
      "#98 three unknown TLVs first: w11 as the plain case")),
    # #98: gmTimeBaseIndicator read two octets late, from the head of
    # lastGmPhaseChange, wherever the information TLV is
    ("word 11 read two octets late (#98)",
     [(FU_TBI, "  localparam logic [15:0] FU_LEFT_AT_TBI_C = 16'd15;\n")],
     ("#98 plain fu: w11 as the plain case", "fu w11",
      "#98 unknown TLV first: w11 as the plain case")),
    ("a Follow_Up is accepted without its information TLV (#98)",
     [(FU_FIN, "                         (!fu_tlv_header_bad_w &&\n"
               "                          !fu_tlv_cut_after_w));\n")],
     refused("#98 no information TLV") +
     ("fu tlvType 0x0008 drop: no event", "fu orgId 00-1B-19 drop: no event",
      "fu orgSubType 2 drop: no event")),
    # #98: a value past messageLength, walked like any other: the walk's
    # header verdict keeps only the odd term, the end-of-frame gate keeps
    # both, so only a header ending ahead of the last octet is lost
    ("a TLV value past messageLength is walked (#98)",
     [(FU_LATCH, "                  if (fu_tlv_header_end_w &&"
                 " acc_nxt_w[0]) begin\n")],
     refused("#98 information TLV past messageLength", True) +
     refused("#98 trailing TLV past messageLength")),
    # #98: the refusal latch of a malformed header lost, the walk still
    # holding header mode: the next four octets are read as a header, so
    # the information TLV right behind it is found and the Follow_Up is
    # accepted. A malformed header with no such TLV behind it is still
    # refused for lack of one or by the cut term.
    ("a malformed TLV header does not latch the refusal (#98)",
     [(FU_LATCH + "                    bad_r <= 1'b1;\n", FU_LATCH)],
     refused("#98 TLV past messageLength ahead of the information TLV", True) +
     refused("#98 odd lengthField ahead of the information TLV", True)),
    # #98: the header's own overrun, when its last octet is the frame's
    # last, reaches the end-of-frame gate only through the current-byte
    # term: the end-of-frame half of a value past messageLength
    ("an EOF header's own overrun is not refused (#98)",
     [(FU_FIN, "                         (fu_found_r &&\n"
               "                          !fu_tlv_cut_after_w));\n")],
     refused("#98 header ends messageLength, value to come")),
    ("an odd lengthField is walked (#98)",
     [(FU_ODD, "      (({6'd0, cnt_r} + {1'b0, acc_nxt_w[15:0]} >"
               " {6'd0, msg_end_r}));\n")],
     refused("#98 odd lengthField", True)),
    ("a TLV header cut by messageLength is accepted (#98)",
     [(FU_FIN, "                         (fu_found_r &&"
               " !fu_tlv_header_bad_w));\n")],
     FU_CUTS),
    ("the walk reads padding past messageLength as a header (#98)",
     [(FU_HDR_BYTE, "  assign fu_tlv_header_byte_w = (mtype_r == MT_FU_C) &&"
                    " tlv_hdr_run_r;\n")],
     ("#98 unknown TLV first, padded: event",
      "#98 unknown TLV first, padded: no drop")),
    ("a later information TLV is read again (#98)",
     [("                  fu_info_r <= !fu_found_r &&\n",
       "                  fu_info_r <=\n")],
     ("#98 second information TLV: w11 as the plain case",)),
    ("a zero-length TLV ends the walk (#98)",
     [(FU_SKIP, "                  end else begin\n"
                "                    tlv_hdr_run_r <= 1'b0;\n")],
     ("#98 three unknown TLVs first: event",
      "#98 three unknown TLVs first: no drop")),
    ("the information TLV is named without its organizationId and subtype (#98)",
     [(FU_MATCH, "                if (fu_info_r && (tlv_left_r =="
                 " FU_LEFT_AT_SUB_C)) fu_found_r <= 1'b1;\n")],
     ("#98 three unknown TLVs first: w11 as the plain case",
      "#98 no information TLV: no event", "fu orgId 00-1B-19 drop: no event",
      "fu orgSubType 2 drop: no event")),
    ("the information TLV is named without its tlvType (#98)",
     [(FU_TYPE, "")],
     refused("fu tlvType 0x0008 drop", True)),
    ("the information TLV is named without its lengthField (#98)",
     [(FU_LEN, "                               1'b1;\n")],
     ("#98 identifiers at octet 6: w11 as the plain case",)),
    # #98: 11.4.4.3.3 fixes lengthField at 28. A walk that takes any
    # lengthField of at least 28 and finds the fields from the TLV's start
    # accepts a longer 00-80-C2/1 TLV.
    ("the information TLV is named by any lengthField of 28 or more (#98)",
     [(FU_DECLS, FU_DECLS +
       "  logic [15:0] mut_len_r;\n"
       "  always_ff @(posedge clk_i)\n"
       "    if (rx_valid_i && fu_tlv_header_end_w) mut_len_r <= acc_nxt_w[15:0];\n"),
      (FU_LEN, "                               (acc_nxt_w[15:0] >= FU_TLV_LEN_C);\n"),
      (FU_MATCH, FU_MATCH.replace("FU_LEFT_AT_SUB_C", "mut_len_r - 16'd5")),
      (FU_W11, FU_W11.replace("FU_LEFT_AT_TBI_C", "mut_len_r - 16'd11"))],
     refused("#98 information TLV with lengthField 30", True)),
    # #98: a well-formed chain that ends on a complete zero-length header
    # at exactly messageLength is accepted; each defect refuses it
    ("a complete header ending on the last declared octet is read as cut (#98)",
     [(FU_CUT, "  assign fu_tlv_cut_after_w = tlv_hdr_run_r &&\n"
               "      (fu_tlv_header_byte_w ? 1'b1\n")],
     FU_AFTER),
    ("a zero-length TLV after the information TLV refuses the Follow_Up (#98)",
     [(FU_SKIP, "                  end else if ((acc_nxt_w[15:0] == 16'd0) &&"
                " fu_found_r) begin\n"
                "                    bad_r <= 1'b1;\n" + FU_SKIP)],
     FU_AFTER),
    ("the last declared octet is not walked as a header byte (#98)",
     [(FU_HDR_BYTE, FU_HDR_BYTE.replace("(cnt_r <= msg_end_r)",
                                        "(cnt_r < msg_end_r)"))],
     FU_AFTER),
]


def stage(work: Path, tag: str,
          edits: list[tuple[str, str]] | None = None) -> Path:
    """A directory holding the RTL, with the parser edited by `edits`.
    Nothing outside the returned directory is written."""
    srcdir = work / f"src_{tag}"
    for name in RTL_SOURCES:
        target = srcdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (HDL / name).read_text(encoding="utf-8")
        if edits and name == PARSER:
            for pattern, replacement in edits:
                text = text.replace(pattern, replacement)
        target.write_text(text, encoding="utf-8")
    return srcdir


def build(srcdir: Path, work: Path, tag: str) -> Path | None:
    """Build the harness against the RTL in `srcdir`; the exe, or None."""
    mdir = work / f"obj_{tag}"
    exe_name = f"Vparser_{tag}"
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


def run_harness(exe: Path) -> tuple[int, str]:
    """(rc, output) of one harness run. The suite is a fixed directed
    sequence with no open-ended wait, so it needs no host deadline."""
    out = subprocess.run([str(exe)], capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def main() -> int:
    """Run the control and every mutant, and report the arm's exit status.

    0 when the unmutated RTL passes and every mutant fails each check it
    names; 1 when any mutant survived, missed a named check, failed to
    build, or no longer matches its pattern.
    """
    passes = fails = 0
    with tempfile.TemporaryDirectory(prefix="parser-mutants-") as td:
        work = Path(td)

        # -- positive control: the real RTL must still pass ------------------
        exe = build(stage(work, "clean"), work, "clean")
        answer = verdict(*run_harness(exe)) if exe else "did not compile"
        if answer == "pass":
            passes += 1
            print("[PASS] the unmutated parser still passes the harness")
        else:
            fails += 1
            print(f"[FAIL] the unmutated parser does NOT pass ({answer}) - "
                  f"every mutant result below is meaningless")

        # -- each mutant must fail every check it names ------------------------
        src = (HDL / PARSER).read_text(encoding="utf-8")
        for name, edits, breaks in MUTATIONS:
            stale = [p for p, _ in edits if src.count(p) != 1]
            if stale:
                fails += 1
                print(f"[FAIL] mutation {name!r}: a pattern no longer appears "
                      f"exactly once in {PARSER}. The RTL moved and this "
                      f"mutant is no longer mutating anything - fix the "
                      f"pattern, do not delete the arm.")
                continue
            tag = "".join(c if c.isalnum() else "_" for c in name)
            exe = build(stage(work, tag, edits), work, tag)
            if exe is None:
                fails += 1
                print(f"[FAIL] mutation {name!r} did not compile; a mutant "
                      f"that cannot build proves nothing about the harness")
                continue
            rc, output = run_harness(exe)
            answer = verdict(rc, output)
            failed = [line for line in output.splitlines()
                      if line.startswith("FAIL ")]
            missed = [check for check in breaks
                      if not any(check in line for line in failed)]
            if answer == "caught" and missed:
                answer = f"missed its named check(s): {', '.join(missed)}"
            if answer == "caught":
                passes += 1
                print(f"[PASS] mutant caught: {name} - fails all "
                      f"{len(breaks)} named check(s), first "
                      f"\"{breaks[0]}\"")
            elif answer == "pass":
                fails += 1
                print(f"[FAIL] mutant SURVIVED: {name}. The harness does not "
                      f"prove \"{breaks[0]}\".")
            else:
                fails += 1
                print(f"[FAIL] mutant {name!r} {answer}")

    total = passes + fails
    print(f"\n{total} checks: {passes} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
