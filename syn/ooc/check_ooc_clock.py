#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Hold the OOC clock order: synth_design must see the 10 ns clock (#70).

Without arguments the check reads both OOC scripts and ooc_clock.xdc. With
--log it reads the Vivado logs those scripts wrote, which proves the order
Vivado actually ran. --selftest plants each defect and expects a finding.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
SCRIPTS = ("ucpu_ooc.tcl", "engine_ooc.tcl")
XDC = "ooc_clock.xdc"
PERIOD_NS = 10.0
CLOCK_PORT = "clk_i"
NAME = "ooc clock order"

# Commands that define or load timing constraints. None may follow
# synth_design: a clock created afterwards only annotates a netlist that was
# synthesized without it.
CONSTRAINT_COMMANDS = {"create_clock", "create_generated_clock", "read_xdc", "source"}

CLOCK_RE = re.compile(
    r"^create_clock\s+-period\s+([0-9.]+)\s+-name\s+\S+\s+\[get_ports\s+(\S+)\]$"
)
LOG_SYNTH_COMMAND_RE = re.compile(r"^Command: synth_design\b")
LOG_SYNTH_START_RE = re.compile(r"^Starting synth_design\b")
LOG_SYNTH_DONE_RE = re.compile(r"^synth_design completed successfully\b")
LOG_MAPPING_RE = re.compile(r"^Start Technology Mapping\b")
LOG_READ_RE = re.compile(r"^# read_xdc\s+\S*\b" + re.escape(XDC) + r"$")
LOG_PARSE_RE = re.compile(r"^Parsing XDC File \[\S*/" + re.escape(XDC) + r"\]$")
LOG_ECHO_RE = re.compile(r"^# (\S+)")


def tcl_commands(text: str) -> list[tuple[int, list[str]]]:
    """Return (line, words) per command; comments dropped, continuations joined."""
    commands: list[tuple[int, list[str]]] = []
    pending = ""
    first = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        if not pending:
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            first = number
        if raw.endswith("\\"):
            pending += raw[:-1] + " "
            continue
        pending += raw
        for part in pending.split(";"):
            if part.strip():
                commands.append((first, part.split()))
        pending = ""
    return commands


def script_findings(path: Path) -> list[str]:
    """Report a script whose clock file is not read before its synth_design."""
    name = path.name
    if not path.is_file():
        return [f"{name}: missing"]
    commands = tcl_commands(path.read_text(encoding="utf-8"))
    synth = [index for index, (_line, words) in enumerate(commands)
             if words[0] == "synth_design"]
    if len(synth) != 1:
        return [f"{name}: expected one synth_design, found {len(synth)}"]
    findings: list[str] = []
    before = commands[:synth[0]]
    if not any(words[0] == "read_xdc" and words[-1].split("/")[-1] == XDC
               for _line, words in before):
        findings.append(f"{name}: {XDC} is not read before synth_design")
    for line, words in commands[synth[0] + 1:]:
        if words[0] in CONSTRAINT_COMMANDS:
            findings.append(f"{name}:{line}: {words[0]} after synth_design")
    return findings


def xdc_findings(path: Path) -> list[str]:
    """Report a constraints file without exactly one 10 ns clock on clk_i."""
    if not path.is_file():
        return [f"{path.name}: missing"]
    clocks = [
        CLOCK_RE.match(" ".join(words))
        for _line, words in tcl_commands(path.read_text(encoding="utf-8"))
        if words[0] == "create_clock"
    ]
    if len(clocks) != 1 or clocks[0] is None:
        return [f"{path.name}: expected one create_clock -period -name [get_ports]"]
    period, port = clocks[0].groups()
    if float(period) != PERIOD_NS or port != CLOCK_PORT:
        return [f"{path.name}: clock is {period} ns on {port}, "
                f"expected {PERIOD_NS:.3f} ns on {CLOCK_PORT}"]
    return []


def check(root: Path = HERE) -> list[str]:
    """Check both scripts and the constraints file they share."""
    findings = xdc_findings(root / XDC)
    for script in SCRIPTS:
        findings.extend(script_findings(root / script))
    return findings


def first(lines: list[str], pattern: re.Pattern[str], start: int = 0,
          stop: int | None = None) -> int | None:
    """Return the index of the first matching line in [start, stop)."""
    for index in range(start, len(lines) if stop is None else stop):
        if pattern.search(lines[index]):
            return index
    return None


def log_findings(path: Path) -> list[str]:
    """Report a Vivado log in which synthesis ran without the clock."""
    name = path.name
    if not path.is_file():
        return [f"{name}: missing"]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    command = first(lines, LOG_SYNTH_COMMAND_RE)
    start = first(lines, LOG_SYNTH_START_RE, command or 0)
    if command is None or start is None:
        return [f"{name}: synth_design never started"]
    done = first(lines, LOG_SYNTH_DONE_RE, start)
    if done is None:
        return [f"{name}: synth_design did not complete"]
    findings: list[str] = []
    if first(lines, LOG_READ_RE, 0, command) is None:
        findings.append(f"{name}: {XDC} is not read before synth_design")
    mapping = first(lines, LOG_MAPPING_RE, start, done)
    if first(lines, LOG_PARSE_RE, start, done if mapping is None else mapping) is None:
        findings.append(f"{name}: synth_design did not parse {XDC} before mapping")
    for index in range(done + 1, len(lines)):
        echo = LOG_ECHO_RE.match(lines[index])
        if echo and echo.group(1) in CONSTRAINT_COMMANDS:
            findings.append(f"{name}:{index + 1}: {echo.group(1)} after synth_design")
    return findings


GOOD_TCL = """# fixture
set SPEC .
read_xdc $SPEC/syn/ooc/ooc_clock.xdc
read_verilog -sv a.sv \\
    b.sv
synth_design -mode out_of_context -top T -part P \\
    -generic UCODE_HEX_P=gptp_ucode.hex
report_timing_summary -file t.rpt
"""
GOOD_XDC = "# fixture\ncreate_clock -period 10.000 -name clk [get_ports clk_i]\n"
GOOD_LOG = """source x.tcl
# set SPEC .
# read_xdc $SPEC/syn/ooc/ooc_clock.xdc
# read_verilog -sv a.sv b.sv
# synth_design -mode out_of_context -top T -part P
Command: synth_design -mode out_of_context -top T -part P
Starting synth_design
Processing XDC Constraints
Parsing XDC File [/w/syn/ooc/ooc_clock.xdc]
Finished Parsing XDC File [/w/syn/ooc/ooc_clock.xdc]
Start Technology Mapping
Parsing XDC File [/w/syn/ooc/ooc_clock.xdc]
synth_design completed successfully
# report_timing_summary -file t.rpt
"""


def selftest() -> int:
    """Plant each order defect and require the check to name it."""
    read = "read_xdc $SPEC/syn/ooc/ooc_clock.xdc\n"
    synth = "    -generic UCODE_HEX_P=gptp_ucode.hex\n"
    clock = "create_clock -period 10.000 -name clk [get_ports clk_i]\n"
    log_read = "# read_xdc $SPEC/syn/ooc/ooc_clock.xdc\n"
    log_parse = ("Parsing XDC File [/w/syn/ooc/ooc_clock.xdc]\n"
                 "Finished Parsing XDC File [/w/syn/ooc/ooc_clock.xdc]\n")
    log_done = "synth_design completed successfully\n"
    tcl_arms = {
        "read_xdc moved after synth_design":
            GOOD_TCL.replace(read, "").replace(synth, synth + read),
        "create_clock after synth_design (the pre-#70 order)":
            GOOD_TCL.replace(read, "").replace(synth, synth + clock),
        "read_xdc of another file": GOOD_TCL.replace("ooc_clock.xdc", "other.xdc"),
        "second synth_design": GOOD_TCL + "synth_design -top T -part P\n",
    }
    xdc_arms = {
        "8 ns period": GOOD_XDC.replace("10.000", "8.000"),
        "clock on another port": GOOD_XDC.replace("clk_i", "clk_o"),
        "no clock": "# fixture\n",
    }
    log_arms = {
        "read_xdc echoed after synth_design":
            GOOD_LOG.replace(log_read, "").replace(log_done, log_done + log_read),
        "create_clock echoed after synth_design (the pre-#70 order)":
            GOOD_LOG.replace(log_read, "").replace(log_parse, "")
            .replace(log_done, log_done + "# " + clock),
        "synthesis without the parsed XDC": GOOD_LOG.replace(log_parse, ""),
        "synth_design that never completed": GOOD_LOG.replace(log_done, ""),
    }
    arms = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / XDC).write_text(GOOD_XDC, encoding="utf-8")
        for script in SCRIPTS:
            (root / script).write_text(GOOD_TCL, encoding="utf-8")
        log = root / "fixture.log"
        log.write_text(GOOD_LOG, encoding="utf-8")
        arms += 1
        if check(root) or log_findings(log):
            print(f"{NAME} selftest: clean fixture failed: "
                  f"{check(root) + log_findings(log)}")
            return 1
        for label, text in tcl_arms.items():
            arms += 1
            (root / SCRIPTS[-1]).write_text(text, encoding="utf-8")
            if not check(root):
                print(f"{NAME} selftest: {label} escaped")
                return 1
        (root / SCRIPTS[-1]).write_text(GOOD_TCL, encoding="utf-8")
        for label, text in xdc_arms.items():
            arms += 1
            (root / XDC).write_text(text, encoding="utf-8")
            if not check(root):
                print(f"{NAME} selftest: {label} escaped")
                return 1
        for label, text in log_arms.items():
            arms += 1
            log.write_text(text, encoding="utf-8")
            if not log_findings(log):
                print(f"{NAME} selftest: {label} escaped")
                return 1
    arms += 1
    if check():
        print(f"{NAME} selftest: production scripts failed")
        return 1
    print(f"{NAME} selftest: PASS ({arms} arms)")
    return 0


def main() -> int:
    """Run the script check, the log check or the self-test."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--log", nargs="+", type=Path, metavar="LOG",
                        help="Vivado logs of the OOC scripts to check")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.log:
        findings = [finding for log in args.log for finding in log_findings(log)]
        subject = ", ".join(log.name for log in args.log)
    else:
        findings = check()
        subject = ", ".join((XDC,) + SCRIPTS)
    if findings:
        print(f"{NAME}: FAIL ({len(findings)} findings)")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"{NAME}: PASS ({subject})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
