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

# The suite runs TWICE against the same build. The second run swaps in a
# regression image whose request counter starts above 16 bits, which is
# the one condition that makes an unbounded claim tag observable: the
# counter reaches it after 2,097,152 requests, 24.3 days at this cadence,
# and no ordinary run can get there. $$readmemh resolves its image by
# RELATIVE name at simulation start, so the seeded pass runs with its cwd
# in seedrun/ and never touches the tracked image; an interrupt there can
# leave nothing but an ignored directory behind
run: gptp_ucode.hex
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vengine_sim
	./obj_dir/Vengine_sim
	@mkdir -p seedrun
	@python3 $(GEN) $(GENARGS) --seq-seed 0x200000 -o seedrun/gptp_ucode.hex >/dev/null
	@echo "-- again, with the request counter seeded above 16 bits --"
	@cd seedrun && ../obj_dir/Vengine_sim

gptp_ucode.hex: $(GEN)
	python3 $< $(GENARGS) -o $@

clean:
	rm -rf obj_dir gptp_ucode.hex seedrun
