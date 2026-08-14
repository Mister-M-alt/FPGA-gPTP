/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : KL_gptp_tx_slot.sv
//  Project     : 802.1AS gPTP protocol processor (time-sync plane)
//
//  Description : One TX PDU slot plus its byte serializer. The µCPU's
//                32-bit build lane writes fields at BYTE cursor addresses
//                (1/2/4-byte strobes, big-endian, possibly unaligned); a
//                small unpack FSM turns each lane write into 1..4 byte
//                writes into a byte-wide slot RAM, using the lane's
//                rb_ready backpressure — the same contract the AECP
//                response buffer established (a refused write holds the
//                µCPU's E stage, so nothing is lost and nothing races).
//
//                SEND latches the built length and streams bytes 0..len-1
//                on the TX byte face with sof/eof marks. The engine gates
//                dispatch of the next event on ser_idle_o, so a µprogram
//                never builds into a slot that is still on the wire.
//---------------------------------------------------------------------------//
`default_nettype none

module KL_gptp_tx_slot
  import gptp_ucpu_pkg::*;
#(
    parameter int unsigned SLOT_BYTES_P = TXSLOT_BYTES_C
) (
    input  wire         clk_i,
    input  wire         rst_n,

    //! µCPU build lane
    input  wire         rb_we_i,
    input  wire  [9:0]  rb_addr_i,
    input  wire  [31:0] rb_wdata_i,
    input  wire  [3:0]  rb_wstrb_i,
    output logic        rb_ready_o,

    //! send request (µCPU OP_SEND_RESP)
    input  wire         send_i,
    input  wire  [10:0] send_len_i,
    output logic        ser_idle_o,

    //! TX byte face
    output logic        tx_valid_o,
    output logic [7:0]  tx_data_o,
    output logic        tx_sof_o,
    output logic        tx_eof_o,
    input  wire         tx_ready_i
);

  localparam int unsigned AW_C = $clog2(SLOT_BYTES_P);

  (* ram_style = "distributed" *) logic [7:0] slot_r [0:SLOT_BYTES_P-1];

  // ------------------------------------------------ lane write unpack FSM
  logic [1:0]      wr_left_r;     //! bytes still to store after this one
  logic            wr_busy_r;
  logic [AW_C-1:0] wr_addr_r;
  logic [31:0]     wr_data_r;

  //! bytes carried by this lane write, from the strobe shape the µCPU
  //! emits (0x1 byte, 0x3 word16, 0xF dword)
  logic [1:0] wr_n_w;
  always_comb begin : strobe_len
    unique case (rb_wstrb_i)
      4'h1:    wr_n_w = 2'd0;
      4'h3:    wr_n_w = 2'd1;
      default: wr_n_w = 2'd3;
    endcase
  end

  //! most-significant used byte first (wire order)
  logic [7:0] wr_byte_w;
  always_comb begin : byte_pick
    unique case (wr_left_r)
      2'd3:    wr_byte_w = wr_data_r[31:24];
      2'd2:    wr_byte_w = wr_data_r[23:16];
      2'd1:    wr_byte_w = wr_data_r[15:8];
      default: wr_byte_w = wr_data_r[7:0];
    endcase
  end

  assign rb_ready_o = !wr_busy_r;

  always_ff @(posedge clk_i) begin : lane_write
    if (!rst_n) begin
      wr_busy_r <= 1'b0;
      wr_left_r <= '0;
      wr_addr_r <= '0;
      wr_data_r <= '0;
    end else begin
      if (!wr_busy_r) begin
        if (rb_we_i) begin
          wr_busy_r <= 1'b1;
          wr_left_r <= wr_n_w;
          wr_addr_r <= rb_addr_i[AW_C-1:0];
          wr_data_r <= rb_wdata_i;
        end
      end else begin
        slot_r[wr_addr_r] <= wr_byte_w;
        wr_addr_r         <= wr_addr_r + AW_C'(1);
        if (wr_left_r == 2'd0) wr_busy_r <= 1'b0;
        else                   wr_left_r <= wr_left_r - 2'd1;
      end
    end
  end

  // ------------------------------------------------------- serializer
  logic            ser_run_r;
  logic [AW_C-1:0] ser_addr_r;
  logic [10:0]     ser_left_r;
  logic            ser_sof_r;

  assign ser_idle_o = !ser_run_r;
  assign tx_valid_o = ser_run_r;
  assign tx_data_o  = slot_r[ser_addr_r];
  assign tx_sof_o   = ser_sof_r;
  assign tx_eof_o   = ser_run_r && (ser_left_r == 11'd1);

  always_ff @(posedge clk_i) begin : serialize
    if (!rst_n) begin
      ser_run_r  <= 1'b0;
      ser_addr_r <= '0;
      ser_left_r <= '0;
      ser_sof_r  <= 1'b0;
    end else begin
      if (!ser_run_r) begin
        if (send_i && (send_len_i != 11'd0)) begin
          ser_run_r  <= 1'b1;
          ser_addr_r <= '0;
          ser_left_r <= send_len_i;
          ser_sof_r  <= 1'b1;
        end
      end else if (tx_ready_i) begin
        ser_sof_r  <= 1'b0;
        ser_addr_r <= ser_addr_r + AW_C'(1);
        ser_left_r <= ser_left_r - 11'd1;
        if (ser_left_r == 11'd1) ser_run_r <= 1'b0;
      end
    end
  end

endmodule : KL_gptp_tx_slot
`default_nettype wire
