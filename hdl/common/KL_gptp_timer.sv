/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : KL_gptp_timer.sv
//  Project     : 802.1AS gPTP protocol processor (time-sync plane)
//
//  Description : Millisecond deadline service, the protocol-processor
//                timer-service shape at gPTP scale: a prescaler chain to
//                a 1 ms tick, a free-running 32-bit absolute ms timebase,
//                and SLOTS_P armed deadlines swept one slot per cycle
//                after each tick. Arming is O(1) through the µCPU state
//                port; expiry raises one event per slot with a
//                valid/ready handshake so the engine's dispatch queue
//                arbitrates it against parser events. Wrap-safe modular
//                compare. Cadences this plane owes (802.1AS-2011 with
//                the Milan v1.2 Table 4.1 profile): Pdelay 1000 ms,
//                Announce 1000 ms, Sync 125 ms, plus the three receipt
//                timeouts — all far below one slot per ms.
//---------------------------------------------------------------------------//
`default_nettype none

module KL_gptp_timer #(
    parameter int unsigned CLK_HZ_P = 100_000_000,
    parameter int unsigned SLOTS_P  = 8
) (
    input  wire         clk_i,
    input  wire         rst_n,

    //! arm/disarm: delta of 0 disarms the slot
    input  wire                       arm_we_i,
    input  wire  [$clog2(SLOTS_P)-1:0] arm_slot_i,
    input  wire  [31:0]               arm_delta_ms_i,

    //! absolute timebase for µcode (gather source)
    output logic [31:0] ms_now_o,

    //! expiry event, one slot at a time
    output logic                       ev_valid_o,
    output logic [$clog2(SLOTS_P)-1:0] ev_slot_o,
    input  wire                        ev_ready_i
);

  localparam int unsigned US_DIV_C = CLK_HZ_P / 1_000_000;
  localparam int unsigned SW_C     = $clog2(SLOTS_P);

  logic [$clog2(US_DIV_C)-1:0] us_cnt_r;
  logic [9:0]                  ms_cnt_r;
  logic                        ms_tick_w;
  logic [31:0]                 ms_now_r;

  assign ms_tick_w = (us_cnt_r == ($clog2(US_DIV_C))'(US_DIV_C - 1)) &&
                     (ms_cnt_r == 10'd999);

  always_ff @(posedge clk_i) begin : timebase
    if (!rst_n) begin
      us_cnt_r <= '0;
      ms_cnt_r <= '0;
      ms_now_r <= '0;
    end else begin
      if (us_cnt_r == ($clog2(US_DIV_C))'(US_DIV_C - 1)) begin
        us_cnt_r <= '0;
        ms_cnt_r <= (ms_cnt_r == 10'd999) ? 10'd0 : ms_cnt_r + 10'd1;
      end else begin
        us_cnt_r <= us_cnt_r + 1'b1;
      end
      if (ms_tick_w) ms_now_r <= ms_now_r + 32'd1;
    end
  end

  assign ms_now_o = ms_now_r;

  // ---------------------------------------------------------- slot store
  logic [SLOTS_P-1:0] armed_r;
  logic [31:0]        deadline_r [0:SLOTS_P-1];

  logic [SW_C-1:0] sweep_r;
  logic            sweeping_r;
  logic            pend_r;
  logic [SW_C-1:0] pend_slot_r;

  //! wrap-safe: expired when (deadline - now) has crossed zero
  logic signed [31:0] delta_w;
  assign delta_w = $signed(deadline_r[sweep_r] - ms_now_r);

  always_ff @(posedge clk_i) begin : slots
    if (!rst_n) begin
      armed_r     <= '0;
      sweep_r     <= '0;
      sweeping_r  <= 1'b0;
      pend_r      <= 1'b0;
      pend_slot_r <= '0;
      for (int i = 0; i < SLOTS_P; i++) deadline_r[i] <= '0;
    end else begin
      // arm port wins over the sweep's disarm (an arm in the expiry
      // cycle re-arms, which is the periodic-cadence idiom)
      if (arm_we_i) begin
        armed_r[arm_slot_i]    <= (arm_delta_ms_i != 32'd0);
        deadline_r[arm_slot_i] <= ms_now_r + arm_delta_ms_i;
      end

      if (ms_tick_w && !sweeping_r) begin
        sweeping_r <= 1'b1;
        sweep_r    <= '0;
      end else if (sweeping_r && !pend_r) begin
        if (armed_r[sweep_r] && (delta_w <= 32'sd0) &&
            !(arm_we_i && (arm_slot_i == sweep_r))) begin
          armed_r[sweep_r] <= 1'b0;
          pend_r           <= 1'b1;
          pend_slot_r      <= sweep_r;
        end
        if (sweep_r == SW_C'(SLOTS_P - 1)) sweeping_r <= 1'b0;
        else                               sweep_r    <= sweep_r + SW_C'(1);
      end

      if (pend_r && ev_ready_i) pend_r <= 1'b0;
    end
  end

  assign ev_valid_o = pend_r;
  assign ev_slot_o  = pend_slot_r;

endmodule : KL_gptp_timer
`default_nettype wire
