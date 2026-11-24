# Replay and receipt map

This packet reviews source head `8e4889bba462d14d4e5a34068769872510d4775d` against base `1213ac5b9e09b8759ba76cc70c53652b5e108996`.

Use a detached clone containing those commits, Python with tar extraction filters, a C++17 compiler, make, the command wrapper, and the required 5.050 simulator. Run the scripts from a copy of this packet if existing receipts must be preserved. Paths derive from the scripts' own directory; every build, generated source, temporary directory and evidence extraction stays under `scratch/`.

```sh
rtk proxy python3 fetch_public_evidence.py /path/to/source-clone
rtk proxy python3 run_focused.py /path/to/source-clone --jobs 8 --simulator /path/to/5.050/verilator
rtk proxy python3 grade_receipts.py
rtk proxy python3 check_artifacts.py /path/to/source-clone
rtk proxy python3 check_builder_parser.py /path/to/source-clone
```

The build uses `make -j16`. Simulation workers are bounded by `--jobs` (1–16); the recorded run used eight. The driver stays in the foreground and waits for every task. It builds the unmodified exact-head harness once, then varies generated images in isolated run directories. Each of the eight #109 controls changes only its generator text in a disposable directory. No mutation edits the reviewed checkout. The four ordinary passes, base-image reproduction, eight controls, documentation gate and interface-contract gate each have their own `.log` and `.rc`.

`grade_receipts.py` reads already completed logs. A control must fail every named behavioral witness, not merely exit nonzero. The base reproduction is expected to fail; the four ordinary passes must be completely clean. `focused-results.json` records the final grading and witnesses.

The exact harness produces 31 failures against base, as recorded in `reproduction-reconciliation.txt`. The published historical receipt records 24 against an earlier zero-background-offset harness. All 24 historical named failures remain, with seven added exact-offset failures from the committed 11 ns background. The initial reviewer driver expected the historical count; its assertion was corrected. No simulation was rerun to change an outcome; the raw completed receipts are graded separately.

`check_artifacts.py` checks every tracked source blob and mode against HEAD, checks the index, verifies the lack of nested gitlinks, validates the public evidence hashes and full-arm ordering, regenerates committed images, and checks an independent arithmetic oracle. The public packet must first be fetched at the pinned evidence commit. `check_builder_parser.py` executes only the extracted public parent constant-parser functions against both generator revisions; it is not a builder bank.

`public-evidence-hashes.txt` records the immutable public packet and all twelve checked hashes. Public source receipt summaries are available at that packet's links; their disposable extraction is deliberately not republished here. `parent-shadow.sv`, `parent-requirements-excerpt.txt`, `parent-builder-excerpt.txt`, and `builder-parser-functions.py` preserve inspected public interface authorities at parent `e275d7950ef3385753e6a15d2e191ba855b171ed`. The parser function definitions are copied unchanged. PR body/discussion snapshots and exact-head hosting queries are also included.

`compile.log` has one private installation prefix redacted as documented in `receipt-redactions.txt`; original and published hashes are retained there, and the original stays only in `scratch/`. Behavioral simulation logs are unredacted. Only files named by `MANIFEST.sha256`, plus REPORT.md, are for publication. Nothing under `scratch/` is publishable.
