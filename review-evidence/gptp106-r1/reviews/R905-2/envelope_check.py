"""Recompute the INTEGRATION.md rate-envelope table from the generator's
ppm_addend expression (exact rationals). Usage: python3 envelope_check.py"""
from fractions import Fraction as F
RATE, B, STEP = 200, F(100, 10**6), 100000
fast = (1 + B) / (1 - B) - 1
slow = (1 - B) / (1 + B) - 1
print(f"fast corner {float(fast*10**6):.6f} ppm, slow corner {float(slow*10**6):.6f} ppm")
for clk in (50_000_000, 100_000_000, 125_000_000, 2_000_000):
    add = (RATE * (1 << 24) * 1000 + clk // 2) // clk
    env = F(add * clk, (1 << 24) * 1000)          # ppm
    excess = fast * 10**6 - env                    # ppm
    ns_per_s = excess * 1000                       # 1 ppm = 1000 ns/s
    print(f"{clk/1e6:g} MHz: addend {add}, envelope {float(env):.6f} ppm, "
          f"beyond {float(excess):.6f} ppm, {float(ns_per_s):.3f} ns/s, "
          f"steps every {float(STEP/ns_per_s):.1f} s")
