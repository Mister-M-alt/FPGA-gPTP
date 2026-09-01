/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : bench_mii_tx.sv
//  Project     : FPGA-gPTP Arty bench (bench-only RTL)
//
//  Description : 100BASE-TX MII transmit gasket, tx_clk domain. Pulls
//                {sof,eof,byte} words from the TX FIFO, sends preamble +
//                SFD, bytes low-nibble-first, appends the FCS
//                (complemented reflected CRC32, low byte first), and
//                holds 96 bit-times of IFG. Starts once ≥8 bytes are
//                buffered — the sys-side producer is ~10x faster than
//                the 100M wire drain, so it can never underrun after
//                that. sfd_toggle at the SFD (egress timestamp point),
//                done_toggle at frame end (egress-timestamp return). The
//                stamped frame's {messageType, sequenceId} is extracted
//                from that same FIFO stream and held stable around the
//                done toggle for bundled-data CDC back to sys.
//---------------------------------------------------------------------------//
`default_nettype none

module bench_mii_tx (
    input  wire        tx_clk_i,
    input  wire        rst_n,

    output logic       mii_en_o,
    output logic [3:0] mii_d_o,

    //! TX FIFO read side (word = {sof, eof, byte}); the level is the
    //! FULL width incl. the all-full MSB — truncating it made a FIFO
    //! at exactly 64 read as level 0 and wedged S_IDLE forever (caught
    //! live on the wire: a become-master TX burst parked the FIFO at
    //! 64 during the previous frame's FCS/IFG and the plane went mute;
    //! issue #54, pinned by tb/verilator/gaskets)
    input  wire  [9:0] f_data_i,
    input  wire        f_empty_i,
    input  wire  [6:0] f_level_i,
    output logic       f_rd_o,

    output logic       sfd_toggle_o,
    output logic       done_toggle_o,
    output logic [15:0] frame_seq_o,
    output logic  [3:0] frame_type_o,
    output logic [15:0] tx_cnt_o
);

  typedef enum logic [2:0] {
    S_IDLE, S_PRE, S_SFD, S_LO, S_HI, S_FCS, S_IFG
  } state_e;
  state_e st_r;

  logic [3:0]  pre_r;
  logic [7:0]  byte_r;
  logic        last_r;
  logic [31:0] crc_r;
  logic [1:0]  fcs_i_r;
  logic        fcs_ph_r;
  logic [4:0]  ifg_r;
  logic [15:0] cnt_r;
  logic [5:0]  frame_byte_r;

  function automatic logic [31:0] crc32_byte(input logic [31:0] c,
                                             input logic [7:0] d);
    logic [31:0] x;
    x = c ^ {24'd0, d};
    for (int i = 0; i < 8; i++)
      x = (x >> 1) ^ (x[0] ? 32'hEDB88320 : 32'd0);
    return x;
  endfunction

  logic [31:0] fcs_w;
  assign fcs_w = ~crc_r;

  logic [7:0] fcs_byte_w;
  always_comb begin : fcs_pick
    unique case (fcs_i_r)
      2'd0: fcs_byte_w = fcs_w[7:0];
      2'd1: fcs_byte_w = fcs_w[15:8];
      2'd2: fcs_byte_w = fcs_w[23:16];
      default: fcs_byte_w = fcs_w[31:24];
    endcase
  end

  always_ff @(posedge tx_clk_i) begin : tx
    if (!rst_n) begin
      st_r          <= S_IDLE;
      pre_r         <= '0;
      byte_r        <= '0;
      last_r        <= 1'b0;
      crc_r         <= '1;
      fcs_i_r       <= '0;
      fcs_ph_r      <= 1'b0;
      ifg_r         <= '0;
      cnt_r         <= '0;
      mii_en_o      <= 1'b0;
      mii_d_o       <= '0;
      f_rd_o        <= 1'b0;
      sfd_toggle_o  <= 1'b0;
      done_toggle_o <= 1'b0;
      frame_seq_o   <= '0;
      frame_type_o  <= '0;
      frame_byte_r  <= '0;
    end else begin
      f_rd_o <= 1'b0;

      unique case (st_r)
        S_IDLE: begin
          mii_en_o <= 1'b0;
          crc_r    <= '1;
          pre_r    <= '0;
          if (!f_empty_i && (f_level_i >= 7'd8)) st_r <= S_PRE;
        end

        S_PRE: begin
          mii_en_o <= 1'b1;
          mii_d_o  <= 4'h5;
          pre_r    <= pre_r + 4'd1;
          if (pre_r == 4'd14) st_r <= S_SFD;       // 15 x 0x5 then 0xD
        end

        S_SFD: begin
          mii_d_o      <= 4'hD;
          sfd_toggle_o <= ~sfd_toggle_o;
          // fetch the first byte (sof word)
          byte_r       <= f_data_i[7:0];
          last_r       <= f_data_i[8];
          crc_r        <= crc32_byte('1, f_data_i[7:0]);
          f_rd_o       <= 1'b1;
          frame_byte_r <= '0;
          frame_seq_o  <= '0;
          frame_type_o <= '0;
          st_r         <= S_LO;
        end

        S_LO: begin
          mii_d_o <= byte_r[3:0];
          st_r    <= S_HI;
        end

        S_HI: begin
          mii_d_o <= byte_r[7:4];
          if (last_r) begin
            st_r     <= S_FCS;
            fcs_i_r  <= '0;
            fcs_ph_r <= 1'b0;
          end else begin
            byte_r <= f_data_i[7:0];
            last_r <= f_data_i[8];
            crc_r  <= crc32_byte(crc_r, f_data_i[7:0]);
            f_rd_o <= 1'b1;
            st_r   <= S_LO;
            if (frame_byte_r != 6'h3F)
              frame_byte_r <= frame_byte_r + 6'd1;
            // Untagged gPTP: messageType is frame byte 14 and sequenceId
            // is the big-endian word at frame bytes 44..45. case selects
            // the word being fetched, i.e. the byte after frame_byte_r.
            unique case (frame_byte_r)
              6'd13: frame_type_o      <= f_data_i[3:0];
              6'd43: frame_seq_o[15:8] <= f_data_i[7:0];
              6'd44: frame_seq_o[7:0]  <= f_data_i[7:0];
              default: ;
            endcase
          end
        end

        S_FCS: begin
          mii_d_o  <= fcs_ph_r ? fcs_byte_w[7:4] : fcs_byte_w[3:0];
          fcs_ph_r <= ~fcs_ph_r;
          if (fcs_ph_r) begin
            fcs_i_r <= fcs_i_r + 2'd1;
            if (fcs_i_r == 2'd3) begin
              st_r          <= S_IFG;
              ifg_r         <= '0;
              done_toggle_o <= ~done_toggle_o;
              cnt_r         <= cnt_r + 16'd1;
            end
          end
        end

        S_IFG: begin
          mii_en_o <= 1'b0;
          mii_d_o  <= '0;
          ifg_r    <= ifg_r + 5'd1;
          if (ifg_r == 5'd23) st_r <= S_IDLE;      // 96 bit-times
        end
        default: st_r <= S_IDLE;
      endcase
    end
  end

  assign tx_cnt_o = cnt_r;

endmodule : bench_mii_tx
`default_nettype wire
