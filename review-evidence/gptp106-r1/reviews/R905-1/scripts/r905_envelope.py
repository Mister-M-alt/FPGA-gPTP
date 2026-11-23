#!/usr/bin/env python3
"""The follow envelope against 802.1AS-2020 B.1.1's corner.

Usage: r905_envelope.py GENERATOR

GENERATOR is hdl/ucode/gen_gptp_ucode.py of the tree under review; its
RATE_PPM_C, LOCAL_CLOCK_PPM_C and ppm_addend() are read from it unchanged.
Prints, for the clocks the repository builds (100 MHz default, the suites'
2 MHz) and 125 MHz, the trim envelope in ppm as the integer addend clamp
realises it, and the largest frequency ratio between two LocalClocks each
within LOCAL_CLOCK_PPM_C of TAI.
"""
import importlib.util
import sys
from fractions import Fraction

spec = importlib.util.spec_from_file_location("gen", sys.argv[1])
gen = importlib.util.module_from_spec(spec)
sys.argv = sys.argv[:1]
spec.loader.exec_module(gen)

lc = Fraction(gen.LOCAL_CLOCK_PPM_C, 10**6)
corner = (1 + lc) / (1 - lc) - 1
print(f"RATE_PPM_C = {gen.RATE_PPM_C}, LOCAL_CLOCK_PPM_C = "
      f"{gen.LOCAL_CLOCK_PPM_C}")
print(f"B.1.1 corner: (1 + {gen.LOCAL_CLOCK_PPM_C} ppm) / (1 - "
      f"{gen.LOCAL_CLOCK_PPM_C} ppm) - 1 = {float(corner) * 1e6:.6f} ppm")
for clk in (100_000_000, 125_000_000, 2_000_000):
    ilim = gen.ppm_addend(gen.RATE_PPM_C, clk)
    env = Fraction(ilim, 1 << 24) / Fraction(10**9, clk)
    short = corner - env
    print(f"clk {clk} Hz: ilim {ilim} units = {float(env) * 1e6:.6f} ppm;"
          f" corner exceeds it by {float(short) * 1e6:+.6f} ppm"
          f" ({float(short) * 1e9:+.3f} ns/s of offset growth)")
    if short > 0:
        lock = gen.STEP_LOCKED_NS_C
        print(f"  offset reaches STEP_LOCKED_NS_C ({lock} ns) after"
              f" {float(lock / (short * 10**9)):.0f} s, then steps again")
