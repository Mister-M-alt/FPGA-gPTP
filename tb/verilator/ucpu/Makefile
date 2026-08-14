# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
VERILATOR ?= verilator
RTL_DIR    = ../../../hdl
TOP        = KL_gptp_ucpu
VFLAGS = --cc --exe --build -j 0 \
         --top-module $(TOP) \
         -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
         -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDPARAM \
         -GUCODE_HEX_P='"gptp_ucode.hex"' \
         -CFLAGS "-std=c++17 -O2 -I$(CURDIR)"
SRCS = $(RTL_DIR)/ucpu/gptp_ucpu_pkg.sv $(RTL_DIR)/ucpu/KL_gptp_ucpu.sv
CPP  = sim_main.cpp

run: gptp_ucode.hex
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vucpu_sim
	./obj_dir/Vucpu_sim

gptp_ucode.hex: $(RTL_DIR)/ucode/gen_gptp_ucode.py
	python3 $< -o $@

clean:
	rm -rf obj_dir gptp_ucode.hex
