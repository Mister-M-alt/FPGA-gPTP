# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
VERILATOR ?= verilator
RTL_DIR    = ../../../hdl
TOP        = KL_gptp_rx_parser
VFLAGS = --cc --exe --build -j 0 \
         --top-module $(TOP) \
         -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
         -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDPARAM \
         -CFLAGS "-std=c++17 -O2 -I$(CURDIR) -Wall -Wextra"
SRCS = $(RTL_DIR)/ucpu/gptp_ucpu_pkg.sv $(RTL_DIR)/wire/KL_gptp_rx_parser.sv
CPP  = sim_main.cpp

.PHONY: all run mutants clean
.DEFAULT_GOAL := all
all: run mutants

run:
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vparser_sim
	./obj_dir/Vparser_sim

# Rule 8: prove the rx_err_i and #87/#88 PathTrace checks above are
# load-bearing. Fifteen defects are injected into the real parser RTL, one at
# a time, and each must fail every check it names in the SAME harness; the
# unmutated build must still pass. Mutants are built in a temporary
# directory, so nothing is written into the tree.
mutants:
	python3 mutants.py

clean:
	rm -rf obj_dir
