# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
VERILATOR ?= verilator
RTL_DIR    = ../../../hdl
TOP        = KL_gptp_rx_parser
VFLAGS = --cc --exe --build -j 0 \
         --top-module $(TOP) \
         -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
         -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDPARAM \
         -CFLAGS "-std=c++17 -O2 -I$(CURDIR)"
SRCS = $(RTL_DIR)/ucpu/gptp_ucpu_pkg.sv $(RTL_DIR)/wire/KL_gptp_rx_parser.sv
CPP  = sim_main.cpp

run:
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vparser_sim
	./obj_dir/Vparser_sim

clean:
	rm -rf obj_dir
