#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Check concise, current, private-safe, and reachable documentation."""

from __future__ import annotations

import argparse
import re
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
        "pub_commit_o",
    ),
    "docs/TEST_DEVELOPER.md": (
        "Python",
        "| C | None |",
        "C++",
        "make -C tb/verilator/engine",
    ),
    "docs/HDL_DEVELOPER.md": (
        "KL_gptp_rx_parser",
        "KL_gptp_timer",
        "KL_gptp_ucpu",
        "KL_gptp_tx_slot",
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
