#!/usr/bin/env python3
"""privacy.scrub_redact(b) == b for every file in a receipts directory: the raw
bytes, and for .gz / .tar.gz the decompressed contents of every member.
Usage: privcheck.py DIR"""
import gzip
import io
import sys
import tarfile
from pathlib import Path

sys.path.insert(0, "<home-path>/milan-fpga-management/2026-09-23")
import privacy  # noqa: E402


def check(name, data, bad):
    if privacy.scrub_redact(data) != data:
        bad.append(name)


def main():
    bad = []
    n = 0
    for p in sorted(Path(sys.argv[1]).rglob("*")):
        if not p.is_file():
            continue
        raw = p.read_bytes()
        n += 1
        check(str(p), raw, bad)
        if p.name.endswith(".tar.gz"):
            with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as t:
                for m in t.getmembers():
                    if m.isfile():
                        n += 1
                        check(f"{p}:{m.name}", t.extractfile(m).read(), bad)
        elif p.name.endswith(".gz"):
            n += 1
            check(f"{p}:(gunzip)", gzip.decompress(raw), bad)
    for b in bad:
        print(f"PRIVACY FAIL {b}")
    print(f"privacy: {n} objects checked, {len(bad)} fail")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
