#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Hold the OOC clock: synth_design must see the 10 ns clock and use it (#70).

Without arguments the check reads both OOC scripts and ooc_clock.xdc. With
--log it reads the Vivado logs those scripts wrote, and the timing report
named after each log, which proves what Vivado actually ran: this
repository's ooc_clock.xdc parsed inside synthesis, clk at 10 ns bound to
clk_i, no unclocked register and no critical warning. --selftest plants
each defect and expects its finding by name.
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
# The one argument read_xdc may take: the scripts set SPEC to the repository
# root, so this names this repository's file, not any file of that basename.
XDC_READ = "$SPEC/syn/ooc/" + XDC
PERIOD_NS = 10.0
CLOCK_PORT = "clk_i"
# The one row the timing report's Clock Summary may hold, whitespace joined.
CLOCK_SUMMARY = "clk {0.000 5.000} 10.000 100.000"
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
LOG_READ_RE = re.compile(r"^# read_xdc " + re.escape(XDC_READ) + r"$")
LOG_ECHO_RE = re.compile(r"^# (\S+)")
LOG_CRITICAL_RE = re.compile(r"^CRITICAL WARNING:")
# Vivado's running message count; the last one in a log closes the session.
LOG_COUNT_RE = re.compile(
    r"^\d+ Infos, \d+ Warnings, (\d+) Critical Warnings and \d+ Errors encountered\.$"
)
RPT_SUMMARY_RE = re.compile(r"^Clock\s+Waveform\(ns\)\s+Period\(ns\)")
RPT_CLOCKS_RE = re.compile(r"^Clock\s+Period\(ns\)\s+Waveform\(ns\)\s+Attributes\s+Sources")
RPT_SOURCES_RE = re.compile(r"\{([^}]*)\}$")
RPT_NO_CLOCK_RE = re.compile(r"^\d+\. checking no_clock \((\d+)\)")


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
    if not any(words == ["read_xdc", XDC_READ] for _line, words in before):
        findings.append(f"{name}: {XDC_READ} is not read before synth_design")
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


def table(lines: list[str], header: re.Pattern[str]) -> list[str]:
    """Return the rows under a report table header, whitespace joined."""
    index = first(lines, header)
    rows: list[str] = []
    for line in [] if index is None else lines[index + 1:]:
        if not line.strip():
            break
        if not line.startswith("-"):
            rows.append(" ".join(line.split()))
    return rows


def timing_findings(path: Path) -> list[str]:
    """Report a timing report in which clk did not take effect on clk_i."""
    name = path.name
    if not path.is_file():
        return [f"{name}: missing"]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    findings: list[str] = []
    summary = table(lines, RPT_SUMMARY_RE)
    if summary != [CLOCK_SUMMARY]:
        findings.append(f"{name}: Clock Summary is {summary}, expected [{CLOCK_SUMMARY!r}]")
    # The Clock Summary has no source column; report_clocks, appended to the
    # same file by the script, names the port each clock is bound to.
    sources = [match.group(1).split() for row in table(lines, RPT_CLOCKS_RE)
               if row.split()[0] == "clk" and (match := RPT_SOURCES_RE.search(row))]
    if sources != [[CLOCK_PORT]]:
        findings.append(f"{name}: clock clk is not bound to {CLOCK_PORT} (sources {sources})")
    no_clock = [match.group(1) for line in lines if (match := RPT_NO_CLOCK_RE.match(line))]
    if no_clock[:1] != ["0"]:
        findings.append(f"{name}: checking no_clock reports {no_clock[:1]}, expected ['0']")
    return findings


def log_findings(path: Path, xdc: Path = HERE / XDC) -> list[str]:
    """Report a Vivado log of synthesis without the clock, or with a critical warning."""
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
        findings.append(f"{name}: {XDC_READ} is not read before synth_design")
    mapping = first(lines, LOG_MAPPING_RE, start, done)
    # Matched by full path: a file of the same basename elsewhere is not it.
    parse = re.compile(r"^Parsing XDC File \[" + re.escape(str(xdc)) + r"\]$")
    if first(lines, parse, start, done if mapping is None else mapping) is None:
        findings.append(f"{name}: synth_design did not parse {xdc} before mapping")
    for index in range(done + 1, len(lines)):
        echo = LOG_ECHO_RE.match(lines[index])
        if echo and echo.group(1) in CONSTRAINT_COMMANDS:
            findings.append(f"{name}:{index + 1}: {echo.group(1)} after synth_design")
    for index, line in enumerate(lines):
        if LOG_CRITICAL_RE.match(line):
            findings.append(f"{name}:{index + 1}: {line}")
    counts = [index for index, line in enumerate(lines) if LOG_COUNT_RE.match(line)]
    if not counts:
        findings.append(f"{name}: no session message count")
    elif (critical := LOG_COUNT_RE.match(lines[counts[-1]]).group(1)) != "0":
        findings.append(f"{name}:{counts[-1] + 1}: session ends with {critical} critical warnings")
    return findings


def post_findings(log: Path, xdc: Path = HERE / XDC) -> list[str]:
    """Check one synthesis: its log and the timing report named after it."""
    report = log.with_name(log.name.removesuffix("_ooc.log") + "_timing.rpt")
    return log_findings(log, xdc) + timing_findings(report)


GOOD_TCL = """# fixture
set SPEC .
read_xdc $SPEC/syn/ooc/ooc_clock.xdc
read_verilog -sv a.sv \\
    b.sv
synth_design -mode out_of_context -top T -part P \\
    -generic UCODE_HEX_P=gptp_ucode.hex
report_timing_summary -file fixture_timing.rpt
report_clocks -append -file fixture_timing.rpt
"""
GOOD_XDC = "# fixture\ncreate_clock -period 10.000 -name clk [get_ports clk_i]\n"
# @XDC@ stands for the fixture's ooc_clock.xdc, which the log names by full path.
GOOD_LOG = """source x.tcl
# set SPEC .
# read_xdc $SPEC/syn/ooc/ooc_clock.xdc
# read_verilog -sv a.sv b.sv
# synth_design -mode out_of_context -top T -part P
Command: synth_design -mode out_of_context -top T -part P
Starting synth_design
Processing XDC Constraints
Parsing XDC File [@XDC@]
Finished Parsing XDC File [@XDC@]
Start Technology Mapping
Parsing XDC File [@XDC@]
Finished Parsing XDC File [@XDC@]
39 Infos, 65 Warnings, 0 Critical Warnings and 0 Errors encountered.
synth_design completed successfully
# report_timing_summary -file fixture_timing.rpt
# report_clocks -append -file fixture_timing.rpt
"""
GOOD_RPT = """| Design       : T
check_timing report

Table of Contents
-----------------
1. checking no_clock (0)

1. checking no_clock (0)
------------------------
 There are 0 register/latch pins with no clock.

| Clock Summary
| -------------
------------------------------------------------------------------------------------------------

Clock  Waveform(ns)       Period(ns)      Frequency(MHz)
-----  ------------       ----------      --------------
clk    {0.000 5.000}      10.000          100.000

Clock Report

Clock  Period(ns)  Waveform(ns)   Attributes  Sources
clk    10.000      {0.000 5.000}  P           {clk_i}

"""


def selftest() -> int:
    """Plant each defect and require the check to name it."""
    read = "read_xdc $SPEC/syn/ooc/ooc_clock.xdc\n"
    synth = "    -generic UCODE_HEX_P=gptp_ucode.hex\n"
    clock = "create_clock -period 10.000 -name clk [get_ports clk_i]\n"
    log_read = "# read_xdc $SPEC/syn/ooc/ooc_clock.xdc\n"
    log_parse = "Parsing XDC File [@XDC@]\nFinished Parsing XDC File [@XDC@]\n"
    log_done = "synth_design completed successfully\n"
    log_count = "39 Infos, 65 Warnings, 0 Critical Warnings and 0 Errors encountered.\n"
    summary = "clk    {0.000 5.000}      10.000          100.000\n"
    sources = "clk    10.000      {0.000 5.000}  P           {clk_i}\n"
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        xdc, tcl = root / XDC, root / SCRIPTS[-1]
        log, report = root / "fixture_ooc.log", root / "fixture_timing.rpt"
        good = {xdc: GOOD_XDC, log: GOOD_LOG, report: GOOD_RPT}
        good.update({root / script: GOOD_TCL for script in SCRIPTS})
        # R614-1's arm: the top's clock port renamed, so create_clock found
        # no port, and synthesis and timing ran with no clock at all.
        renamed = {
            log: GOOD_LOG.replace(
                "Finished Parsing", "CRITICAL WARNING: [Vivado 12-4739] create_clock:No valid "
                "object(s) found for '-objects [get_ports clk_i]'. [@XDC@:9]\nFinished Parsing")
            .replace(log_count, log_count.replace("0 Critical", "2 Critical")),
            report: GOOD_RPT.replace("no_clock (0)", "no_clock (1003)")
            .split("| Clock Summary")[0] + "Clock Report\n\nClock  Period(ns)  Waveform(ns)  "
            "Attributes  Sources\n\n",
        }
        # (label, planted files, words a finding must carry; None deletes a file)
        arms: list[tuple[str, dict[Path, str | None], list[str]]] = [
            ("read_xdc moved after synth_design",
             {tcl: GOOD_TCL.replace(read, "").replace(synth, synth + read)},
             ["read_xdc after synth_design"]),
            ("create_clock after synth_design (the pre-#70 order)",
             {tcl: GOOD_TCL.replace(read, "").replace(synth, synth + clock)},
             ["create_clock after synth_design"]),
            ("no read_xdc", {tcl: GOOD_TCL.replace(read, "")}, ["is not read before"]),
            ("read_xdc of another file",
             {tcl: GOOD_TCL.replace("ooc_clock.xdc", "other.xdc")}, ["is not read before"]),
            ("read_xdc of a foreign ooc_clock.xdc of the same basename",
             {tcl: GOOD_TCL.replace(read, "read_xdc /elsewhere/ooc_clock.xdc\n")},
             ["is not read before"]),
            ("create_clock added after synth_design", {tcl: GOOD_TCL + clock},
             ["create_clock after synth_design"]),
            ("second synth_design", {tcl: GOOD_TCL + "synth_design -top T -part P\n"},
             ["expected one synth_design"]),
            ("8 ns period", {xdc: GOOD_XDC.replace("10.000", "8.000")}, ["clock is 8.000 ns"]),
            ("clock on another port", {xdc: GOOD_XDC.replace("clk_i", "clk_o")}, ["on clk_o"]),
            ("no clock", {xdc: "# fixture\n"}, ["expected one create_clock"]),
            ("XDC with two create_clock lines", {xdc: GOOD_XDC + clock},
             ["expected one create_clock"]),
            ("read_xdc echoed after synth_design",
             {log: GOOD_LOG.replace(log_read, "").replace(log_done, log_done + log_read)},
             ["is not read before", "read_xdc after synth_design"]),
            ("create_clock echoed after synth_design (the pre-#70 order)",
             {log: GOOD_LOG.replace(log_read, "").replace(log_parse, "")
              .replace(log_done, log_done + "# " + clock)},
             ["create_clock after synth_design"]),
            ("no read_xdc echo", {log: GOOD_LOG.replace(log_read, "")}, ["is not read before"]),
            ("synthesis without the parsed XDC", {log: GOOD_LOG.replace(log_parse, "")},
             ["did not parse"]),
            ("foreign ooc_clock.xdc of the same basename read and parsed",
             {log: GOOD_LOG.replace("$SPEC/syn/ooc/ooc_clock.xdc", "/elsewhere/ooc_clock.xdc")
              .replace("@XDC@", "/elsewhere/ooc_clock.xdc")},
             ["is not read before", "did not parse"]),
            ("ooc_clock.xdc parsed from another checkout",
             {log: GOOD_LOG.replace("@XDC@", "/elsewhere/syn/ooc/ooc_clock.xdc")},
             ["did not parse"]),
            ("create_clock echoed after a constrained synthesis", {log: GOOD_LOG + "# " + clock},
             ["create_clock after synth_design"]),
            ("synth_design that never started",
             {log: GOOD_LOG.replace("Command: synth_design", "Command: report_timing")},
             ["never started"]),
            ("synth_design that never completed", {log: GOOD_LOG.replace(log_done, "")},
             ["did not complete"]),
            ("critical-warning count above zero",
             {log: GOOD_LOG.replace("0 Critical Warnings", "1 Critical Warnings")},
             ["session ends with 1 critical warnings"]),
            ("no session message count", {log: GOOD_LOG.replace(log_count, "")},
             ["no session message count"]),
            ("critical warning after the session count",
             {log: GOOD_LOG + "CRITICAL WARNING: [Timing 38-1] planted\n"},
             ["CRITICAL WARNING: [Timing 38-1]"]),
            ("wrong period",
             {report: GOOD_RPT.replace("{0.000 5.000}      10.000          100.000",
                                       "{0.000 4.000}      8.000           125.000")
              .replace("10.000      {0.000 5.000}", "8.000       {0.000 4.000}")},
             ["Clock Summary is"]),
            ("second clock", {report: GOOD_RPT.replace(summary, summary + summary)},
             ["Clock Summary is"]),
            ("clock bound to another port",
             {report: GOOD_RPT.replace(sources, sources.replace("clk_i", "rst_i"))},
             ["not bound to clk_i"]),
            ("unclocked registers", {report: GOOD_RPT.replace("no_clock (0)", "no_clock (12)")},
             ["checking no_clock reports"]),
            ("no timing report", {report: None}, ["fixture_timing.rpt: missing"]),
            ("renamed clock port (R614-1)", renamed,
             ["CRITICAL WARNING: [Vivado 12-4739]", "session ends with 2 critical warnings",
              "Clock Summary is", "not bound to clk_i", "checking no_clock reports"]),
        ]

        def findings(planted: dict[Path, str | None]) -> list[str]:
            for path, text in {**good, **planted}.items():
                if text is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(text.replace("@XDC@", str(xdc)), encoding="utf-8")
            return check(root) + post_findings(log, xdc)

        if clean := findings({}):
            print(f"{NAME} selftest: clean fixture failed: {clean}")
            return 1
        for label, planted, words in arms:
            found = findings(planted)
            for word in words:
                if not any(word in finding for finding in found):
                    print(f"{NAME} selftest: {label} escaped (no finding names {word!r})")
                    return 1
    print(f"{NAME} selftest: PASS ({len(arms) + 1} arms)")
    return 0


def main() -> int:
    """Run the script check, the post-synthesis check or the self-test."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--log", nargs="+", type=Path, metavar="LOG",
                        help="Vivado logs of the OOC scripts to check, each with "
                             "the <top>_timing.rpt written beside it")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.log:
        findings = [finding for log in args.log for finding in post_findings(log)]
        subject = ", ".join(log.name for log in args.log) + " and their timing reports"
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
