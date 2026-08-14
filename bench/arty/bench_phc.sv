/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : bench_phc.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL)
//
//  Description : Free-running 64-bit ns hardware clock with a Q8.24
//                fractional accumulator, 10 ns per 100 MHz tick. The
//                engine's rate-addend writes add a signed Q8.24 ns/tick
//                trim (unused in the observe-only µcode round, wired for
//                the servo round); step writes add a signed ns offset.
//---------------------------------------------------------------------------//
`default_nettype none

module bench_phc (
    input  wire         clk_i,
    input  wire         rst_n,

    input  wire         addend_we_i,
    input  wire  [31:0] addend_i,
    input  wire         step_we_i,
    input  wire  [63:0] step_i,

    output logic [63:0] ns_o
);

  logic [63:0] ns_r;
  logic [23:0] frac_r;
  logic signed [31:0] trim_r;

  //! base increment 10 ns in Q8.24 plus the signed trim; the whole-ns
  //! carry out of the fraction is what advances the counter
  logic signed [34:0] inc_w;
  assign inc_w = 35'sd167772160 + 35'(trim_r);   // 10 << 24

  logic [34:0] sum_w;
  assign sum_w = {11'd0, frac_r} + unsigned'(35'(inc_w));

  always_ff @(posedge clk_i) begin : phc
    if (!rst_n) begin
      ns_r   <= '0;
      frac_r <= '0;
      trim_r <= '0;
    end else begin
      frac_r <= sum_w[23:0];
      ns_r   <= ns_r + {53'd0, sum_w[34:24]}
                + (step_we_i ? step_i : 64'd0);
      if (addend_we_i) trim_r <= signed'(addend_i);
    end
  end

  assign ns_o = ns_r;

endmodule : bench_phc
`default_nettype wire
