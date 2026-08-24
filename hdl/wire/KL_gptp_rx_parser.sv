/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : KL_gptp_rx_parser.sv
//  Project     : 802.1AS gPTP protocol processor (time-sync plane)
//
//  Description : Byte-serial 802.1AS-2011 receive parser. Consumes one
//                pre-classified frame (DA byte first, FCS already stripped
//                and verified by the MAC) at one byte per cycle, extracts
//                the common header and the per-type body into the message
//                bank as packed 64-bit words, and raises one event at end
//                of frame. There is no backpressure on the byte face —
//                the integrator's control-frame FIFO owns rate matching,
//                exactly as in the protocol-processor's KL_pp_shadow.
//
//                Checks that DROP (counted, no event): EtherType not
//                0x88F7, transportSpecific != 1, versionPTP != 2,
//                domainNumber != DOMAIN_C (802.1AS-2011 8.1: a gPTP
//                domain is domain 0; IEEE 1588-2008 9.5.1: a message
//                whose domainNumber does not match is not accepted for
//                processing), messageLength below the per-type minimum
//                (10.5.2.2.4 / 11.4.2.2: the octet count of header,
//                body and TLVs; Table 11-11 makes a Pdelay_Req 54, the
//                header and two reserved fields, so the header alone no
//                longer draws a response), frame truncated before that
//                minimum,
//                a Follow_Up whose information TLV header is not the
//                one 11.4.4.3 prescribes (Table 11-9 makes the TLV a
//                field of the 76-octet Follow_Up, 11.4.4.2.2 places it
//                first), rx_err_i. The domain and messageLength arms
//                sit at header bytes 4 and 2..3, ahead of every
//                message-bank write, so a foreign-domain or short-
//                declared frame leaves nothing a handler could read.
//                The declared messageLength is also the hard parsing
//                boundary: physical Ethernet padding is ignored, a frame
//                shorter than its declaration is refused. A fixed 64-octet
//                Announce may omit Path Trace; the absent case distinguished
//                by 10.3.10.2.1(d) / 10.3.13.2.1(f) is reported honestly as
//                count zero. When the TLV is present it must be identity-
//                aligned, wholly contained, and carry stepsRemoved+1
//                identities as required by 802.1AS-2011 10.5.3.3.4.
//                The TLV arm can only follow the body it qualifies: a
//                refused Follow_Up's header words land in the write
//                bank like those of any frame cut by truncation or
//                rx_err, no event names that bank, and the next frame
//                overwrites it. TLVs after the information TLV are not
//                parsed (11.4.1: ignore a TLV and attempt the next), so
//                a messageLength above 76 is accepted.
//
//                Message bank map (64-bit words, region 0 of the µCPU
//                state port):
//                  w0  {8'd0, msgType, seqId, domain, flags, logInterval}
//                      (domain reads DOMAIN_C: the parser admits exactly
//                      one domain, so the byte is the constant, not a
//                      register)
//                  w1  correctionField
//                  w2  sourcePortIdentity.clockIdentity
//                  w3  {48'd0, sourcePortIdentity.portNumber}
//                  w4  {16'd0, timestamp.seconds[47:0]}
//                  w5  {32'd0, timestamp.nanoseconds}
//                  w6  requestingPortIdentity.clockIdentity
//                  w7  {48'd0, requestingPortIdentity.portNumber}
//                  w8  {currentUtcOffset, gmPriority1, gmClockQuality,
//                       gmPriority2}
//                  w9  grandmasterIdentity
//                  w10 {stepsRemoved, timeSource, 40'd0}
//                  w11 {cumulativeScaledRateOffset, gmTimeBaseIndicator,
//                       16'd0}
//                  w12 {55'd0, pathContainsThisClock, pathTraceCount}
//                  w16..w23  path trace clockIdentities (capped at 8;
//                            hops beyond the cap are skipped, the count
//                            still reports the TLV's true hop count so
//                            µcode can tell a capped read from a full one)
//
//                SKELETON NOTE: single message bank, so a frame that
//                arrives while µcode still walks the previous one would
//                overwrite it. The dispatch queue depth and a second bank
//                are integration decisions this resource experiment
//                deliberately leaves to the engine revision that carries
//                real µcode.
//---------------------------------------------------------------------------//
`default_nettype none

module KL_gptp_rx_parser
  import gptp_ucpu_pkg::*;
(
    input  wire         clk_i,
    input  wire         rst_n,

    //! byte face: one frame, DA first, no backpressure
    input  wire         rx_valid_i,
    input  wire  [7:0]  rx_data_i,
    input  wire         rx_sof_i,     //! asserted with the first byte
    input  wire         rx_eof_i,     //! asserted with the last byte
    input  wire         rx_err_i,     //! abort: drop silently
    input  wire  [63:0] local_clock_id_i, //! complete PathTrace loop check
    input  wire         local_clock_valid_i,

    //! message bank write lane (engine owns the RAM)
    output logic        bank_we_o,
    output logic [4:0]  bank_addr_o,
    output logic [63:0] bank_wdata_o,

    //! one event per accepted frame
    output logic        ev_valid_o,
    output logic [7:0]  ev_code_o,
    output logic [15:0] ev_seq_o,

    //! diagnostics
    output logic [15:0] drop_cnt_o
);

  // ---- 802.1AS message types --------------------------------------------
  //! The COMPLETE set a gPTP port carries: Table 10-5 (10.5.2.2.2) names
  //! Announce 0xB and Signaling 0xC, Table 11-3 (11.4.2.1) names Sync
  //! 0x0, Pdelay_Req 0x2, Pdelay_Resp 0x3, Follow_Up 0x8 and
  //! Pdelay_Resp_Follow_Up 0xA, and the NOTE under Table 11-3 closes the
  //! set: "Other values for the messageType field, except for 0xB ... and
  //! 0xC ..., are not used in this standard". The other nine values are
  //! IEEE 1588-2008 Table 19's Delay_Req 0x1, Delay_Resp 0x9 and
  //! Management 0xD (the delay-request mechanism and management, which
  //! 802.1AS does not use) and its reserved 0x4..0x7 and 0xE..0xF. None
  //! has a handler here, so the type arm below refuses them rather than
  //! let the engine dispatch an event no entry claims (FPGA-gPTP #22);
  //! one list, used by the refusal, the minimum-length table and the
  //! event map alike.
  localparam logic [3:0] MT_SYNC_C   = 4'h0;
  localparam logic [3:0] MT_PDREQ_C  = 4'h2;
  localparam logic [3:0] MT_PDRESP_C = 4'h3;
  localparam logic [3:0] MT_FU_C     = 4'h8;
  localparam logic [3:0] MT_PDRFU_C  = 4'hA;
  localparam logic [3:0] MT_ANN_C    = 4'hB;
  localparam logic [3:0] MT_SIG_C    = 4'hC;

  // ---- the one gPTP domain ----------------------------------------------
  //! 802.1AS-2011 8.1: the domain number of a gPTP domain shall be 0, and
  //! 10.5.2.2.5 carries that value in every message. IEEE 1588-2008 9.5.1
  //! is the receive rule: only a message whose domainNumber matches the
  //! local domain is accepted for processing. Derived here, in the one
  //! place the receive side qualifies it; the TX builder emits the same
  //! zero from the register file's zero source (e_hdr).
  localparam logic [7:0] DOMAIN_C = 8'd0;

  // ---- the Follow_Up information TLV header -----------------------------
  //! 802.1AS-2011 11.4.4.3, Table 11-10: tlvType 0x3 (ORGANIZATION_EXTENSION,
  //! 11.4.4.3.2), lengthField 28 (11.4.4.3.3), organizationId 00-80-C2
  //! (11.4.4.3.4), organizationSubType 1 (11.4.4.3.5). Table 11-9 makes
  //! the TLV a field of the Follow_Up message and 11.4.4.2.2 places it
  //! first after the fixed fields, so octets 44..53 of every Follow_Up
  //! are this header; a frame that carries anything else there has no
  //! information TLV and is refused (FPGA-gPTP #11).
  localparam logic [15:0] FU_TLV_TYPE_C = 16'h0003;
  localparam logic [63:0] FU_TLV_HDR_C  = {16'd28, 24'h0080C2, 24'd1};

  // ---- absolute byte offsets (DA = byte 0, PTP header = byte 14) --------
  localparam int unsigned OFF_ETYPE_HI_C = 12;
  localparam int unsigned OFF_ETYPE_LO_C = 13;
  localparam int unsigned OFF_TYPE_C     = 14;
  localparam int unsigned OFF_VER_C      = 15;
  localparam int unsigned OFF_MSGLEN_END_C = 17;
  localparam int unsigned OFF_DOM_C      = 18;
  localparam int unsigned OFF_FLAGS0_C   = 20;
  localparam int unsigned OFF_CORR_END_C = 29;
  localparam int unsigned OFF_SRCID_END_C = 41;
  localparam int unsigned OFF_SRCPN_END_C = 43;
  localparam int unsigned OFF_SEQ0_C     = 44;
  localparam int unsigned OFF_CTRL_C     = 46;
  localparam int unsigned OFF_LOGI_C     = 47;
  localparam int unsigned OFF_TS_SEC_END_C = 53;
  localparam int unsigned OFF_TS_NS_END_C  = 57;
  localparam int unsigned OFF_RQID_END_C   = 65;
  localparam int unsigned OFF_RQPN_END_C   = 67;
  // announce body
  localparam int unsigned OFF_AN_UTC0_C   = 58;
  localparam int unsigned OFF_AN_P1_C     = 61;
  localparam int unsigned OFF_AN_CQ_END_C = 65;
  localparam int unsigned OFF_AN_P2_C     = 66;
  localparam int unsigned OFF_AN_GM_END_C = 74;
  localparam int unsigned OFF_AN_SR_END_C = 76;
  localparam int unsigned OFF_AN_TSRC_C   = 77;
  localparam int unsigned OFF_AN_TLV_C    = 78;
  // follow-up information TLV (Table 11-10 offsets + 58)
  localparam int unsigned OFF_FU_TLVT_END_C = 59;   //! tlvType
  localparam int unsigned OFF_FU_TLVH_END_C = 67;   //! lengthField..organizationSubType
  localparam int unsigned OFF_FU_CSRO_END_C = 71;
  localparam int unsigned OFF_FU_TBI_END_C  = 73;
  localparam int unsigned OFF_FU_END_C      = 89;   //! scaledLastGmFreqChange

  // ---- parse state -------------------------------------------------------
  logic [10:0] cnt_r;          //! absolute byte index of the CURRENT byte
  logic        run_r;          //! a frame is being consumed
  logic        bad_r;          //! poisoned: consume to eof, then drop
  logic [3:0]  mtype_r;
  logic [15:0] seq_r;
  logic [15:0] flags_r;
  logic [63:0] acc_r;          //! big-endian byte accumulator
  logic [15:0] utc_r;          //! announce currentUtcOffset (straddles acc)
  logic [10:0] msg_end_r;      //! absolute final declared byte (DA = 0)
  logic [15:0] steps_r;
  logic [63:0] gm_r;
  // announce TLV chain and PathTrace walk
  logic        tlv_hdr_run_r;  //! consuming the next generic 4-byte header
  logic  [1:0] tlv_hdr_pos_r;  //! byte inside that generic header
  logic [15:0] tlv_left_r;     //! bytes remaining in the current TLV value
  logic        tlv_chain_done_r; //! declared suffix ended on a TLV boundary
  logic [15:0] pt_left_r;      //! PathTrace value bytes remaining
  logic [7:0]  pt_cnt_r;       //! hops seen
  logic [2:0]  pt_byte_r;      //! byte inside the current identity
  logic        pt_run_r;
  logic        pt_seen_r;
  logic        pt_self_r;
  logic [15:0] drop_cnt_r;
  //! the two refusals that can resolve on ONE edge: a deferred
  //! end-of-frame whose frame was refused, and a one-byte frame arriving
  //! in that same cycle. They belong to DIFFERENT frames, so both must
  //! count; as two increments of one register only one survived, because
  //! non-blocking assignments to the same register on one edge keep the
  //! last. One write site, fed by both (FPGA-gPTP #27)
  logic fin_drop_w, runt_drop_w;
  //! end-of-frame settles one cycle late: last-byte field writes are
  //! non-blocking, and the announce hop-count word must not fight the
  //! final identity write for the one bank lane
  logic        fin_r;
  logic        fin_ok_r;

  logic [63:0] acc_nxt_w;
  assign acc_nxt_w = {acc_r[55:0], rx_data_i};

  //! per-type minimum length (absolute index of the last mandatory byte):
  //! the fixed message lengths of 802.1AS-2011 Table 10-7 (Announce 64;
  //! a receiver also validates PathTrace strictly when it is present),
  //! Table 11-8 (Sync 44), Table 11-9 (Follow_Up 76: the information
  //! TLV is a field, not a suffix), Tables 11-11 / 11-12 / 11-13
  //! (Pdelay_Req, Pdelay_Resp and Pdelay_Resp_Follow_Up 54: IEEE
  //! 1588-2008 13.9 pads the request with a second reserved field to the
  //! response's length, so the three share one index) and the 34-octet
  //! header for Signaling, each as the frame index of its last octet
  //! (the header starts at byte 14). The
  //! one table gates both the declared messageLength and the bytes
  //! actually received; no second flag mirrors it.
  logic [10:0] min_end_w;
  always_comb begin : min_len
    unique case (mtype_r)
      MT_ANN_C:    min_end_w = 11'(OFF_AN_TSRC_C);
      MT_FU_C:     min_end_w = 11'(OFF_FU_END_C);
      MT_PDREQ_C,
      MT_PDRESP_C,
      MT_PDRFU_C:  min_end_w = 11'(OFF_RQPN_END_C);
      MT_SYNC_C:   min_end_w = 11'(OFF_TS_NS_END_C);
      MT_SIG_C:    min_end_w = 11'(OFF_LOGI_C);
      default:     min_end_w = 11'(OFF_LOGI_C);
    endcase
  end

  //! the same minimum as a messageLength bound: 10.5.2.2.4 / 11.4.2.2
  //! count the octets from the first header octet through the last TLV
  //! octet, so the bound is the last mandatory index + 1 less the 14-byte
  //! Ethernet header; a declared length above it (trailing TLVs) passes
  logic [15:0] min_len_w;
  assign min_len_w = 16'(min_end_w) + 16'd1 - 16'(OFF_TYPE_C);

  //! This parser consumes an untagged Ethernet-II frame (DA first), whose
  //! PTP payload cannot exceed the 1500-octet Ethernet payload. Besides
  //! documenting the integration boundary, the upper bound prevents a
  //! hostile 16-bit declaration from wrapping the 11-bit byte index.
  localparam logic [15:0] MAX_MSG_LEN_C = 16'd1500;

  //! End-of-frame checks must include the current byte: sequential path
  //! counters update on the same edge as EOF. In particular, a valid final
  //! identity arrives with pt_left==1/pt_byte==7 before that edge, whereas
  //! a two-identity declaration cut after one arrives with pt_left==9.
  logic ann_tlv_header_byte_w, ann_tlv_header_end_w;
  logic ann_tlv_value_byte_w, ann_tlv_value_end_w;
  logic ann_tlv_header_bad_w, ann_tlv_chain_done_after_w;
  logic ann_pt_byte_w, ann_pt_identity_w, ann_head_bad_w;
  logic [15:0] ann_pt_left_after_w;
  wire [15:0] ann_tlv_type_w = acc_nxt_w[31:16];
  wire [15:0] ann_tlv_len_w  = acc_nxt_w[15:0];
  assign ann_tlv_header_byte_w = (mtype_r == MT_ANN_C) && tlv_hdr_run_r &&
                                 (cnt_r <= msg_end_r);
  assign ann_tlv_header_end_w = ann_tlv_header_byte_w &&
                                (tlv_hdr_pos_r == 2'd3);
  assign ann_tlv_value_byte_w = (mtype_r == MT_ANN_C) && !tlv_hdr_run_r &&
                                (tlv_left_r != 16'd0) &&
                                (cnt_r <= msg_end_r);
  assign ann_tlv_value_end_w = ann_tlv_value_byte_w &&
                               (tlv_left_r == 16'd1);
  //! IEEE 1588-2008 5.3.8: lengthField makes the total TLV length even.
  //! A generic zero-length value is complete; PATH_TRACE adds its own 8N,
  //! nonzero/count/head rules and is singular in an Announce.
  assign ann_tlv_header_bad_w = ann_tlv_header_end_w &&
      (ann_tlv_len_w[0] ||
       ({6'd0, cnt_r} + {1'b0, ann_tlv_len_w} > {6'd0, msg_end_r}) ||
       ((ann_tlv_type_w == 16'h0008) &&
        ((ann_tlv_len_w == 16'd0) || ann_tlv_len_w[2:0] || pt_seen_r ||
         ({1'b0, ann_tlv_len_w[15:3]} !=
          ({1'b0, steps_r} + 17'd1)))));
  //! Include the current EOF byte despite non-blocking state updates. This is
  //! true only at the exact fixed-body end or at a complete header/value end
  //! that coincides with the declared messageLength; physical padding cannot
  //! finish a partial declared TLV chain.
  assign ann_tlv_chain_done_after_w = tlv_chain_done_r ||
      ((cnt_r == 11'(OFF_AN_TSRC_C)) &&
       (msg_end_r == 11'(OFF_AN_TSRC_C))) ||
      (ann_tlv_header_end_w && (ann_tlv_len_w == 16'd0) &&
       (cnt_r == msg_end_r) && !ann_tlv_header_bad_w) ||
      (ann_tlv_value_end_w && (cnt_r == msg_end_r));
  assign ann_pt_byte_w = (mtype_r == MT_ANN_C) && pt_run_r &&
                          (pt_left_r != 16'd0) &&
                         (cnt_r <= msg_end_r);
  assign ann_pt_identity_w = ann_pt_byte_w && (pt_byte_r == 3'd7);
  assign ann_head_bad_w = ann_pt_identity_w && (pt_cnt_r == 8'd0) &&
                          (acc_nxt_w != gm_r);
  assign ann_pt_left_after_w = pt_left_r - (ann_pt_byte_w ? 16'd1 : 16'd0);

  logic [7:0] ev_map_w;
  always_comb begin : ev_map
    unique case (mtype_r)
      MT_SYNC_C:   ev_map_w = EV_RX_SYNC_C;
      MT_FU_C:     ev_map_w = EV_RX_FOLLOWUP_C;
      MT_ANN_C:    ev_map_w = EV_RX_ANNOUNCE_C;
      MT_PDREQ_C:  ev_map_w = EV_RX_PDREQ_C;
      MT_PDRESP_C: ev_map_w = EV_RX_PDRESP_C;
      MT_PDRFU_C:  ev_map_w = EV_RX_PDRFU_C;
      MT_SIG_C:    ev_map_w = EV_RX_SIGNAL_C;
      default:     ev_map_w = 8'd0;
    endcase
  end

  // ------------------------------------------------------------ sequential
  always_ff @(posedge clk_i) begin : parse
    if (!rst_n) begin
      cnt_r       <= '0;
      run_r       <= 1'b0;
      bad_r       <= 1'b0;
      mtype_r     <= '0;
      seq_r       <= '0;
      flags_r     <= '0;
      acc_r       <= '0;
      utc_r       <= '0;
      msg_end_r   <= '0;
      steps_r     <= '0;
      gm_r        <= '0;
      tlv_hdr_run_r <= 1'b0;
      tlv_hdr_pos_r <= '0;
      tlv_left_r    <= '0;
      tlv_chain_done_r <= 1'b0;
      pt_left_r   <= '0;
      pt_cnt_r    <= '0;
      pt_byte_r   <= '0;
      pt_run_r    <= 1'b0;
      pt_seen_r   <= 1'b0;
      pt_self_r   <= 1'b0;
      drop_cnt_r  <= '0;
      fin_r       <= 1'b0;
      fin_ok_r    <= 1'b0;
      bank_we_o   <= 1'b0;
      bank_addr_o <= '0;
      bank_wdata_o <= '0;
      ev_valid_o  <= 1'b0;
      ev_code_o   <= '0;
      ev_seq_o    <= '0;
    end else begin
      bank_we_o  <= 1'b0;
      ev_valid_o <= 1'b0;

      // deferred end-of-frame: every last-byte write has settled
      if (fin_drop_w || runt_drop_w)
        drop_cnt_r <= drop_cnt_r +
                      ((fin_drop_w && runt_drop_w) ? 16'd2 : 16'd1);

      if (fin_r) begin
        fin_r <= 1'b0;
        if (fin_ok_r) begin
          if (mtype_r == MT_ANN_C) begin
            bank_we_o    <= 1'b1;
            bank_addr_o  <= 5'd12;
            bank_wdata_o <= {55'd0, pt_self_r, pt_cnt_r};
          end
          ev_valid_o <= 1'b1;
          ev_code_o  <= ev_map_w;
          ev_seq_o   <= seq_r;
        end
      end

      if (rx_valid_i) begin
        if (rx_sof_i) begin
          cnt_r    <= 11'd1;
          run_r    <= 1'b1;
          bad_r    <= 1'b0;
          mtype_r  <= '0;
          msg_end_r <= '0;
          steps_r  <= '0;
          gm_r     <= '0;
          tlv_hdr_run_r <= 1'b0;
          tlv_hdr_pos_r <= '0;
          tlv_left_r <= '0;
          tlv_chain_done_r <= 1'b0;
          pt_run_r <= 1'b0;
          pt_cnt_r <= '0;
          pt_left_r <= '0;
          pt_byte_r <= '0;
          pt_seen_r <= 1'b0;
          pt_self_r <= 1'b0;
          acc_r    <= {56'd0, rx_data_i};
        end else if (run_r) begin
          cnt_r <= cnt_r + 11'd1;
          acc_r <= acc_nxt_w;

          // ---------------- header + common fields --------------------
          unique case (cnt_r)
            11'(OFF_ETYPE_LO_C):
              if ({acc_r[7:0], rx_data_i} != 16'h88F7) bad_r <= 1'b1;
            11'(OFF_TYPE_C): begin
              if (rx_data_i[7:4] != 4'h1) bad_r <= 1'b1;
              // an unlisted messageType has no handler, no body layout and
              // no minimum of its own: refuse it here, beside the
              // transportSpecific compare and ahead of every bank write
              if (!(rx_data_i[3:0] inside {MT_SYNC_C, MT_PDREQ_C, MT_PDRESP_C,
                                           MT_FU_C, MT_PDRFU_C, MT_ANN_C,
                                           MT_SIG_C})) bad_r <= 1'b1;
              //! Before the generated image has installed thisClock there
              //! is no sound all-hop loop verdict. Refuse the whole Announce
              //! rather than let a pre-init over-cap path escape.
              if ((rx_data_i[3:0] == MT_ANN_C) && !local_clock_valid_i)
                bad_r <= 1'b1;
              mtype_r <= rx_data_i[3:0];
            end
            11'(OFF_VER_C):
              if (rx_data_i[3:0] != 4'h2) bad_r <= 1'b1;
            11'(OFF_MSGLEN_END_C): begin
              msg_end_r <= 11'(acc_nxt_w[15:0] +
                               16'(OFF_TYPE_C - 1));
              if ((acc_nxt_w[15:0] < min_len_w) ||
                  (acc_nxt_w[15:0] > MAX_MSG_LEN_C)) bad_r <= 1'b1;
            end
            11'(OFF_DOM_C):
              if (rx_data_i != DOMAIN_C) bad_r <= 1'b1;
            11'(OFF_CORR_END_C): begin
              bank_we_o    <= !bad_r;
              bank_addr_o  <= 5'd1;
              bank_wdata_o <= acc_nxt_w;
            end
            11'(OFF_SRCID_END_C): begin
              bank_we_o    <= !bad_r;
              bank_addr_o  <= 5'd2;
              bank_wdata_o <= acc_nxt_w;
            end
            11'(OFF_SRCPN_END_C): begin
              bank_we_o    <= !bad_r;
              bank_addr_o  <= 5'd3;
              bank_wdata_o <= {48'd0, acc_nxt_w[15:0]};
            end
            11'(OFF_FLAGS0_C + 1): flags_r <= acc_nxt_w[15:0];
            11'(OFF_SEQ0_C + 1):   seq_r   <= acc_nxt_w[15:0];
            11'(OFF_LOGI_C): begin
              bank_we_o    <= !bad_r;
              bank_addr_o  <= 5'd0;
              bank_wdata_o <= {8'd0, 4'd0, mtype_r, seq_r, DOMAIN_C,
                               flags_r, rx_data_i};
            end
            default: ;
          endcase

          // ---------------- per-type body ------------------------------
          if (!bad_r) begin
            // shared 10-byte timestamp position (sync / fu / pdelay)
            if (mtype_r inside {MT_SYNC_C, MT_FU_C, MT_PDRESP_C,
                                MT_PDRFU_C}) begin
              if (cnt_r == 11'(OFF_TS_SEC_END_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd4;
                bank_wdata_o <= {16'd0, acc_nxt_w[47:0]};
              end
              if (cnt_r == 11'(OFF_TS_NS_END_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd5;
                bank_wdata_o <= {32'd0, acc_nxt_w[31:0]};
              end
            end
            if (mtype_r inside {MT_PDRESP_C, MT_PDRFU_C}) begin
              if (cnt_r == 11'(OFF_RQID_END_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd6;
                bank_wdata_o <= acc_nxt_w;
              end
              if (cnt_r == 11'(OFF_RQPN_END_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd7;
                bank_wdata_o <= {48'd0, acc_nxt_w[15:0]};
              end
            end
            if (mtype_r == MT_FU_C) begin
              // the information TLV header: tlvType at octets 44..45,
              // then lengthField, organizationId and organizationSubType
              // at 46..53; a mismatch poisons the frame, so neither the
              // w11 write below nor the event follows
              if ((cnt_r == 11'(OFF_FU_TLVT_END_C)) &&
                  (acc_nxt_w[15:0] != FU_TLV_TYPE_C)) bad_r <= 1'b1;
              if ((cnt_r == 11'(OFF_FU_TLVH_END_C)) &&
                  (acc_nxt_w != FU_TLV_HDR_C)) bad_r <= 1'b1;
              if (cnt_r == 11'(OFF_FU_TBI_END_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd11;
                bank_wdata_o <= {acc_nxt_w[47:16], acc_nxt_w[15:0],
                                 16'd0};
              end
            end
            if (mtype_r == MT_ANN_C) begin
              if (cnt_r == 11'(OFF_AN_UTC0_C + 1))
                utc_r <= acc_nxt_w[15:0];
              if (cnt_r == 11'(OFF_AN_P2_C)) begin
                // utc straddles the 8-byte window, latched separately
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd8;
                bank_wdata_o <= {utc_r, acc_nxt_w[47:40],
                                 acc_nxt_w[39:8], acc_nxt_w[7:0]};
              end
              if (cnt_r == 11'(OFF_AN_GM_END_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd9;
                bank_wdata_o <= acc_nxt_w;
                gm_r         <= acc_nxt_w;
              end
              if (cnt_r == 11'(OFF_AN_SR_END_C))
                steps_r <= acc_nxt_w[15:0];
              if (cnt_r == 11'(OFF_AN_TSRC_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd10;
                bank_wdata_o <= {acc_r[15:0], rx_data_i, 40'd0};
                if (msg_end_r == 11'(OFF_AN_TSRC_C)) begin
                  tlv_chain_done_r <= 1'b1;
                end else if (msg_end_r > 11'(OFF_AN_TSRC_C)) begin
                  tlv_hdr_run_r <= 1'b1;
                  tlv_hdr_pos_r <= '0;
                end
              end
              // Generic TLV chain (IEEE 1588-2008 5.3.8 / 14.1): use every
              // complete header's length to skip an unknown type and attempt
              // the next TLV. A malformed/truncated chain is not allowed to
              // turn into an early accepted Announce. PATH_TRACE is singular
              // and adds the profile's complete 8N/count/head/loop checks.
              if (ann_tlv_header_byte_w) begin
                if (!ann_tlv_header_end_w) begin
                  tlv_hdr_pos_r <= tlv_hdr_pos_r + 2'd1;
                end else begin
                  tlv_hdr_run_r <= 1'b0;
                  tlv_hdr_pos_r <= '0;
                  if (ann_tlv_header_bad_w) begin
                    bad_r <= 1'b1;
                  end else if (ann_tlv_len_w == 16'd0) begin
                    tlv_left_r <= '0;
                    pt_run_r   <= 1'b0;
                    if (cnt_r == msg_end_r)
                      tlv_chain_done_r <= 1'b1;
                    else
                      tlv_hdr_run_r <= 1'b1;
                  end else begin
                    tlv_left_r <= ann_tlv_len_w;
                    if (ann_tlv_type_w == 16'h0008) begin
                      pt_seen_r <= 1'b1;
                      pt_run_r  <= 1'b1;
                      pt_left_r <= ann_tlv_len_w;
                      pt_byte_r <= '0;
                    end else begin
                      pt_run_r <= 1'b0;
                    end
                  end
                end
              end else if (ann_tlv_value_byte_w) begin
                tlv_left_r <= tlv_left_r - 16'd1;
                if (pt_run_r) begin
                  pt_left_r <= pt_left_r - 16'd1;
                  pt_byte_r <= pt_byte_r + 3'd1;
                  if (pt_byte_r == 3'd7) begin
                    if (pt_cnt_r < 8'd8) begin
                      bank_we_o    <= 1'b1;
                      bank_addr_o  <= 5'd16 + 5'(pt_cnt_r[2:0]);
                      bank_wdata_o <= acc_nxt_w;
                    end
                    if (acc_nxt_w == local_clock_id_i) pt_self_r <= 1'b1;
                    //! Never synthesize {grandmasterIdentity, tail}: the first
                    //! received identity is part of the authenticated epoch.
                    if ((pt_cnt_r == 8'd0) && (acc_nxt_w != gm_r))
                      bad_r <= 1'b1;
                    pt_cnt_r <= pt_cnt_r + 8'd1;
                  end
                end
                if (ann_tlv_value_end_w) begin
                  pt_run_r <= 1'b0;
                  if (cnt_r == msg_end_r)
                    tlv_chain_done_r <= 1'b1;
                  else begin
                    tlv_hdr_run_r <= 1'b1;
                    tlv_hdr_pos_r <= '0;
                  end
                end
              end
            end
          end

          // ---------------- end of frame -------------------------------
          //! bad_r is sampled as registered. Fixed header/FU poison arms sit
          //! below their type minima. Announce TLV headers and the first path
          //! identity can legitimately end on EOF, so their current-byte bad
          //! terms and chain completion are included explicitly below.
          if (rx_eof_i) begin
            run_r    <= 1'b0;
            fin_r    <= 1'b1;
            fin_ok_r <= !bad_r && !rx_err_i && (cnt_r >= min_end_w) &&
                        (cnt_r >= msg_end_r) &&
                        ((mtype_r != MT_ANN_C) ||
                         (ann_tlv_chain_done_after_w &&
                          !ann_tlv_header_bad_w && !ann_head_bad_w &&
                          (!pt_seen_r ||
                           (ann_pt_left_after_w == 16'd0))));
          end
        end

        if (rx_sof_i && rx_eof_i) begin
          // one-byte frame: malformed by construction, counted above
          run_r <= 1'b0;
        end
      end
    end
  end

  assign fin_drop_w  = fin_r && !fin_ok_r;
  assign runt_drop_w = rx_valid_i && rx_sof_i && rx_eof_i;

  assign drop_cnt_o = drop_cnt_r;

endmodule : KL_gptp_rx_parser
`default_nettype wire
