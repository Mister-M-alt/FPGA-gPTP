/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : KL_gptp_engine.sv
//  Project     : 802.1AS gPTP protocol processor (time-sync plane)
//
//  Description : The time-sync plane, one clock domain, one byte in / one
//                byte out — the KL_pp_shadow integration shape. Contains:
//
//                  KL_gptp_rx_parser  802.1AS receive -> message bank
//                  KL_gptp_ucpu       micro-coded handlers (grown ISA)
//                  KL_gptp_tx_slot    PDU build slot + byte serializer
//                  KL_gptp_timer      ms deadline service, 8 slots
//
//                and the engine-owned state the µCPU reaches through its
//                one state port, region-selected by st_addr[19:16]:
//
//                  0  message bank      RO  (parser-written, PING-PONG
//                                            2 x 32 x 64: each accepted
//                                            frame lands in the bank its
//                                            event names, so a handler
//                                            delayed behind another never
//                                            reads a successor's frame)
//                  1  timestamp regs    RO  (0 ingress ts, 1 egress ts)
//                  2  scratch RAM       RW  (64 x 64, protocol state)
//                  3  publish bank      RW  (0 gm id, 1 parent id,
//                                            2 flags, 3 pdelay ns)
//                  4  PHC control       WO  (0 rate addend, 1 step)
//                  5  timer arm         WO  (slot = addr, delta ms = data)
//
//                gather: sel 0 = live PHC ns snapshot, sel 1 = ms now.
//
//                The publish bank IS the software contract this plane
//                retires (GM identity, asCapable/sync verdicts, peer
//                delay): what a daemon used to poll and mirror into CSRs
//                becomes wires, latched by OP_COMMIT.
//
//                Parser and timer events dispatch through a 4-deep queue;
//                parser wins a same-cycle push and the timer waits on its
//                ready. One egress timestamp pends on a priority side path.
//                A later Pdelay_Req stays queued while a response owns the
//                only requester context, but that owner's stamp bypasses it
//                and releases the claim before the later request dispatches.
//                Dispatch is gated on the serializer being idle so a handler
//                never builds into a slot still on the wire.
//                r14 carries the frame's ingress timestamp (or the
//                egress stamp for EV_TX_TS), r13 the PHC at dispatch.
//---------------------------------------------------------------------------//
`default_nettype none

module KL_gptp_engine
  import gptp_ucpu_pkg::*;
#(
    parameter string       UCODE_HEX_P = "gptp_ucode.hex",
    parameter int unsigned CLK_HZ_P    = 100_000_000
) (
    input  wire         clk_i,
    input  wire         rst_n,

    //! RX byte face: pre-classified 0x88F7 frames, DA first, FCS-checked
    input  wire         rx_valid_i,
    input  wire  [7:0]  rx_data_i,
    input  wire         rx_sof_i,
    input  wire         rx_eof_i,
    input  wire         rx_err_i,
    input  wire  [63:0] rx_ts_i,       //! ingress timestamp, stable at sof

    //! TX byte face
    output logic        tx_valid_o,
    output logic [7:0]  tx_data_o,
    output logic        tx_sof_o,
    output logic        tx_eof_o,
    input  wire         tx_ready_i,

    //! egress timestamp return, identified by the stamped PTP header
    input  wire         txts_valid_i,
    input  wire  [63:0] txts_ns_i,
    input  wire  [15:0] txts_seq_i,
    input  wire   [3:0] txts_type_i,

    //! PHC face (the parent timestamp_counter's knobs)
    input  wire  [63:0] phc_ns_i,
    output logic        phc_addend_we_o,
    output logic [31:0] phc_addend_o,
    output logic        phc_step_we_o,
    output logic [63:0] phc_step_o,

    //! publish bank as wires — the retired software contract
    output logic [63:0] pub_gm_id_o,
    output logic [63:0] pub_parent_id_o,
    output logic [31:0] pub_flags_o,   //! asCapable, sync ok, gm present…
    output logic [31:0] pub_pdelay_ns_o,
    output logic [31:0] pub_offset_o,  //! last sync offset, ns (signed)
    output logic [63:0] pub_annq_o,    //! last received announce vector, raw
    output logic        pub_commit_o,

    //! reserved effect strobes (base-ISA compat, unused by gPTP µcode)
    output logic        eff_nvm_stb_o,
    output logic  [7:0] eff_nvm_mark_o,
    output logic        eff_notify_stb_o,
    output logic  [3:0] eff_notify_class_o,

    //! diagnostics
    output logic [15:0] dbg_rx_drop_o,
    output logic [15:0] dbg_ev_drop_o,
    output logic        dbg_busy_o,
    output logic  [4:0] dbg_status_o
);

  // ---------------------------------------------------------- RX parser
  logic        bank_we_w;
  logic [4:0]  bank_addr_w;
  logic [63:0] bank_wdata_w;
  logic        pev_valid_w;
  logic [7:0]  pev_code_w;
  logic [15:0] pev_seq_w;

  KL_gptp_rx_parser u_parser (
      .clk_i        (clk_i),
      .rst_n        (rst_n),
      .rx_valid_i   (rx_valid_i),
      .rx_data_i    (rx_data_i),
      .rx_sof_i     (rx_sof_i),
      .rx_eof_i     (rx_eof_i),
      .rx_err_i     (rx_err_i),
      .bank_we_o    (bank_we_w),
      .bank_addr_o  (bank_addr_w),
      .bank_wdata_o (bank_wdata_w),
      .ev_valid_o   (pev_valid_w),
      .ev_code_o    (pev_code_w),
      .ev_seq_o     (pev_seq_w),
      .drop_cnt_o   (dbg_rx_drop_o)
  );

  // -------------------------------------------------- engine state RAMs
  //! the message bank ping-pongs: bank_sel_r flips as each accepted
  //! frame's event is pushed, so the frame a handler's event names
  //! survives ONE in-flight successor; a third frame within two
  //! handler latencies reuses the first bank (the announce handler's
  //! seq guard covers the worst consequence of that depth)
  (* ram_style = "distributed" *) logic [63:0] bank_r    [0:63];
  (* ram_style = "distributed" *) logic [63:0] scratch_r [0:63];
  logic bank_sel_r;

  //! Scratch survives a warm reset, but an egress claim cannot: the frame
  //! and timestamp pipelines reset, so a pre-reset return may never arrive.
  //! Keep resettable validity beside the two LUTRAM claim words. Reads see
  //! zero until post-reset µcode writes a new pending claim; the other
  //! protocol state (notably the Milan cease countdown) still survives.
  logic tmr_claim_valid_r, resp_claim_valid_r;

  //! LUTRAM has no reset; the bitstream's initial state is the reset.
  //! µcode's init-once flag (scratch S_INIT) DEPENDS on this being zero.
  initial begin : ram_poweron
    for (int i = 0; i < 64; i++) begin
      bank_r[i]    = '0;
      scratch_r[i] = '0;
    end
  end

  always_ff @(posedge clk_i) begin : bank_write
    if (!rst_n) begin
      bank_sel_r <= 1'b0;
    end else begin
      if (bank_we_w) bank_r[{bank_sel_r, bank_addr_w}] <= bank_wdata_w;
      if (pev_valid_w && !evq_full_w) bank_sel_r <= !bank_sel_r;
    end
  end

  //! the ingress timestamp ping-pongs WITH the message bank: a single
  //! register loses the race when the next frame's sof lands before the
  //! previous frame's event dispatches (a fabric FIFO delivers frames
  //! back-to-back; the parent integration found the resp's handler
  //! reading the chasing follow-up's arrival time). Two steps: the sof
  //! stamp STAGES, and the frame's own EOF commits it into the bank the
  //! frame occupies. The eof is strictly earlier than any successor's
  //! sof on a byte face, and strictly earlier than the event push (fin
  //! settles a cycle late), so the commit can never read a chaser's
  //! stamp and the event's bank bit names the committed slot.
  //! ...and the commit is qualified on frame length >= 3 bytes: a 1-2
  //! byte runt's eof can land inside the two-cycle window before the
  //! PREDECESSOR's bank flip (the parser drops runts without an event,
  //! so no flip follows) and would poison the predecessor's stamp. No
  //! event-carrying frame is ever that short, and a >= 3-byte frame's
  //! eof always postdates the flip window.
  logic [63:0] rxts_stage_r;
  logic [63:0] rxts_bank_r [0:1];
  logic [63:0] txts_r;
  logic [1:0]  rxts_len_r;
  always_ff @(posedge clk_i) begin : ts_latch
    if (!rst_n) begin
      rxts_stage_r   <= '0;
      rxts_bank_r[0] <= '0;
      rxts_bank_r[1] <= '0;
      txts_r         <= '0;
      rxts_len_r     <= 2'd0;
    end else begin
      if (rx_valid_i) begin
        if (rx_sof_i)                rxts_len_r <= 2'd1;
        else if (rxts_len_r != 2'd3) rxts_len_r <= rxts_len_r + 2'd1;
      end
      if (rx_valid_i && rx_sof_i) rxts_stage_r <= rx_ts_i;
      if (rx_valid_i && rx_eof_i && !rx_sof_i && (rxts_len_r >= 2'd2))
        rxts_bank_r[bank_sel_r] <= rxts_stage_r;
      if (txts_valid_i)           txts_r <= txts_ns_i;
    end
  end

  // ------------------------------------------------------------- timer
  logic        tmr_arm_we_w;
  logic [2:0]  tmr_arm_slot_w;
  logic [31:0] tmr_arm_delta_w;
  logic [31:0] ms_now_w;
  logic        tev_valid_w;
  logic [2:0]  tev_slot_w;
  logic        tev_ready_w;

  KL_gptp_timer #(
      .CLK_HZ_P (CLK_HZ_P),
      .SLOTS_P  (8)
  ) u_timer (
      .clk_i          (clk_i),
      .rst_n          (rst_n),
      .arm_we_i       (tmr_arm_we_w),
      .arm_slot_i     (tmr_arm_slot_w),
      .arm_delta_ms_i (tmr_arm_delta_w),
      .ms_now_o       (ms_now_w),
      .ev_valid_o     (tev_valid_w),
      .ev_slot_o      (tev_slot_w),
      .ev_ready_i     (tev_ready_w)
  );

  // ------------------------------------------------------- event queue
  //! 4 deep, {code, seq, aux}; parser wins a same-cycle queue push and the
  //! timer waits on its own ready. TX timestamps use the priority side
  //! channel below: a queued second Pdelay_Req must not sit ahead of the
  //! stamp that releases the first response's claim/context (#40).
  logic [39:0] evq_r [0:3];
  logic [1:0]  evq_wp_r, evq_rp_r;
  logic [2:0]  evq_lvl_r;
  logic [15:0] ev_drop_r;
  logic        txts_pend_r;
  logic [15:0] txts_pend_seq_r;
  logic  [3:0] txts_pend_type_r;

  logic evq_full_w, evq_empty_w;
  assign evq_full_w  = (evq_lvl_r == 3'd4);
  assign evq_empty_w = (evq_lvl_r == 3'd0);

  logic disp_ready_w;
  logic ser_idle_w;
  logic disp_valid_r;
  logic txts_pop_w;

  logic        push_w;
  logic [39:0] push_data_w;
  always_comb begin : push_arb
    push_w      = 1'b0;
    push_data_w = '0;
    tev_ready_w = 1'b0;
    if (pev_valid_w) begin
      push_w      = !evq_full_w;
      push_data_w = {pev_code_w, pev_seq_w, 15'd0, bank_sel_r};
    end else if (tev_valid_w) begin
      push_w      = !evq_full_w;
      push_data_w = {EV_TMR_C, 16'd0, 13'd0, tev_slot_w};
      tev_ready_w = !evq_full_w;
    end
  end

  logic pop_w;

  always_ff @(posedge clk_i) begin : evq
    if (!rst_n) begin
      evq_wp_r        <= '0;
      evq_rp_r        <= '0;
      evq_lvl_r       <= '0;
      ev_drop_r       <= '0;
      txts_pend_r     <= 1'b0;
      txts_pend_seq_r <= '0;
      txts_pend_type_r <= '0;
    end else begin
      if (push_w) begin
        evq_r[evq_wp_r] <= push_data_w;
        evq_wp_r        <= evq_wp_r + 2'd1;
      end
      if (pop_w) evq_rp_r <= evq_rp_r + 2'd1;
      evq_lvl_r <= evq_lvl_r + (push_w ? 3'd1 : 3'd0)
                             - (pop_w  ? 3'd1 : 3'd0);

      if (pev_valid_w && evq_full_w) ev_drop_r <= ev_drop_r + 16'd1;

      if (txts_valid_i) begin
        txts_pend_r     <= 1'b1;
        txts_pend_seq_r <= txts_seq_i;
        txts_pend_type_r <= txts_type_i;
      end else if (txts_pop_w) begin
        txts_pend_r <= 1'b0;
      end
    end
  end

  assign dbg_ev_drop_o = ev_drop_r;

  // --------------------------------------------------------- dispatch
  logic [39:0] ev_head_w;
  assign ev_head_w = evq_r[evq_rp_r];

  //! S_TXQ_RESP is scratch slot 41 in gen_gptp_ucode.py. While its pending
  //! bit stands, the bank/context belongs to the response already queued
  //! downstream. Hold a later Pdelay_Req at the event-queue head until the
  //! matching type-3 timestamp handler clears that claim. Timestamp returns
  //! bypass the held head through txts_pop_w, so this cannot deadlock.
  logic pdreq_block_w;
  assign pdreq_block_w = !evq_empty_w &&
                         (ev_head_w[39:32] == EV_RX_PDREQ_C) &&
                         resp_claim_valid_r;

  //! TX events repack the complete claim tag into aux[19:0]:
  //! {messageType, sequenceId}. The handler compares it in one masked read.
  logic [39:0] txts_ev_w;
  assign txts_ev_w = {EV_TX_TS_C, 12'd0, txts_pend_type_r,
                      txts_pend_seq_r};

  //! µPC entry table — matches hdl/ucode/gen_gptp_ucode.py
  logic [UPC_W_C-1:0] entry_w;
  always_comb begin : entry_table
    unique case (ev_head_w[39:32])
      EV_RX_SYNC_C:     entry_w = UPC_W_C'(16);
      EV_RX_FOLLOWUP_C: entry_w = UPC_W_C'(64);
      EV_RX_ANNOUNCE_C: entry_w = UPC_W_C'(128);
      EV_RX_PDREQ_C:    entry_w = UPC_W_C'(192);
      EV_RX_PDRESP_C:   entry_w = UPC_W_C'(256);
      EV_RX_PDRFU_C:    entry_w = UPC_W_C'(320);
      EV_RX_SIGNAL_C:   entry_w = UPC_W_C'(384);
      EV_TX_TS_C:       entry_w = UPC_W_C'(448);
      //! EV_TMR_C, and structurally every code no arm above claims.
      //! The three push sources are the parser's ev_code_o, the literal
      //! EV_TX_TS_C and the literal EV_TMR_C, and since the parser
      //! refuses an unlisted messageType at its type byte its ev_map's
      //! own default can no longer be latched (FPGA-gPTP #22), so
      //! EV_TMR_C is the only code that reaches this arm. Left as a
      //! catch-all rather than narrowed: a no-op default would need a
      //! ROM entry of its own, and the hazard is closed at the source
      default:          entry_w = UPC_W_C'(512);
    endcase
  end

  //! one pop per accepted dispatch: the µCPU acknowledges by leaving
  //! IDLE (disp_ready falls) one cycle after valid — popping again while
  //! valid is still up would clobber the preload operands mid-handshake
  //! and silently eat the second event (the bug the 44-check engine
  //! suite caught: become-master ran with a TX-timestamp event's
  //! operands and the timestamp event vanished)
  assign txts_pop_w = txts_pend_r && disp_ready_w && ser_idle_w &&
                      !disp_valid_r;
  assign pop_w = !txts_pend_r && !evq_empty_w && !pdreq_block_w &&
                 disp_ready_w && ser_idle_w && !disp_valid_r;

  logic [UPC_W_C-1:0] disp_upc_r;
  logic [63:0] disp_ev_r, disp_ts0_r, disp_ts1_r;
  logic        disp_bank_r;

  always_ff @(posedge clk_i) begin : dispatch
    if (!rst_n) begin
      disp_valid_r <= 1'b0;
      disp_upc_r   <= '0;
      disp_ev_r    <= '0;
      disp_ts0_r   <= '0;
      disp_ts1_r   <= '0;
      disp_bank_r  <= 1'b0;
    end else begin
      if (txts_pop_w || pop_w) disp_valid_r <= 1'b1;
      else if (!disp_ready_w)  disp_valid_r <= 1'b0;   // accepted
      if (txts_pop_w) begin
        disp_upc_r  <= UPC_W_C'(448);
        disp_bank_r <= 1'b0;
        disp_ev_r   <= {24'd0, txts_ev_w};
        disp_ts0_r  <= txts_r;
        disp_ts1_r  <= phc_ns_i;
      end else if (pop_w) begin
        disp_upc_r  <= entry_w;
        disp_bank_r <= ev_head_w[0];
        disp_ev_r  <= {24'd0, ev_head_w};
        disp_ts0_r <= (ev_head_w[39:32] == EV_TX_TS_C) ? txts_r
                    : (ev_head_w[39:32] == EV_TMR_C)
                        ? {32'd0, ms_now_w}
                        : rxts_bank_r[ev_head_w[0]];
        disp_ts1_r <= phc_ns_i;
      end
    end
  end

  // ------------------------------------------------------------- µCPU
  logic        st_req_w, st_we_w, st_name_w;
  logic [19:0] st_addr_w;
  logic [63:0] st_wdata_w;
  logic  [7:0] st_wstrb_w;
  logic        st_rvalid_r;
  logic [63:0] st_rdata_r;
  logic        gx_req_w;
  logic  [7:0] gx_sel_w;
  logic        gx_valid_r;
  logic [63:0] gx_data_r;
  logic        rb_we_w;
  logic  [9:0] rb_addr_w;
  logic [31:0] rb_wdata_w;
  logic  [3:0] rb_wstrb_w;
  logic        rb_ready_w;
  logic        resp_send_w;
  logic [10:0] resp_len_w;
  logic  [4:0] resp_status_w;
  logic        ucpu_tx_ready_w;
  logic        ucpu_done_w;
  logic [UPC_W_C-1:0] ucpu_dbg_upc_w;
  logic        ucpu_dbg_ovf_w;

  KL_gptp_ucpu #(
      .UCODE_HEX_P (UCODE_HEX_P)
  ) u_ucpu (
      .clk_i              (clk_i),
      .rst_n              (rst_n),
      .disp_valid_i       (disp_valid_r),
      .disp_ready_o       (disp_ready_w),
      .disp_upc_i         (disp_upc_r),
      .disp_ev_i          (disp_ev_r),
      .disp_ts0_i         (disp_ts0_r),
      .disp_ts1_i         (disp_ts1_r),
      .st_req_o           (st_req_w),
      .st_we_o            (st_we_w),
      .st_name_o          (st_name_w),
      .st_addr_o          (st_addr_w),
      .st_wdata_o         (st_wdata_w),
      .st_wstrb_o         (st_wstrb_w),
      .st_ready_i         (1'b1),
      .st_rvalid_i        (st_rvalid_r),
      .st_rdata_i         (st_rdata_r),
      .st_err_i           (1'b0),
      .gx_req_o           (gx_req_w),
      .gx_sel_o           (gx_sel_w),
      .gx_valid_i         (gx_valid_r),
      .gx_data_i          (gx_data_r),
      .lock_held_i        (1'b0),
      .lock_ctlr_i        (64'd0),
      .rb_we_o            (rb_we_w),
      .rb_addr_o          (rb_addr_w),
      .rb_wdata_o         (rb_wdata_w),
      .rb_wstrb_o         (rb_wstrb_w),
      .rb_ready_i         (rb_ready_w),
      .resp_send_o        (resp_send_w),
      .resp_len_o         (resp_len_w),
      .resp_status_o      (resp_status_w),
      .tx_ready_i         (ucpu_tx_ready_w),
      .eff_commit_o       (pub_commit_o),
      .eff_nvm_mark_o     (eff_nvm_mark_o),
      .eff_nvm_stb_o      (eff_nvm_stb_o),
      .eff_notify_class_o (eff_notify_class_o),
      .eff_notify_stb_o   (eff_notify_stb_o),
      .busy_o             (dbg_busy_o),
      .done_o             (ucpu_done_w),
      .dbg_upc_o          (ucpu_dbg_upc_w),
      .dbg_status_o       (dbg_status_o),
      .dbg_ovf_o          (ucpu_dbg_ovf_w)
  );

  // -------------------------------------------- state port region map
  logic [63:0] pub_gm_r, pub_parent_r, pub_annq_r;
  logic [31:0] pub_flags_r, pub_pdelay_r, pub_offset_r;

  logic [63:0] st_rd_mux_w;
  always_comb begin : st_read_mux
    unique case (st_addr_w[19:16])
      4'd0: st_rd_mux_w = bank_r[{disp_bank_r, st_addr_w[4:0]}];
      4'd1: st_rd_mux_w = st_addr_w[0] ? txts_r
                                       : rxts_bank_r[disp_bank_r];
      4'd2: begin
        if ((st_addr_w[5:0] == 6'd18) && !tmr_claim_valid_r)
          st_rd_mux_w = 64'd0;
        else if ((st_addr_w[5:0] == 6'd41) && !resp_claim_valid_r)
          st_rd_mux_w = 64'd0;
        else
          st_rd_mux_w = scratch_r[st_addr_w[5:0]];
      end
      4'd3: begin
        unique case (st_addr_w[2:0])
          3'd0: st_rd_mux_w = pub_gm_r;
          3'd1: st_rd_mux_w = pub_parent_r;
          3'd2: st_rd_mux_w = {32'd0, pub_flags_r};
          3'd3: st_rd_mux_w = {32'd0, pub_pdelay_r};
          3'd4: st_rd_mux_w = {32'd0, pub_offset_r};
          3'd5: st_rd_mux_w = pub_annq_r;
          default: st_rd_mux_w = 64'd0;
        endcase
      end
      default: st_rd_mux_w = 64'd0;
    endcase
  end

  //! Timer bootstrap: nothing arms a timer before µcode runs, and no µcode
  //! runs before an event. Arm the Pdelay cadence and Announce receipt watch
  //! once after every reset. Cold init re-arms slot 2 when slot 0 first runs;
  //! on a warm reset S_INIT skips that leg, so the hardware arm is what lets
  //! an asCapable port regain mastership and its Sync cadence.
  logic       boot_done_r;
  logic [7:0] boot_cnt_r;

  always_ff @(posedge clk_i) begin : st_port
    if (!rst_n) begin
      st_rvalid_r     <= 1'b0;
      st_rdata_r      <= '0;
      gx_valid_r      <= 1'b0;
      gx_data_r       <= '0;
      pub_gm_r        <= '0;
      pub_parent_r    <= '0;
      pub_flags_r     <= '0;
      pub_pdelay_r    <= '0;
      pub_offset_r    <= '0;
      pub_annq_r      <= '0;
      boot_done_r     <= 1'b0;
      boot_cnt_r      <= '0;
      phc_addend_we_o <= 1'b0;
      phc_addend_o    <= '0;
      phc_step_we_o   <= 1'b0;
      phc_step_o      <= '0;
      tmr_arm_we_w    <= 1'b0;
      tmr_arm_slot_w  <= '0;
      tmr_arm_delta_w <= '0;
      tmr_claim_valid_r  <= 1'b0;
      resp_claim_valid_r <= 1'b0;
    end else begin
      phc_addend_we_o <= 1'b0;
      phc_step_we_o   <= 1'b0;
      tmr_arm_we_w    <= 1'b0;

      if (!boot_done_r) begin
        boot_cnt_r <= boot_cnt_r + 8'd1;
        if (boot_cnt_r == 8'd254) begin
          tmr_arm_we_w    <= 1'b1;
          tmr_arm_slot_w  <= 3'd2;
          tmr_arm_delta_w <= 32'd3000;
        end
        if (boot_cnt_r == 8'd255) begin
          boot_done_r     <= 1'b1;
          tmr_arm_we_w    <= 1'b1;
          tmr_arm_slot_w  <= 3'd0;
          tmr_arm_delta_w <= 32'd1200;
        end
      end

      // one-shot read completion
      st_rvalid_r <= st_req_w && !st_we_w && !st_rvalid_r;
      if (st_req_w && !st_we_w) st_rdata_r <= st_rd_mux_w;

      // writes: single-cycle, full-width (µcode contract; the byte
      // strobes exist for the base ISA's sake and are not honoured here)
      if (st_req_w && st_we_w) begin
        unique case (st_addr_w[19:16])
          4'd2: begin
            scratch_r[st_addr_w[5:0]] <= st_wdata_w;
            // Slots mirror S_TXQ_TMR=18 and S_TXQ_RESP=41 in the generator.
            // Bit 20 is TXP_PEND_C, so a handler's zero write consumes the
            // resettable validity together with the LUTRAM claim.
            if (st_addr_w[5:0] == 6'd18)
              tmr_claim_valid_r <= st_wdata_w[20];
            if (st_addr_w[5:0] == 6'd41)
              resp_claim_valid_r <= st_wdata_w[20];
          end
          4'd3: begin
            unique case (st_addr_w[2:0])
              3'd0: pub_gm_r     <= st_wdata_w;
              3'd1: pub_parent_r <= st_wdata_w;
              3'd2: pub_flags_r  <= st_wdata_w[31:0];
              3'd3: pub_pdelay_r <= st_wdata_w[31:0];
              3'd4: pub_offset_r <= st_wdata_w[31:0];
              3'd5: pub_annq_r   <= st_wdata_w;
              default: ;
            endcase
          end
          4'd4: begin
            if (st_addr_w[0]) begin
              phc_step_we_o <= 1'b1;
              phc_step_o    <= st_wdata_w;
            end else begin
              phc_addend_we_o <= 1'b1;
              phc_addend_o    <= st_wdata_w[31:0];
            end
          end
          4'd5: begin
            tmr_arm_we_w    <= 1'b1;
            tmr_arm_slot_w  <= st_addr_w[2:0];
            tmr_arm_delta_w <= st_wdata_w[31:0];
          end
          default: ;
        endcase
      end

      // gather: atomic snapshots
      gx_valid_r <= gx_req_w && !gx_valid_r;
      if (gx_req_w) begin
        gx_data_r <= (gx_sel_w[3:0] == 4'd1) ? {32'd0, ms_now_w}
                                             : phc_ns_i;
      end
    end
  end

  assign pub_gm_id_o     = pub_gm_r;
  assign pub_parent_id_o = pub_parent_r;
  assign pub_flags_o     = pub_flags_r;
  assign pub_pdelay_ns_o = pub_pdelay_r;
  assign pub_offset_o    = pub_offset_r;
  assign pub_annq_o      = pub_annq_r;

  // ------------------------------------------------------------ TX slot
  KL_gptp_tx_slot u_txslot (
      .clk_i      (clk_i),
      .rst_n      (rst_n),
      .rb_we_i    (rb_we_w),
      .rb_addr_i  (rb_addr_w),
      .rb_wdata_i (rb_wdata_w),
      .rb_wstrb_i (rb_wstrb_w),
      .rb_ready_o (rb_ready_w),
      .send_i     (resp_send_w),
      .send_len_i (resp_len_w),
      .ser_idle_o (ser_idle_w),
      .tx_valid_o (tx_valid_o),
      .tx_data_o  (tx_data_o),
      .tx_sof_o   (tx_sof_o),
      .tx_eof_o   (tx_eof_o),
      .tx_ready_i (tx_ready_i)
  );

  assign ucpu_tx_ready_w = ser_idle_w && rb_ready_w;

  //! resp_status is engine-local bookkeeping; nothing on the wire face
  //! consumes it (a gPTP PDU carries no status field)
  logic [4:0] unused_status_w;
  assign unused_status_w = resp_status_w;
  logic unused_name_w;
  assign unused_name_w = st_name_w;
  logic [2:0] unused_strb_w;
  assign unused_strb_w = st_wstrb_w[2:0];
  logic unused_dbg_w;
  assign unused_dbg_w = ucpu_done_w ^ (^ucpu_dbg_upc_w) ^ ucpu_dbg_ovf_w;

endmodule : KL_gptp_engine
`default_nettype wire
