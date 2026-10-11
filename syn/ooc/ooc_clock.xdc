# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
#
# The one clock of both OOC measurements. engine_ooc.tcl and ucpu_ooc.tcl
# read this file before synth_design, so synthesis optimizes against the
# 10 ns target and the reported slack is a constrained result (#70).
# check_ooc_clock.py holds that order; keep the clock here, not in the
# scripts.
create_clock -period 10.000 -name clk [get_ports clk_i]
