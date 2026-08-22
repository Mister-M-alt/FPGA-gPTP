/*
 * SPDX-FileCopyrightText: 2026 Kebag Logic
 * SPDX-License-Identifier: CERN-OHL-W-2.0
 */
//---------------------------------------------------------------------------//
//  File        : gptp_ucpu_pkg.sv
//  Project     : 802.1AS gPTP protocol processor (time-sync plane)
//
//  Description : µISA for the gPTP micro-coded engine. This is the AECP
//                processor's 48-bit encoding (protocol-processor
//                hdl/aecp/ucpu_pkg.sv) grown by the two opcode groups that
//                802.1AS arithmetic needs and AECP deliberately never had:
//
//                  OP_ALU     cnd selects ADD/SUB/AND/OR/XOR/SHL/SHR/SAR,
//                             64-bit datapath; shifts are SERIAL (one bit
//                             per cycle) because every gPTP computation
//                             runs at protocol rate (<= 8 Hz) and a barrel
//                             shifter would buy latency nothing needs.
//                  OP_MULDIV  cnd 0 = MULS 32x32 -> 64 (DSP-inferred,
//                             short pipeline); cnd 1 = DIVU 64/32 -> 64
//                             (restoring, one bit per cycle) for
//                             neighborRateRatio and servo scaling.
//
//                One µop is 48 bits, field layout IDENTICAL to the AECP
//                encoding so gen tooling carries over:
//
//                  [47:43] op    [42:39] rd   [38:35] ra   [34:31] rb
//                  [30:28] fmt   [27:24] cnd  [23:0]  imm24
//
//                ROM depth is 1024 (UPC_W_C = 10): gPTP µprograms are
//                event handlers, not descriptor walks; half the AECP depth
//                is one RAMB36 less on the reference part.
//
//                The register file is 16 x 64 bits. r15..r13 are preloaded
//                at dispatch with the event descriptor:
//                  r15 = {event_code[7:0], seq_id[15:0], aux[15:0]}
//                  r14 = event timestamp 0 (rx capture / expiry time, ns)
//                  r13 = event timestamp 1 (secondary capture, ns)
//---------------------------------------------------------------------------//
`default_nettype none

package gptp_ucpu_pkg;

  // ---- µop geometry ------------------------------------------------------
  localparam int unsigned UCODE_W_C = 48;
  localparam int unsigned UPC_W_C   = 10;   // 1024 x 48 = 49,152 b = 2 RAMB36

  typedef struct packed {
    logic [4:0]  op;
    logic [3:0]  rd;
    logic [3:0]  ra;
    logic [3:0]  rb;
    logic [2:0]  fmt;
    logic [3:0]  cnd;
    logic [23:0] imm;
  } uop_t;

  // ---- operations: base 29 kept in place, arithmetic added at 29/30 ------
  typedef enum logic [4:0] {
    // Flow
    OP_NOP        = 5'd0,
    OP_BRANCH     = 5'd1,
    OP_BR_STATUS  = 5'd2,
    OP_END        = 5'd3,
    // Data
    OP_MOVE       = 5'd4,
    OP_COMPARE    = 5'd5,
    OP_SET_MASKED = 5'd6,
    // State (engine-side region map: msg bank / ts regs / scratch /
    // publish / phc / timer — see KL_gptp_engine)
    OP_DESC_ADDR  = 5'd7,   // loads the state-port base register: the
                            // announce handler's path-trace walk indexes
                            // the bank hops with it (10.3.10.2.1 c)
    OP_READ_ST    = 5'd8,
    OP_WRITE_ST   = 5'd9,
    OP_NAME_RD    = 5'd10,  // kept; unused (no name region in this plane)
    OP_NAME_WR    = 5'd11,  // kept; unused
    OP_COPY_BUF   = 5'd12,  // kept; unused (PDUs are built field-wise)
    // Checks
    OP_CHECK_LOCK = 5'd13,  // kept; unused (no lock context)
    OP_CHECK_ARG  = 5'd14,
    OP_MAP_VALID  = 5'd15,  // kept; unused
    // Gather (atomic snapshots: live PHC, free-running ms)
    OP_GATHER_EXT = 5'd16,
    OP_READ_CTRS  = 5'd17,  // kept; unused
    // Iterate
    OP_ITER_OPEN  = 5'd18,
    OP_ITER_NEXT  = 5'd19,
    OP_APPEND     = 5'd20,
    // Effects
    OP_COMMIT     = 5'd21,  // publish-bank commit strobe to the wires face
    OP_NVM_MARK   = 5'd22,  // kept; unused
    OP_NOTIFY_ENQ = 5'd23,  // kept; unused
    // Respond (PDU build into the TX slot)
    OP_SET_STATUS = 5'd24,
    OP_SET_LENGTH = 5'd25,
    OP_BUILD_HDR  = 5'd26,  // kept; unused (gPTP has no eid/status header)
    OP_BUILD_FLD  = 5'd27,
    OP_SEND_RESP  = 5'd28,
    // Arithmetic growth — the reason this derivative exists
    OP_ALU        = 5'd29,
    OP_MULDIV     = 5'd30
  } ucpu_op_e;

  // ---- OP_ALU functions (cnd[2:0]) ---------------------------------------
  localparam logic [2:0] ALU_ADD_C = 3'd0;
  localparam logic [2:0] ALU_SUB_C = 3'd1;
  localparam logic [2:0] ALU_AND_C = 3'd2;
  localparam logic [2:0] ALU_OR_C  = 3'd3;
  localparam logic [2:0] ALU_XOR_C = 3'd4;
  localparam logic [2:0] ALU_SHL_C = 3'd5;
  localparam logic [2:0] ALU_SHR_C = 3'd6;   // logical
  localparam logic [2:0] ALU_SAR_C = 3'd7;   // arithmetic

  // ---- OP_MULDIV functions (cnd[0]) --------------------------------------
  localparam logic MD_MULS_C = 1'b0;   // signed 32 x 32 -> 64
  localparam logic MD_DIVU_C = 1'b1;   // unsigned 64 / 32 -> 64 (quotient)

  // ---- fmt codes (operand shaping, as base) ------------------------------
  localparam logic [2:0] FMT_B_C = 3'd0;
  localparam logic [2:0] FMT_W_C = 3'd1;
  localparam logic [2:0] FMT_D_C = 3'd2;
  localparam logic [2:0] FMT_Q_C = 3'd3;

  // ---- COMPARE / CHECK_ARG relations (cnd[2:0]) --------------------------
  localparam logic [3:0] REL_EQ_C = 4'd0;
  localparam logic [3:0] REL_NE_C = 4'd1;
  localparam logic [3:0] REL_LT_C = 4'd2;
  localparam logic [3:0] REL_GE_C = 4'd3;

  // ---- status codes (engine-local, not a wire format) --------------------
  localparam logic [4:0] ST_OK_C       = 5'd0;
  localparam logic [4:0] ST_DROP_C     = 5'd1;   // handler chose to ignore
  localparam logic [4:0] ST_MALFORMED_C = 5'd7;

  // ---- dispatch event codes (r15[39:32]) ---------------------------------
  localparam logic [7:0] EV_RX_SYNC_C     = 8'd1;
  localparam logic [7:0] EV_RX_FOLLOWUP_C = 8'd2;
  localparam logic [7:0] EV_RX_ANNOUNCE_C = 8'd3;
  localparam logic [7:0] EV_RX_PDREQ_C    = 8'd4;
  localparam logic [7:0] EV_RX_PDRESP_C   = 8'd5;
  localparam logic [7:0] EV_RX_PDRFU_C    = 8'd6;
  localparam logic [7:0] EV_RX_SIGNAL_C   = 8'd7;
  localparam logic [7:0] EV_TX_TS_C       = 8'd8;   // egress stamp returned
  localparam logic [7:0] EV_TMR_C         = 8'd16;  // +slot index in aux

  // ---- TX slot geometry --------------------------------------------------
  // Largest 802.1AS-2011 PDU this plane emits is Announce + path trace TLV
  // (8 hops): 14 + 64 + 12 + 64 = capped at 128 bytes of slot.
  localparam int unsigned TXSLOT_BYTES_C = 128;

endpackage : gptp_ucpu_pkg
`default_nettype wire
