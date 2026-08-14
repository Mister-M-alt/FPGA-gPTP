# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
# FPGA-gPTP Arty A7-100T first-light bench — non-project batch build.
set HERE [file normalize [file dirname [info script]]]
set SPEC [file normalize $HERE/../..]

read_verilog -sv [list \
  $SPEC/hdl/ucpu/gptp_ucpu_pkg.sv \
  $SPEC/hdl/ucpu/KL_gptp_ucpu.sv \
  $SPEC/hdl/wire/KL_gptp_rx_parser.sv \
  $SPEC/hdl/wire/KL_gptp_tx_slot.sv \
  $SPEC/hdl/common/KL_gptp_timer.sv \
  $SPEC/hdl/top/KL_gptp_engine.sv \
  $HERE/bench_afifo.sv \
  $HERE/bench_mii_rx.sv \
  $HERE/bench_mii_tx.sv \
  $HERE/bench_phc.sv \
  $HERE/bench_uart_report.sv \
  $HERE/bench_arty_top.sv ]
read_xdc $HERE/arty.xdc

synth_design -top bench_arty_top -part xc7a100tcsg324-1
opt_design
place_design
route_design
report_utilization -file bench_util.rpt
report_timing_summary -delay_type max -max_paths 5 -file bench_timing.rpt
write_bitstream -force bench_arty.bit
