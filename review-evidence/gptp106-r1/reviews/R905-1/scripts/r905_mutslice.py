#!/usr/bin/env python3
"""Reviewer slice of the engine mutation arm, run in parallel.

Usage: r905_mutslice.py ARM_DIR WORK_DIR JOBS [--probes]

ARM_DIR   tb/verilator/engine of the tree under review (its mutants.py is
          imported unchanged and each control goes through its own
          run_mutant()).
WORK_DIR  a private, existing, empty directory for the staged builds.
JOBS      worker processes.

Selected arm controls: every control of p106_mutants.P106_MUTATIONS and
p107_mutants.P107_MUTATIONS, and the #100 controls whose pattern is the
frequency-change operand TLV_DLT. With --probes, reviewer-planted defects
(defined below, not part of the arm) are run through the same run_mutant();
each names the checks a reviewer expects it to fail, so a probe that
"misses" or "survives" is a finding candidate, not an arm failure.
Prints the positive control and one verdict block per control, in order.
"""
import contextlib
import importlib.util
import io
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ARM = WORK = None
M = None


def load(arm: Path):
    sys.path.insert(0, str(arm))
    spec = importlib.util.spec_from_file_location("arm_mutants",
                                                  arm / "mutants.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def probes(m):
    """Reviewer probes, in the arm's (name, file, pattern, repl, breaks)."""
    gen = "ucode/gen_gptp_ucode.py"
    eng = "top/KL_gptp_engine.sv"
    shl = '    p.emit("ALU", rd=RT, ra=RT, rb=0, cnd=ALU_SHL, imm=32)\n'
    self_tail = ('    p.emit("COMMIT")\n'
                 '    p.emit("BR", label=LB["ANNTX"])\n')
    sync = ('    p.emit("WRST", ra=RT, imm=RG_TMR | 1, fmt=FMT_Q)'
            '  # sync now\n')
    word3 = ('    p.emit("WRST", ra=RT, imm=RG_PHC | 3, fmt=FMT_Q)\n'
             '    # no peer is elected')
    return [
        # the seen flag set by any addend pulse, BECOME's own included
        ("R905 probe: slave rate seen on any addend pulse", eng,
         "      if (tlv_rate_w) slave_rate_seen_r <= 1'b1;\n",
         "      if (phc_addend_we_o) slave_rate_seen_r <= 1'b1;\n",
         "#107 TLV unfollowed: scaledLastGmFreqChange is rate 0 less the"
         " estimate"),
        # BECOME writes rate 0 but no change in the high word
        ("R905 probe: BECOME's high word is zero", gen, shl,
         '    p.emit("MOVE", rd=RT, ra=0, imm=0)\n',
         "#100 TLV settled: scaledLastGmFreqChange is rate 0 less the"
         " estimate | #107 TLV after a grandmaster +10 ppm:"
         " scaledLastGmFreqChange is the change of the time base"),
        # 1616fc8f's deferred first Announce, on a 1 ms beat, not 2 ms
        ("R905 probe: the first master Announce waits 1 ms", gen,
         [(self_tail, '    p.emit("COMMIT")\n    p.emit("END")\n'),
          (sync, sync + '    p.emit("MOVE", rd=RT, ra=0, imm=1)\n'
                        '    p.emit("WRST", ra=RT, imm=RG_TMR | 3,'
                        ' fmt=FMT_Q)\n')],
         None,
         "#106 3.0 s, a clock after the tick: a master Announce on the wire"
         " after the instant | #106 regain race: one master Announce leaves"
         " before the better one is taken"),
        # documented: "The integrator keeps the slave's estimate through
        # the mastership". Probe: BECOME clears it
        ("R905 probe: BECOME clears the integrator", gen, word3,
         '    p.emit("WRST", ra=RT, imm=RG_PHC | 3, fmt=FMT_Q)\n'
         '    p.emit("WRST", ra=0, imm=RG_SCR | S_INTG, fmt=FMT_Q)\n'
         '    # no peer is elected',
         "#107 "),
    ]


def init(arm, work):
    global ARM, WORK, M
    ARM, WORK = Path(arm), Path(work)
    M = load(ARM)


def one(args):
    idx, mutation, clean_exe = args
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            ok = M.run_mutant(WORK, Path(clean_exe), mutation)
        except Exception as exc:  # report, never hide
            print(f"[FAIL] {mutation[0]!r} raised {exc!r}")
            ok = False
    return idx, mutation[0], ok, buf.getvalue()


def main() -> int:
    arm, work, jobs = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), \
        int(sys.argv[3])
    m = load(arm)
    import p100_mutants  # noqa: E402  (from ARM_DIR)
    import p106_mutants  # noqa: E402
    import p107_mutants  # noqa: E402
    sel = [*p106_mutants.P106_MUTATIONS, *p107_mutants.P107_MUTATIONS,
           *[mu for mu in p100_mutants.P100_MUTATIONS
             if mu[2] == p100_mutants.TLV_DLT]]
    names = {mu[0] for mu in m.MUTATIONS}
    for mu in sel:
        assert mu[0] in names, f"{mu[0]} is not in the arm's MUTATIONS"
    if "--probes" in sys.argv:
        sel += probes(m)
    clean_src = m.stage(work, "clean")
    clean_exe = m.build(clean_src, work, "clean")
    if clean_exe is None:
        print("[FAIL] the unmutated sources did not build")
        return 1
    clean_run = work / "run_clean"
    assert m.generate_image(clean_src, clean_run)
    print(f"selected {len(sel)} controls of {len(m.MUTATIONS)} arm"
          f" controls (+probes)" if "--probes" in sys.argv else
          f"selected {len(sel)} controls", flush=True)
    jobs_list = [(i, mu, str(clean_exe)) for i, mu in enumerate(sel)]
    with ProcessPoolExecutor(max_workers=jobs, initializer=init,
                             initargs=(str(arm), str(work))) as ex:
        ctrl = ex.submit(lambda_ctrl, str(clean_exe), str(clean_run))
        results = list(ex.map(one, jobs_list))
        answer = ctrl.result()
    print(f"[{'PASS' if answer == 'pass' else 'FAIL'}] positive control: "
          f"{answer}")
    fails = answer != "pass"
    for idx, name, ok, text in sorted(results):
        print(f"-- control {idx}: {name}: {'CAUGHT' if ok else 'NOT CAUGHT'}")
        print(text.rstrip())
        fails += not ok
    print(f"SLICE {len(results)} controls: {len(results) - sum(not r[2] for r in results)}"
          f" caught, {sum(not r[2] for r in results)} not caught;"
          f" positive control {answer}")
    return 1 if fails else 0


def lambda_ctrl(clean_exe, clean_run):
    return M.verdict(*M.run_harness(Path(clean_exe), Path(clean_run)))


if __name__ == "__main__":
    sys.exit(main())
