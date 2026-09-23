#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Mutation arm for the engine suite: prove its checks are load-bearing.

Why this exists. `sim_main.cpp` grades the whole plane through its wire and
publish faces, and the arms that repair FPGA-gPTP #31 - the accepted-beat
result face, the message-scoped lost arm, the retained Pdelay pairing
context and the three admission gates - are exactly the kind of behaviour a
harness can appear to check without checking. A suite whose assertions never
fail is indistinguishable from a suite that asserts nothing, and the defect
this round repairs was invisible to a green suite for that reason.

So the real engine RTL and the real micro-code generator are mutated, one
defect at a time, and the SAME harness is run against each mutant. Every
mutant must make it FAIL. The unmutated build must still PASS, without which
the arm would be satisfied by a harness that fails on everything.

"Caught" means the harness's own tally says so; see tb/mutation_verdict.py
for why a non-zero exit alone is not a catch. Everything is staged into a
temporary directory, so nothing is written into the tree.

Cost note, recorded rather than hidden: micro-code mutants reuse one build of
the unmutated RTL, because a generator change moves only the ROM image the
simulation reads at start-up. RTL mutants are built individually.

What this arm deliberately does NOT list, recorded rather than hidden,
because the value of a mutation arm is also the map of what it cannot reach.
Removing the reset-backed read gate on the pending-pair cell alone survives
every check, and that survival is a property of the design rather than a gap
in the harness: the cell is read in only two places, and a new Pdelay_Req
clears it at its commit point before any post-reset timestamp result can
match a claim. The gate is kept because it is the second half of a stated
rule that pairs it with the t1 validity beside it, whose own removal IS
caught below; it is defence in depth with no reachable arm, not a checked
behaviour. Closing that would need a reachable state, not another mutant.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
HDL = (HERE / "../../../hdl").resolve()
sys.path.insert(0, str((HERE / "../../").resolve()))

from mutation_verdict import verdict  # noqa: E402

#: the RTL the suite builds, in the order the Makefile lists it
RTL_SOURCES = (
    "ucpu/gptp_ucpu_pkg.sv",
    "ucpu/KL_gptp_ucpu.sv",
    "wire/KL_gptp_rx_parser.sv",
    "wire/KL_gptp_tx_slot.sv",
    "common/KL_gptp_timer.sv",
    "top/KL_gptp_engine.sv",
)
GENERATOR = "ucode/gen_gptp_ucode.py"
#: the shipping arguments of this suite's image, as tb/verilator/engine/Makefile
GENARGS = ("--clk-hz", "2000000", "--cease-ms", "3000")

VFLAGS = [
    "--cc", "--exe", "--build", "-j", "4", "--top-module", "KL_gptp_engine",
    "-Wall", "-Wno-fatal", "-Wno-DECLFILENAME", "-Wno-UNUSEDSIGNAL",
    "-Wno-WIDTHEXPAND", "-Wno-WIDTHTRUNC", "-Wno-UNUSEDPARAM",
    "-GUCODE_HEX_P=\"gptp_ucode.hex\"", "-GCLK_HZ_P=2000000",
]

#: (name, file under hdl/, pattern, replacement, the property it should break)
MUTATIONS = [
    # ---- the result face: acceptance, and what acceptance protects -------
    ("result face always ready", "top/KL_gptp_engine.sv",
     "assign txts_ready_o  = !txts_pend_r && rst_n;",
     "assign txts_ready_o  = 1'b1;",
     "a result already owed to the micro-code cannot be replaced by a "
     "later one"),
    ("result value taken without an accepted beat", "top/KL_gptp_engine.sv",
     "if (txts_accept_w)          txts_r <= txts_ns_i;",
     "if (txts_valid_i)          txts_r <= txts_ns_i;",
     "the accepted result keeps its own timestamp until its dispatch"),
    ("result tag taken without an accepted beat", "top/KL_gptp_engine.sv",
     "if (txts_accept_w) begin",
     "if (txts_valid_i) begin",
     "the accepted result keeps its own tag and outcome until its dispatch"),
    # ---- reset-backed validity of the pairing cells ----------------------
    ("recorded t1 survives reset", "top/KL_gptp_engine.sv",
     "        else if ((st_addr_w[5:0] == 6'd37) && !t1v_valid_r)\n"
     "          st_rd_mux_w = 64'd0;\n",
     "",
     "a t1 measured before a reset cannot pair with a later Follow_Up"),
    # ---- the byte face, which decides how many frames were sent ----------
    ("byte face advances without ready", "wire/KL_gptp_tx_slot.sv",
     "      end else if (tx_ready_i) begin",
     "      end else begin",
     "a stalled byte, including the final one, waits for an accepted "
     "transfer"),
    # ---- the lost arm, and its scope -------------------------------------
    ("lost t1 fabricates a time and a companion", GENERATOR,
     "    p.label(\"t1\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n",
     "    p.label(\"t1\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"BR\", label=LB[\"TXT1OK\"])\n",
     "a lost result writes no time and completes no exchange"),
    ("lost Sync cancels the requester exchange", GENERATOR,
     "    p.label(\"sync\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"END\")                      # no SYNCFU: there is no "
     "origin time\n",
     "    p.label(\"sync\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n",
     "a lost Sync result retires the Sync claim and nothing else"),
    ("lost response cancels the requester exchange", GENERATOR,
     "    p.label(\"resp\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_RESP, fmt=FMT_Q)\n"
     "    p.emit(\"END\")                      # no RFU: there is no t3 to "
     "carry\n",
     "    p.label(\"resp\")\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_TXQ_RESP, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n",
     "a lost Pdelay_Resp result retires the response claim and nothing "
     "else"),
    # ---- the retained pairing context -------------------------------------
    ("a later response re-arms the frozen pair", GENERATOR,
     "    p.emit(\"RDST\", rd=RU, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"CMP\", ra=RU, rb=0, fmt=FMT_D, imm=0)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"arm_go\")\n"
     "    p.emit(\"BR\", label=\"multi\")                                   "
     "# frozen\n"
     "    p.label(\"arm_go\")\n",
     "    p.label(\"arm_go\")\n",
     "a complete pair keeps its own identity and operands until its t1"),
    ("the tail runs before its own t1", GENERATOR,
     "    p.emit(\"RDST\", rd=RT, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=1)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"t1_here\")\n"
     "    p.emit(\"WRST\", ra=RC, imm=RG_SCR | S_T3, fmt=FMT_Q)\n"
     "    p.emit(\"MOVE\", rd=RT, ra=0, imm=1)\n"
     "    p.emit(\"WRST\", ra=RT, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"END\")\n"
     "    p.label(\"t1_here\")\n",
     "    p.label(\"t1_here\")\n",
     "a delay is computed from this exchange's own t1, never a "
     "predecessor's"),
    ("a new request leaves the old pair live", GENERATOR,
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_T1V, fmt=FMT_Q)\n"
     "    p.emit(\"WRST\", ra=0, imm=RG_SCR | S_PDWAIT, fmt=FMT_Q)\n"
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)\n",
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_MYSEQ, fmt=FMT_Q)\n",
     "a superseded exchange cannot pair with the new request's t1"),
    # ---- the three admission gates, one arm each --------------------------
    ("credit gate removed from the Pdelay_Req leg", GENERATOR,
     "    e_credit_gate(p, \"beat_off\")\n",
     "",
     "a Pdelay_Req beat is postponed while the transmit path has no "
     "credit"),
    ("credit gate removed from the Sync leg", GENERATOR,
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    e_credit_gate(p, \"skip\")\n"
     "    p.emit(\"RDST\", rd=RB, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n",
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    p.emit(\"RDST\", rd=RB, imm=RG_SCR | S_TXQ_TMR, fmt=FMT_Q)\n",
     "a Sync beat is postponed while the transmit path has no credit"),
    ("credit gate removed from the Announce leg", GENERATOR,
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    e_credit_gate(p, \"skip\")\n"
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_ASEQ, fmt=FMT_Q)\n",
     "    e_flag_gate(p, FL_ASCAP_C, FL_ASCAP_C, \"ac\", \"skip\")\n"
     "    p.emit(\"RDST\", rd=RA, imm=RG_SCR | S_ASEQ, fmt=FMT_Q)\n",
     "an Announce beat is postponed while the transmit path has no credit"),
    # ---- the #68 step-versus-slew policy, one arm per rule -----------------
    ("a synchronized servo may step", GENERATOR,
     "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=0)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"sv_first\")\n",
     "    p.emit(\"BR\", label=\"sv_first\")\n",
     "only a first synchronization may step"),
    ("the first-synchronization test inverted", GENERATOR,
     "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=0)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"sv_first\")\n",
     "    p.emit(\"CMP\", ra=RT, rb=0, fmt=FMT_D, imm=FL_SYNCOK_C)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"sv_first\")\n",
     "a first synchronization over one second steps"),
    ("every first synchronization steps", GENERATOR,
     "    p.emit(\"MD\", rd=RU, ra=RT, rb=RB, cnd=MD_DIVU)\n"
     "    p.emit(\"CMP\", ra=RU, rb=0, fmt=FMT_Q, imm=0)\n"
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"sv_slew\")\n",
     "",
     "a first synchronization under one second slews"),
    ("the pre-#68 20 us threshold", GENERATOR,
     "    p.emit(\"RDST\", rd=RB, imm=RG_SCR | S_1E9, fmt=FMT_Q)\n",
     "    p.emit(\"MOVE\", rd=RB, ra=0, imm=20000)\n",
     "the step threshold is one second"),
    ("exactly one second steps", GENERATOR,
     "    p.emit(\"ALU\", rd=RB, ra=RB, rb=0, cnd=ALU_ADD, imm=1)\n"
     "    p.emit(\"MD\", rd=RU, ra=RT, rb=RB, cnd=MD_DIVU)\n",
     "    p.emit(\"ALU\", rd=RB, ra=RB, rb=0, cnd=ALU_ADD, imm=0)\n"
     "    p.emit(\"MD\", rd=RU, ra=RT, rb=RB, cnd=MD_DIVU)\n",
     "an offset of exactly one second does not exceed the threshold"),
    ("the step arm is unreachable", GENERATOR,
     "    p.emit(\"BRS\", cnd=BRS_Z, label=\"sv_slew\")\n"
     "    p.emit(\"ALU\", rd=RB, ra=R0, rb=RA, cnd=ALU_SUB)          "
     "# -offset\n",
     "    p.emit(\"BR\", label=\"sv_slew\")\n"
     "    p.emit(\"ALU\", rd=RB, ra=R0, rb=RA, cnd=ALU_SUB)          "
     "# -offset\n",
     "a first synchronization over one second steps"),
    ("a grandmaster change keeps synchronization", GENERATOR,
     "    e_flags(p, andm=FL_ASCAP_C, orm=FL_PRESENT_C)\n",
     "    e_flags(p, andm=FL_ASCAP_C | FL_SYNCOK_C, orm=FL_PRESENT_C)\n",
     "a grandmaster identity change makes the next pair first"),
    ("the slew input is not saturated", GENERATOR,
     "    e_sat(p, RA, SLEW_NS_C, \"sv_in\")\n",
     "",
     "a large offset slews within the pre-#68 rate envelope"),
    ("the integrator is not clamped", GENERATOR,
     "    e_sat(p, RC, RUNTIME[\"ilim\"], \"sv_i\")                    "
     "# +-ILIM\n",
     "",
     "the integrator stays within +-200 ppm"),
]


def stage(work: Path, tag: str,
          mutate: tuple[str, str, str] | None = None) -> Path:
    """A directory holding the RTL and the generator, with at most one
    mutated. Nothing outside the returned directory is written."""
    srcdir = work / f"src_{tag}"
    for name in RTL_SOURCES + (GENERATOR,):
        target = srcdir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = (HDL / name).read_text(encoding="utf-8")
        if mutate is not None and mutate[0] == name:
            text = text.replace(mutate[1], mutate[2])
        target.write_text(text, encoding="utf-8")
    return srcdir


def generate_image(srcdir: Path, rundir: Path) -> bool:
    """Write the suite's ROM image from `srcdir`'s generator. False when the
    generator refuses, which for a packing failure is a real answer."""
    rundir.mkdir(parents=True, exist_ok=True)
    out = subprocess.run(
        [sys.executable, str(srcdir / GENERATOR), *GENARGS,
         "-o", str(rundir / "gptp_ucode.hex")],
        capture_output=True, text=True)
    return out.returncode == 0 and (rundir / "gptp_ucode.hex").is_file()


def build(srcdir: Path, work: Path, tag: str) -> Path | None:
    """Build the harness against the RTL in `srcdir`; the exe, or None."""
    mdir = work / f"obj_{tag}"
    exe_name = f"Vengine_{tag}"
    out = subprocess.run(
        ["verilator", *VFLAGS, "--Mdir", str(mdir),
         "-CFLAGS", f"-std=c++17 -O2 -I{HERE} -Wall -Wextra",
         *[str(srcdir / s) for s in RTL_SOURCES],
         str(HERE / "sim_main.cpp"), "-o", exe_name],
        capture_output=True, text=True)
    exe = mdir / exe_name
    if out.returncode != 0 or not exe.is_file():
        return None
    return exe


def run_harness(exe: Path, rundir: Path) -> tuple[int, str]:
    """(rc, output) of one harness run, reading its image from `rundir`.

    No host deadline: every wait in sim_main.cpp is bounded in DUT cycles and
    reports its own timeout as a failed check, so a mutant that wedges the
    plane still returns a verdict.
    """
    out = subprocess.run([str(exe)], cwd=str(rundir),
                         capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


def main() -> int:
    """Run the control and every mutant, and report the arm's exit status.

    0 when the unmutated sources pass and every mutant is caught; 1 when any
    mutant survived, failed to build, or no longer matches its pattern, each
    printed with the property it was defending.
    """
    passes = fails = 0
    with tempfile.TemporaryDirectory(prefix="engine-mutants-") as td:
        work = Path(td)

        # -- positive control: the real sources must still pass -------------
        clean_src = stage(work, "clean")
        clean_run = work / "run_clean"
        clean_exe = build(clean_src, work, "clean")
        if clean_exe is None or not generate_image(clean_src, clean_run):
            print("[FAIL] the unmutated sources did not build; every mutant "
                  "result below would be meaningless")
            return 1
        answer = verdict(*run_harness(clean_exe, clean_run))
        if answer == "pass":
            passes += 1
            print("[PASS] the unmutated engine still passes the harness")
        else:
            fails += 1
            print(f"[FAIL] the unmutated engine does NOT pass ({answer}) - "
                  f"every mutant result below is meaningless")

        # -- each mutant must be caught --------------------------------------
        for name, fname, pattern, replacement, breaks in MUTATIONS:
            src = (HDL / fname).read_text(encoding="utf-8")
            if src.count(pattern) != 1:
                fails += 1
                print(f"[FAIL] mutation {name!r}: its pattern appears "
                      f"{src.count(pattern)} time(s) in {fname}, expected "
                      f"exactly 1. The source moved and this mutant is no "
                      f"longer mutating anything - fix the pattern, do not "
                      f"delete the arm.")
                continue
            tag = "".join(c if c.isalnum() else "_" for c in name)
            srcdir = stage(work, tag, (fname, pattern, replacement))
            rundir = work / f"run_{tag}"
            if not generate_image(srcdir, rundir):
                fails += 1
                print(f"[FAIL] mutation {name!r}: the generator refused its "
                      f"image, so this mutant proves nothing about the "
                      f"harness")
                continue
            if fname == GENERATOR:
                exe = clean_exe          # only the ROM image differs
            else:
                exe = build(srcdir, work, tag)
            if exe is None:
                fails += 1
                print(f"[FAIL] mutation {name!r} did not build; a mutant that "
                      f"cannot build proves nothing about the harness")
                continue
            answer = verdict(*run_harness(exe, rundir))
            if answer == "caught":
                passes += 1
                print(f"[PASS] mutant caught: {name} - breaks \"{breaks}\"")
            elif answer == "pass":
                fails += 1
                print(f"[FAIL] mutant SURVIVED: {name}. The harness does not "
                      f"prove \"{breaks}\".")
            else:
                fails += 1
                print(f"[FAIL] mutant {name!r} {answer}")

    total = passes + fails
    print(f"\n{total} checks: {passes} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
