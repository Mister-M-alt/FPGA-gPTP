/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : bench_uart_report.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL)
//
//  Description : 115200-8N1 TX-only reporter. Once per second prints one
//                line of the engine's published truth in fixed hex:
//
//                S=ss G=gggggggggggggggg P=pppppppppppppppp F=ff
//                D=dddddddd O=oooooooo R=rrrr C=cccc Q=qqqq E=eeee T=tttt
//
//                S seconds · G grandmaster identity · P parent identity ·
//                F flags (bit0 gm_present) · D meanLinkDelay ns ·
//                O sync offset ns (signed) · R RX frames delivered ·
//                C CRC-bad frames · Q parser drops · E event-queue drops
//                · T TX frames.
//---------------------------------------------------------------------------//
`default_nettype none

module bench_uart_report #(
    parameter int unsigned CLK_HZ_P = 100_000_000,
    parameter int unsigned BAUD_P   = 115_200
) (
    input  wire         clk_i,
    input  wire         rst_n,

    input  wire  [63:0] gm_i,
    input  wire  [63:0] parent_i,
    input  wire  [7:0]  flags_i,
    input  wire  [31:0] pdelay_i,
    input  wire  [31:0] offset_i,
    input  wire  [15:0] rxf_i,
    input  wire  [15:0] crcbad_i,
    input  wire  [15:0] pdrop_i,
    input  wire  [15:0] evdrop_i,
    input  wire  [15:0] txf_i,

    output logic        uart_tx_o
);

  localparam int unsigned DIV_C = CLK_HZ_P / BAUD_P;

  // ---- field table: {label, width-in-nibbles, source} --------------------
  localparam int unsigned NFIELDS_C = 11;
  logic [7:0]  sec_r;
  logic [63:0] fld_w [0:NFIELDS_C-1];
  logic [7:0]  lbl_w [0:NFIELDS_C-1];
  logic [4:0]  nib_w [0:NFIELDS_C-1];

  always_comb begin : fields
    lbl_w[0]  = "S"; nib_w[0]  = 5'd2;  fld_w[0]  = {56'd0, sec_r};
    lbl_w[1]  = "G"; nib_w[1]  = 5'd16; fld_w[1]  = gm_i;
    lbl_w[2]  = "P"; nib_w[2]  = 5'd16; fld_w[2]  = parent_i;
    lbl_w[3]  = "F"; nib_w[3]  = 5'd2;  fld_w[3]  = {56'd0, flags_i};
    lbl_w[4]  = "D"; nib_w[4]  = 5'd8;  fld_w[4]  = {32'd0, pdelay_i};
    lbl_w[5]  = "O"; nib_w[5]  = 5'd8;  fld_w[5]  = {32'd0, offset_i};
    lbl_w[6]  = "R"; nib_w[6]  = 5'd4;  fld_w[6]  = {48'd0, rxf_i};
    lbl_w[7]  = "C"; nib_w[7]  = 5'd4;  fld_w[7]  = {48'd0, crcbad_i};
    lbl_w[8]  = "Q"; nib_w[8]  = 5'd4;  fld_w[8]  = {48'd0, pdrop_i};
    lbl_w[9]  = "E"; nib_w[9]  = 5'd4;  fld_w[9]  = {48'd0, evdrop_i};
    lbl_w[10] = "T"; nib_w[10] = 5'd4;  fld_w[10] = {48'd0, txf_i};
  end

  // ---- 1 Hz trigger ------------------------------------------------------
  logic [$clog2(CLK_HZ_P)-1:0] sec_cnt_r;
  logic go_r;

  // ---- byte-level line FSM ----------------------------------------------
  typedef enum logic [2:0] {
    L_IDLE, L_LBL, L_EQ, L_HEX, L_SP, L_CR, L_LF
  } line_e;
  line_e lst_r;
  logic [3:0]  fidx_r;
  logic [4:0]  nleft_r;
  logic [63:0] shreg_r;

  logic [3:0] nib_cur_w;
  assign nib_cur_w = shreg_r[63:60];
  logic [7:0] hex_w;
  assign hex_w = (nib_cur_w < 4'd10) ? ("0" + {4'd0, nib_cur_w})
                                     : ("A" + {4'd0, nib_cur_w} - 8'd10);

  // ---- bit-level UART ----------------------------------------------------
  logic        b_busy_r;
  logic [3:0]  b_idx_r;
  logic [9:0]  b_sh_r;
  logic [$clog2(DIV_C)-1:0] b_div_r;
  logic        b_go_w;
  logic [7:0]  b_data_w;

  always_comb begin : next_byte
    b_go_w   = 1'b0;
    b_data_w = 8'h20;
    if (!b_busy_r) begin
      unique case (lst_r)
        L_LBL: begin b_go_w = 1'b1; b_data_w = lbl_w[fidx_r]; end
        L_EQ:  begin b_go_w = 1'b1; b_data_w = "="; end
        L_HEX: begin b_go_w = 1'b1; b_data_w = hex_w; end
        L_SP:  begin b_go_w = 1'b1; b_data_w = " "; end
        L_CR:  begin b_go_w = 1'b1; b_data_w = 8'h0D; end
        L_LF:  begin b_go_w = 1'b1; b_data_w = 8'h0A; end
        default: ;
      endcase
    end
  end

  always_ff @(posedge clk_i) begin : uart
    if (!rst_n) begin
      sec_cnt_r <= '0;
      sec_r     <= '0;
      go_r      <= 1'b0;
      lst_r     <= L_IDLE;
      fidx_r    <= '0;
      nleft_r   <= '0;
      shreg_r   <= '0;
      b_busy_r  <= 1'b0;
      b_idx_r   <= '0;
      b_sh_r    <= '1;
      b_div_r   <= '0;
      uart_tx_o <= 1'b1;
    end else begin
      go_r <= 1'b0;
      if (sec_cnt_r == ($clog2(CLK_HZ_P))'(CLK_HZ_P - 1)) begin
        sec_cnt_r <= '0;
        sec_r     <= sec_r + 8'd1;
        go_r      <= 1'b1;
      end else sec_cnt_r <= sec_cnt_r + 1'b1;

      // line sequencing
      unique case (lst_r)
        L_IDLE: if (go_r) begin lst_r <= L_LBL; fidx_r <= '0; end
        L_LBL:  if (b_go_w) lst_r <= L_EQ;
        L_EQ:   if (b_go_w) begin
                  lst_r   <= L_HEX;
                  nleft_r <= nib_w[fidx_r];
                  shreg_r <= fld_w[fidx_r] << (4 * (16 - nib_w[fidx_r]));
                end
        L_HEX:  if (b_go_w) begin
                  shreg_r <= shreg_r << 4;
                  nleft_r <= nleft_r - 5'd1;
                  if (nleft_r == 5'd1)
                    lst_r <= (fidx_r == 4'(NFIELDS_C - 1)) ? L_CR : L_SP;
                end
        L_SP:   if (b_go_w) begin lst_r <= L_LBL; fidx_r <= fidx_r + 4'd1; end
        L_CR:   if (b_go_w) lst_r <= L_LF;
        L_LF:   if (b_go_w) lst_r <= L_IDLE;
        default: lst_r <= L_IDLE;
      endcase

      // byte shifter
      if (b_go_w) begin
        b_busy_r <= 1'b1;
        b_sh_r   <= {1'b1, b_data_w, 1'b0};    // stop, data, start
        b_idx_r  <= '0;
        b_div_r  <= '0;
      end else if (b_busy_r) begin
        if (b_div_r == ($clog2(DIV_C))'(DIV_C - 1)) begin
          b_div_r   <= '0;
          uart_tx_o <= b_sh_r[0];
          b_sh_r    <= {1'b1, b_sh_r[9:1]};
          b_idx_r   <= b_idx_r + 4'd1;
          if (b_idx_r == 4'd9) b_busy_r <= 1'b0;
        end else b_div_r <= b_div_r + 1'b1;
      end
    end
  end

endmodule : bench_uart_report
`default_nettype wire
