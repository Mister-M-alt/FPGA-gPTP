#!/usr/bin/env python3
"""Reviewer driver: run a chosen subset of the engine mutation arm.

Usage: run_p109_arm.py ENGINE_DIR MODE [--jobs N]

ENGINE_DIR is tb/verilator/engine of a disposable copy of the reviewed tree.
MODE is one of
  p109      the eight #109 controls of p109_mutants.py, as published
  probes    reviewer-written extra controls (below), not part of the PR
  width     reviewer width probes for the new phase-64 trial (round 2)
  all       the full arm as published (every entry of mutants.MUTATIONS)
  slice:A:B entries A..B-1 of the full arm (0-based, list order)
  idx:I,J,. the listed entries of the full arm (0-based, list order)

The arm's own main() is used unchanged: it builds the unmutated control
first, then plants each mutant in its own temporary directory, so nothing
is written into ENGINE_DIR's tree. Verilator is whatever `verilator` is on
PATH (the reviewer puts the pinned 5.050 wrapper first).
"""
import sys
from pathlib import Path


def reviewer_probes(p109):
    """Extra controls written by the reviewer; each names the checks it
    must fail, with the arm's own every-named-check rule (#109 prefix)."""
    floor = p109.FLOOR
    used = p109.USED
    pub = p109.PUB
    verdict = p109.VERDICT
    gen = p109.GENERATOR
    exact = p109.EXACT
    return [
        # the floor one beyond the ruling, at -801
        ("R1 the floor is -801 ns", gen, floor,
         floor.replace("imm=NPD_HI_C)", "imm=NPD_HI_C + 1)"),
         f"#109 D -801: {exact} | #109 D -801: the engine publishes the"
         " used delay"),
        # the engine clamps only its publication to 0; the Sync path keeps
        # the signed floored value (the ruling says the publication stays
        # signed in the engine)
        ("R2 the engine publishes a negative delay as 0", gen, pub,
         "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=0, cnd=ALU_SAR, imm=63)\n"
         "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=RT, cnd=ALU_AND)\n"
         "    p.emit(\"ALU\", rd=RT, ra=RD_, rb=RT, cnd=ALU_SUB)\n"
         "    p.emit(\"WRST\", ra=RT, imm=RG_PUB | 3, fmt=FMT_Q)\n",
         "#109 D -3: the engine publishes the used delay"
         " | #109 D -263: the engine publishes the used delay"),
        # the floor's mask by a logical shift: 0 or 1, so no floor
        ("R3 the floor mask uses a logical shift", gen,
         "    p.emit(\"ALU\", rd=RU, ra=RT, rb=0, cnd=ALU_SAR, imm=63)\n",
         "    p.emit(\"ALU\", rd=RU, ra=RT, rb=0, cnd=ALU_SHR, imm=63)\n",
         f"#109 D -801: {exact} | #109 D -5000000: no PHC step"),
        # the Sync path is written before the floor, the publication after
        ("R4 only the publication is floored", gen, floor + used + pub,
         used + floor + pub,
         f"#109 D -801: {exact} | #109 D -5000000: no PHC step"),
        # the verdict reads bit 31 rather than bit 63 of D - 801: a strength
        # probe for huge positive delays (expected to SURVIVE if no trial
        # computes a positive delay at or above 2^31 ns)
        ("R5 the verdict reads bit 31", gen, verdict,
         verdict.replace("cnd=ALU_SHR, imm=63)", "cnd=ALU_SHR, imm=31)"),
         "probe: a huge positive delay is bad"),
    ]


def width_probes(p109):
    """Round 2: how narrow a verdict the phase-64 trial kills. The trial's
    D is about 2.147e18 ns, between 2^60 and 2^61, so a verdict reading
    D - 801 from bit 60 or below judges it good (must be caught), and one
    reading bit 61 or 62 is equivalent to bit 63 on every delay the wire
    can produce (|D| < 2^61; expected to SURVIVE)."""
    verdict = p109.VERDICT
    gen = p109.GENERATOR
    names = ("#109 the most positive delay of the wire: asCapable falls"
             " | #109 the most positive delay of the wire: the next"
             " Follow_Up is not used")
    return [
        ("W60 the verdict reads D - 801 from bit 60", gen, verdict,
         verdict.replace("cnd=ALU_SHR, imm=63)", "cnd=ALU_SHR, imm=60)"),
         names),
        ("W61 the verdict reads D - 801 from bit 61", gen, verdict,
         verdict.replace("cnd=ALU_SHR, imm=63)", "cnd=ALU_SHR, imm=61)"),
         names),
    ]


def main() -> int:
    engine = Path(sys.argv[1]).resolve()
    mode = sys.argv[2]
    rest = sys.argv[3:]
    sys.path.insert(0, str(engine))
    import mutants  # noqa: E402  (the arm under review)
    import p109_mutants  # noqa: E402
    full = list(mutants.MUTATIONS)
    print(f"INFO full arm entries: {len(full)}; #109 entries: "
          f"{len(p109_mutants.P109_MUTATIONS)}")
    if mode == "p109":
        sel = list(p109_mutants.P109_MUTATIONS)
    elif mode == "probes":
        sel = reviewer_probes(p109_mutants)
    elif mode == "width":
        sel = width_probes(p109_mutants)
    elif mode == "all":
        sel = full
    elif mode.startswith("idx:"):
        sel = [full[int(i)] for i in mode[4:].split(",")]
    elif mode.startswith("slice:"):
        _, a, b = mode.split(":")
        sel = full[int(a):int(b)]
    else:
        raise SystemExit(f"unknown mode {mode}")
    print(f"INFO running {len(sel)} entries")
    for m in sel:
        print(f"INFO entry: {m[0]}")
    mutants.MUTATIONS = sel
    sys.stdout.flush()
    return mutants.main(rest)


if __name__ == "__main__":
    sys.exit(main())
