#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Check concise, current, private-safe, and reachable documentation."""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "docs" / "history" / "v1"
HISTORY_INDEX = HISTORY / "README.md"
MAX_WORDS = 10

LINK_RE = re.compile(r"!?\[([^\]]*)]\(([^)]+)\)")
INLINE_CODE_RE = re.compile(r"`[^`]+`")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
TABLE_RULE_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$")
LIST_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")

RETIRED_TERMS = (
    "lin" + "ux",
    "lin" + "uxptp",
    "ptp" + "4l",
    "root" + "fs",
    "dae" + "mon",
    "dae" + "mons",
)
RETIRED_RE = re.compile(
    r"\b(?:" + "|".join(map(re.escape, RETIRED_TERMS)) + r")\b|"
    + re.escape("/dev/" + "ptp"),
    re.IGNORECASE,
)
PRIVATE_RE = re.compile(r"\b" + re.escape("DS" + "20D") + r"\b", re.IGNORECASE)

ARCHIVE_HEADER_RE = re.compile(r"^\[OBSOLETE \+ \d{4}-\d{2}-\d{2}]$")
ARCHIVE_STATUS_RE = re.compile(r"^> Status: Historical$", re.MULTILINE)
ARCHIVE_ORIGINAL_RE = re.compile(r"^> Original path: `([^`]+)`$", re.MULTILINE)
ARCHIVE_DATE_RE = re.compile(r"^> Archived: \d{4}-\d{2}-\d{2}$", re.MULTILINE)
ARCHIVE_SUCCESSOR_RE = re.compile(
    r"^> Current successor: \[[^\]]+]\(([^)]+)\)$", re.MULTILINE
)
ARCHIVE_TOTAL_RE = re.compile(r"^Archive total: (\d+) Markdown pages\.$", re.MULTILINE)

REQUIRED_CURRENT = {
    "README.md": (
        "docs/MANAGER.md",
        "docs/INTEGRATION.md",
        "docs/HDL_DEVELOPER.md",
        "docs/TEST_DEVELOPER.md",
        "docs/SOURCE_EVIDENCE.md",
        "docs/history/v1/README.md",
    ),
    "docs/INTEGRATION.md": (
        "GPTP_PLANE_EN_P",
        "by default",
        "comparison builds only",
        "rx_err_i",
        "txts_type_i",
        "txts_ready_o",
        "txts_ok_i",
        "tx_credit_i",
        "pub_commit_o",
    ),
    "docs/TEST_DEVELOPER.md": (
        "Python",
        "| C | None |",
        "C++",
        "make -C tb/verilator/engine",
        "mutants.py",
    ),
    "docs/HDL_DEVELOPER.md": (
        "KL_gptp_rx_parser",
        "KL_gptp_timer",
        "KL_gptp_ucpu",
        "KL_gptp_tx_slot",
        "Egress result ownership",
        "Retained pairing context",
        "wavedrom/rx_accept.png",
        "wavedrom/tx_backpressure.png",
    ),
    "docs/SOURCE_EVIDENCE.md": (
        "Deferred receive event",
        "Stable stalled transmission",
        "Parent default enabled",
        "Issue #31",
        "Issue #35",
    ),
}

STATUS_PAGE = "docs/README.md"
STATUS_HEADING = "## Document status"
STATUS_VALUES = ("Current", "Historical")
HISTORY_ROW = "docs/history/v1/"
STATUS_ROW_RE = re.compile(r"^\|\s*`([^`]+)`\s*\|(?:[^|]*\|){2}\s*([^|]*?)\s*\|\s*$")

GENERATOR = "hdl/ucode/gen_gptp_ucode.py"
CONSTANTS_PAGE = "docs/INTEGRATION.md"
CONSTANTS_HEADING = "## Protocol constants"
CONSTANT_ROW_RE = re.compile(r"^\|\s*`([A-Z][A-Z0-9_]*)`\s*\|\s*([0-9][0-9,]*)\s*\|")
ROM_PAGE = "docs/MANAGER.md"
ROM_HEADING = "## Current ROM budget"
ROM_ROW_RE = re.compile(
    r"^\|\s*(Shipping|Seeded regression)\s*\|\s*([0-9,]+) of ([0-9,]+)\s*\|"
    r"\s*([0-9,]+)\s*\|\s*$"
)
SEEDED_SEQ_SEED = 0x200000

TEXT_SUFFIXES = {
    ".md", ".py", ".sv", ".cpp", ".h", ".sh", ".tcl", ".xdc", ".yml", ".yaml",
    ".svg",  # rendered diagrams carry visible labels the vocabulary rule owns
}


def markdown_files(root: Path = ROOT) -> list[Path]:
    """Return repository Markdown, including new working files."""
    return sorted(
        path
        for path in root.rglob("*.md")
        if ".git" not in path.parts and "obj_dir" not in path.parts
    )


def current_markdown(root: Path = ROOT) -> list[Path]:
    """Return maintained Markdown outside versioned history."""
    history = root / "docs" / "history" / "v1"
    return [path for path in markdown_files(root) if history not in path.parents]


def textual_files(root: Path = ROOT) -> list[Path]:
    """Return first-party text carrying searchable vocabulary."""
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "obj_dir" in path.parts:
            continue
        if path.suffix in TEXT_SUFFIXES or path.name == "Makefile":
            files.append(path)
    return sorted(files)


def without_fences(text: str) -> str:
    """Remove fenced code and HTML comments."""
    text = HTML_COMMENT_RE.sub("", text)
    output: list[str] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            output.append(line)
    return "\n".join(output)


def clean_prose(text: str) -> str:
    """Remove Markdown syntax while retaining visible words."""
    text = LINK_RE.sub(lambda match: match.group(1), text)
    text = INLINE_CODE_RE.sub(" code ", text)
    text = HTML_TAG_RE.sub(" ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return text.translate(str.maketrans("", "", "*_~#>|"))


def prose_units(text: str) -> list[tuple[int, str]]:
    """Return visible sentence units with starting lines."""
    text = without_fences(text)
    units: list[tuple[int, str]] = []
    paragraph: list[str] = []
    paragraph_line = 1

    def flush() -> None:
        """End the paragraph being accumulated, emitting its sentences.

        Everything gathered since the last flush is joined into one line and
        split on sentence boundaries, and each sentence is emitted against the
        line the paragraph STARTED on - a sentence that runs across a wrapped
        paragraph is reported where a reader will find it. Nothing is emitted
        when no paragraph is open, so a blank line costs nothing.
        """
        nonlocal paragraph
        if paragraph:
            combined = " ".join(part.strip() for part in paragraph)
            units.extend((paragraph_line, sentence) for sentence in SENTENCE_RE.split(combined))
            paragraph = []

    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            flush()
            continue
        if TABLE_RULE_RE.match(line):
            flush()
            continue
        if line.startswith("|") and line.endswith("|"):
            flush()
            for cell in line.strip("|").split("|"):
                units.append((number, cell.strip()))
            continue
        if line.startswith("#"):
            flush()
            units.append((number, line.lstrip("# ")))
            continue
        if LIST_RE.match(line):
            flush()
            paragraph_line = number
            paragraph.append(LIST_RE.sub("", line, count=1))
            continue
        if not paragraph:
            paragraph_line = number
        paragraph.append(line.lstrip("> "))
    flush()
    return units


def style_findings(path: Path, text: str) -> list[str]:
    """Report visible units exceeding ten words."""
    findings: list[str] = []
    for number, unit in prose_units(text):
        visible = clean_prose(unit)
        count = len(WORD_RE.findall(visible))
        if count > MAX_WORDS:
            findings.append(f"{path}:{number}: {count} words: {visible.strip()}")
    return findings


def vocabulary_findings(root: Path = ROOT) -> list[str]:
    """Reject retired-stack and private-device vocabulary everywhere."""
    findings: list[str] = []
    for path in textual_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if RETIRED_RE.search(line):
                findings.append(
                    f"{path.relative_to(root)}:{number}: retired host-stack reference"
                )
            if PRIVATE_RE.search(line):
                findings.append(
                    f"{path.relative_to(root)}:{number}: private device identifier"
                )
    return findings


def local_link_findings(root: Path = ROOT) -> list[str]:
    """Reject missing local documentation targets."""
    findings: list[str] = []
    for path in markdown_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            for _label, raw in LINK_RE.findall(line):
                target = raw.strip("<>").split("#", 1)[0].split("?", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    findings.append(
                        f"{path.relative_to(root)}:{number}: missing link target: {target}"
                    )
    return findings


def archive_metadata_findings(root: Path = ROOT) -> list[str]:
    """Verify archive banners, index coverage, successors, and totals."""
    history = root / "docs" / "history" / "v1"
    index = history / "README.md"
    pages = sorted(path for path in history.rglob("*.md") if path != index)
    findings: list[str] = []
    indexed_text = index.read_text(encoding="utf-8")
    for page in pages:
        relative = page.relative_to(root)
        text = page.read_text(encoding="utf-8", errors="replace")
        head = "\n".join(text.splitlines()[:18])
        lines = text.splitlines()
        if not lines or ARCHIVE_HEADER_RE.fullmatch(lines[0]) is None:
            findings.append(f"{relative}: missing obsolete header")
        if ARCHIVE_STATUS_RE.search(head) is None:
            findings.append(f"{relative}: missing historical status")
        if ARCHIVE_ORIGINAL_RE.search(head) is None:
            findings.append(f"{relative}: missing original path")
        if ARCHIVE_DATE_RE.search(head) is None:
            findings.append(f"{relative}: missing archive date")
        successor = ARCHIVE_SUCCESSOR_RE.search(head)
        if successor is None:
            findings.append(f"{relative}: missing current successor")
        else:
            target = (page.parent / successor.group(1)).resolve()
            if not target.exists():
                findings.append(f"{relative}: missing current successor target")
        indexed_target = page.relative_to(history).as_posix()
        if indexed_text.count(f"]({indexed_target})") != 1:
            findings.append(f"{relative}: archive index coverage is not one")
    totals = [int(value) for value in ARCHIVE_TOTAL_RE.findall(indexed_text)]
    if totals != [len(pages)]:
        findings.append(
            f"docs/history/v1/README.md: archive total {totals}, expected {[len(pages)]}"
        )
    return findings


def required_current_findings(root: Path = ROOT) -> list[str]:
    """Verify each audience and integration seam remains represented."""
    findings: list[str] = []
    for relative, tokens in REQUIRED_CURRENT.items():
        path = root / relative
        if not path.is_file():
            findings.append(f"{relative}: required current page is missing")
            continue
        text = path.read_text(encoding="utf-8")
        findings.extend(
            f"{relative}: missing current documentation token: {token}"
            for token in tokens
            if token not in text
        )
    return findings


def section_lines(text: str, heading: str) -> list[str]:
    """Return the lines under one second-level heading."""
    lines: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line.strip() == heading
            continue
        if inside:
            lines.append(line)
    return lines


def status_findings(root: Path = ROOT, text: str | None = None) -> list[str]:
    """Require one status row for every maintained Markdown page."""
    if text is None:
        text = (root / STATUS_PAGE).read_text(encoding="utf-8")
    findings: list[str] = []
    seen: dict[str, str] = {}
    for line in section_lines(text, STATUS_HEADING):
        match = STATUS_ROW_RE.match(line.strip())
        if match is None:
            continue
        page, status = match.groups()
        if page in seen:
            findings.append(f"{STATUS_PAGE}: duplicate status row: {page}")
        seen[page] = status
        expected = "Historical" if page == HISTORY_ROW else "Current"
        if status != expected:
            findings.append(
                f"{STATUS_PAGE}: {page}: status {status!r}, expected {expected!r}"
            )
        target = root / page
        if not (target.is_dir() if page == HISTORY_ROW else target.is_file()):
            findings.append(f"{STATUS_PAGE}: status row names a missing page: {page}")
    if not seen:
        findings.append(f"{STATUS_PAGE}: no document status rows")
    if HISTORY_ROW not in seen:
        findings.append(f"{STATUS_PAGE}: no status row for {HISTORY_ROW}")
    for path in current_markdown(root):
        relative = path.relative_to(root).as_posix()
        if relative not in seen:
            findings.append(f"{STATUS_PAGE}: no status row for {relative}")
    return findings


def load_generator(root: Path = ROOT):
    """Import the microcode generator that owns the protocol constants."""
    spec = importlib.util.spec_from_file_location(
        "gen_gptp_ucode_docs", root / GENERATOR
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {GENERATOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def constant_findings(text: str, generator) -> list[str]:
    """Bind each constants-table value to the generator constant it names."""
    findings: list[str] = []
    seen: set[str] = set()
    for line in section_lines(text, CONSTANTS_HEADING):
        match = CONSTANT_ROW_RE.match(line.strip())
        if match is None:
            continue
        name, cell = match.groups()
        if name in seen:
            findings.append(f"{CONSTANTS_PAGE}: duplicate constant row: {name}")
        seen.add(name)
        actual = getattr(generator, name, None)
        if not isinstance(actual, int):
            findings.append(f"{CONSTANTS_PAGE}: {name} is not a generator constant")
        elif int(cell.replace(",", "")) != actual:
            findings.append(
                f"{CONSTANTS_PAGE}: {name} is {cell}, generator has {actual}"
            )
    if not seen:
        findings.append(f"{CONSTANTS_PAGE}: no protocol constant rows")
    return findings


def rom_usage(root: Path = ROOT, *extra: str) -> tuple[int, int]:
    """Run the generator as shipped and return (real words, depth)."""
    with tempfile.TemporaryDirectory() as directory:
        result = subprocess.run(
            [sys.executable, str(root / GENERATOR), *extra,
             "-o", str(Path(directory) / "gptp_ucode.hex")],
            check=True, capture_output=True, text=True,
        )
    match = re.search(r": (\d+) words, (\d+) real ", result.stdout)
    if match is None:
        raise ValueError(f"unexpected generator report: {result.stdout!r}")
    return int(match.group(2)), int(match.group(1))


def rom_findings(text: str, usage: dict[str, tuple[int, int]]) -> list[str]:
    """Bind the ROM budget table to the generator's own word count."""
    findings: list[str] = []
    seen: set[str] = set()
    for line in section_lines(text, ROM_HEADING):
        match = ROM_ROW_RE.match(line.strip())
        if match is None:
            continue
        image = match.group(1)
        used, depth, free = (int(value.replace(",", "")) for value in match.groups()[1:])
        seen.add(image)
        real_used, real_depth = usage[image]
        if (used, depth, free) != (real_used, real_depth, real_depth - real_used):
            findings.append(
                f"{ROM_PAGE}: {image} image reads {used} of {depth} with {free} free; "
                f"generator builds {real_used} of {real_depth}"
            )
    findings.extend(
        f"{ROM_PAGE}: no ROM budget row for the {image} image"
        for image in usage
        if image not in seen
    )
    return findings


def freshness_findings(root: Path = ROOT) -> list[str]:
    """Tie the constants and ROM budget tables to the generator."""
    generator = load_generator(root)
    findings = constant_findings(
        (root / CONSTANTS_PAGE).read_text(encoding="utf-8"), generator
    )
    usage = {
        "Shipping": rom_usage(root),
        "Seeded regression": rom_usage(root, "--seq-seed", hex(SEEDED_SEQ_SEED)),
    }
    findings.extend(rom_findings((root / ROM_PAGE).read_text(encoding="utf-8"), usage))
    return findings


def check(root: Path = ROOT) -> list[str]:
    """Run every documentation rule."""
    findings: list[str] = []
    history = root / "docs" / "history" / "v1"
    for path in current_markdown(root):
        findings.extend(
            style_findings(path.relative_to(root), path.read_text(encoding="utf-8"))
        )
        if history in path.parents:
            raise AssertionError("current page entered history")
    findings.extend(vocabulary_findings(root))
    findings.extend(local_link_findings(root))
    findings.extend(archive_metadata_findings(root))
    findings.extend(required_current_findings(root))
    findings.extend(status_findings(root))
    findings.extend(freshness_findings(root))
    return findings


def selftest() -> int:
    """Prove important wording and routing defects become visible."""
    arms = 0
    arms += 1
    long = "One two three four five six seven eight nine ten eleven."
    if not style_findings(Path("fixture.md"), long):
        print("docs selftest: long sentence escaped")
        return 1
    arms += 1
    if style_findings(Path("fixture.md"), "One two three four five."):
        print("docs selftest: short sentence failed")
        return 1
    arms += 1
    wrapped = "- One two three four five six\n  seven eight nine ten eleven.\n"
    if not style_findings(Path("fixture.md"), wrapped):
        print("docs selftest: wrapped long sentence escaped")
        return 1
    arms += 1
    wrapped_short = "- One two three four five\n  six seven eight nine ten.\n"
    if style_findings(Path("fixture.md"), wrapped_short):
        print("docs selftest: wrapped short sentence failed")
        return 1
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "README.md").write_text(
            "A " + "lin" + "ux reference.\n", encoding="utf-8"
        )
        arms += 1
        if not vocabulary_findings(root):
            print("docs selftest: retired vocabulary escaped")
            return 1
        (root / "README.md").write_text(
            "A " + "DS" + "20D reference.\n", encoding="utf-8"
        )
        arms += 1
        if not vocabulary_findings(root):
            print("docs selftest: private identifier escaped")
            return 1
        (root / "README.md").write_text("[missing](gone.md)\n", encoding="utf-8")
        arms += 1
        if not local_link_findings(root):
            print("docs selftest: missing link escaped")
            return 1
        (root / "target.md").write_text("# Target\n", encoding="utf-8")
        (root / "README.md").write_text("[present](target.md)\n", encoding="utf-8")
        arms += 1
        if local_link_findings(root):
            print("docs selftest: valid link failed")
            return 1
    missing = dict(REQUIRED_CURRENT)
    victim = next(iter(missing))
    arms += 1
    if not any(victim in finding for finding in required_current_findings(Path("/nonexistent"))):
        print("docs selftest: missing audience page escaped")
        return 1
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "docs" / "history" / "v1").mkdir(parents=True)
        (root / "README.md").write_text("# Root\n", encoding="utf-8")
        (root / "docs" / "README.md").write_text("# Map\n", encoding="utf-8")
        rows = {
            "README.md": "Current",
            STATUS_PAGE: "Current",
            HISTORY_ROW: "Historical",
        }

        def table(entries: dict[str, str]) -> str:
            """Render a status section holding one row per entry."""
            body = "".join(
                f"| `{page}` | Reader | Topic | {status} |\n"
                for page, status in entries.items()
            )
            return f"{STATUS_HEADING}\n\n| Page | Audience | Describes | Status |\n|---|---|---|---|\n{body}"

        arms += 1
        if status_findings(root, table(rows)):
            print("docs selftest: complete status table failed")
            return 1
        arms += 1
        if not status_findings(root, table({k: v for k, v in rows.items() if k != "README.md"})):
            print("docs selftest: unlisted page escaped")
            return 1
        arms += 1
        if not status_findings(root, table({**rows, "docs/GONE.md": "Current"})):
            print("docs selftest: status row for a missing page escaped")
            return 1
        arms += 1
        if not status_findings(root, table({**rows, "README.md": "Stale"})):
            print("docs selftest: wrong status escaped")
            return 1
        arms += 1
        if not status_findings(root, table(rows) + "| `README.md` | Reader | Topic | Current |\n"):
            print("docs selftest: duplicate status row escaped")
            return 1
    generator = load_generator(ROOT)
    good = f"{CONSTANTS_HEADING}\n\n| `SYNC_RTO_MS_C` | {generator.SYNC_RTO_MS_C} | ms |\n"
    arms += 1
    if constant_findings(good, generator):
        print("docs selftest: true constant failed")
        return 1
    arms += 1
    if not constant_findings(good.replace(f"| {generator.SYNC_RTO_MS_C} |",
                                          f"| {generator.SYNC_RTO_MS_C + 1} |"), generator):
        print("docs selftest: drifted constant escaped")
        return 1
    arms += 1
    if not constant_findings(good.replace("SYNC_RTO_MS_C", "NO_SUCH_C"), generator):
        print("docs selftest: unknown constant escaped")
        return 1
    arms += 1
    if not constant_findings(f"{CONSTANTS_HEADING}\n\nNo table.\n", generator):
        print("docs selftest: empty constants table escaped")
        return 1
    usage = {"Shipping": (1000, 1024), "Seeded regression": (1001, 1024)}
    rom = (f"{ROM_HEADING}\n\n| Image | Words used | Free |\n|---|---|---:|\n"
           "| Shipping | 1,000 of 1,024 | 24 |\n"
           "| Seeded regression | 1,001 of 1,024 | 23 |\n")
    arms += 1
    if rom_findings(rom, usage):
        print("docs selftest: true ROM budget failed")
        return 1
    arms += 1
    if not rom_findings(rom.replace("1,000 of", "999 of"), usage):
        print("docs selftest: drifted ROM count escaped")
        return 1
    arms += 1
    if not rom_findings(rom.replace("| 24 |", "| 25 |"), usage):
        print("docs selftest: drifted free count escaped")
        return 1
    arms += 1
    if not rom_findings(rom.replace("| Seeded regression |", "| Seeded |"), usage):
        print("docs selftest: missing ROM row escaped")
        return 1
    arms += 1
    if vocabulary_findings(ROOT):
        print("docs selftest: production vocabulary failed")
        return 1
    print(f"docs selftest: PASS ({arms} arms)")
    return 0


def main() -> int:
    """Run production checks or mutation controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    findings = check()
    if findings:
        print(f"docs check: FAIL ({len(findings)} findings)")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(
        f"docs check: PASS ({len(current_markdown())} current pages, "
        f"{len(markdown_files()) - len(current_markdown()) - 1} historical pages)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
