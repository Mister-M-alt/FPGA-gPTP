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
//                                            2 flags, 3 pdelay ns,
//                                            6 path count, 8..14 path tail)
//                  4  PHC control       WO  (0 rate addend, 1 step)
//                  5  timer arm         WO  (slot = addr, delta ms = data)
//
//                gather: free-running millisecond time.
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
//                egress stamp for EV_TX_TS).
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
    //! Raw selected PathTrace publication. A present sequence reports its
    //! complete received length including the separately published GM at slot
    //! zero; an absent TLV reports count zero. pub_path_o carries slots 1..7,
    //! and every inactive tail slot is zero.
    output logic  [3:0] pub_path_count_o,
    output logic [7*64-1:0] pub_path_o,
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
  //! The generated image writes its clockIdentity once during cold init and
  //! scratch retains it across warm reset. Mirror that write in a dedicated
  //! register so the streaming parser can compare every PathTrace identity,
  //! including identities beyond the eight retained public slots, without
  //! adding a second read port (and a LUTRAM replica) to scratch_r.
  //! FPGA configuration establishes the cold-invalid state. These mirrors
  //! deliberately have no warm-reset assignment: scratch is warm-retentive,
  //! so the write-snooped identity must be as well. Avoiding a reset-time
  //! scratch read preserves scratch_r's single-read-port LUTRAM inference.
  /* verilator lint_off PROCASSINIT */
  logic [63:0] local_clock_id_r = 64'd0;
  logic        local_clock_valid_r = 1'b0;
  /* verilator lint_on PROCASSINIT */

  KL_gptp_rx_parser u_parser (
      .clk_i        (clk_i),
      .rst_n        (rst_n),
      .rx_valid_i   (rx_valid_i),
      .rx_data_i    (rx_data_i),
      .rx_sof_i     (rx_sof_i),
      .rx_eof_i     (rx_eof_i),
      .rx_err_i     (rx_err_i),
      .local_clock_id_i (local_clock_id_r),
      .local_clock_valid_i (local_clock_valid_r),
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
  //! survives ONE in-flight successor. A third frame within two handler
  //! latencies reuses the first bank. Announce has the frozen single-owner
  //! context below; accepted Pdelay_Req events snapshot every handler input
  //! into the event-queue slot below, because a
  //! live response claim can deliberately hold one behind arbitrary
  //! accepted traffic.
  (* ram_style = "distributed" *) logic [63:0] bank_r    [0:63];
  (* ram_style = "distributed" *) logic [63:0] scratch_r [0:63];
  logic bank_sel_r;

  //! Hold the just-parsed source identity and port without adding read ports
  //! to bank_r. An event pushes two cycles after its frame's EOF, whereas a
  //! zero-gap successor cannot reach these header fields in fewer than 42
  //! byte clocks, so they still belong to the event being enqueued.
  logic [63:0] frame_cid_r;
  logic [15:0] frame_pn_r;

  //! One complete frozen Announce context, written by the parser's existing
  //! single bank-write stream and read serially by the µCPU. Keeping the
  //! original 5-bit bank addresses makes this one compact 32x64 LUTRAM rather
  //! than a wide register snapshot or a multi-read replica of bank_r.
  (* ram_style = "distributed" *) logic [63:0] ann_ctx_r [0:31];
  //! Publication needs the selected path in one state-port transaction. Keep
  //! only that payload beside the serial-read context: the count plus w17..w23
  //! (w16 is the separately published GM). Inactive words may remain stale
  //! here; address 7 count-gates and zeroes them in the raw publish bank. No
  //! reset/initial value is required: a qualified frame always writes w12 and
  //! every tail word its count makes active before its handler can read them.
  logic [7:0] ann_pub_count_r;
  logic [7*64-1:0] ann_pub_tail_r;
  logic ann_ctx_busy_r, ann_frame_capture_r, ann_event_capture_r;
  logic [2:0] ann_fin_wait_r;
  logic ann_reject_w, ann_deferred_capture_w, evq_full_w, push_w;
  logic disp_announce_r;
  logic ucpu_done_w;

  //! w12 and the parser event are deliberately deferred together until all
  //! final identity writes have settled. Bind that word to the accepted EOF
  //! qualification, not to ann_frame_capture_r: a legal successor SOF may
  //! already have changed the latter by the time this write reaches us.
  assign ann_deferred_capture_w = bank_we_w && (bank_addr_w == 5'd12) &&
                                  pev_valid_w &&
                                  (pev_code_w == EV_RX_ANNOUNCE_C) &&
                                  ann_event_capture_r;

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
      if (i < 32) ann_ctx_r[i] = '0;
    end
  end

  always_ff @(posedge clk_i) begin : bank_write
    if (!rst_n) begin
      bank_sel_r  <= 1'b0;
      frame_cid_r <= '0;
      frame_pn_r  <= '0;
      ann_frame_capture_r <= 1'b0;
      ann_event_capture_r <= 1'b0;
      ann_ctx_busy_r      <= 1'b0;
      ann_fin_wait_r      <= '0;
    end else begin
      //! A frame that starts while the one Announce context is owned stays
      //! rejected even if the prior handler finishes in its middle; accepting
      //! a suffix would create exactly the mixed epoch this context prevents.
      if (rx_valid_i && rx_sof_i)
        ann_frame_capture_r <= !ann_ctx_busy_r;
      //! Preserve the completed frame's qualification across a zero-gap
      //! successor SOF. The parser presents its event two clocks after EOF.
      if (rx_valid_i && rx_eof_i) begin
        ann_event_capture_r <= ann_frame_capture_r;
        if (ann_ctx_busy_r && ann_frame_capture_r)
          ann_fin_wait_r <= 3'd3;
      end else if (ann_fin_wait_r != 3'd0) begin
        ann_fin_wait_r <= ann_fin_wait_r - 3'd1;
        //! A frame may be poisoned after its Announce-specific words were
        //! staged. If no accepted parser event follows its EOF, release the
        //! early reservation; the zero-gap successor remains conservatively
        //! refused because its per-frame qualification was already false.
        if (ann_fin_wait_r == 3'd1) ann_ctx_busy_r <= 1'b0;
      end
      if (bank_we_w) begin
        bank_r[{bank_sel_r, bank_addr_w}] <= bank_wdata_w;
        if (bank_addr_w == 5'd2) frame_cid_r <= bank_wdata_w;
        if (bank_addr_w == 5'd3) frame_pn_r  <= bank_wdata_w[15:0];
        if (ann_frame_capture_r || ann_deferred_capture_w) begin
          ann_ctx_r[bank_addr_w] <= bank_wdata_w;
          if (bank_addr_w == 5'd12)
            ann_pub_count_r <= bank_wdata_w[7:0];
          if ((bank_addr_w >= 5'd17) && (bank_addr_w <= 5'd23))
            ann_pub_tail_r[64*(bank_addr_w-5'd17) +: 64] <= bank_wdata_w;
          //! Reserve at the first Announce-only bank word, well before EOF,
          //! so a zero-gap successor cannot overwrite source/path staging in
          //! the two cycles before the deferred event appears.
          if (bank_addr_w == 5'd8) ann_ctx_busy_r <= 1'b1;
        end
      end
      if (pev_valid_w && (pev_code_w == EV_RX_ANNOUNCE_C)) begin
        //! Only the frame that acquired this context may release a failed
        //! enqueue. A deliberately rejected chaser has event_capture=false
        //! and must not unlock or overwrite the still-queued owner.
        if (ann_event_capture_r) begin
          ann_fin_wait_r <= '0;
          if (!push_w) ann_ctx_busy_r <= 1'b0;
        end
      end
      if (ucpu_done_w && disp_announce_r) ann_ctx_busy_r <= 1'b0;
      if (pev_valid_w && !evq_full_w && !ann_reject_w)
        bank_sel_r <= !bank_sel_r;
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
  //! The last qualified EOF remains current through the event push: the
  //! shortest successor that can replace it takes three byte clocks, while
  //! the predecessor's event enters the queue after two.
  logic [63:0] rxts_stage_r;
  logic [63:0] rxts_commit_r;
  logic [63:0] rxts_bank_r [0:1];
  logic [63:0] txts_r;
  logic [1:0]  rxts_len_r;
  always_ff @(posedge clk_i) begin : ts_latch
    if (!rst_n) begin
      rxts_stage_r   <= '0;
      rxts_commit_r  <= '0;
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
      if (rx_valid_i && rx_eof_i && !rx_sof_i && (rxts_len_r >= 2'd2)) begin
        rxts_bank_r[bank_sel_r] <= rxts_stage_r;
        rxts_commit_r           <= rxts_stage_r;
      end
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
  //! A queued Pdelay_Req can wait longer than the two-bank lifetime while
  //! an earlier response owns S_TXQ_RESP. Preserve the request's complete
  //! handler input beside its event until dispatch. This array shares the
  //! event queue's write/read pointers; non-Pdelay slots are don't-care.
  (* ram_style = "distributed" *) logic [143:0] evq_pd_ctx_r [0:3];
  //! Announce qualification, BMCA and public PathTrace consume the frozen
  //! write-stream context above. At most one Announce may own it: later
  //! Announces are explicitly dropped and counted until the accepted handler
  //! completes, while unrelated events continue to use this queue. Milan's
  //! one-Hz Announce cadence makes overload exceptional; an explicit drop is
  //! safe, bounded and observable, unlike parser-bank ABA or a mixed epoch.
  logic [1:0]  evq_wp_r, evq_rp_r;
  logic [2:0]  evq_lvl_r;
  logic [15:0] ev_drop_r;
  logic        txts_pend_r;
  logic [15:0] txts_pend_seq_r;
  logic  [3:0] txts_pend_type_r;

  logic evq_empty_w;
  assign evq_full_w  = (evq_lvl_r == 3'd4);
  assign evq_empty_w = (evq_lvl_r == 3'd0);

  logic disp_ready_w;
  logic ser_idle_w;
  logic disp_valid_r;
  logic txts_pop_w;

  logic [39:0] push_data_w;
  always_comb begin : push_arb
    push_w      = 1'b0;
    push_data_w = '0;
    tev_ready_w = 1'b0;
    ann_reject_w = pev_valid_w &&
                   (pev_code_w == EV_RX_ANNOUNCE_C) &&
                   !ann_event_capture_r;
    if (pev_valid_w) begin
      push_w      = !evq_full_w && !ann_reject_w;
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
        if (pev_valid_w && (pev_code_w == EV_RX_PDREQ_C)) begin
          evq_pd_ctx_r[evq_wp_r] <= {frame_cid_r, frame_pn_r,
                                      rxts_commit_r};
        end
        evq_wp_r        <= evq_wp_r + 2'd1;
      end
      if (pop_w) evq_rp_r <= evq_rp_r + 2'd1;
      evq_lvl_r <= evq_lvl_r + (push_w ? 3'd1 : 3'd0)
                             - (pop_w  ? 3'd1 : 3'd0);

      if (pev_valid_w && (evq_full_w || ann_reject_w))
        ev_drop_r <= ev_drop_r + 16'd1;


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
  logic [63:0] disp_ev_r, disp_ts0_r;
  logic        disp_bank_r;
  logic        disp_pdreq_r;
  logic [63:0] disp_pd_cid_r;
  logic [15:0] disp_pd_pn_r;

  always_ff @(posedge clk_i) begin : dispatch
    if (!rst_n) begin
      disp_valid_r <= 1'b0;
      disp_upc_r   <= '0;
      disp_ev_r    <= '0;
      disp_ts0_r   <= '0;
      disp_bank_r  <= 1'b0;
      disp_pdreq_r <= 1'b0;
      disp_announce_r <= 1'b0;
      disp_pd_cid_r <= '0;
      disp_pd_pn_r <= '0;
    end else begin
      if (txts_pop_w || pop_w) disp_valid_r <= 1'b1;
      else if (!disp_ready_w)  disp_valid_r <= 1'b0;   // accepted
      if (txts_pop_w) begin
        disp_upc_r  <= UPC_W_C'(448);
        disp_bank_r <= 1'b0;
        disp_pdreq_r <= 1'b0;
        disp_announce_r <= 1'b0;
        disp_ev_r   <= {24'd0, txts_ev_w};
        disp_ts0_r  <= txts_r;
      end else if (pop_w) begin
        disp_upc_r   <= entry_w;
        disp_bank_r  <= ev_head_w[0];
        disp_pdreq_r <= (ev_head_w[39:32] == EV_RX_PDREQ_C);
        disp_announce_r <= (ev_head_w[39:32] == EV_RX_ANNOUNCE_C);
        disp_pd_cid_r <= evq_pd_ctx_r[evq_rp_r][143:80];
        disp_pd_pn_r  <= evq_pd_ctx_r[evq_rp_r][79:64];
        disp_ev_r    <= {24'd0, ev_head_w};
        disp_ts0_r   <= (ev_head_w[39:32] == EV_TX_TS_C) ? txts_r
                      : (ev_head_w[39:32] == EV_TMR_C)
                          ? {32'd0, ms_now_w}
                          : (ev_head_w[39:32] == EV_RX_PDREQ_C)
                              ? evq_pd_ctx_r[evq_rp_r][63:0]
                              : rxts_bank_r[ev_head_w[0]];
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
  logic  [3:0] pub_path_count_r;
  logic [7*64-1:0] pub_path_r;
  //! Path state is staged directly into the raw publish bank on BTCA `take`.
  //! The wrapper samples that bank only on COMMIT, just as it already does for
  //! GM/parent. If the local vector wins, BECOME overwrites it with `[self]`
  //! before the handler's sole COMMIT; a worse Announce never executes `take`
  //! and therefore cannot disturb the selected record. Preserve this raw path
  //! across warm reset with the scratch best vector; outward wires are gated
  //! to canonical zero while the reset-cleared GM is zero.
  // The initial writer is configuration state, not a second runtime driver.
  /* verilator lint_off MULTIDRIVEN */
  initial begin : pub_path_poweron
    pub_path_count_r = '0;
    pub_path_r       = '0;
  end
  //! The raw public ABI is bounded to eight complete entries. Count zero is
  //! the honest publication for a selected fixed Announce without PathTrace;
  //! its GM remains separately published and every tail word is zero. Counts
  //! above the retained bank cap publish the first eight received entries.
  wire [3:0] ann_pub_count_clamped_w = (ann_pub_count_r > 8'd8)
      ? 4'd8 : ann_pub_count_r[3:0];

  logic [63:0] st_rd_mux_w;
  always_comb begin : st_read_mux
    unique case (st_addr_w[19:16])
      4'd0: begin
        if (disp_pdreq_r) begin
          unique case (st_addr_w[4:0])
            5'd0: st_rd_mux_w = {8'd0, 4'd0, 4'h2,
                                  disp_ev_r[31:16], 32'd0};
            5'd2: st_rd_mux_w = disp_pd_cid_r;
            5'd3: st_rd_mux_w = {48'd0, disp_pd_pn_r};
            default: st_rd_mux_w = bank_r[{disp_bank_r, st_addr_w[4:0]}];
          endcase
        end else if (disp_announce_r) begin
          //! Complete frozen Announce epoch at the same addresses as bank_r;
          //! fixed-vector and BMCA reads therefore cannot mix parser epochs.
          st_rd_mux_w = ann_ctx_r[st_addr_w[4:0]];
        end else begin
          st_rd_mux_w = bank_r[{disp_bank_r, st_addr_w[4:0]}];
        end
      end
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
        unique case (st_addr_w[3:0])
          4'd0: st_rd_mux_w = pub_gm_r;
          4'd1: st_rd_mux_w = pub_parent_r;
          4'd2: st_rd_mux_w = {32'd0, pub_flags_r};
          4'd3: st_rd_mux_w = {32'd0, pub_pdelay_r};
          4'd4: st_rd_mux_w = {32'd0, pub_offset_r};
          4'd5: st_rd_mux_w = pub_annq_r;
          4'd6: st_rd_mux_w = {60'd0, pub_path_count_r};
          4'd8, 4'd9, 4'd10, 4'd11, 4'd12, 4'd13, 4'd14:
            st_rd_mux_w = pub_path_r[64*(st_addr_w[3:0]-4'd8) +: 64];
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
`ifndef SYNTHESIS
  //! Address 7 may change raw path state before publication, but the BTCA
  //! contest must always resolve through address 6 before any COMMIT. This
  //! assertion makes a µcode mutation that exposes the transient fatal.
  logic path_stage_pending_r;
`endif

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
`ifndef SYNTHESIS
      path_stage_pending_r <= 1'b0;
`endif
    end else begin
      phc_addend_we_o <= 1'b0;
      phc_step_we_o   <= 1'b0;
      tmr_arm_we_w    <= 1'b0;
`ifndef SYNTHESIS
      if (local_clock_valid_r &&
          (local_clock_id_r != scratch_r[6'd25]))
        $error("PathTrace local clock mirror differs from ucode S_CID");
      if (pub_commit_o && path_stage_pending_r)
        $error("PathTrace COMMIT before BTCA path contest resolved");
      if (pub_commit_o && (pub_path_count_r == 4'd0) &&
          (pub_path_r != '0))
        $error("Raw empty PathTrace committed with a nonzero tail");
`endif

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
            // Slot 25 mirrors generator S_CID.
            if (st_addr_w[5:0] == 6'd25)
              begin
                local_clock_id_r    <= st_wdata_w;
                local_clock_valid_r <= 1'b1;
              end
            // Slots mirror S_TXQ_TMR=18 and S_TXQ_RESP=41 in the generator.
            // Bit 20 is TXP_PEND_C, so a handler's zero write consumes the
            // resettable validity together with the LUTRAM claim.
            if (st_addr_w[5:0] == 6'd18)
              tmr_claim_valid_r <= st_wdata_w[20];
            if (st_addr_w[5:0] == 6'd41)
              resp_claim_valid_r <= st_wdata_w[20];
          end
          4'd3: begin
            unique case (st_addr_w[3:0])
              4'd0: pub_gm_r     <= st_wdata_w;
              4'd1: pub_parent_r <= st_wdata_w;
              4'd2: pub_flags_r  <= st_wdata_w[31:0];
              4'd3: pub_pdelay_r <= st_wdata_w[31:0];
              4'd4: pub_offset_r <= st_wdata_w[31:0];
              4'd5: pub_annq_r   <= st_wdata_w;
              //! Address 6 selects the already-staged best path (zero, hence
              //! no write) or overwrites it with the self-master one-entry
              //! path (nonzero). The handler has no COMMIT between address 7
              //! and this own-vs-best contest, so raw transients are private.
              4'd6: begin
`ifndef SYNTHESIS
                path_stage_pending_r <= 1'b0;
`endif
                if (st_wdata_w[3:0] != 4'd0) begin
                  pub_path_count_r <= 4'd1;
                  pub_path_r       <= '0;
                end
              end
              //! Address 7 stages the current frozen Announce payload only
              //! after BTCA `take`. Copy all active tails and clear every
              //! inactive word on this one edge, so a following COMMIT cannot
              //! expose parser-stale data from a prior longer PathTrace.
              4'd7: begin
`ifndef SYNTHESIS
                path_stage_pending_r <= 1'b1;
`endif
                pub_path_count_r <= ann_pub_count_clamped_w;
                for (int unsigned pk = 0; pk < 7; pk++) begin
                  if (4'(pk + 2) <= ann_pub_count_clamped_w)
                    pub_path_r[64*pk +: 64] <=
                        ann_pub_tail_r[64*pk +: 64];
                  else
                    pub_path_r[64*pk +: 64] <= 64'd0;
                end
              end
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

      // gather: atomic millisecond snapshot
      gx_valid_r <= gx_req_w && !gx_valid_r;
      if (gx_req_w) begin
        gx_data_r <= {32'd0, ms_now_w};
      end
    end
  end
  /* verilator lint_on MULTIDRIVEN */

  assign pub_gm_id_o     = pub_gm_r;
  assign pub_parent_id_o = pub_parent_r;
  assign pub_flags_o     = pub_flags_r;
  assign pub_pdelay_ns_o = pub_pdelay_r;
  assign pub_offset_o    = pub_offset_r;
  assign pub_annq_o      = pub_annq_r;
  assign pub_path_count_o = (pub_gm_r == 64'd0) ? 4'd0
                                                 : pub_path_count_r;
  assign pub_path_o       = (pub_gm_r == 64'd0) ? '0 : pub_path_r;

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
