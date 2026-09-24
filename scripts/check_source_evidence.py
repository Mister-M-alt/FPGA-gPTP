#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Bind each local line anchor in the evidence ledger to its claimed construct."""

import argparse
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ENGINE = "hdl/top/KL_gptp_engine.sv"
PARSER = "hdl/wire/KL_gptp_rx_parser.sv"
UCPU = "hdl/ucpu/KL_gptp_ucpu.sv"
ANCHOR = re.compile(r"\]\((\.\./[^)#]+)#L(\d+)\)")

# Pin constructs, not line numbers: moving code requires moving the link.
# Keep the claim as the key so replacing a link with another valid symbol
# cannot silently change what the ledger purports to demonstrate.
EXPECTED = {
    "Single clock domain": [(ENGINE, "module KL_gptp_engine")],
    "Four instantiated blocks": [(ENGINE, "KL_gptp_rx_parser u_parser (")],
    "Deferred receive event": [(PARSER, "if (fin_r) begin")],
    "Four-entry event queue": [(ENGINE, "logic [39:0] evq_r [0:3];")],
    "Parser arbitration priority": [(ENGINE, "always_comb begin : push_arb")],
    "Priority timestamp return": [(ENGINE, "logic        txts_pend_r;")],
    "Accepted-beat result face": [(ENGINE, "assign txts_ready_o  = !txts_pend_r && rst_n;")],
    "Reset-backed pairing validity": [(ENGINE, "logic t1v_valid_r, pdwait_valid_r;")],
    "Transmit admission credit": [(ENGINE, "input  wire         tx_credit_i,")],
    "Eight timer slots": [(ENGINE, "KL_gptp_timer #(")],
    "Six state regions": [(ENGINE, "//                  0  message bank      RO  (parser-written, PING-PONG")],
    "Stable stalled transmission": [("hdl/wire/KL_gptp_tx_slot.sv", "assign tx_valid_o = ser_run_r;")],
    "Committed publication": [(ENGINE, "output logic        pub_commit_o,")],
    "1,024-word microcode ROM": [(UCPU, "// ------------------------------------------------------------------ ROM")],
    "Sixteen registers": [(UCPU, "// 16 x 64 distributed RAM, 1W3R (SET_MASKED reads rd as well).")],
    "Registered policy slew level": [
        (ENGINE, "output logic        phc_slew_active_o,"),
        (ENGINE, "2'd2: begin"),
        (ENGINE, "2'd3: begin"),
        ("hdl/ucode/gen_gptp_ucode.py", "def prog_leg_slew(base: int) -> Prog:"),
    ],
    "Ignored receive flag bits": [(PARSER, "11'(OFF_FLAGS0_C + 1): flags_r <= acc_nxt_w[15:0];")],
}


def check(root: Path = ROOT, ledger: str | None = None,
          expected: dict[str, list[tuple[str, str]]] = EXPECTED) -> tuple[list[str], list[str]]:
    """Return (findings, exact anchors); missing or unbound links also fail."""
    if ledger is None:
        ledger = (root / "docs/SOURCE_EVIDENCE.md").read_text()
    findings, exact, seen = [], [], set()
    for row in ledger.splitlines():
        if not row.startswith("|"):
            continue
        claim = row.split("|")[1].strip()
        links = ANCHOR.findall(row)
        if claim not in expected and not links:
            continue
        if claim in seen:
            findings.append(f"duplicate claim: {claim}")
        seen.add(claim)
        targets = expected.get(claim, [])
        if len(links) != len(targets) or not targets:
            findings.append(f"{claim}: unbound or missing local line anchor")
            continue
        for (relative, number), (source, construct) in zip(links, targets):
            label = f"{source}#L{number} ({claim})"
            path = root / "docs" / relative
            if path.resolve() != (root / source).resolve() or not path.is_file():
                findings.append(f"{label}: wrong or missing source")
                continue
            lines = path.read_text().splitlines()
            index = int(number) - 1
            if not 0 <= index < len(lines) or lines[index].strip() != construct:
                findings.append(f"{label}: STALE; expected {construct!r}")
            else:
                exact.append(f"EXACT {label}: {construct}")
    findings.extend(f"missing claim: {claim}" for claim in expected.keys() - seen)
    return findings, exact


def selftest() -> None:
    """A shifted link, wrong construct, removed link and unknown link fail."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs").mkdir()
        (root / "source.sv").write_text("\nmodule checked\nmodule other\n")
        targets = {"Claim": [("source.sv", "module checked")]}
        good = "| Claim | [source](../source.sv#L2) | Suite |"
        findings, exact = check(root, good, targets)
        assert not findings and len(exact) == 1
        for bad in (good.replace("L2", "L1"), good.replace("L2", "L3"),
                    good.replace("#L2", ""), good.replace("Claim", "Unknown"),
                    good.replace("source.sv", "absent.sv"), ""):
            assert check(root, bad, targets)[0], bad
    print("source evidence selftest: PASS (7 arms)")


def main() -> int:
    """Run the ledger check or its self-test and return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    if parser.parse_args().selftest:
        selftest()
        return 0
    findings, exact = check()
    for line in exact + findings:
        print(line)
    print(f"source evidence: {len(exact)} exact, {len(findings)} findings")
    return int(bool(findings))


if __name__ == "__main__":
    sys.exit(main())
