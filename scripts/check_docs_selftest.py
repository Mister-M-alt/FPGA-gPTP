# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Fixture arms of scripts/check_docs.py: each planted defect must show.

check_docs.py --selftest runs them. They live in their own module so that
each module and function stays within the parent repository's Python
length rules (#98); the arms, their order and their messages are those
check_docs.py carried.
"""

from __future__ import annotations

import tempfile
import types
from pathlib import Path

from check_docs import (
    CONSTANTS,
    CONSTANTS_HEADING,
    CONSTANTS_PAGE,
    HISTORY_ROW,
    REQUIRED_CURRENT,
    ROM_HEADING,
    ROOT,
    STATUS_HEADING,
    STATUS_PAGE,
    constant_findings,
    copy_findings,
    load_generator,
    local_link_findings,
    required_current_findings,
    rom_findings,
    status_findings,
    style_findings,
    vocabulary_findings,
)


#: the eleven-word sentence the style arms plant, one word over MAX_WORDS
_LONG = "One two three four five six seven eight nine ten eleven."


def _selftest_sentences() -> int | None:
    """Sentence-length arms; the arm count, or None after a failure."""
    arms = 0
    arms += 1
    if not style_findings(Path("fixture.md"), _LONG):
        print("docs selftest: long sentence escaped")
        return None
    arms += 1
    if style_findings(Path("fixture.md"), "One two three four five."):
        print("docs selftest: short sentence failed")
        return None
    arms += 1
    wrapped = "- One two three four five six\n  seven eight nine ten eleven.\n"
    if not style_findings(Path("fixture.md"), wrapped):
        print("docs selftest: wrapped long sentence escaped")
        return None
    arms += 1
    wrapped_short = "- One two three four five\n  six seven eight nine ten.\n"
    if style_findings(Path("fixture.md"), wrapped_short):
        print("docs selftest: wrapped short sentence failed")
        return None
    return arms


def _selftest_vocabulary_and_links() -> int | None:
    """Vocabulary, link and audience-page arms; the arm count, or None."""
    arms = 0
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "README.md").write_text(
            "A " + "lin" + "ux reference.\n", encoding="utf-8"
        )
        arms += 1
        if not vocabulary_findings(root):
            print("docs selftest: retired vocabulary escaped")
            return None
        (root / "README.md").write_text(
            "A " + "DS" + "20D reference.\n", encoding="utf-8"
        )
        arms += 1
        if not vocabulary_findings(root):
            print("docs selftest: private identifier escaped")
            return None
        (root / "README.md").write_text("[missing](gone.md)\n", encoding="utf-8")
        arms += 1
        if not local_link_findings(root):
            print("docs selftest: missing link escaped")
            return None
        (root / "target.md").write_text("# Target\n", encoding="utf-8")
        (root / "README.md").write_text("[present](target.md)\n", encoding="utf-8")
        arms += 1
        if local_link_findings(root):
            print("docs selftest: valid link failed")
            return None
    missing = dict(REQUIRED_CURRENT)
    victim = next(iter(missing))
    arms += 1
    if not any(victim in finding for finding in required_current_findings(Path("/nonexistent"))):
        print("docs selftest: missing audience page escaped")
        return None
    return arms


def _selftest_status() -> int | None:
    """Status-table arms; the arm count, or None after a failure."""
    arms = 0
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
            return None
        arms += 1
        if not status_findings(root, table({k: v for k, v in rows.items() if k != "README.md"})):
            print("docs selftest: unlisted page escaped")
            return None
        arms += 1
        if not status_findings(root, table({**rows, "docs/GONE.md": "Current"})):
            print("docs selftest: status row for a missing page escaped")
            return None
        arms += 1
        if not status_findings(root, table({**rows, "README.md": "Stale"})):
            print("docs selftest: wrong status escaped")
            return None
        arms += 1
        if not status_findings(root, table(rows) + "| `README.md` | Reader | Topic | Current |\n"):
            print("docs selftest: duplicate status row escaped")
            return None
    return arms


def _selftest_constants() -> int | None:
    """Constants-table arms; the arm count, or None after a failure."""
    arms = 0
    generator = load_generator(ROOT)
    good = f"{CONSTANTS_HEADING}\n\n| Constant | Value |\n|---|---:|\n" + "".join(
        f"| `{name}` | {getattr(generator, name):,} |\n" for name in CONSTANTS
    )
    sync = f"| {generator.SYNC_RTO_MS_C} |"
    stale = generator.SYNC_RTO_MS_C + 1
    arms += 1
    if constant_findings(good, generator):
        print("docs selftest: true constants table failed")
        return None
    arms += 1
    if not constant_findings(good.replace(sync, f"| {stale} |"), generator):
        print("docs selftest: drifted constant escaped")
        return None
    arms += 1
    if not constant_findings(good.replace("SYNC_RTO_MS_C", "NO_SUCH_C"), generator):
        print("docs selftest: unknown constant escaped")
        return None
    arms += 1
    if not constant_findings(f"{CONSTANTS_HEADING}\n\nNo table.\n", generator):
        print("docs selftest: empty constants table escaped")
        return None
    for label, cell in (("bold", f"**{stale}**"), ("negative", "-1"),
                        ("unit-bearing", f"{stale} ms"), ("bold true", f"**{stale - 1}**")):
        arms += 1
        named = constant_findings(good.replace(sync, f"| {cell} |"), generator)
        if not any("SYNC_RTO_MS_C value" in finding for finding in named):
            print(f"docs selftest: {label} constant cell escaped")
            return None
    arms += 1
    deleted = "".join(line + "\n" for line in good.splitlines() if "SYNC_RTO_MS_C" not in line)
    if not constant_findings(deleted, generator):
        print("docs selftest: deleted constant row escaped")
        return None
    arms += 1
    if not constant_findings(good.replace("`SYNC_RTO_MS_C`", "SYNC_RTO_MS_C"), generator):
        print("docs selftest: unnamed constant row escaped")
        return None
    arms += 1
    row = next(line for line in good.splitlines() if "`SYNC_RTO_MS_C`" in line)
    named = constant_findings(f"{good}{row}\n", generator)
    if not any("duplicate constant row: SYNC_RTO_MS_C" in finding for finding in named):
        print("docs selftest: duplicate constant row escaped")
        return None
    return arms


def _copy_fixture() -> tuple[str, types.SimpleNamespace]:
    """The constants table and generator stand-in the copy arms share."""
    fixture = types.SimpleNamespace(
        SYNC_RTO_MS_C=375, FU_RTO_MS_C=125, CEASE_MS_C=300_000,
        STEP_LINKUP_NS_C=20_000, RATE_PPM_C=200,
    )
    table = (f"{CONSTANTS_HEADING}\n\n| Constant | Value | Meaning |\n|---|---:|---|\n"
             "| `SYNC_RTO_MS_C` | 375 | syncReceiptTimeout, ms |\n"
             "| `FU_RTO_MS_C` | 125 | Follow_Up receipt timeout, ms |\n"
             "| `CEASE_MS_C` | 300,000 | Cease countdown, ms |\n"
             "| `STEP_LINKUP_NS_C` | 20,000 | Step threshold, ns |\n"
             "| `RATE_PPM_C` | 200 | Rate bound, ppm |\n"
             "| Sync interval | 375 ms | Literal kept in the home |\n")
    return table, fixture


def _selftest_copies_kept() -> int | None:
    """Copy arms that must stay quiet or catch a plain copy; the count, or None."""
    arms = 0
    table, fixture = _copy_fixture()
    linked = "The [`SYNC_RTO_MS_C`](INTEGRATION.md#protocol-constants) Sync watch.\n"
    arms += 1
    if copy_findings({"docs/GUIDE.md": linked, CONSTANTS_PAGE: table}, table, fixture):
        print("docs selftest: linked constant or its home row failed")
        return None
    arms += 1
    if copy_findings({"docs/GUIDE.md": "```\nsleep 375 ms\n```\n"}, table, fixture):
        print("docs selftest: fenced command failed")
        return None
    arms += 1
    if copy_findings({"docs/GUIDE.md": "A 1.375 ms gap and 3,750 ms.\n"}, table, fixture):
        print("docs selftest: unrelated number failed")
        return None
    for label, copy in (
        ("plain", "A 375 ms Sync watch."),
        ("grouped", "A 300,000 ms countdown."),
        ("converted", "A 20 us threshold."),
        ("second-converted", "A 300 s countdown."),
        ("spelled", "The five-minute countdown."),
        ("rate", "Inside 200 ppm."),
        ("outside the home", f"{table}\n## Next\n\nA 375 ms watch.\n"),
    ):
        arms += 1
        if not copy_findings({CONSTANTS_PAGE: copy}, table, fixture):
            print(f"docs selftest: {label} constant copy escaped")
            return None
    for label, text in (
        ("decimal minutes", "A 2.5 min hold."),
        ("decimal minute word", "Wait 0.5 minutes."),
        ("larger number word", "A twenty-five minutes soak."),
        ("word starting min", "At least 5 minimum samples."),
        ("tilde fence", "~~~\nsleep 375 ms\n~~~\n"),
        ("unit-word prefix", "A 375 msec gap."),
        ("larger number", "A 1375 ms gap."),
        ("underscores between word characters", "snake_5_min"),
        ("underscores between word characters in code", "`snake_5_min`"),
        ("content of a longer tilde fence", "~~~~\n~~~\nA 375 ms watch.\n~~~~\n"),
        ("content of a longer backtick fence", "````\n```\nA 375 ms watch.\n````\n"),
        ("backtick line in a tilde fence", "~~~\n```\nA 375 ms watch.\n~~~\n"),
        ("tilde line in a backtick fence", "```\n~~~\nA 375 ms watch.\n```\n"),
        ("close marker with text", "~~~\n~~~ x\nA 375 ms watch.\n~~~\n"),
        ("close marker before a form feed", "~~~\n~~~\x0c\nA 375 ms watch.\n~~~\n"),
        ("close marker indented four", "~~~\n    ~~~\nA 375 ms watch.\n~~~\n"),
        ("tilde info string holding markers", "~~~ a`b~\nA 375 ms watch.\n~~~\n"),
        ("fence inside a list item", "1.  Item.\n\n    ```\n    A 375 ms watch.\n    ```\n"),
        ("fence on a list marker", "- ```\n  A 375 ms watch.\n  ```\n"),
        ("fence on a nested list marker", "- - ```\n    A 375 ms watch.\n    ```\n"),
        ("tab-indented fence in a list item", "1.  Item.\n\n\t```\n\tA 375 ms watch.\n\t```\n"),
        ("blank line in a list-item fence", "- ```\n  x\n\n  A 375 ms watch.\n  ```\n"),
        ("fence after an empty list item", "-\n ```\nA 375 ms watch.\n```\n"),
        ("fence after an HTML comment", "<!-- x -->\n```\nA 375 ms watch.\n```\n"),
        ("fence after an indented comment marker", "    <!--\n```\nA 375 ms watch.\n```\n"),
        ("unindented line in an indented fence", "  ```\nA 375 ms watch.\n  ```\n"),
    ):
        arms += 1
        if copy_findings({"docs/GUIDE.md": text}, table, fixture):
            print(f"docs selftest: {label} failed")
            return None
    return arms


def _selftest_copies_caught() -> int | None:
    """Copy arms each copy shape must trip; the arm count, or None."""
    arms = 0
    table, fixture = _copy_fixture()
    rto, follow_up, cease = "SYNC_RTO_MS_C", "FU_RTO_MS_C", "CEASE_MS_C"
    for label, copy, name in (
        ("unspaced minutes", "A 5min countdown.", cease),
        ("number word and min", "A five min countdown.", cease),
        ("copy after a tilde fence", "~~~\n```\n~~~\nA 375 ms watch.\n", rto),
        ("copy after a longer tilde fence", "~~~~\n~~~\n~~~~\nThe Sync watch is 375 ms.\n", rto),
        ("copy after a tilde close with text",
         "~~~text\nliteral\n~~~ not a close\nmore\n~~~\nThe Sync watch is 375 ms.\n", rto),
        ("copy after a longer backtick fence", "````\n```\n````\nThe Sync watch is 375 ms.\n", rto),
        ("copy after a backtick close with text", "```\n``` x\n```\nA 375 ms watch.\n", rto),
        ("copy after an inner info-string tilde", "~~~sh\n~~~ x\n~~~\nA 375 ms watch.\n", rto),
        ("second copy after a longer tilde fence",
         "~~~~text\n~~~\n~~~~\n\nThe Sync receipt timeout is 125 ms.\n", follow_up),
        ("second copy after an inner tilde info",
         "~~~text\n~~~example\n~~~\n\nThe Sync receipt timeout is 125 ms.\n", follow_up),
        ("second copy after a four-tilde block",
         "~~~~text\nexample\n~~~~\n\nThe Sync receipt timeout is 125 ms.\n", follow_up),
        ("copy after a close with trailing blanks", "~~~\n~~~  \t\nA 375 ms watch.\n", rto),
        ("copy after a close indented three", "~~~\n   ~~~\nA 375 ms watch.\n", rto),
        ("copy after a marker indented four", "    ~~~\nA 375 ms watch.\n", rto),
        ("copy after a marker tab-indented", "\t~~~\nA 375 ms watch.\n", rto),
        ("copy after a two-character run", "~~\nA 375 ms watch.\n", rto),
        ("copy after a backtick info with a backtick", "``` a`b\nA 375 ms watch.\n", rto),
        ("copy after a fence on a list marker", "- ```\n  x\n  ```\nA 375 ms watch.\n", rto),
        ("copy after a list item ended its fence", "- Item.\n  ```\n  x\n\nA 375 ms watch.\n", rto),
        ("copy after a marker in an HTML comment", "<!--\n```\n-->\nA 375 ms watch.\n", rto),
        ("copy after a comment on a list marker", "- <!--\n  ```\n  -->\nA 375 ms watch.\n", rto),
        ("copy under a list marker indented four", "    - ```\n      A 375 ms watch.\n", rto),
        ("copy after a list-item fence",
         "1.  Item.\n\n    ```\n    x\n    ```\n    A 375 ms watch.\n", rto),
        ("underscore unit copy", "The Sync watch is _375 ms_.", rto),
        ("underscore digit minutes", "After _5 minutes_ it ceases.", cease),
        ("underscore word minutes", "After _five minutes_ it ceases.", cease),
        ("underscore second copy", "The Sync receipt timeout is _125 ms_.", follow_up),
        ("underscore digit minutes opening", "A _5 minutes_ countdown.", cease),
        ("underscore word minutes opening", "A _five minutes_ countdown.", cease),
        ("asterisk second copy", "The Sync receipt timeout is *125 ms*.", follow_up),
        ("strong underscore", "A __375 ms__ watch.", rto),
        ("nested markup", "A _**375 ms**_ watch.", rto),
        ("code span", "A `375 ms` watch.", rto),
        ("markup on the value alone", "A **375** ms watch.", rto),
        ("underscore on the value alone", "A _375_ ms watch.", rto),
        ("code span on the value alone", "A `375` ms watch.", rto),
        ("markup on the unit alone", "A 375 *ms* watch.", rto),
        ("markup on digit minutes before a hyphen", "A **5**-minute countdown.", cease),
        ("markup on the minute word after a hyphen", "A 5-*minute* countdown.", cease),
        ("markup inside the value", "A 37*5* ms watch.", rto),
        ("code span against the value", "`hold`five minutes", cease),
        ("two spaces before the unit", "A 375  ms watch.", rto),
    ):
        arms += 1
        if not any(f"restates {name}" in finding
                   for finding in copy_findings({"docs/GUIDE.md": copy}, table, fixture)):
            print(f"docs selftest: {label} constant copy escaped")
            return None
    for cell in ("syncReceiptTimeout ms", "syncReceiptTimeout in ms", "syncReceiptTimeout (ms)"):
        arms += 1
        unit = table.replace("syncReceiptTimeout, ms", cell)
        if not any("restates SYNC_RTO_MS_C" in finding
                   for finding in copy_findings({"docs/GUIDE.md": "A 375 ms watch."}, unit, fixture)):
            print(f"docs selftest: copy of a row whose Meaning ends {cell!r} escaped")
            return None
    arms += 1
    planted = f"{CONSTANTS_HEADING}\n\n```\n## Next\n```\nA 375 ms watch.\n"
    if copy_findings({CONSTANTS_PAGE: planted}, table, fixture):
        print("docs selftest: heading inside a fence closed the home section")
        return None
    arms += 1
    planted = "```\n## Protocol constants\n```\nA 375 ms watch.\n"
    if not copy_findings({CONSTANTS_PAGE: planted}, table, fixture):
        print("docs selftest: heading inside a fence opened the home section")
        return None
    return arms


def _selftest_fences_and_misses() -> int | None:
    """Fenced-sentence arms and the expected misses (#96); the count, or None."""
    arms = 0
    table, fixture = _copy_fixture()
    arms += 1
    if not style_findings(Path("fixture.md"), f"````\n```\n````\n{_LONG}\n"):
        print("docs selftest: long sentence after a longer fence escaped")
        return None
    arms += 1
    if style_findings(Path("fixture.md"), f"~~~\n{_LONG}\n~~~\n"):
        print("docs selftest: long line in a tilde fence failed")
        return None
    # Expected failures: real copies the rule misses today. Catching one fails
    # its arm here, and the case then moves to the must-fail arms above (#96).
    for label, page, copy in (
        ("decimal seconds", "docs/GUIDE.md", "A 0.375 s watch."),
        ("spelled unit", "docs/GUIDE.md", "A 375 milliseconds watch."),
        ("wrapped line", "docs/GUIDE.md", "The Sync watch is 375\nms long.\n"),
        ("link on the value", "docs/GUIDE.md", "A [375](x.md) ms watch."),
        ("HTML tag on the value", "docs/GUIDE.md", "A <b>375</b> ms watch."),
        ("HTML entity as the space", "docs/GUIDE.md", "A 375&nbsp;ms watch."),
        ("strikethrough on the value", "docs/GUIDE.md", "A ~~375~~ ms watch."),
        ("marker in an HTML block", "docs/GUIDE.md", "<pre>\n```\n</pre>\n\nA 375 ms watch.\n"),
        ("indented heading after the home", CONSTANTS_PAGE, f"{table}\n  ## Aside\n\nA 375 ms watch.\n"),
        ("fence after a lazy list line", "docs/GUIDE.md", "- Item.\nlazy\n  ```\nA 375 ms watch.\n"),
    ):
        arms += 1
        if copy_findings({page: copy}, table, fixture):
            print(f"docs selftest: expected failure now caught: {label}")
            return None
    return arms


def _selftest_rom() -> int | None:
    """ROM budget and production vocabulary arms; the count, or None."""
    arms = 0
    usage = {"Shipping": (1000, 1024), "Seeded regression": (1001, 1024)}
    rom = (f"{ROM_HEADING}\n\n| Image | Words used | Free |\n|---|---|---:|\n"
           "| Shipping | 1,000 of 1,024 | 24 |\n"
           "| Seeded regression | 1,001 of 1,024 | 23 |\n")
    arms += 1
    if rom_findings(rom, usage):
        print("docs selftest: true ROM budget failed")
        return None
    arms += 1
    if not rom_findings(rom.replace("1,000 of", "999 of"), usage):
        print("docs selftest: drifted ROM count escaped")
        return None
    arms += 1
    if not rom_findings(rom.replace("| 24 |", "| 25 |"), usage):
        print("docs selftest: drifted free count escaped")
        return None
    arms += 1
    if not rom_findings(rom.replace("| Seeded regression |", "| Seeded |"), usage):
        print("docs selftest: missing ROM row escaped")
        return None
    arms += 1
    if not rom_findings(rom.replace("1,000 of", "**999** of"), usage):
        print("docs selftest: formatted ROM count escaped")
        return None
    arms += 1
    if not rom_findings(rom + "| Shipping | 1,000 of 1,024 | 24 |\n", usage):
        print("docs selftest: duplicate ROM row escaped")
        return None
    arms += 1
    if vocabulary_findings(ROOT):
        print("docs selftest: production vocabulary failed")
        return None
    return arms


def selftest() -> int:
    """Prove important wording and routing defects become visible."""
    arms = 0
    for arm_group in (_selftest_sentences, _selftest_vocabulary_and_links, _selftest_status,
                      _selftest_constants, _selftest_copies_kept, _selftest_copies_caught,
                      _selftest_fences_and_misses, _selftest_rom):
        count = arm_group()
        if count is None:
            return 1
        arms += count
    print(f"docs selftest: PASS ({arms} arms)")
    return 0
