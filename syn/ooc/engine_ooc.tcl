# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
#
# Out-of-context synthesis of the whole gPTP engine — parser, µCPU, TX
# slot, timer, region map. Same instrument as every anchor in the
# protocol-processor resource record: post-synthesis hierarchical
# utilization, xc7a100t-2, 100 MHz OOC. This number is the measured
# replacement for the "+1,500…+2,500 LUT gPTP engine" ESTIMATE in the
# 2026-08-14 no-DDR3 resource study.
set SPEC [file normalize [file dirname [info script]]/../..]
read_verilog -sv \
    $SPEC/hdl/ucpu/gptp_ucpu_pkg.sv \
    $SPEC/hdl/ucpu/KL_gptp_ucpu.sv \
    $SPEC/hdl/wire/KL_gptp_rx_parser.sv \
    $SPEC/hdl/wire/KL_gptp_tx_slot.sv \
    $SPEC/hdl/common/KL_gptp_timer.sv \
    $SPEC/hdl/top/KL_gptp_engine.sv
synth_design -mode out_of_context -top KL_gptp_engine -part xc7a100tfgg484-2 \
    -generic UCODE_HEX_P=gptp_ucode.hex
create_clock -period 10.000 -name clk [get_ports clk_i]
report_utilization -hierarchical -file engine_util_hier.rpt
report_utilization -file engine_util.rpt
report_timing_summary -delay_type max -max_paths 3 -file engine_timing.rpt
