# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
VERILATOR ?= verilator
RTL_DIR    = ../../../hdl
TOP        = KL_gptp_engine
VFLAGS = --cc --exe --build -j 0 \
         --top-module $(TOP) \
         -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
         -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDPARAM \
         -GUCODE_HEX_P='"gptp_ucode.hex"' -GCLK_HZ_P=2000000 \
         -CFLAGS "-std=c++17 -O2 -I$(CURDIR)"
SRCS = $(RTL_DIR)/ucpu/gptp_ucpu_pkg.sv $(RTL_DIR)/ucpu/KL_gptp_ucpu.sv \
       $(RTL_DIR)/wire/KL_gptp_rx_parser.sv $(RTL_DIR)/wire/KL_gptp_tx_slot.sv \
       $(RTL_DIR)/common/KL_gptp_timer.sv $(RTL_DIR)/top/KL_gptp_engine.sv
CPP  = sim_main.cpp

run: gptp_ucode.hex
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vengine_sim
	./obj_dir/Vengine_sim

gptp_ucode.hex: $(RTL_DIR)/ucode/gen_gptp_ucode.py
	python3 $< --clk-hz 2000000 --cease-ms 3000 -o $@

clean:
	rm -rf obj_dir gptp_ucode.hex
