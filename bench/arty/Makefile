# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0

.PHONY: test lint clean

VERILATOR ?= verilator
TOP        = bench_mii_tx
RTL_DIR    = ../../hdl
VFLAGS     = --cc --exe --build -j 0 --top-module $(TOP) \
             -Wall -Wno-fatal -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
             -Wno-UNUSEDPARAM -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC
LINTFLAGS  = --lint-only -Wall -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL \
             -Wno-UNUSEDPARAM -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC \
             -Wno-PINCONNECTEMPTY --top-module bench_arty_top
RTL_SRCS   = $(RTL_DIR)/ucpu/gptp_ucpu_pkg.sv \
             $(RTL_DIR)/ucpu/KL_gptp_ucpu.sv \
             $(RTL_DIR)/wire/KL_gptp_rx_parser.sv \
             $(RTL_DIR)/wire/KL_gptp_tx_slot.sv \
             $(RTL_DIR)/common/KL_gptp_timer.sv \
             $(RTL_DIR)/top/KL_gptp_engine.sv bench_afifo.sv \
             bench_mii_rx.sv bench_mii_tx.sv bench_phc.sv \
             bench_uart_report.sv bench_arty_top.sv

test:
	$(VERILATOR) $(VFLAGS) bench_mii_tx.sv bench_mii_tx_tag_test.cpp \
	  -o Vbench_mii_tx_tag_test
	./obj_dir/Vbench_mii_tx_tag_test

lint:
	$(VERILATOR) $(LINTFLAGS) $(RTL_SRCS)

clean:
	rm -rf obj_dir
