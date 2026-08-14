/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : KL_gptp_ucpu.sv
//  Project     : 802.1AS gPTP protocol processor (time-sync plane)
//
//  Description : gPTP micro-coded engine — a PURE SUPERSET of the AECP
//                µCPU skeleton (protocol-processor hdl/aecp/KL_aecp_ucpu.sv,
//                measured 1,070 LUT / 491 FF / 3 RAMB36 on xc7a100t-2).
//                Every base pipeline stage, port and decode arm is kept in
//                place so that this module's out-of-context delta against
//                that anchor prices EXACTLY the arithmetic growth:
//
//                  OP_ALU     64-bit ADD/SUB/AND/OR/XOR single-cycle;
//                             SHL/SHR/SAR serial, one bit per cycle
//                             (protocol rate is <= 8 Hz — a barrel
//                             shifter would buy latency nothing needs).
//                  OP_MULDIV  MULS: signed 32x32 -> 64, one registered
//                             product stage (DSP-inferred);
//                             DIVU: restoring 64/32 -> 64 quotient, one
//                             bit per cycle. Divide-by-zero is µcode's
//                             contract to guard; hardware returns an
//                             all-ones-shaped quotient and does not trap.
//
//                Differences from the base other than the two opcodes:
//                the ROM is 1024 deep (UPC_W_C = 10 — event handlers, not
//                descriptor walks), and dispatch clears the build cursor
//                to 0 (a gPTP PDU has no 12-byte AECP response header).
//                r15/r14/r13 preload at dispatch: event descriptor,
//                timestamp 0, timestamp 1 (gptp_ucpu_pkg).
//
//                RAW hazard: single pending-writeback interlock. Branches
//                resolve in E and flush F/D. Multi-cycle operations
//                (state, gather, copy, shift, mul, div, send) hold E.
//---------------------------------------------------------------------------//
`default_nettype none

module KL_gptp_ucpu
  import gptp_ucpu_pkg::*;
#(
    //! path of the µcode ROM image (1024 lines of 12 hex digits)
    parameter string UCODE_HEX_P = "gptp_ucode.hex"
) (
    input  wire         clk_i,
    input  wire         rst_n,

    //! dispatch: one event enters with its µPC entry + preload operands
    input  wire                disp_valid_i,
    output logic               disp_ready_o,
    input  wire  [UPC_W_C-1:0] disp_upc_i,
    input  wire  [63:0]        disp_ev_i,     //! -> r15 event descriptor
    input  wire  [63:0]        disp_ts0_i,    //! -> r14 timestamp 0
    input  wire  [63:0]        disp_ts1_i,    //! -> r13 timestamp 1

    //! state port: engine region map (msg bank / ts regs / scratch /
    //! publish / phc / timer), 1RW, single outstanding
    output logic        st_req_o,
    output logic        st_we_o,
    output logic        st_name_o,         //! base-compat region select
    output logic [19:0] st_addr_o,
    output logic [63:0] st_wdata_o,
    output logic  [7:0] st_wstrb_o,
    input  wire         st_ready_i,
    input  wire         st_rvalid_i,
    input  wire  [63:0] st_rdata_i,
    input  wire         st_err_i,

    //! gather port: atomic snapshots (live PHC ns, free-running ms)
    output logic        gx_req_o,
    output logic  [7:0] gx_sel_o,
    input  wire         gx_valid_i,
    input  wire  [63:0] gx_data_i,

    //! lock context — base-compat, tie inert (no locks in this plane)
    input  wire         lock_held_i,
    input  wire  [63:0] lock_ctlr_i,

    //! TX slot: 32-bit write lane + strobes, flow controlled
    output logic        rb_we_o,
    output logic  [9:0] rb_addr_o,
    output logic [31:0] rb_wdata_o,
    output logic  [3:0] rb_wstrb_o,
    input  wire         rb_ready_i,

    //! respond / effects
    output logic        resp_send_o,
    output logic [10:0] resp_len_o,
    output logic  [4:0] resp_status_o,
    input  wire         tx_ready_i,
    output logic        eff_commit_o,
    output logic  [7:0] eff_nvm_mark_o,
    output logic        eff_nvm_stb_o,
    output logic  [3:0] eff_notify_class_o,
    output logic        eff_notify_stb_o,

    //! observability
    output logic               busy_o,
    output logic               done_o,
    output logic [UPC_W_C-1:0] dbg_upc_o,
    output logic  [4:0]        dbg_status_o,
    output logic               dbg_ovf_o
);

  // ------------------------------------------------------------------ ROM
  logic [UCODE_W_C-1:0] rom_r [0:(1<<UPC_W_C)-1];
  initial $readmemh(UCODE_HEX_P, rom_r);

  logic [UCODE_W_C-1:0] rom_q_r;
  logic [UPC_W_C-1:0]   upc_r;

  // ------------------------------------------------------- register file
  // 16 x 64 distributed RAM, 1W3R (SET_MASKED reads rd as well).
  (* ram_style = "distributed" *) logic [63:0] rf_r [0:15];
  logic  [3:0] rf_waddr_w;
  logic [63:0] rf_wdata_w;
  logic        rf_we_w;

  always_ff @(posedge clk_i) begin : rf_write
    if (rf_we_w) rf_r[rf_waddr_w] <= rf_wdata_w;
  end

  // ------------------------------------------------------- machine state
  typedef enum logic [2:0] {
    S_IDLE, S_PRE2, S_PRE1, S_PRE0, S_RUN
  } mstate_e;
  mstate_e ms_r;

  // pipeline registers
  logic        vld_d_r;
  uop_t        uop_e_r;
  logic        vld_e_r;
  logic [63:0] opa_e_r, opb_e_r, opd_e_r;
  logic  [3:0] wb_rd_r;
  logic [63:0] wb_data_r;
  logic        wb_we_r;

  // architectural side state
  logic  [4:0] status_r;
  logic        z_r, lt_r, ovf_r;
  logic [19:0] desc_base_r;
  logic  [7:0] iter_cnt_r, iter_idx_r;
  logic  [9:0] cursor_r;
  logic [10:0] resp_len_r;

  // multi-cycle E sequencing (base)
  logic  [3:0] eseq_r;
  logic        copy_go_r;
  logic [15:0] copy_left_r;
  logic [12:0] copy_idx_r;
  logic [63:0] copy_lane_r;

  // multi-cycle E sequencing (arithmetic growth)
  logic        sh_go_r;                     //! serial shift in flight
  logic [63:0] sh_acc_r;
  logic  [5:0] sh_cnt_r;
  logic        md_go_r;                     //! mul/div in flight
  (* use_dsp = "yes" *) logic [63:0] md_p_r; //! registered 32x32 product
  logic [31:0] md_rem_r;
  logic [63:0] md_quo_r;
  logic [31:0] md_div_r;
  logic  [6:0] md_cnt_r;

  uop_t uop_d_w;
  assign uop_d_w = uop_t'(rom_q_r);

  // ------------------------------------------------------------- hazards
  logic raw_d_w;
  logic e_writes_w;
  always_comb begin : raw_detect
    e_writes_w = vld_e_r && (uop_e_r.op inside {OP_MOVE, OP_SET_MASKED,
                                                OP_READ_ST, OP_NAME_RD,
                                                OP_GATHER_EXT,
                                                OP_ALU, OP_MULDIV});
    raw_d_w = vld_d_r &&
              ((e_writes_w && ((uop_d_w.ra == uop_e_r.rd) ||
                               (uop_d_w.rb == uop_e_r.rd) ||
                               (uop_d_w.rd == uop_e_r.rd))) ||
               (wb_we_r    && ((uop_d_w.ra == wb_rd_r) ||
                               (uop_d_w.rb == wb_rd_r) ||
                               (uop_d_w.rd == wb_rd_r))));
  end

  // ------------------------------------------------------------ E stage
  logic [63:0] a_fmt_w, b_or_imm_w;
  always_comb begin : operand_shape
    unique case (uop_e_r.fmt)
      FMT_B_C: a_fmt_w = {56'd0, opa_e_r[7:0]};
      FMT_W_C: a_fmt_w = {48'd0, opa_e_r[15:0]};
      FMT_D_C: a_fmt_w = {32'd0, opa_e_r[31:0]};
      default: a_fmt_w = opa_e_r;
    endcase
    b_or_imm_w = (uop_e_r.rb != 4'd0) ? opb_e_r : {40'd0, uop_e_r.imm};
  end

  // 32-bit ALU (compare path) + 64-bit merge (base)
  logic [32:0] sub_w;
  logic        cmp_z_w, cmp_lt_w;
  logic [63:0] merged_w;
  always_comb begin : alu
    sub_w    = {1'b0, a_fmt_w[31:0]} - {1'b0, b_or_imm_w[31:0]};
    cmp_z_w  = (uop_e_r.fmt == FMT_Q_C) ? (opa_e_r == b_or_imm_w)
                                        : (sub_w[31:0] == 32'd0);
    cmp_lt_w = sub_w[32];
    merged_w = (opd_e_r & ~opb_e_r) | (opa_e_r & opb_e_r);
  end

  // 64-bit arithmetic datapath (growth)
  logic        alu_is_shift_w;
  logic [63:0] alu_res_w;
  always_comb begin : alu64
    alu_is_shift_w = (uop_e_r.cnd[2:0] inside {ALU_SHL_C, ALU_SHR_C,
                                               ALU_SAR_C});
    unique case (uop_e_r.cnd[2:0])
      ALU_ADD_C: alu_res_w = opa_e_r + b_or_imm_w;
      ALU_SUB_C: alu_res_w = opa_e_r - b_or_imm_w;
      ALU_AND_C: alu_res_w = opa_e_r & b_or_imm_w;
      ALU_OR_C:  alu_res_w = opa_e_r | b_or_imm_w;
      ALU_XOR_C: alu_res_w = opa_e_r ^ b_or_imm_w;
      default:   alu_res_w = sh_acc_r;      // shifts complete out of sh_acc
    endcase
  end

  logic [63:0] mult_w;
  always_comb begin : mult
    mult_w = 64'(signed'(opa_e_r[31:0]) * signed'(opb_e_r[31:0]));
  end

  // restoring divider step: rem < div is the loop invariant, so the
  // 33-bit trial value never needs a stored bit 32
  logic [32:0] div_work_w;
  logic        div_ge_w;
  always_comb begin : div_step
    div_work_w = {md_rem_r, md_quo_r[63]};
    div_ge_w   = (div_work_w >= {1'b0, md_div_r});
  end

  logic sh_done_w, md_done_w;
  assign sh_done_w = sh_go_r && (sh_cnt_r == 6'd0);
  assign md_done_w = md_go_r && (md_cnt_r == 7'd0);

  logic rel_pass_w;
  always_comb begin : relation
    unique case (uop_e_r.cnd[2:0])
      3'd0:    rel_pass_w = cmp_z_w;
      3'd1:    rel_pass_w = !cmp_z_w;
      3'd2:    rel_pass_w = cmp_lt_w;
      3'd3:    rel_pass_w = !cmp_lt_w;
      default: rel_pass_w = cmp_z_w;
    endcase
  end

  logic brflag_w;
  always_comb begin : branch_flag
    unique case (uop_e_r.cnd)
      4'd0:    brflag_w = (status_r != ST_OK_C);
      4'd1:    brflag_w = (iter_idx_r == iter_cnt_r);
      4'd2:    brflag_w = z_r;
      4'd3:    brflag_w = lt_r;
      4'd4:    brflag_w = ovf_r;
      default: brflag_w = 1'b0;
    endcase
  end

  logic [3:0] fld_len_w;
  always_comb begin : field_len
    unique case (uop_e_r.fmt)
      FMT_B_C: fld_len_w = 4'd1;
      FMT_W_C: fld_len_w = 4'd2;
      FMT_D_C: fld_len_w = 4'd4;
      default: fld_len_w = 4'd8;
    endcase
  end

  logic [3:0] copy_adv1_w, copy_adv2_w;
  always_comb begin : copy_residual
    copy_adv1_w = (copy_left_r > 16'd4) ? 4'd4 : 4'(copy_left_r[3:0]);
    if (copy_left_r <= 16'd4)      copy_adv2_w = 4'd0;
    else if (copy_left_r > 16'd8)  copy_adv2_w = 4'd4;
    else                           copy_adv2_w = 4'(copy_left_r[3:0] - 4'd4);
  end

  logic append_skip_w;
  assign append_skip_w = (uop_e_r.op == OP_APPEND) &&
                         (({1'b0, cursor_r} + {7'd0, fld_len_w}) >
                          11'(TXSLOT_BYTES_C));

  logic is_q_field_w;
  assign is_q_field_w = (uop_e_r.op inside {OP_BUILD_FLD, OP_APPEND}) &&
                        (uop_e_r.fmt == FMT_Q_C) && !append_skip_w;

  logic rb_hold_w;
  assign rb_hold_w = rb_we_o && !rb_ready_i;

  // ---- E-stage control outcomes ----------------------------------------
  logic stall_e_w;
  logic br_taken_w;
  logic [UPC_W_C-1:0] br_tgt_w;
  logic end_op_w;

  always_comb begin : e_control
    stall_e_w  = 1'b0;
    br_taken_w = 1'b0;
    br_tgt_w   = uop_e_r.imm[UPC_W_C-1:0];
    end_op_w   = 1'b0;
    if (vld_e_r) begin
      unique case (uop_e_r.op)
        OP_BRANCH:     br_taken_w = 1'b1;
        OP_BR_STATUS:  br_taken_w = brflag_w;
        OP_END:        end_op_w   = 1'b1;
        OP_DESC_ADDR,
        OP_READ_ST,
        OP_NAME_RD:    stall_e_w = !st_rvalid_i;
        OP_WRITE_ST,
        OP_NAME_WR:    stall_e_w = !st_ready_i;
        OP_GATHER_EXT,
        OP_MAP_VALID:  stall_e_w = !gx_valid_i;
        OP_READ_CTRS:  stall_e_w = (eseq_r != 4'd4);
        OP_COPY_BUF:   stall_e_w = !copy_go_r || (copy_left_r != 16'd0) ||
                                   (eseq_r != 4'd0);
        OP_BUILD_HDR:  stall_e_w = (eseq_r != 4'd2);
        OP_BUILD_FLD,
        OP_APPEND:     stall_e_w = is_q_field_w && (eseq_r == 4'd0);
        OP_SEND_RESP:  stall_e_w = !tx_ready_i;
        OP_CHECK_LOCK: br_taken_w = lock_held_i && (lock_ctlr_i != opa_e_r);
        OP_CHECK_ARG:  br_taken_w = !rel_pass_w;
        OP_ALU:        stall_e_w = alu_is_shift_w && !sh_done_w;
        OP_MULDIV:     stall_e_w = !md_done_w;
        default: ;
      endcase
      if ((uop_e_r.op == OP_MAP_VALID) && gx_valid_i && !gx_data_i[0])
        br_taken_w = 1'b1;
      if (rb_hold_w) stall_e_w = 1'b1;
    end
  end

  // ------------------------------------------------------- state port out
  always_comb begin : state_port
    st_req_o   = 1'b0;
    st_we_o    = 1'b0;
    st_name_o  = 1'b0;
    st_wdata_o = opa_e_r;
    st_addr_o  = desc_base_r + uop_e_r.imm[19:0];
    unique case (uop_e_r.fmt)
      FMT_B_C: st_wstrb_o = 8'h01;
      FMT_W_C: st_wstrb_o = 8'h03;
      FMT_D_C: st_wstrb_o = 8'h0F;
      default: st_wstrb_o = 8'hFF;
    endcase
    if (vld_e_r) begin
      unique case (uop_e_r.op)
        OP_DESC_ADDR: begin
          st_req_o  = 1'b1;
          st_addr_o = uop_e_r.imm[19:0] ^ {4'd0, opa_e_r[15:0]};
        end
        OP_READ_ST:  st_req_o = 1'b1;
        OP_NAME_RD:  begin st_req_o = 1'b1; st_name_o = 1'b1; end
        OP_WRITE_ST: begin st_req_o = 1'b1; st_we_o = 1'b1; end
        OP_NAME_WR:  begin st_req_o = 1'b1; st_we_o = 1'b1;
                           st_name_o = 1'b1; end
        OP_COPY_BUF: begin
          st_req_o  = copy_go_r && (copy_left_r != 16'd0) &&
                      (eseq_r == 4'd0);
          st_addr_o = desc_base_r + uop_e_r.imm[19:0] +
                      {4'd0, copy_idx_r, 3'd0};
        end
        default: ;
      endcase
    end
  end

  // ------------------------------------------------------ gather port out
  always_comb begin : gather_port
    gx_req_o = 1'b0;
    gx_sel_o = {uop_e_r.cnd, uop_e_r.imm[3:0]};
    if (vld_e_r) begin
      unique case (uop_e_r.op)
        OP_GATHER_EXT: gx_req_o = 1'b1;
        OP_MAP_VALID:  begin gx_req_o = 1'b1;
                             gx_sel_o = {uop_e_r.cnd, 4'd0}; end
        OP_READ_CTRS:  begin gx_req_o = (eseq_r < 4'd4);
                             gx_sel_o = {uop_e_r.cnd, eseq_r}; end
        default: ;
      endcase
    end
  end

  // -------------------------------------------------- TX slot write lane
  logic [31:0] hdr_word_w;
  always_comb begin : header_word
    unique case (eseq_r)
      4'd0:    hdr_word_w = opa_e_r[63:32];
      4'd1:    hdr_word_w = opa_e_r[31:0];
      default: hdr_word_w = {opb_e_r[15:0], 3'd0, status_r, 8'd0};
    endcase
  end

  always_comb begin : resp_buffer
    rb_we_o    = 1'b0;
    rb_addr_o  = cursor_r;
    rb_wdata_o = a_fmt_w[31:0];
    rb_wstrb_o = 4'hF;
    if (vld_e_r) begin
      unique case (uop_e_r.op)
        OP_BUILD_HDR: begin
          rb_we_o    = 1'b1;
          rb_addr_o  = {4'd0, eseq_r[1:0], 4'd0} >> 2;
          rb_wdata_o = hdr_word_w;
        end
        OP_BUILD_FLD, OP_APPEND: begin
          rb_we_o = !append_skip_w;
          if (is_q_field_w) begin
            rb_addr_o  = cursor_r + ((eseq_r == 4'd1) ? 10'd4 : 10'd0);
            rb_wdata_o = (eseq_r == 4'd0) ? opa_e_r[63:32] : opa_e_r[31:0];
          end else begin
            unique case (uop_e_r.fmt)
              FMT_B_C: rb_wstrb_o = 4'h1;
              FMT_W_C: rb_wstrb_o = 4'h3;
              default: rb_wstrb_o = 4'hF;
            endcase
          end
        end
        OP_READ_CTRS: begin
          rb_we_o    = gx_valid_i && (eseq_r < 4'd4);
          rb_wdata_o = gx_data_i[31:0];
        end
        OP_COPY_BUF: begin
          rb_we_o    = (eseq_r == 4'd1) || (eseq_r == 4'd2);
          rb_wdata_o = (eseq_r == 4'd1) ? copy_lane_r[63:32]
                                        : copy_lane_r[31:0];
        end
        default: ;
      endcase
    end
  end

  // ------------------------------------------------------------ effects
  logic advance_e_w;
  assign advance_e_w = vld_e_r && !stall_e_w;

  always_comb begin : effects
    eff_commit_o       = advance_e_w && (uop_e_r.op == OP_COMMIT);
    eff_nvm_stb_o      = advance_e_w && (uop_e_r.op == OP_NVM_MARK);
    eff_nvm_mark_o     = uop_e_r.imm[7:0];
    eff_notify_stb_o   = advance_e_w && (uop_e_r.op == OP_NOTIFY_ENQ);
    eff_notify_class_o = uop_e_r.imm[3:0];
    resp_send_o        = advance_e_w && (uop_e_r.op == OP_SEND_RESP);
    resp_len_o         = resp_len_r;
    resp_status_o      = status_r;
  end

  // --------------------------------------------------------- W writeback
  always_comb begin : writeback_mux
    rf_we_w    = wb_we_r;
    rf_waddr_w = wb_rd_r;
    rf_wdata_w = wb_data_r;
    unique case (ms_r)
      S_PRE2: begin rf_we_w = 1'b1; rf_waddr_w = 4'd15;
                    rf_wdata_w = disp_ev_i; end
      S_PRE1: begin rf_we_w = 1'b1; rf_waddr_w = 4'd14;
                    rf_wdata_w = disp_ts0_i; end
      S_PRE0: begin rf_we_w = 1'b1; rf_waddr_w = 4'd13;
                    rf_wdata_w = disp_ts1_i; end
      default: ;
    endcase
  end

  // ------------------------------------------------------- sequential core
  always_ff @(posedge clk_i) begin : core
    if (!rst_n) begin
      ms_r        <= S_IDLE;
      upc_r       <= '0;
      vld_d_r     <= 1'b0;
      vld_e_r     <= 1'b0;
      wb_we_r     <= 1'b0;
      wb_rd_r     <= '0;
      wb_data_r   <= '0;
      status_r    <= ST_OK_C;
      z_r         <= 1'b0;
      lt_r        <= 1'b0;
      ovf_r       <= 1'b0;
      desc_base_r <= '0;
      iter_cnt_r  <= '0;
      iter_idx_r  <= '0;
      cursor_r    <= '0;
      resp_len_r  <= '0;
      eseq_r      <= '0;
      copy_go_r   <= 1'b0;
      copy_left_r <= '0;
      copy_idx_r  <= '0;
      copy_lane_r <= '0;
      sh_go_r     <= 1'b0;
      sh_acc_r    <= '0;
      sh_cnt_r    <= '0;
      md_go_r     <= 1'b0;
      md_p_r      <= '0;
      md_rem_r    <= '0;
      md_quo_r    <= '0;
      md_div_r    <= '0;
      md_cnt_r    <= '0;
      rom_q_r     <= '0;
      uop_e_r     <= '0;
      opa_e_r     <= '0;
      opb_e_r     <= '0;
      opd_e_r     <= '0;
      done_o      <= 1'b0;
    end else begin
      done_o  <= 1'b0;
      wb_we_r <= 1'b0;

      unique case (ms_r)
        S_IDLE: begin
          vld_d_r <= 1'b0;
          vld_e_r <= 1'b0;
          if (disp_valid_i) begin
            ms_r        <= S_PRE2;
            upc_r       <= disp_upc_i;
            status_r    <= ST_OK_C;
            z_r         <= 1'b0;
            lt_r        <= 1'b0;
            ovf_r       <= 1'b0;
            cursor_r    <= 10'd0;       //! gPTP PDUs build from byte 0
            resp_len_r  <= 11'd0;
            iter_cnt_r  <= '0;
            iter_idx_r  <= '0;
            eseq_r      <= '0;
            copy_go_r   <= 1'b0;
            copy_left_r <= '0;
            sh_go_r     <= 1'b0;
            md_go_r     <= 1'b0;
          end
        end
        S_PRE2: ms_r <= S_PRE1;
        S_PRE1: ms_r <= S_PRE0;
        S_PRE0: ms_r <= S_RUN;

        S_RUN: begin
          // ---------------- F: µcode ROM sync read ----------------------
          if (!stall_e_w && !raw_d_w) begin
            rom_q_r <= rom_r[upc_r];
            vld_d_r <= 1'b1;
            upc_r   <= upc_r + UPC_W_C'(1);
          end

          // ---------------- D -> E latch --------------------------------
          if (!stall_e_w) begin
            if (raw_d_w) begin
              vld_e_r <= 1'b0;
            end else begin
              vld_e_r <= vld_d_r;
              uop_e_r <= uop_d_w;
              opa_e_r <= rf_r[uop_d_w.ra];
              opb_e_r <= rf_r[uop_d_w.rb];
              opd_e_r <= rf_r[uop_d_w.rd];
            end
          end

          // ---------------- E: per-beat sequencing ----------------------
          if (vld_e_r && !rb_hold_w) begin
            unique case (uop_e_r.op)
              OP_BUILD_HDR: begin
                eseq_r <= (eseq_r == 4'd2) ? 4'd0 : eseq_r + 4'd1;
              end
              OP_BUILD_FLD, OP_APPEND: begin
                if (is_q_field_w)
                  eseq_r <= (eseq_r == 4'd1) ? 4'd0 : 4'd1;
              end
              OP_READ_CTRS: begin
                if (gx_valid_i && (eseq_r < 4'd4)) begin
                  eseq_r     <= eseq_r + 4'd1;
                  cursor_r   <= cursor_r + 10'd4;
                  resp_len_r <= resp_len_r + 11'd4;
                end else if (eseq_r == 4'd4) begin
                  eseq_r <= 4'd0;
                end
              end
              OP_COPY_BUF: begin
                if (!copy_go_r) begin
                  copy_go_r   <= 1'b1;
                  copy_left_r <= opa_e_r[15:0];
                  copy_idx_r  <= '0;
                end else if ((eseq_r == 4'd0) && st_rvalid_i &&
                             (copy_left_r != 16'd0)) begin
                  copy_lane_r <= st_rdata_i;
                  eseq_r      <= 4'd1;
                end else if (eseq_r == 4'd1) begin
                  eseq_r     <= 4'd2;
                  cursor_r   <= cursor_r + {6'd0, copy_adv1_w};
                  resp_len_r <= resp_len_r + {7'd0, copy_adv1_w};
                end else if (eseq_r == 4'd2) begin
                  eseq_r      <= 4'd0;
                  cursor_r    <= cursor_r + {6'd0, copy_adv2_w};
                  resp_len_r  <= resp_len_r + {7'd0, copy_adv2_w};
                  copy_left_r <= (copy_left_r > 16'd8)
                               ? copy_left_r - 16'd8 : 16'd0;
                  copy_idx_r  <= copy_idx_r + 13'd1;
                end
              end
              //! serial shift: load beat arms, then one bit per cycle
              OP_ALU: begin
                if (alu_is_shift_w) begin
                  if (!sh_go_r) begin
                    sh_go_r  <= 1'b1;
                    sh_acc_r <= opa_e_r;
                    sh_cnt_r <= b_or_imm_w[5:0];
                  end else if (sh_cnt_r != 6'd0) begin
                    sh_cnt_r <= sh_cnt_r - 6'd1;
                    unique case (uop_e_r.cnd[2:0])
                      ALU_SHL_C: sh_acc_r <= {sh_acc_r[62:0], 1'b0};
                      ALU_SHR_C: sh_acc_r <= {1'b0, sh_acc_r[63:1]};
                      default:   sh_acc_r <= {sh_acc_r[63],
                                              sh_acc_r[63:1]};
                    endcase
                  end
                end
              end
              //! MULS: arm, one product register stage, complete.
              //! DIVU: arm, then 64 restoring beats.
              OP_MULDIV: begin
                if (!md_go_r) begin
                  md_go_r <= 1'b1;
                  if (uop_e_r.cnd[0] == MD_DIVU_C) begin
                    md_rem_r <= '0;
                    md_quo_r <= opa_e_r;
                    md_div_r <= (uop_e_r.rb != 4'd0) ? opb_e_r[31:0]
                                                     : {8'd0,
                                                        uop_e_r.imm};
                    md_cnt_r <= 7'd64;
                  end else begin
                    md_p_r   <= mult_w;
                    md_cnt_r <= 7'd1;
                  end
                end else if (md_cnt_r != 7'd0) begin
                  md_cnt_r <= md_cnt_r - 7'd1;
                  if (uop_e_r.cnd[0] == MD_DIVU_C) begin
                    md_rem_r <= div_ge_w ? (div_work_w[31:0] -
                                            md_div_r[31:0])
                                         : div_work_w[31:0];
                    md_quo_r <= {md_quo_r[62:0], div_ge_w};
                  end
                end
              end
              default: eseq_r <= 4'd0;
            endcase

            if (advance_e_w) begin
              copy_go_r <= 1'b0;
              sh_go_r   <= 1'b0;
              md_go_r   <= 1'b0;
              // writeback staging
              unique case (uop_e_r.op)
                OP_MOVE: begin
                  wb_we_r <= 1'b1; wb_rd_r <= uop_e_r.rd;
                  wb_data_r <= (uop_e_r.ra == 4'd0)
                             ? {40'd0, uop_e_r.imm}
                             : a_fmt_w;
                end
                OP_SET_MASKED: begin
                  wb_we_r <= 1'b1; wb_rd_r <= uop_e_r.rd;
                  wb_data_r <= merged_w;
                end
                OP_READ_ST, OP_NAME_RD: begin
                  wb_we_r <= 1'b1; wb_rd_r <= uop_e_r.rd;
                  wb_data_r <= st_rdata_i;
                end
                OP_GATHER_EXT: begin
                  wb_we_r <= 1'b1; wb_rd_r <= uop_e_r.rd;
                  wb_data_r <= gx_data_i;
                end
                OP_ALU: begin
                  wb_we_r <= 1'b1; wb_rd_r <= uop_e_r.rd;
                  wb_data_r <= alu_res_w;
                end
                OP_MULDIV: begin
                  wb_we_r <= 1'b1; wb_rd_r <= uop_e_r.rd;
                  wb_data_r <= (uop_e_r.cnd[0] == MD_DIVU_C) ? md_quo_r
                                                             : md_p_r;
                end
                default: ;
              endcase

              // architectural side effects at op completion
              unique case (uop_e_r.op)
                OP_COMPARE:    begin z_r <= cmp_z_w; lt_r <= cmp_lt_w; end
                OP_DESC_ADDR:  begin
                  if (st_err_i) status_r <= ST_MALFORMED_C;
                  else          desc_base_r <= st_rdata_i[19:0];
                end
                OP_CHECK_LOCK:
                  if (br_taken_w) status_r <= ST_DROP_C;
                OP_CHECK_ARG:
                  if (br_taken_w)
                    status_r <= uop_e_r.cnd[3] ? ST_DROP_C
                                               : ST_MALFORMED_C;
                OP_MAP_VALID:
                  if (br_taken_w) status_r <= ST_MALFORMED_C;
                OP_ITER_OPEN:  begin
                  iter_cnt_r <= opa_e_r[7:0]; iter_idx_r <= '0;
                end
                OP_ITER_NEXT:  iter_idx_r <= iter_idx_r + 8'd1;
                OP_SET_STATUS: status_r   <= uop_e_r.imm[4:0];
                OP_SET_LENGTH: resp_len_r <= uop_e_r.imm[10:0];
                OP_BUILD_FLD, OP_APPEND: begin
                  if (append_skip_w) ovf_r <= 1'b1;
                  else begin
                    cursor_r   <= cursor_r + {6'd0, fld_len_w};
                    resp_len_r <= resp_len_r + {7'd0, fld_len_w};
                  end
                end
                default: ;
              endcase

              // control flow
              if (end_op_w) begin
                ms_r    <= S_IDLE;
                vld_d_r <= 1'b0;
                vld_e_r <= 1'b0;
                done_o  <= 1'b1;
              end else if (br_taken_w) begin
                upc_r   <= br_tgt_w;
                vld_d_r <= 1'b0;
                vld_e_r <= 1'b0;
              end
            end
          end
        end
        default: ms_r <= S_IDLE;
      endcase
    end
  end

  assign disp_ready_o = (ms_r == S_IDLE);
  assign busy_o       = (ms_r != S_IDLE);
  assign dbg_upc_o    = upc_r;
  assign dbg_status_o = status_r;
  assign dbg_ovf_o    = ovf_r;

endmodule : KL_gptp_ucpu
`default_nettype wire
