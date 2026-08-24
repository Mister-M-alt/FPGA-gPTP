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

GEN = $(RTL_DIR)/ucode/gen_gptp_ucode.py
GENARGS = --clk-hz 2000000 --cease-ms 3000

# The suite runs THREE times against the same build. Regression images seed
# the request and Sync counters independently above 16 bits, where an
# unbounded counter aliases into the claim's flags or messageType. Ordinary
# runs need 2,097,152 requests (24.3 days) or 65,536 Syncs (2 h 16 min at
# 8 Hz) to reach those states. $$readmemh resolves its image by RELATIVE name
# at simulation start, so seeded passes run from ignored directories and an
# interrupt can leave no tracked artifact behind.
run: gptp_ucode.hex
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vengine_sim
	./obj_dir/Vengine_sim
	@mkdir -p seedrun
	@python3 $(GEN) $(GENARGS) --seq-seed 0x200000 -o seedrun/gptp_ucode.hex >/dev/null
	@echo "-- again, with the request counter seeded above 16 bits --"
	@cd seedrun && ../obj_dir/Vengine_sim
	@mkdir -p syncseedrun
	@python3 $(GEN) $(GENARGS) --sync-seq-seed 0x10000 -o syncseedrun/gptp_ucode.hex >/dev/null
	@echo "-- again, with the Sync counter seeded above 16 bits --"
	@cd syncseedrun && ../obj_dir/Vengine_sim

gptp_ucode.hex: $(GEN)
	python3 $< $(GENARGS) -o $@

clean:
	rm -rf obj_dir gptp_ucode.hex seedrun syncseedrun
