/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : gasket_tb_top.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL) — gasket testbench
//
//  Description : Loopback harness for the bench MII gaskets, the seam the
//                engine suites do not cover and where the wire found a
//                real deadlock (the 7-bit TX FIFO level truncated to 6:
//                a FIFO at exactly 64 read as level 0 and S_IDLE never
//                started — issue #54). The chain is the
//                bench_arty_top arrangement verbatim: sys-side producer
//                -> TX afifo -> bench_mii_tx -> MII nibbles looped into
//                bench_mii_rx -> RX afifo -> sys-side consumer.
//                corrupt_i XORs the MII data nibbles to prove the FCS
//                drop arm.
//---------------------------------------------------------------------------//
`default_nettype none

module gasket_tb_top (
    input  wire        sys_clk_i,
    input  wire        mii_clk_i,
    input  wire        rst_n,

    //! sys-side TX producer (the engine's byte face shape)
    input  wire        tx_valid_i,
    input  wire  [7:0] tx_data_i,
    input  wire        tx_sof_i,
    input  wire        tx_eof_i,
    output logic       tx_ready_o,

    //! fault injection: XORed onto the MII nibbles
    input  wire  [3:0] corrupt_i,

    //! sys-side RX consumer
    output logic       rx_valid_o,
    output logic [7:0] rx_data_o,
    output logic       rx_sof_o,
    output logic       rx_eof_o,
    output logic       rx_err_o,

    //! observability
    output logic        mii_en_o,
    output logic        tx_sfd_tgl_o,
    output logic        tx_done_tgl_o,
    output logic        rx_sfd_tgl_o,
    output logic [15:0] tx_cnt_o,
    output logic [15:0] crc_bad_o,
    output logic [15:0] tx_frame_seq_o,
    output logic  [3:0] tx_frame_type_o
);

  // ------------------------------------------------------- TX direction
  logic       txf_full_w, txf_empty_w;
  logic [9:0] txf_data_w;
  logic [6:0] txf_lvl_w;
  logic       txrd_w;
  logic [3:0] mii_d_w;
  logic       mii_en_w;

  bench_afifo #(.W_P(10), .AW_P(6)) u_txfifo (
      .wclk_i   (sys_clk_i),
      .wrst_n   (rst_n),
      .wr_i     (tx_valid_i && !txf_full_w),
      .wdata_i  ({tx_sof_i, tx_eof_i, tx_data_i}),
      .full_o   (txf_full_w),
      .rclk_i   (mii_clk_i),
      .rrst_n   (rst_n),
      .rd_i     (txrd_w),
      .rdata_o  (txf_data_w),
      .empty_o  (txf_empty_w),
      .rlevel_o (txf_lvl_w)
  );
  assign tx_ready_o = !txf_full_w;

  bench_mii_tx u_tx (
      .tx_clk_i      (mii_clk_i),
      .rst_n         (rst_n),
      .mii_en_o      (mii_en_w),
      .mii_d_o       (mii_d_w),
      .f_data_i      (txf_data_w),
      .f_empty_i     (txf_empty_w),
      .f_level_i     (txf_lvl_w),
      .f_rd_o        (txrd_w),
      .sfd_toggle_o  (tx_sfd_tgl_o),
      .done_toggle_o (tx_done_tgl_o),
      .frame_seq_o   (tx_frame_seq_o),
      .frame_type_o  (tx_frame_type_o),
      .tx_cnt_o      (tx_cnt_o)
  );
  assign mii_en_o = mii_en_w;

  // --------------------------------------------- MII loop with corruption
  logic [3:0] rx_d_w;
  assign rx_d_w = mii_d_w ^ corrupt_i;

  // ------------------------------------------------------- RX direction
  logic       rxb_v_w, rxb_sof_w, rxb_eof_w, rxb_err_w;
  logic [7:0] rxb_d_w;

  bench_mii_rx u_rx (
      .rx_clk_i      (mii_clk_i),
      .rst_n         (rst_n),
      .mii_dv_i      (mii_en_w),
      .mii_er_i      (1'b0),
      .mii_d_i       (rx_d_w),
      .b_valid_o     (rxb_v_w),
      .b_data_o      (rxb_d_w),
      .b_sof_o       (rxb_sof_w),
      .b_eof_o       (rxb_eof_w),
      .b_err_o       (rxb_err_w),
      .sfd_toggle_o  (rx_sfd_tgl_o),
      .crc_bad_cnt_o (crc_bad_o)
  );

  logic        rxf_empty_w;
  logic [10:0] rxf_data_w;
  logic [6:0]  rxf_lvl_w;

  bench_afifo #(.W_P(11), .AW_P(6)) u_rxfifo (
      .wclk_i   (mii_clk_i),
      .wrst_n   (rst_n),
      .wr_i     (rxb_v_w),
      .wdata_i  ({rxb_err_w, rxb_eof_w, rxb_sof_w, rxb_d_w}),
      .full_o   (),
      .rclk_i   (sys_clk_i),
      .rrst_n   (rst_n),
      .rd_i     (!rxf_empty_w),
      .rdata_o  (rxf_data_w),
      .empty_o  (rxf_empty_w),
      .rlevel_o (rxf_lvl_w)
  );

  assign rx_valid_o = !rxf_empty_w;
  assign rx_data_o  = rxf_data_w[7:0];
  assign rx_sof_o   = rxf_data_w[8];
  assign rx_eof_o   = rxf_data_w[9];
  assign rx_err_o   = rxf_data_w[10];

  logic [6:0] unused_lvl_w;
  assign unused_lvl_w = rxf_lvl_w;

endmodule : gasket_tb_top
`default_nettype wire
