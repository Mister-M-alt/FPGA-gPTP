/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : bench_afifo.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL, not the shipping tree)
//
//  Description : Dual-clock FIFO, gray-coded pointers, 2-FF synchronizers,
//                show-ahead read. Depth 2**AW_P.
//---------------------------------------------------------------------------//
`default_nettype none

module bench_afifo #(
    parameter int unsigned W_P  = 8,
    parameter int unsigned AW_P = 5
) (
    input  wire            wclk_i,
    input  wire            wrst_n,
    input  wire            wr_i,
    input  wire  [W_P-1:0] wdata_i,
    output logic           full_o,

    input  wire            rclk_i,
    input  wire            rrst_n,
    input  wire            rd_i,
    output logic [W_P-1:0] rdata_o,
    output logic           empty_o,
    output logic [AW_P:0]  rlevel_o
);

  logic [W_P-1:0] mem_r [0:(1<<AW_P)-1];

  logic [AW_P:0] wptr_r, wgray_r, rptr_r, rgray_r;
  logic [AW_P:0] wgray_rq1_r, wgray_rq2_r;   // wgray into read domain
  logic [AW_P:0] rgray_wq1_r, rgray_wq2_r;   // rgray into write domain

  function automatic logic [AW_P:0] bin2gray(input logic [AW_P:0] b);
    return b ^ (b >> 1);
  endfunction

  function automatic logic [AW_P:0] gray2bin(input logic [AW_P:0] g);
    logic [AW_P:0] b;
    b = '0;
    for (int i = AW_P; i >= 0; i--)
      b[i] = (i == AW_P) ? g[i] : (b[i+1] ^ g[i]);
    return b;
  endfunction

  // ------------------------------------------------------------- write side
  always_ff @(posedge wclk_i) begin : wside
    if (!wrst_n) begin
      wptr_r      <= '0;
      wgray_r     <= '0;
      rgray_wq1_r <= '0;
      rgray_wq2_r <= '0;
    end else begin
      rgray_wq1_r <= rgray_r;
      rgray_wq2_r <= rgray_wq1_r;
      if (wr_i && !full_o) begin
        mem_r[wptr_r[AW_P-1:0]] <= wdata_i;
        wptr_r  <= wptr_r + 1'b1;
        wgray_r <= bin2gray(wptr_r + 1'b1);
      end
    end
  end

  assign full_o = (wgray_r == {~rgray_wq2_r[AW_P:AW_P-1],
                               rgray_wq2_r[AW_P-2:0]});

  // -------------------------------------------------------------- read side
  always_ff @(posedge rclk_i) begin : rside
    if (!rrst_n) begin
      rptr_r      <= '0;
      rgray_r     <= '0;
      wgray_rq1_r <= '0;
      wgray_rq2_r <= '0;
    end else begin
      wgray_rq1_r <= wgray_r;
      wgray_rq2_r <= wgray_rq1_r;
      if (rd_i && !empty_o) begin
        rptr_r  <= rptr_r + 1'b1;
        rgray_r <= bin2gray(rptr_r + 1'b1);
      end
    end
  end

  assign empty_o  = (rgray_r == wgray_rq2_r);
  assign rdata_o  = mem_r[rptr_r[AW_P-1:0]];
  assign rlevel_o = gray2bin(wgray_rq2_r) - rptr_r;

endmodule : bench_afifo
`default_nettype wire
