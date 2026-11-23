"""envelope.py GENERATOR: the trim envelope as the generator's integer clamp realises it, per clock, against the two
corners of IEEE 802.1AS-2020 B.1.1 (each LocalClock within +-LOCAL_CLOCK_PPM_C of TAI). The trim a LocalClock at
-a needs to follow a grandmaster at +b is (1 + b) / (1 - a) - 1; the corners are a = b = 100 ppm (the grandmaster
fast) and a = b = -100 ppm (the grandmaster slow). Reads RATE_PPM_C, LOCAL_CLOCK_PPM_C, STEP_LOCKED_NS_C and
ppm_addend() from GENERATOR unchanged."""
import importlib.util
import sys
from fractions import Fraction

spec = importlib.util.spec_from_file_location("gen", sys.argv[1])
gen = importlib.util.module_from_spec(spec)
sys.argv = sys.argv[:1]
spec.loader.exec_module(gen)
lc = Fraction(gen.LOCAL_CLOCK_PPM_C, 10**6)
fast, slow = (1 + lc) / (1 - lc) - 1, (1 - lc) / (1 + lc) - 1
ppm = lambda x: float(x) * 1e6  # noqa: E731
print(f"RATE_PPM_C {gen.RATE_PPM_C}, LOCAL_CLOCK_PPM_C {gen.LOCAL_CLOCK_PPM_C}, STEP_LOCKED_NS_C {gen.STEP_LOCKED_NS_C}")
print(f"corner, grandmaster 100 ppm fast of a LocalClock 100 ppm slow: (1 + 100 ppm) / (1 - 100 ppm) - 1 = {ppm(fast):+.6f} ppm")
print(f"corner, grandmaster 100 ppm slow of a LocalClock 100 ppm fast: (1 - 100 ppm) / (1 + 100 ppm) - 1 = {ppm(slow):+.6f} ppm")
for clk, what in ((50_000_000, "the parent's images, milan_clk_hz"), (100_000_000, "the generator's default"),
                  (125_000_000, ""), (2_000_000, "the engine suite's")):
    ilim = gen.ppm_addend(gen.RATE_PPM_C, clk)
    env = Fraction(ilim, 1 << 24) / Fraction(10**9, clk)
    short = fast - env
    print(f"clk {clk} Hz{' (' + what + ')' if what else ''}: ilim {ilim} units = +-{ppm(env):.6f} ppm")
    print(f"  fast corner beyond it by {ppm(short):.6f} ppm: the offset grows {float(short) * 1e9:.3f} ns/s and reaches "
          f"STEP_LOCKED_NS_C after {float(Fraction(gen.STEP_LOCKED_NS_C) / (short * 10**9)):.0f} s, then steps again")
    print(f"  slow corner inside it, leaving {ppm(env + slow):.6f} ppm for phase")
