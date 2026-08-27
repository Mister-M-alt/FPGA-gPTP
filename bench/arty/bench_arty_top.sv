/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : bench_arty_top.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL)
//
//  Description : First-light top for the Digilent Arty A7-100T against a
//                gPTP-enabled peer (STM32) on the 100BASE-TX MII PHY
//                (DP83848). No SoC, no software: MII gaskets + PHC +
//                KL_gptp_engine + a 1 Hz UART truth line.
//
//                Clocks: sys = the board's 100 MHz oscillator (engine,
//                PHC, UART); eth_rx_clk / eth_tx_clk = the PHY's two
//                25 MHz MII clocks (gaskets), crossed with gray FIFOs.
//                The FPGA supplies the PHY's 25 MHz reference on
//                eth_ref_clk (divide-by-4 of sys, same XO ppm).
//
//                Timestamp points: PHC latched in sys on the synchronized
//                RX-SFD and TX-SFD toggles; the TX done toggle returns
//                the egress stamp and its header tag to the engine. The
//                MII serializer has one wire frame outstanding; a later
//                FIFO-queued frame cannot replace the held tag before the
//                current frame's done handshake crosses back to sys.
//---------------------------------------------------------------------------//
`default_nettype none

module bench_arty_top (
    input  wire       clk100_i,
    input  wire       cpu_reset_n,     //! button, low while pressed

    output logic      eth_ref_clk_o,
    output logic      eth_rst_n_o,
    input  wire       eth_rx_clk_i,
    input  wire       eth_rx_dv_i,
    input  wire       eth_rx_er_i,
    input  wire [3:0] eth_rxd_i,
    input  wire       eth_tx_clk_i,
    output logic      eth_tx_en_o,
    output logic [3:0] eth_txd_o,

    output logic      uart_tx_o,
    output logic [3:0] led_o
);

  // ------------------------------------------------------------ resets
  //! 7-series configuration leaves registers at 0: that IS the power-on
  //! reset for this counter; the button restarts it
  logic [23:0] por_r;
  logic        rst_n;
  always_ff @(posedge clk100_i) begin : por
    if (!cpu_reset_n) por_r <= '0;
    else if (!(&por_r)) por_r <= por_r + 24'd1;
  end
  assign rst_n = &por_r;

  logic rxrst_q1_r, rxrst_n, txrst_q1_r, txrst_n;
  always_ff @(posedge eth_rx_clk_i) begin
    rxrst_q1_r <= rst_n;
    rxrst_n    <= rxrst_q1_r;
  end
  always_ff @(posedge eth_tx_clk_i) begin
    txrst_q1_r <= rst_n;
    txrst_n    <= txrst_q1_r;
  end

  // ------------------------------------------- PHY reference + reset
  logic [1:0] ref_r;
  always_ff @(posedge clk100_i) ref_r <= ref_r + 2'd1;
  assign eth_ref_clk_o = ref_r[1];

  //! DP83848 wants its clock long before reset release: ~21 ms here
  logic [20:0] phyrst_r;
  always_ff @(posedge clk100_i) begin : phyrst
    if (!rst_n) phyrst_r <= '0;
    else if (!(&phyrst_r)) phyrst_r <= phyrst_r + 21'd1;
  end
  assign eth_rst_n_o = &phyrst_r;

  // ------------------------------------------------------------- PHC
  logic        phc_add_we_w, phc_step_we_w;
  logic [31:0] phc_add_w;
  logic [63:0] phc_step_w, phc_ns_w;

  bench_phc u_phc (
      .clk_i       (clk100_i),
      .rst_n       (rst_n),
      .addend_we_i (phc_add_we_w),
      .addend_i    (phc_add_w),
      .step_we_i   (phc_step_we_w),
      .step_i      (phc_step_w),
      .ns_o        (phc_ns_w)
  );

  // ------------------------------------------------------- RX gasket
  logic       rxb_v_w, rxb_sof_w, rxb_eof_w, rxb_err_w;
  logic [7:0] rxb_d_w;
  logic       rx_sfd_tgl_w;
  logic [15:0] crc_bad_w;

  bench_mii_rx u_rx (
      .rx_clk_i      (eth_rx_clk_i),
      .rst_n         (rxrst_n),
      .mii_dv_i      (eth_rx_dv_i),
      .mii_er_i      (eth_rx_er_i),
      .mii_d_i       (eth_rxd_i),
      .b_valid_o     (rxb_v_w),
      .b_data_o      (rxb_d_w),
      .b_sof_o       (rxb_sof_w),
      .b_eof_o       (rxb_eof_w),
      .b_err_o       (rxb_err_w),
      .sfd_toggle_o  (rx_sfd_tgl_w),
      .crc_bad_cnt_o (crc_bad_w)
  );

  logic        rxf_empty_w;
  logic [10:0] rxf_data_w;
  logic [6:0]  rxf_lvl_w;

  bench_afifo #(.W_P(11), .AW_P(6)) u_rxfifo (
      .wclk_i   (eth_rx_clk_i),
      .wrst_n   (rxrst_n),
      .wr_i     (rxb_v_w),
      .wdata_i  ({rxb_err_w, rxb_eof_w, rxb_sof_w, rxb_d_w}),
      .full_o   (),
      .rclk_i   (clk100_i),
      .rrst_n   (rst_n),
      .rd_i     (!rxf_empty_w),
      .rdata_o  (rxf_data_w),
      .empty_o  (rxf_empty_w),
      .rlevel_o (rxf_lvl_w)
  );

  // RX SFD timestamp: latch PHC on the synchronized toggle edge
  logic rxsfd_q1_r, rxsfd_q2_r, rxsfd_q3_r;
  logic [63:0] rxts_r;
  always_ff @(posedge clk100_i) begin : rxts
    rxsfd_q1_r <= rx_sfd_tgl_w;
    rxsfd_q2_r <= rxsfd_q1_r;
    rxsfd_q3_r <= rxsfd_q2_r;
    if (rxsfd_q2_r != rxsfd_q3_r) rxts_r <= phc_ns_w;
  end

  logic [15:0] rxf_cnt_r;
  always_ff @(posedge clk100_i) begin : rxcnt
    if (!rst_n) rxf_cnt_r <= '0;
    else if (!rxf_empty_w && rxf_data_w[9]) rxf_cnt_r <= rxf_cnt_r + 16'd1;
  end

  // ------------------------------------------------------- TX gasket
  logic       txe_v_w, txe_sof_w, txe_eof_w, txe_rdy_w;
  logic [7:0] txe_d_w;
  logic       txf_full_w, txf_empty_w;
  logic [9:0] txf_data_w;
  logic [6:0] txf_lvl_w;
  logic       txrd_w;
  logic       tx_sfd_tgl_w, tx_done_tgl_w;
  logic [15:0] tx_frame_seq_w;
  logic [3:0]  tx_frame_type_w;
  logic [15:0] txf_cnt_w;

  bench_afifo #(.W_P(10), .AW_P(6)) u_txfifo (
      .wclk_i   (clk100_i),
      .wrst_n   (rst_n),
      .wr_i     (txe_v_w && txe_rdy_w),
      .wdata_i  ({txe_sof_w, txe_eof_w, txe_d_w}),
      .full_o   (txf_full_w),
      .rclk_i   (eth_tx_clk_i),
      .rrst_n   (txrst_n),
      .rd_i     (txrd_w),
      .rdata_o  (txf_data_w),
      .empty_o  (txf_empty_w),
      .rlevel_o (txf_lvl_w)
  );
  assign txe_rdy_w = !txf_full_w;

  bench_mii_tx u_tx (
      .tx_clk_i      (eth_tx_clk_i),
      .rst_n         (txrst_n),
      .mii_en_o      (eth_tx_en_o),
      .mii_d_o       (eth_txd_o),
      .f_data_i      (txf_data_w),
      .f_empty_i     (txf_empty_w),
      .f_level_i     (txf_lvl_w[5:0]),
      .f_rd_o        (txrd_w),
      .sfd_toggle_o  (tx_sfd_tgl_w),
      .done_toggle_o (tx_done_tgl_w),
      .frame_seq_o   (tx_frame_seq_w),
      .frame_type_o  (tx_frame_type_w),
      .tx_cnt_o      (txf_cnt_w)
  );

  // TX SFD stamp + bundled tag/done handshake -> egress timestamp return.
  // The MII-side tag is stable from byte 45 until the next frame's SFD;
  // synchronize it continuously and sample stage 2 only after the done
  // toggle has crossed one additional stage.
  (* ASYNC_REG = "TRUE" *) logic txsfd_q1_r, txsfd_q2_r;
  (* ASYNC_REG = "TRUE" *) logic txdone_q1_r, txdone_q2_r;
  (* ASYNC_REG = "TRUE" *) logic [15:0] txseq_q1_r, txseq_q2_r;
  (* ASYNC_REG = "TRUE" *) logic  [3:0] txtype_q1_r, txtype_q2_r;
  logic txsfd_q3_r, txdone_q3_r;
  logic [63:0] txts_r;
  logic        txts_v_r;
  logic [15:0] txts_seq_r;
  logic  [3:0] txts_type_r;
  always_ff @(posedge clk100_i) begin : txts
    if (!rst_n) begin
      txsfd_q1_r  <= 1'b0;
      txsfd_q2_r  <= 1'b0;
      txsfd_q3_r  <= 1'b0;
      txdone_q1_r <= 1'b0;
      txdone_q2_r <= 1'b0;
      txdone_q3_r <= 1'b0;
      txseq_q1_r  <= '0;
      txseq_q2_r  <= '0;
      txtype_q1_r <= '0;
      txtype_q2_r <= '0;
      txts_r      <= '0;
      txts_v_r    <= 1'b0;
      txts_seq_r  <= '0;
      txts_type_r <= '0;
    end else begin
      txsfd_q1_r  <= tx_sfd_tgl_w;
      txsfd_q2_r  <= txsfd_q1_r;
      txsfd_q3_r  <= txsfd_q2_r;
      txdone_q1_r <= tx_done_tgl_w;
      txdone_q2_r <= txdone_q1_r;
      txdone_q3_r <= txdone_q2_r;
      txseq_q1_r  <= tx_frame_seq_w;
      txseq_q2_r  <= txseq_q1_r;
      txtype_q1_r <= tx_frame_type_w;
      txtype_q2_r <= txtype_q1_r;
      if (txsfd_q2_r != txsfd_q3_r) txts_r <= phc_ns_w;
      txts_v_r <= (txdone_q2_r != txdone_q3_r);
      if (txdone_q2_r != txdone_q3_r) begin
        txts_seq_r  <= txseq_q2_r;
        txts_type_r <= txtype_q2_r;
      end
    end
  end

  // ------------------------------------------------------------ engine
  logic [63:0] pub_gm_w, pub_parent_w, pub_annq_w;
  logic [31:0] pub_flags_w, pub_pd_w, pub_off_w;
  logic [15:0] pdrop_w, evdrop_w;

  KL_gptp_engine #(
      .UCODE_HEX_P ("gptp_ucode.hex"),
      .CLK_HZ_P    (100_000_000)
  ) u_engine (
      .clk_i              (clk100_i),
      .rst_n              (rst_n),
      .rx_valid_i         (!rxf_empty_w),
      .rx_data_i          (rxf_data_w[7:0]),
      .rx_sof_i           (rxf_data_w[8]),
      .rx_eof_i           (rxf_data_w[9]),
      .rx_err_i           (rxf_data_w[10]),
      .rx_ts_i            (rxts_r),
      .tx_valid_o         (txe_v_w),
      .tx_data_o          (txe_d_w),
      .tx_sof_o           (txe_sof_w),
      .tx_eof_o           (txe_eof_w),
      .tx_ready_i         (txe_rdy_w),
      .txts_valid_i       (txts_v_r),
      .txts_ns_i          (txts_r),
      .txts_seq_i         (txts_seq_r),
      .txts_type_i        (txts_type_r),
      .phc_addend_we_o    (phc_add_we_w),
      .phc_addend_o       (phc_add_w),
      .phc_step_we_o      (phc_step_we_w),
      .phc_step_o         (phc_step_w),
      .pub_gm_id_o        (pub_gm_w),
      .pub_parent_id_o    (pub_parent_w),
      .pub_flags_o        (pub_flags_w),
      .pub_pdelay_ns_o    (pub_pd_w),
      .pub_offset_o       (pub_off_w),
      .pub_annq_o         (pub_annq_w),
      .pub_path_count_o   (),
      .pub_path_o         (),
      .pub_commit_o       (),
      .eff_nvm_stb_o      (),
      .eff_nvm_mark_o     (),
      .eff_notify_stb_o   (),
      .eff_notify_class_o (),
      .dbg_rx_drop_o      (pdrop_w),
      .dbg_ev_drop_o      (evdrop_w),
      .dbg_busy_o         (),
      .dbg_status_o       ()
  );

  // ------------------------------------------------------------- UART
  bench_uart_report u_uart (
      .clk_i     (clk100_i),
      .rst_n     (rst_n),
      .gm_i      (pub_gm_w),
      .parent_i  (pub_parent_w),
      .annq_i    (pub_annq_w),
      .flags_i   (pub_flags_w[7:0]),
      .pdelay_i  (pub_pd_w),
      .offset_i  (pub_off_w),
      .rxf_i     (rxf_cnt_r),
      .crcbad_i  (crc_bad_w),
      .pdrop_i   (pdrop_w),
      .evdrop_i  (evdrop_w),
      .txf_i     (txf_cnt_w),
      .uart_tx_o (uart_tx_o)
  );

  // -------------------------------------------------------------- LEDs
  logic [24:0] hb_r;
  logic [21:0] rxact_r, txact_r;
  always_ff @(posedge clk100_i) begin : leds
    hb_r <= hb_r + 25'd1;
    rxact_r <= (!rxf_empty_w && rxf_data_w[9]) ? '1
             : (rxact_r != 0 ? rxact_r - 22'd1 : rxact_r);
    txact_r <= txts_v_r ? '1 : (txact_r != 0 ? txact_r - 22'd1 : txact_r);
  end
  assign led_o = {pub_flags_w[0], |txact_r, |rxact_r, hb_r[24]};

endmodule : bench_arty_top
`default_nettype wire
