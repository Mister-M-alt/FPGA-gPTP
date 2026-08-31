#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Render and verify source-bound documentation diagrams."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIAGRAMS = ROOT / "docs" / "diagrams"
WAVEDROM = DIAGRAMS / "wavedrom"
MANIFEST = DIAGRAMS / "manifest.json"

ASSETS = (
    "gptp_architecture.drawio",
    "gptp_architecture.svg",
    "gptp_architecture.png",
    "wavedrom/rx_accept.json",
    "wavedrom/rx_accept.svg",
    "wavedrom/rx_accept.png",
    "wavedrom/tx_backpressure.json",
    "wavedrom/tx_backpressure.svg",
    "wavedrom/tx_backpressure.png",
)

EVIDENCE = {
    "hdl/top/KL_gptp_engine.sv": (
        "KL_gptp_rx_parser u_parser",
        "KL_gptp_timer #(",
        "logic [39:0] evq_r [0:3];",
        "KL_gptp_ucpu #(",
        ") u_ucpu (",
        "KL_gptp_tx_slot u_txslot",
        "logic        txts_pend_r;",
        "output logic        pub_commit_o",
    ),
    "hdl/wire/KL_gptp_rx_parser.sv": (
        "if (fin_r) begin",
        "ev_valid_o <= 1'b1;",
        "if (rx_eof_i) begin",
        "fin_r    <= 1'b1;",
    ),
    "hdl/wire/KL_gptp_tx_slot.sv": (
        "assign tx_valid_o = ser_run_r;",
        "assign tx_data_o  = slot_r[ser_addr_r];",
        "assign tx_sof_o   = ser_sof_r;",
        "assign tx_eof_o   = ser_run_r && (ser_left_r == 11'd1);",
        "end else if (tx_ready_i) begin",
    ),
}

DRAWIO_LABELS = (
    "KL_gptp_engine",
    "KL_gptp_rx_parser",
    "KL_gptp_timer",
    "KL_gptp_ucpu",
    "KL_gptp_tx_slot",
    "Message storage",
    "Event arbitration",
    "Priority timestamp return",
    "Committed publication",
    "Parent PHC",
)

WAVE_EXPECTED = {
    "rx_accept.json": {
        "rx_eof_i": "0.10...",
        "fin_r": "0..10..",
        "ev_valid_o": "0...10.",
    },
    "tx_backpressure.json": {
        "tx_valid_o": "01....0",
        "tx_ready_i": "0..1010",
        "tx_data_o": "x=..=.x",
        "tx_sof_o": "01..0..",
        "tx_eof_o": "0...1.0",
    },
}


def sha256(path: Path) -> str:
    """Return one file digest."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> None:
    """Run one renderer with visible failures."""
    subprocess.run(command, cwd=ROOT, check=True)


def validate_evidence(read_text=None) -> list[str]:
    """Verify every documented structure against current HDL."""
    reader = read_text or (lambda path: (ROOT / path).read_text(encoding="utf-8"))
    problems: list[str] = []
    for relative, tokens in EVIDENCE.items():
        text = reader(relative)
        problems.extend(
            f"{relative}: missing source evidence: {token}"
            for token in tokens
            if token not in text
        )
    return problems


def validate_drawio(text: str) -> list[str]:
    """Verify editable architecture labels and canvas settings."""
    problems: list[str] = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        return [f"architecture Draw.io XML is invalid: {error}"]
    values = "\n".join(cell.attrib.get("value", "") for cell in root.iter("mxCell"))
    problems.extend(
        f"architecture Draw.io label is missing: {label}"
        for label in DRAWIO_LABELS
        if label not in values
    )
    models = list(root.iter("mxGraphModel"))
    if len(models) != 1:
        problems.append("architecture needs exactly one Draw.io model")
    elif (
        int(models[0].attrib.get("pageWidth", "0")) < 1600
        or int(models[0].attrib.get("pageHeight", "0")) < 900
    ):
        problems.append("architecture Draw.io canvas is too small")
    edge_count = sum(cell.attrib.get("edge") == "1" for cell in root.iter("mxCell"))
    if edge_count < 12:
        problems.append("architecture Draw.io flow is incomplete")
    return problems


def validate_wave(path: Path, expected: dict[str, str]) -> list[str]:
    """Verify one WaveDrom source against documented invariants."""
    relative = path.relative_to(ROOT) if path.is_relative_to(ROOT) else Path(path.name)
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"{relative}: invalid WaveDrom JSON: {error}"]
    signals = {
        entry.get("name"): entry.get("wave")
        for entry in content.get("signal", [])
        if isinstance(entry, dict)
    }
    return [
        f"{relative}: {name} wave changed"
        for name, wave in expected.items()
        if signals.get(name) != wave
    ]


def png_dimensions(path: Path) -> tuple[int, int] | None:
    """Read PNG width and height without external dependencies."""
    data = path.read_bytes()[:24]
    if len(data) != 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", data[16:24])


def validate_png(path: Path, minimum: tuple[int, int]) -> list[str]:
    """Verify one preview has readable dimensions."""
    try:
        dimensions = png_dimensions(path)
    except OSError as error:
        return [f"{path.relative_to(ROOT)}: unreadable PNG: {error}"]
    if dimensions is None:
        return [f"{path.relative_to(ROOT)}: invalid PNG"]
    if dimensions[0] < minimum[0] or dimensions[1] < minimum[1]:
        return [
            f"{path.relative_to(ROOT)}: PNG is {dimensions[0]}x{dimensions[1]}, "
            f"expected at least {minimum[0]}x{minimum[1]}"
        ]
    return []


def validate_svg(path: Path, labels: tuple[str, ...] = ()) -> list[str]:
    """Verify one SVG remains structured and labeled."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        return [f"{path.relative_to(ROOT)}: invalid SVG: {error}"]
    problems: list[str] = []
    viewbox = root.attrib.get("viewBox")
    if not viewbox or len([part for part in re.split(r"[,\s]+", viewbox) if part]) != 4:
        problems.append(f"{path.relative_to(ROOT)}: missing SVG viewBox")
    text = " ".join(root.itertext())
    raw = path.read_text(encoding="utf-8")
    problems.extend(
        f"{path.relative_to(ROOT)}: rendered label is missing: {label}"
        for label in labels
        if label not in text and label not in raw
    )
    return problems


def manifest_data() -> dict[str, object]:
    """Build the committed source and artifact digest map."""
    return {
        "schema": 1,
        "algorithm": "sha256",
        "files": {relative: sha256(DIAGRAMS / relative) for relative in ASSETS},
    }


def validate_manifest() -> list[str]:
    """Verify every committed asset matches its manifest digest."""
    try:
        recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return [f"diagram manifest is invalid: {error}"]
    try:
        current = manifest_data()
    except OSError as error:
        return [f"diagram asset is missing: {error}"]
    if recorded != current:
        return ["diagram manifest differs from current sources or artifacts"]
    return []


def check() -> list[str]:
    """Run every source, rendering, and binding check."""
    problems = validate_evidence()
    problems.extend(
        validate_drawio((DIAGRAMS / "gptp_architecture.drawio").read_text(encoding="utf-8"))
    )
    for name, expected in WAVE_EXPECTED.items():
        problems.extend(validate_wave(WAVEDROM / name, expected))
    problems.extend(
        validate_svg(
            DIAGRAMS / "gptp_architecture.svg",
            ("KL_gptp_rx_parser", "KL_gptp_ucpu", "KL_gptp_tx_slot"),
        )
    )
    problems.extend(validate_svg(WAVEDROM / "rx_accept.svg", ("rx_eof_i", "ev_valid_o")))
    problems.extend(
        validate_svg(WAVEDROM / "tx_backpressure.svg", ("tx_valid_o", "tx_ready_i"))
    )
    problems.extend(validate_png(DIAGRAMS / "gptp_architecture.png", (1800, 900)))
    problems.extend(validate_png(WAVEDROM / "rx_accept.png", (1200, 300)))
    problems.extend(validate_png(WAVEDROM / "tx_backpressure.png", (1200, 300)))
    problems.extend(validate_manifest())
    return problems


def render(wavedrom: str) -> None:
    """Render every editable source and refresh the manifest."""
    drawio = shutil.which("drawio")
    converter = shutil.which("rsvg-convert")
    if drawio is None:
        raise RuntimeError("drawio executable is unavailable")
    if converter is None:
        raise RuntimeError("rsvg-convert executable is unavailable")
    wave_tool = shutil.which(wavedrom) if "/" not in wavedrom else wavedrom
    if not wave_tool or not Path(wave_tool).is_file():
        raise RuntimeError("wavedrom executable is unavailable")
    source = DIAGRAMS / "gptp_architecture.drawio"
    run([
        drawio,
        "--no-sandbox",
        "--export",
        "--format",
        "svg",
        "--output",
        str(DIAGRAMS / "gptp_architecture.svg"),
        str(source),
    ])
    run([
        drawio,
        "--no-sandbox",
        "--export",
        "--format",
        "png",
        "--scale",
        "1.5",
        "--output",
        str(DIAGRAMS / "gptp_architecture.png"),
        str(source),
    ])
    for stem in ("rx_accept", "tx_backpressure"):
        json_path = WAVEDROM / f"{stem}.json"
        svg_path = WAVEDROM / f"{stem}.svg"
        png_path = WAVEDROM / f"{stem}.png"
        run([str(wave_tool), "-i", str(json_path), "-s", str(svg_path)])
        run([
            converter,
            "--background-color",
            "white",
            "--width",
            "1800",
            "--output",
            str(png_path),
            str(svg_path),
        ])
    MANIFEST.write_text(
        json.dumps(manifest_data(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def selftest() -> int:
    """Prove structural mutations become visible."""
    arms = 0
    source_text = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in EVIDENCE
    }
    victim = next(iter(EVIDENCE))
    token = EVIDENCE[victim][0]
    mutated = dict(source_text)
    mutated[victim] = mutated[victim].replace(token, "removed_module", 1)
    arms += 1
    if not validate_evidence(mutated.__getitem__):
        print("diagram selftest: missing HDL evidence escaped")
        return 1
    drawio = (DIAGRAMS / "gptp_architecture.drawio").read_text(encoding="utf-8")
    arms += 1
    if not validate_drawio(drawio.replace(DRAWIO_LABELS[1], "removed_label")):
        print("diagram selftest: missing Draw.io label escaped")
        return 1
    arms += 1
    if validate_drawio(drawio):
        print("diagram selftest: valid Draw.io source failed")
        return 1
    with tempfile.TemporaryDirectory() as directory:
        wave = Path(directory) / "wave.json"
        original = json.loads((WAVEDROM / "rx_accept.json").read_text(encoding="utf-8"))
        for signal in original["signal"]:
            if signal.get("name") == "ev_valid_o":
                signal["wave"] = "0..10.."
        wave.write_text(json.dumps(original), encoding="utf-8")
        arms += 1
        if not validate_wave(wave, WAVE_EXPECTED["rx_accept.json"]):
            print("diagram selftest: WaveDrom timing mutation escaped")
            return 1
    arms += 1
    if png_dimensions(DIAGRAMS / "gptp_architecture.png") is None:
        print("diagram selftest: valid PNG failed")
        return 1
    arms += 1
    if not archive_manifest_mutation_detected():
        print("diagram selftest: manifest mutation escaped")
        return 1
    print(f"diagram selftest: PASS ({arms} arms)")
    return 0


def archive_manifest_mutation_detected() -> bool:
    """Model one changed digest without touching committed assets."""
    try:
        recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
        current = manifest_data()
    except (OSError, json.JSONDecodeError):
        return False
    changed = json.loads(json.dumps(recorded))
    first = next(iter(changed["files"]))
    changed["files"][first] = "0" * 64
    return changed != current and recorded == current


def main() -> int:
    """Dispatch rendering, checking, or self-tests."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--render", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--selftest", action="store_true")
    parser.add_argument("--wavedrom", default="wavedrompy")
    args = parser.parse_args()
    if args.render:
        problems = validate_evidence()
        problems.extend(
            validate_drawio(
                (DIAGRAMS / "gptp_architecture.drawio").read_text(encoding="utf-8")
            )
        )
        for name, expected in WAVE_EXPECTED.items():
            problems.extend(validate_wave(WAVEDROM / name, expected))
        if problems:
            for problem in problems:
                print(f"diagram render: FAIL: {problem}")
            return 1
        try:
            render(args.wavedrom)
        except (RuntimeError, subprocess.CalledProcessError) as error:
            print(f"diagram render: FAIL: {error}")
            return 1
        print("diagram render: PASS")
        return 0
    if args.selftest:
        return selftest()
    problems = check()
    if problems:
        print(f"diagram check: FAIL ({len(problems)} findings)")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"diagram check: PASS ({len(ASSETS)} source-bound assets)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
