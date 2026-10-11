# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
#
# Out-of-context synthesis of KL_gptp_ucpu (post-synthesis hierarchical
# utilization, ship part, 100 MHz OOC). Until #70 this was the SAME
# INSTRUMENT as the protocol-processor's syn/ooc/ucpu_ooc.tcl: the delta
# against that repo's measurement of record (1,070 LUT / 491 FF / 3 RAMB36,
# 2026-08-13) priced the arithmetic ISA growth alone, because this module
# is a pure superset, and every figure it produced came from an
# unconstrained synthesis: create_clock ran after synth_design. The clock
# now comes from ooc_clock.xdc, read before synth_design, so a delta
# against that record needs a run in the old order.
set SPEC [file normalize [file dirname [info script]]/../..]
read_xdc $SPEC/syn/ooc/ooc_clock.xdc
read_verilog -sv $SPEC/hdl/ucpu/gptp_ucpu_pkg.sv $SPEC/hdl/ucpu/KL_gptp_ucpu.sv
synth_design -mode out_of_context -top KL_gptp_ucpu -part xc7a100tfgg484-2 \
    -generic UCODE_HEX_P=gptp_ucode.hex
report_utilization -hierarchical -file ucpu_util_hier.rpt
report_utilization -file ucpu_util.rpt
report_timing_summary -delay_type max -max_paths 3 -file ucpu_timing.rpt
# The timing summary's Clock Summary has no source column; this names the
# port clk is bound to, which check_ooc_clock.py requires to be clk_i.
report_clocks -append -file ucpu_timing.rpt
