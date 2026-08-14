/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : bench_mii_rx.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL)
//
//  Description : 100BASE-TX MII receive gasket, rx_clk domain. Nibbles
//                (low first) to bytes, preamble/SFD hunt, CRC32 over the
//                whole frame including FCS (reflected poly 0xEDB88320,
//                init all-ones; good frame leaves the residue 0xDEBB20E3),
//                FCS stripped by a 4-byte delay line, and a one-byte hold
//                stage so eof + the CRC verdict ride ON the last payload
//                byte. sfd_toggle_o flips at the SFD for the timestamp
//                latch in the sys domain.
//---------------------------------------------------------------------------//
`default_nettype none

module bench_mii_rx (
    input  wire        rx_clk_i,
    input  wire        rst_n,          //! already synchronized to rx_clk

    input  wire        mii_dv_i,
    input  wire        mii_er_i,
    input  wire  [3:0] mii_d_i,

    output logic       b_valid_o,
    output logic [7:0] b_data_o,
    output logic       b_sof_o,
    output logic       b_eof_o,
    output logic       b_err_o,

    output logic       sfd_toggle_o,
    output logic [15:0] crc_bad_cnt_o
);

  localparam logic [31:0] CRC_RESIDUE_C = 32'hDEBB20E3;

  typedef enum logic [1:0] { S_IDLE, S_PRE, S_DATA } state_e;
  state_e st_r;

  logic       phase_r;                 //! 0 = expecting low nibble
  logic [3:0] lo_r;
  logic [31:0] crc_r;
  logic        er_seen_r;

  // FCS strip: 4-byte delay + 1-byte hold (emit on next byte or frame end)
  logic [7:0] dly_r [0:3];
  logic [2:0] dly_cnt_r;
  logic [7:0] hold_r;
  logic       hold_v_r;
  logic       hold_sof_r;
  logic       first_out_r;
  logic [15:0] crc_bad_r;

  function automatic logic [31:0] crc32_byte(input logic [31:0] c,
                                             input logic [7:0] d);
    logic [31:0] x;
    x = c ^ {24'd0, d};
    for (int i = 0; i < 8; i++)
      x = (x >> 1) ^ (x[0] ? 32'hEDB88320 : 32'd0);
    return x;
  endfunction

  logic byte_now_w;
  logic [7:0] byte_w;
  assign byte_now_w = mii_dv_i && (st_r == S_DATA) && phase_r;
  assign byte_w     = {mii_d_i, lo_r};

  logic frame_end_w;
  assign frame_end_w = !mii_dv_i && (st_r == S_DATA);

  logic crc_ok_w;
  assign crc_ok_w = (crc_r == CRC_RESIDUE_C) && !er_seen_r &&
                    (dly_cnt_r >= 3'd4);

  always_ff @(posedge rx_clk_i) begin : rx
    if (!rst_n) begin
      st_r         <= S_IDLE;
      phase_r      <= 1'b0;
      lo_r         <= '0;
      crc_r        <= '1;
      er_seen_r    <= 1'b0;
      dly_cnt_r    <= '0;
      hold_v_r     <= 1'b0;
      hold_sof_r   <= 1'b0;
      first_out_r  <= 1'b0;
      sfd_toggle_o <= 1'b0;
      crc_bad_r    <= '0;
      b_valid_o    <= 1'b0;
      b_data_o     <= '0;
      b_sof_o      <= 1'b0;
      b_eof_o      <= 1'b0;
      b_err_o      <= 1'b0;
      hold_r       <= '0;
      for (int i = 0; i < 4; i++) dly_r[i] <= '0;
    end else begin
      b_valid_o <= 1'b0;
      b_sof_o   <= 1'b0;
      b_eof_o   <= 1'b0;
      b_err_o   <= 1'b0;

      unique case (st_r)
        S_IDLE: begin
          hold_v_r    <= 1'b0;
          first_out_r <= 1'b1;
          dly_cnt_r   <= '0;
          crc_r       <= '1;
          er_seen_r   <= 1'b0;
          phase_r     <= 1'b0;
          if (mii_dv_i && (mii_d_i == 4'h5)) st_r <= S_PRE;
        end

        S_PRE: begin
          if (!mii_dv_i) st_r <= S_IDLE;
          else if (mii_d_i == 4'hD) begin
            st_r         <= S_DATA;
            sfd_toggle_o <= ~sfd_toggle_o;
            phase_r      <= 1'b0;
          end else if (mii_d_i != 4'h5) st_r <= S_IDLE;
        end

        S_DATA: begin
          if (mii_dv_i) begin
            if (mii_er_i) er_seen_r <= 1'b1;
            phase_r <= ~phase_r;
            if (!phase_r) lo_r <= mii_d_i;
            else begin
              // one whole byte
              crc_r <= crc32_byte(crc_r, byte_w);
              dly_r[3] <= dly_r[2];
              dly_r[2] <= dly_r[1];
              dly_r[1] <= dly_r[0];
              dly_r[0] <= byte_w;
              if (dly_cnt_r < 3'd4) dly_cnt_r <= dly_cnt_r + 3'd1;
              else begin
                // dly_r[3] is 4 bytes behind: payload, FCS never emerges
                if (hold_v_r) begin
                  b_valid_o   <= 1'b1;
                  b_data_o    <= hold_r;
                  b_sof_o     <= hold_sof_r;
                end
                hold_r      <= dly_r[3];
                hold_sof_r  <= first_out_r;
                first_out_r <= 1'b0;
                hold_v_r    <= 1'b1;
              end
            end
          end else begin
            // frame ended: the held byte is the last payload byte
            st_r <= S_IDLE;
            if (hold_v_r) begin
              b_valid_o <= 1'b1;
              b_data_o  <= hold_r;
              b_sof_o   <= hold_sof_r;
              b_eof_o   <= 1'b1;
              b_err_o   <= !crc_ok_w;
              if (!crc_ok_w) crc_bad_r <= crc_bad_r + 16'd1;
            end
          end
        end
        default: st_r <= S_IDLE;
      endcase
    end
  end

  assign crc_bad_cnt_o = crc_bad_r;

  logic unused_w;
  assign unused_w = frame_end_w;

endmodule : bench_mii_rx
`default_nettype wire
