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
         -CFLAGS "-std=c++17 -O2 -I$(CURDIR) -Wall -Wextra"
SRCS = $(RTL_DIR)/ucpu/gptp_ucpu_pkg.sv $(RTL_DIR)/ucpu/KL_gptp_ucpu.sv \
       $(RTL_DIR)/wire/KL_gptp_rx_parser.sv $(RTL_DIR)/wire/KL_gptp_tx_slot.sv \
       $(RTL_DIR)/common/KL_gptp_timer.sv $(RTL_DIR)/top/KL_gptp_engine.sv
CPP  = sim_main.cpp

GEN = $(RTL_DIR)/ucode/gen_gptp_ucode.py
GENARGS = --clk-hz 2000000 --cease-ms 3000

# #104: Verilator's C++ compiles through ccache when ccache is on PATH, so
# a translation unit compiled before is not compiled again: the runtime and
# the harness are the same in every build, and a model is the same in every
# run. OBJCACHE is verilated.mk's own variable; `make OBJCACHE=` builds
# without a cache. CCACHE_NOHASHDIR keeps the build directory out of the
# cache key. mutants.py sets both the same way, and builds in temporary
# directories from relative source names. The suite builds in the tree, so
# CCACHE_BASEDIR names this checkout's paths relative to it, and a new
# checkout still hits. The cache lives where ccache keeps it (CCACHE_DIR,
# or ~/.cache/ccache), never in the tree. A setting of the caller's own wins.
OBJCACHE ?= $(if $(shell command -v ccache),ccache)
CCACHE_NOHASHDIR ?= 1
export OBJCACHE CCACHE_NOHASHDIR
run: export CCACHE_BASEDIR ?= $(abspath ../../..)

.PHONY: all run mutants mutants-jobs-test clean
.DEFAULT_GOAL := all
all: run mutants

# The suite runs THREE times against the same build. Regression images seed
# the request and Sync counters independently above 16 bits, where an
# unbounded counter aliases into the claim's flags or messageType. Ordinary
# runs need 2,097,152 requests (24.3 days) or 65,536 Syncs (2 h 16 min at
# 8 Hz) to reach those states. $$readmemh resolves its image by RELATIVE name
# at simulation start, so seeded passes run from ignored directories and an
# interrupt can leave no tracked artifact behind. A fourth pass (#82) runs
# only the self-publication phases, from an image whose priority1 is 255.
# That image also states clockAccuracy 0xFE, so the pass proves the #100
# --clock-accuracy build parameter against the 0x22 of the shipping image.
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
	@mkdir -p p1run
	@python3 $(GEN) $(GENARGS) --p1 255 --clock-accuracy 0xFE -o p1run/gptp_ucode.hex >/dev/null
	@echo "-- the self publication again, not grandmaster-capable (priority1 255), clockAccuracy 0xFE --"
	@cd p1run && ../obj_dir/Vengine_sim +not-gm-capable

# Rule 8: prove the checks above are load-bearing. Defects are injected into
# the real engine RTL and the real micro-code generator, one per mutant, and
# each must make the SAME harness fail; the unmutated build must still pass.
# Everything is staged into a temporary directory, so nothing is written into
# the tree. Since #102 several mutants run at once, each in a directory of
# its own, at most 8 and no more than the CPUs make may use; the verdicts
# print in list order. `python3 mutants.py --jobs 1` runs them one by one.
mutants: gptp_ucode.hex
	python3 mutants.py

# #102: mutants.py runs its mutants concurrently, --jobs of them at once.
# This test runs it with --jobs 1 and with --jobs 4 and compares what the
# two print byte for byte, every verdict, its order and the tally. The
# serial run takes as long as the whole arm did before #102, so `all`
# leaves the test out.
mutants-jobs-test:
	python3 ../../mutation_jobs_test.py mutants.py

gptp_ucode.hex: $(GEN)
	python3 $< $(GENARGS) -o $@

clean:
	rm -rf obj_dir gptp_ucode.hex seedrun syncseedrun p1run
