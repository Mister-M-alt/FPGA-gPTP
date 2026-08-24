# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0

.PHONY: all tb lint ooc clean

all: tb lint

tb:
	$(MAKE) -C tb/verilator/ucpu
	$(MAKE) -C tb/verilator/parser
	$(MAKE) -C tb/verilator/engine
	$(MAKE) -C bench/arty test

lint:
	verilator --lint-only -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
	  -Wno-UNUSEDPARAM -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
	  --top-module KL_gptp_engine \
	  hdl/ucpu/gptp_ucpu_pkg.sv hdl/ucpu/KL_gptp_ucpu.sv \
	  hdl/wire/KL_gptp_rx_parser.sv hdl/wire/KL_gptp_tx_slot.sv \
	  hdl/common/KL_gptp_timer.sv hdl/top/KL_gptp_engine.sv
	$(MAKE) -C bench/arty lint

ooc:
	syn/ooc/run.sh

clean:
	$(MAKE) -C tb/verilator/ucpu clean
	$(MAKE) -C tb/verilator/parser clean
	$(MAKE) -C tb/verilator/engine clean
	$(MAKE) -C bench/arty clean
	rm -rf syn/ooc/work
