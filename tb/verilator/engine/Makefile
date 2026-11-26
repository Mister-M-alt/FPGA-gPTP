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

.PHONY: all run mutants mutants-jobs-test mutants-order-test clean
.DEFAULT_GOAL := all
all: run passes-test mutants-order-test mutants

# The suite runs FOUR times against the same build. Regression images seed
# the request and Sync counters independently above 16 bits, where an
# unbounded counter aliases into the claim's flags or messageType. Ordinary
# runs need 2,097,152 requests (24.3 days) or 65,536 Syncs (2 h 16 min at
# 8 Hz) to reach those states. $$readmemh resolves its image by RELATIVE name
# at simulation start, so seeded passes run from ignored directories and an
# interrupt can leave no tracked artifact behind. A fourth pass (#82) runs
# only the self-publication phases, from an image whose priority1 is 255.
# That image also states clockAccuracy 0xFE, so the pass proves the #100
# --clock-accuracy build parameter against the 0x22 of the shipping image.
#
# #111: the four passes are independent: each reads its own image from its own
# directory, and none writes anything another reads. Each pass is a target of
# its own, so make runs them within the caller's job budget: one at a time with
# no -j or -j1, all four with -j4, each one job of a parent make's jobserver.
# pass_run.py runs a pass and keeps what it printed and how it ended. `run`'s
# rules then print each pass in the serial order, from its own recipe line,
# under the serial echo lines, and end that line as the serial line ended (its
# exit status, or the signal that killed it), so the transcript and make's own
# messages are the serial run's, under -s, -i and -k too; only the recipe line
# numbers in make's messages differ. The first failing pass in order stops the
# later ones, whose output the serial recipe never printed; -i runs and prints
# all four, as the serial recipe did. An INT, TERM, QUIT or HUP stops every
# pass. On four free job slots the run takes about as long as its longest pass.
# `make passes-test` proves all of this with stub tools in about 90 s.
PASS = python3 pass_run.py $(if $(findstring i,$(firstword -$(MAKEFLAGS))),--ignore-errors)
PASSES = engine-pass0 engine-pass1 engine-pass2 engine-pass3
.PHONY: engine-fresh $(PASSES) passes-test
run:: engine-fresh gptp_ucode.hex
	$(VERILATOR) $(VFLAGS) $(SRCS) $(CPP) -o Vengine_sim
	@mkdir -p obj_dir/engine-passes && touch obj_dir/engine-passes/build.ok
run:: $(PASSES)
	@$(PASS) replay 0 $(if $(findstring s,$(firstword -$(MAKEFLAGS))),,--banner ./obj_dir/Vengine_sim)
run::
	@$(PASS) replay-gen 1
	@$(PASS) replay 1 --banner "-- again, with the request counter seeded above 16 bits --"
run::
	@$(PASS) replay-gen 2
	@$(PASS) replay 2 --banner "-- again, with the Sync counter seeded above 16 bits --"
run::
	@$(PASS) replay-gen 3
	@$(PASS) replay 3 --banner "-- the self publication again, not grandmaster-capable (priority1 255), clockAccuracy 0xFE --"
engine-fresh:
	@rm -rf obj_dir/engine-passes
engine-pass0:
	@$(PASS) run 0 -- ./obj_dir/Vengine_sim
engine-pass1:
	@$(PASS) run 1 --mkdir seedrun --gen 'python3 $(GEN) $(GENARGS) --seq-seed 0x200000 -o seedrun/gptp_ucode.hex' \
	  --shell 'cd seedrun && ../obj_dir/Vengine_sim'
engine-pass2:
	@$(PASS) run 2 --mkdir syncseedrun --gen 'python3 $(GEN) $(GENARGS) --sync-seq-seed 0x10000 -o syncseedrun/gptp_ucode.hex' \
	  --shell 'cd syncseedrun && ../obj_dir/Vengine_sim'
engine-pass3:
	@$(PASS) run 3 --mkdir p1run --gen 'python3 $(GEN) $(GENARGS) --p1 255 --clock-accuracy 0xFE -o p1run/gptp_ucode.hex' \
	  --shell 'cd p1run && ../obj_dir/Vengine_sim +not-gm-capable'

# #111: the serial order, the budget, the fail-fast stop and the signals, all
# against the serial recipe, with stub tools in a scratch copy; about 90 s.
# #113: the test watches real processes on the host's clock, so, like the
# mutation arm's order and jobs tests, it sits in tb/, outside the suite.
passes-test:
	python3 ../../engine_passes_test.py

# Rule 8: prove the checks above are load-bearing. Defects are injected into
# the real engine RTL and the real micro-code generator, one per mutant, and
# each must make the SAME harness fail; the unmutated build must still pass.
# Everything is staged into a temporary directory, so nothing is written into
# the tree. Since #102 several mutants run at once, each in a directory of
# its own, at most 8 and no more than the CPUs make may use; the verdicts
# print in list order. `python3 mutants.py --jobs 1` runs them one by one.
mutants: gptp_ucode.hex
	python3 mutants.py

# #102, #104: neither running mutants at once nor ccache may change what
# mutants.py prints. This test runs it six times, at --jobs 1 and --jobs 8,
# each with ccache off, cold and warm, and compares what every run prints
# byte for byte, every verdict, its order and the tally. Each serial run
# takes as long as the whole arm did before #102 or longer, and the test
# about seven hours on sixteen CPUs, so `all` leaves it out and runs
# mutants-order-test instead.
mutants-jobs-test:
	python3 ../../mutation_jobs_test.py mutants.py

# #104: mutants.py's own main at --jobs 1 and --jobs 8, with its builds and
# harness runs stubbed so that entries finish out of list order; the
# verdicts must still print in list order. It takes seconds.
mutants-order-test:
	python3 ../../mutation_order_test.py mutants.py

gptp_ucode.hex: $(GEN)
	python3 $< $(GENARGS) -o $@

clean:
	rm -rf obj_dir gptp_ucode.hex seedrun syncseedrun p1run
