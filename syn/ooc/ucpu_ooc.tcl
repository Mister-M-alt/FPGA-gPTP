# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
#
# Out-of-context synthesis of KL_gptp_ucpu — the SAME INSTRUMENT as the
# protocol-processor's syn/ooc/ucpu_ooc.tcl (post-synthesis hierarchical
# utilization, ship part, 100 MHz OOC). The delta against that repo's
# measurement of record (1,070 LUT / 491 FF / 3 RAMB36, 2026-08-13) prices
# the arithmetic ISA growth alone, because this module is a pure superset.
set SPEC [file normalize [file dirname [info script]]/../..]
read_verilog -sv $SPEC/hdl/ucpu/gptp_ucpu_pkg.sv $SPEC/hdl/ucpu/KL_gptp_ucpu.sv
synth_design -mode out_of_context -top KL_gptp_ucpu -part xc7a100tfgg484-2 \
    -generic UCODE_HEX_P=gptp_ucode.hex
create_clock -period 10.000 -name clk [get_ports clk_i]
report_utilization -hierarchical -file ucpu_util_hier.rpt
report_utilization -file ucpu_util.rpt
report_timing_summary -delay_type max -max_paths 3 -file ucpu_timing.rpt
