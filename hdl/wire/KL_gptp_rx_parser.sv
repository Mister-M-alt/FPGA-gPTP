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
//                processing), frame truncated before the per-type
//                minimum, rx_err_i. The domain arm sits at header byte
//                4, ahead of every message-bank write, so a foreign-
//                domain frame leaves nothing a handler could read.
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
//                  w12 {56'd0, pathTraceCount}
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

  // ---- absolute byte offsets (DA = byte 0, PTP header = byte 14) --------
  localparam int unsigned OFF_ETYPE_HI_C = 12;
  localparam int unsigned OFF_ETYPE_LO_C = 13;
  localparam int unsigned OFF_TYPE_C     = 14;
  localparam int unsigned OFF_VER_C      = 15;
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
  // follow-up information TLV
  localparam int unsigned OFF_FU_TLVT_END_C = 59;
  localparam int unsigned OFF_FU_CSRO_END_C = 71;
  localparam int unsigned OFF_FU_TBI_END_C  = 73;

  // ---- parse state -------------------------------------------------------
  logic [10:0] cnt_r;          //! absolute byte index of the CURRENT byte
  logic        run_r;          //! a frame is being consumed
  logic        bad_r;          //! poisoned: consume to eof, then drop
  logic [3:0]  mtype_r;
  logic [15:0] seq_r;
  logic [15:0] flags_r;
  logic [63:0] acc_r;          //! big-endian byte accumulator
  logic        min_ok_r;       //! per-type minimum body consumed
  logic [15:0] utc_r;          //! announce currentUtcOffset (straddles acc)
  logic        fu_tlv_ok_r;    //! follow-up information TLV type matched
  // announce path trace walk
  logic [15:0] pt_left_r;      //! TLV bytes remaining
  logic [7:0]  pt_cnt_r;       //! hops seen
  logic [2:0]  pt_byte_r;      //! byte inside the current identity
  logic        pt_run_r;
  logic [15:0] drop_cnt_r;
  //! end-of-frame settles one cycle late: last-byte field writes and the
  //! per-type minimum flag are non-blocking, and the announce hop-count
  //! word must not fight the final identity write for the one bank lane
  logic        fin_r;
  logic        fin_ok_r;

  logic [63:0] acc_nxt_w;
  assign acc_nxt_w = {acc_r[55:0], rx_data_i};

  //! per-type minimum length (absolute index of the last mandatory byte)
  logic [10:0] min_end_w;
  always_comb begin : min_len
    unique case (mtype_r)
      MT_ANN_C:    min_end_w = 11'(OFF_AN_TSRC_C);
      MT_PDRESP_C,
      MT_PDRFU_C:  min_end_w = 11'(OFF_RQPN_END_C);
      MT_SYNC_C,
      MT_FU_C:     min_end_w = 11'(OFF_TS_NS_END_C);
      MT_PDREQ_C,
      MT_SIG_C:    min_end_w = 11'(OFF_LOGI_C);
      default:     min_end_w = 11'(OFF_LOGI_C);
    endcase
  end

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
      min_ok_r    <= 1'b0;
      utc_r       <= '0;
      fu_tlv_ok_r <= 1'b0;
      pt_left_r   <= '0;
      pt_cnt_r    <= '0;
      pt_byte_r   <= '0;
      pt_run_r    <= 1'b0;
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
      if (fin_r) begin
        fin_r <= 1'b0;
        if (fin_ok_r && min_ok_r) begin
          if (mtype_r == MT_ANN_C) begin
            bank_we_o    <= 1'b1;
            bank_addr_o  <= 5'd12;
            bank_wdata_o <= {56'd0, pt_cnt_r};
          end
          ev_valid_o <= 1'b1;
          ev_code_o  <= ev_map_w;
          ev_seq_o   <= seq_r;
        end else begin
          drop_cnt_r <= drop_cnt_r + 16'd1;
        end
      end

      if (rx_valid_i) begin
        if (rx_sof_i) begin
          cnt_r    <= 11'd1;
          run_r    <= 1'b1;
          bad_r    <= 1'b0;
          mtype_r  <= '0;
          min_ok_r <= 1'b0;
          pt_run_r <= 1'b0;
          pt_cnt_r <= '0;
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
              mtype_r <= rx_data_i[3:0];
            end
            11'(OFF_VER_C):
              if (rx_data_i[3:0] != 4'h2) bad_r <= 1'b1;
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
              min_ok_r     <= (mtype_r inside {MT_PDREQ_C, MT_SIG_C});
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
                min_ok_r     <= (mtype_r inside {MT_SYNC_C, MT_FU_C});
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
                min_ok_r     <= 1'b1;
              end
            end
            if (mtype_r == MT_FU_C) begin
              if (cnt_r == 11'(OFF_FU_TLVT_END_C))
                // information TLV type must be 0x0003; else ignore body
                fu_tlv_ok_r <= (acc_nxt_w[15:0] == 16'h0003);
              if (cnt_r == 11'(OFF_FU_TBI_END_C)) begin
                bank_we_o    <= fu_tlv_ok_r;
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
              end
              if (cnt_r == 11'(OFF_AN_TSRC_C)) begin
                bank_we_o    <= 1'b1;
                bank_addr_o  <= 5'd10;
                bank_wdata_o <= {acc_r[15:0], rx_data_i, 40'd0};
                min_ok_r     <= 1'b1;
              end
              // path trace TLV: header, then 8-byte identities
              if (cnt_r == 11'(OFF_AN_TLV_C + 3)) begin
                if (acc_nxt_w[31:16] == 16'h0008) begin
                  pt_run_r  <= 1'b1;
                  pt_left_r <= acc_nxt_w[15:0];
                  pt_byte_r <= '0;
                end
              end else if (pt_run_r && (pt_left_r != 16'd0)) begin
                pt_left_r <= pt_left_r - 16'd1;
                pt_byte_r <= pt_byte_r + 3'd1;
                if (pt_byte_r == 3'd7) begin
                  if (pt_cnt_r < 8'd8) begin
                    bank_we_o    <= 1'b1;
                    bank_addr_o  <= 5'd16 + 5'(pt_cnt_r[2:0]);
                    bank_wdata_o <= acc_nxt_w;
                  end
                  pt_cnt_r <= pt_cnt_r + 8'd1;
                end
              end
            end
          end

          // ---------------- end of frame -------------------------------
          if (rx_eof_i) begin
            run_r    <= 1'b0;
            fin_r    <= 1'b1;
            fin_ok_r <= !bad_r && !rx_err_i && (cnt_r >= min_end_w);
          end
        end

        if (rx_sof_i && rx_eof_i) begin
          // one-byte frame: malformed by construction
          run_r      <= 1'b0;
          drop_cnt_r <= drop_cnt_r + 16'd1;
        end
      end
    end
  end

  assign drop_cnt_o = drop_cnt_r;

endmodule : KL_gptp_rx_parser
`default_nettype wire
