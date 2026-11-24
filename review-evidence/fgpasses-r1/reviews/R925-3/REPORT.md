[R925] NEGATIVE - exact head f1b566a881573611637e7bd6ecd257799b8c991c

# R925-3: independent re-review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111), round 3

- Exact head `f1b566a881573611637e7bd6ecd257799b8c991c`, tree `c4cd0d38763e6d99ad35d8b6dc7e30db6fa38924`, source base `1213ac5b9e09b8759ba76cc70c53652b5e108996`.
- Review start: https://github.com/Mister-M-alt/FPGA-gPTP/pull/112#issuecomment-7146706951.
- Previously reviewed head (this reviewer): `661e4c3a` (R925-2, NEGATIVE). The delta judged here is `661e4c3a..f1b566a8`. It has two commits:
  - `0ba80c4f` is docs only: `docs/TEST_DEVELOPER.md`, +3 -1.
  - `f1b566a8` is code and test: `tb/verilator/engine/pass_run.py` +9 -2 and `passes_test.py` +29 -2.
- **Scope note.** The round brief describes "ONE docs commit 661e4c3a..0ba80c4f, nothing else changed". That describes the other reviewer's round at `0ba80c4f` (author packet `author-r3`). The head under review is `f1b566a8`, one more commit carrying code (author packet `author-r4`). That commit answers R925-2-F1 and R925-2-F2. I therefore reviewed both commits, and also both of the other reviewer's named findings (R926-2-F1, R926-2-F2).

**Verdict: NEGATIVE.** The docs commit, the criterion-2 amendment and the R926-2 findings are resolved. Two findings remain open:

- **F1 (MINOR).** `f1b566a8` adds a fallback that maps a generator shell's signal death to `128+n`. That path is unreachable on this host's bash. On a `/bin/sh` that execs the generator (as dash does), it is wrong in exactly the case it handles: make reports `Error 139` where the serial recipe reported `Segmentation fault (core dumped)`. Under emulation, the new passes-test plan then fails 5 of 5 comparisons.
- **F2 (MINOR).** One published CPU percentage (`-j1`) is misrounded.

## 1. Authorities reconstructed

- **Repository guides.** `AGENTS.md` and `CONTRIBUTING.md` do not exist in this repository. I used `README.md` and `docs/README.md`:
  - truth order: RTL, then tests, then current guides, then history;
  - `make docs` rules are `scripts/check_docs.py`.
- **`docs/TEST_DEVELOPER.md`** is the guide the delta edits.
- **Issue #111** (`receipts/issue111-body.md`, body updated 2026-11-24T21:52:48Z):
  - Criterion 1: the transcript (host text removed) and the exit code equal the serial run's at the same head, both clean and with a planted defect in one pass.
  - Criterion 2 (amended): wall time falls. Work is measured as retired user instructions (`instructions:u`) and stays within +1 % of the serial recipe at `-j1` and at `-j4`. CPU seconds and cycles are recorded and published for every pair, but they are not the gate.
- **The amendment** (`receipts/issue111-amendment.md`): issue comment 7145509264.
  - It was posted by the repository account with author association **OWNER**, under the manager role label, as the issue's author.
  - It states its rationale and data: CPU −24 %, −17 % and +30 % across three `-j4` pairs at identical instruction counts. The issue body was edited 2 s later to match.
- **Interface authority.** The serial recipe at base `1213ac5`, `tb/verilator/engine/Makefile:52-63`. Each generator line is `@python3 $(GEN) … -o DIR/gptp_ucode.hex >/dev/null`, which make runs through `/bin/sh -c`.
- **Public evidence.** Evidence tree `0e29af3b…/review-evidence/fgpasses-r1`:
  - `author-r2/receipts/gptp/summary.txt`, the measurements;
  - `author-r3`, the docs round, and `author-r4`, the `f1b566a8` round;
  - the copy of the amendment in `author-r3` is byte-identical to the public comment apart from the trailing newline.

## 2. Own executable evidence (this packet)

All probes ran in copies under `scratch/`. The clone was never modified (§7).

| Probe | Result | Receipt |
|---|---|---|
| `passes_test.py` at head (96 s) | rc 0; 69 `[PASS]`, 0 `[FAIL]`, including the 5 comparisons of the new `pass 1 image generator SIGSEGV` plan and check 6 | `receipts/passes-test-head.log`, `.rc` |
| M1: generator line without its `>/dev/null` (the pre-delta call) | **survives** (rc 0): bash then execs the generator, and the `128 - returncode` mapping turns -11 into the serial 139 | `receipts/mutants/m1-no-redirect.*` |
| M2: no `128 - returncode` mapping | **survives** (rc 0): with the redirection, bash forks, so the return code is never negative | `receipts/mutants/m2-raw-returncode.*` |
| M3: `os.chdir(STATE)` removed from `replay` | caught: check 6 FAIL (1 FAIL) | `receipts/mutants/m3-no-chdir.*` |
| M4: the end-of-run `SIGUSR1 → SIG_IGN` removed | survives one run (a race; see S4) | `receipts/mutants/m4-no-usr1-ignore.*` |
| M5: the forward after `Popen` of a signal received earlier, removed | survives one run (a race; see S4) | `receipts/mutants/m5-no-early-forward.*` |
| E1: a `/bin/sh` that execs a one-command `-c` line (dash's documented behaviour, emulated by a bash shim). Used as make's `SHELL` and as `pass_run.py`'s `/bin/sh`, for check 1 on the clean, pass-2 SIGSEGV, refused-image and generator-SIGSEGV plans | clean, pass-2 SIGSEGV and refused image: 16/16 PASS. **Generator SIGSEGV: 5/5 FAIL**, where serial `make: *** [Makefile:54: run] Segmentation fault (core dumped)` becomes `make: *** [Makefile:73: run] Error 139` | `receipts/mutants/e1-exec-sh.*`, `scripts/exec-sh-probe.sh` |
| `-i` and no-option behaviour against the new guide sentences: passes 1 and 2 fail, serial vs head, at `-j4`, `-j4 -i` and `-j1 -i` | Without `-i`: rc 2 and `Error 1` for pass 1; passes 2 and 3 are stopped, and nothing prints after pass 1. With `-i`: rc 0, all four print, and there are two `Error 1 (ignored)`. Serial and head are identical | `receipts/ignore-errors.txt`, `scripts/ignore_errors.py` |
| Criterion-2 arithmetic from `summary.txt` | instructions +0.293 % (`-j4`, all three pairs) and +0.040 % (`-j1`). CPU +30.279 %, −16.549 %, −24.205 % and `-j1` **+3.553 %**. `-j1` cycles +3.48 % | `receipts/figures.txt`, `scripts/figures.py` |
| Work effect of `f1b566a8` (the shell now forks the generator) | `instructions:u` of `sh -c 'true'` is 1.983 M; with `>/dev/null` it is 1.973 M. No measurable user work is added per generator line, so the `661e4c3` instruction figures carry to this head | `receipts/fork-instructions.txt` |
| `make docs`; `make lint` (pinned Verilator 5.050, identity checked) | both rc 0 | `receipts/make-docs.*`, `receipts/make-lint.*` |

## 3. Prior findings at this head

| Prior finding | Status | Evidence at this head |
|---|---|---|
| R925-2-F1 MINOR: a replayed core-dumping death writes the interpreter's core over the simulator's | **RESOLVED** | `pass_run.py:239` re-raises from `obj_dir/engine-passes/`. Check 6 PASS, and my M3 is caught. The PR "Core dumps" item (body lines 91-96) states both the piped case and the file `core_pattern` case. Limit: a file `core_pattern` was not executed (§7). |
| R925-2-F2 MINOR: a generator signal death replayed as `Error 245` | **RESOLVED on hosts whose `/bin/sh` forks a redirected command** (bash: 5/5 identical plus `-j1`). **Superseded by R925-3-F1** for shells that exec. One of the two outcomes my R925-2 offered, "map −n to 128+n", is wrong when the shell execs. I withdraw it: F1 below. |
| R925-2-F3 MINOR: CPU figures not per concurrent pair | **RESOLVED, except one figure** | The PR now gives +30.3 %, −16.5 % and −24.2 % per pair, says CPU seconds track host contention, and claims criterion 2 on instructions under the public amendment. The `-j1` figure is still "+3.5 %" where CPU seconds give +3.553 %: **R925-3-F2**. |
| R925-2-R1 RESIDUE: `passes_test.py:31` "it takes seconds" | **RETAINED** in R925-3-R2 | Unchanged at head. |
| R925-2-R2 RESIDUE: `summary.txt` names `tools/logcmp.py` | **RETAINED** | The `author-r2` packet is unchanged. R925-3-R3. |
| R925-2-S1: a signal during the simulator's spawn is not forwarded | **TAKEN** | `pass_run.py:140-141`. |
| R925-2-S2/S3/S4 (core flag not discriminated; wrapper crash text; self-contained comparer) | **RETAINED** as suggestions | The delta does not touch them. |
| R926-2-F1 MAJOR: CPU acceptance unproved | **RESOLVED** | The required outcome allowed "an explicit public maintainer acceptance amendment". Comment 7145509264 is one: OWNER, the issue author, public, with the issue body edited to match. My recomputation gives +0.293 % and +0.040 % instructions, so the measurements meet it. The PR "Measured" section states the amended gate, links it, gives both instruction figures and labels CPU "recorded, not the gate". The measurements are from `661e4c3`; my fork probe shows `f1b566a8` adds no user work. Remaining gaps: the `-j1` CPU figure (F2) and the cycles column (S2). |
| R926-2-F2 MINOR: the guide omits the `-i` exception | **RESOLVED** | `docs/TEST_DEVELOPER.md:75`, `:77` and `:79` are the three required sentences verbatim. My `receipts/ignore-errors.txt` confirms each against both recipes. `make docs` rc 0. |
| R926-3-R1 RESIDUE: stale PR opening | **RETAINED and extended** in R925-3-R1 | The PR now has four commits. |
| R926-2-S1 SUGGESTION: progressive printing | **RETAINED**, optional | Disclosed under "Output timing". |
| Round-1 findings resolved at R925-2 | **Still RESOLVED** | The delta changes neither the budget, the `-s`/`-i`/`-k` flags, simulator signal replay, nor print-failure handling. All 69 checks pass. |

## 4. Findings

### R925-3-F1 - MINOR - Conformance, Robustness, Tests, Docs: a generator shell that dies of a signal is replayed as `Error 128+n`, while the serial recipe reported the signal

- **Where**:
  - `tb/verilator/engine/pass_run.py:131`: `record["gen"] = done.returncode if done.returncode >= 0 else 128 - done.returncode`, then `replay_gen` returns that status (`:212-214`).
  - The comment at `:126`.
  - `author-r4/REVIEW-READY.md` ("a negative status maps to 128+n as a fallback").
  - The PR body lines 35-37: "Each replay line ends as the serial line ended … or by re-raising the same signal".
- **Authority**:
  - Issue #111 criterion 1: identical transcript and exit code, with a planted defect in one pass.
  - `f1b566a8`'s own claim: "Replay an image generator's signal death … as the serial recipe left them".
- **Evidence**:
  - `done.returncode` is negative only if `/bin/sh` itself died of the signal, that is, the shell exec'd the generator. In that case the serial recipe's shell, running the same line, also died of the signal, and make printed `Segmentation fault (core dumped)` (or `Killed` for an OOM kill), not `Error 139`/`Error 137`. So the fallback converts a signal ending into a status ending in the only case where it runs.
  - On this host's bash 5.3, a redirected command is forked, so the branch is unreachable. My M2 (no mapping) survives the suite.
  - With the redirection removed (M1), the mapping happens to produce bash's 139, so M1 also survives. Neither half of the fix is guarded alone; only the author's combined plant is caught.
  - Emulating a `/bin/sh` that execs the command (E1, both recipes under the same shell) makes all 5 comparisons of the new `pass 1 image generator SIGSEGV` plan FAIL: `Segmentation fault (core dumped)` serially, `Error 139` replayed. The other plans, including the simulator's SIGSEGV, stay identical, because `replay` re-raises recorded signals faithfully.
- **Impact**:
  - The verdict and make's exit 2 survive.
  - On a host whose `/bin/sh` execs the last simple command of `-c` (dash, the Debian/Ubuntu default), make's message for that line differs from the serial one.
  - On such a host `passes-test`, which is in the engine suite's `all`, would fail its own new plan. A bank on such a host would then fail `make -C gptp-processor all`. Whether the manager's builder bank uses such a shell is unknown to me (pending duty §9).
- **Required outcome**:
  - When the generator's shell ended by a signal (`returncode < 0`), record the signal and its core flag, as `run` does for the simulator. `replay-gen` should then end by that signal, as `replay` does: the core limit handled from the record, re-raised from `obj_dir/engine-passes/`.
  - Keep `128+n` only where the shell itself reported `128+n`, which is the positive return code already stored.
  - Make the branch testable on bash hosts, for example:
    - a `passes-test` check that feeds `replay-gen` a crafted record with a generator signal and asserts make's `Segmentation fault`/`Killed` line against the serial form;
    - or a plan whose generator line the shell execs.
  - Correct the comment at `:126` and the PR sentence if the behaviour stays shell-dependent.
- **Verification**: `scripts/exec-sh-probe.sh CLONE PACKET` gives 21/21 PASS, with the generator SIGSEGV plan identical under the exec-ing shell. The new check fails when the signal re-raise in `replay-gen` is removed, and `passes-test` stays PASS on bash.

### R925-3-F2 - MINOR - Docs: the `-j1` CPU figure is misrounded

- **Where**: PR body, Measured, line 128: "The `-j1` pair, the same work one pass at a time, is +3.5 %."
- **Authority**:
  - Amended criterion 2: CPU seconds "recorded and published for every pair".
  - The PR's own table: 458.8 s and 475.1 s.
- **Evidence**:
  - `summary.txt` gives 458.77 and 475.07 CPU-s, so +3.553 % (`receipts/figures.txt`). Even with ±0.005 s of rounding the ratio stays ≥ +3.5507 %, which is +3.6 % to one decimal.
  - The three `-j4` figures in the same bullet are rounded correctly from CPU seconds.
  - +3.5 % matches the `-j1` *cycles* (+3.48 %) instead.
  - The same figure was named in R925-2-F3's required outcome ("+3.6 % at `-j1`").
- **Impact**: a published measurement figure is wrong in the last digit, or comes from a different metric than its label. It is not the gate, so acceptance is unaffected. It is still a figure, so it is not RESIDUE under the owner rule.
- **Required outcome**: "is +3.6 %", or "+3.5 % in cycles" if cycles were meant.
- **Verification**: recompute 475.07 / 458.77 from `summary.txt`.

### R925-3-R1 - RESIDUE - Docs (PR body): stale branch paragraph

- **Where**: PR body lines 8-12: "two commits on main `1213ac5` (#108), head `661e4c3a…`", followed by a two-item commit list.
- **Evidence**: the PR has four commits, and its head is `f1b566a8`. The figures' provenance is public in the linked amendment ("base 1213ac5 against head 661e4c3"), so no measurement binding is lost.
- **Exact fix**:
  - Replace the opening sentence with: "Branch `engine-run-passes-at-once`: four commits on main `1213ac5` (#108), head `f1b566a881573611637e7bd6ecd257799b8c991c`."
  - Add two items to the list:
    - "`0ba80c4` states the `-i` exception to the first-failure rule in the test guide."
    - "`f1b566a` replays an image generator's signal death and a core dump as the serial recipe left them, and closes two signal races."
  - Optionally add to the Measured heading: "(base `1213ac5` against `661e4c3`; `f1b566a` adds no user work)".

### R925-3-R2 - RESIDUE - Tests/Docs (test docstring): `passes_test.py`'s check list lags the checks

- **Where**: `tb/verilator/engine/passes_test.py:12-31`.
  - The docstring lists checks 1-5. Check 6 (`replay_cwd`, `:322`) is missing.
  - Check 1's plan list names "a failing image generator", but not the new generator SIGSEGV plan.
  - "it takes seconds" is retained from R925-2-R1.
- **Exact fix**:
  - In item 1, after "a failing image generator", insert "and one killed by SIGSEGV".
  - Add item "6. A replayed signal death is re-raised from obj_dir/engine-passes/, so a file core_pattern keeps the simulator's core."
  - Change the last line to "Nothing is built or simulated; it takes about 90 seconds."

### R925-3-R3 - RESIDUE - evidence packet (retained R925-2-R2)

- `author-r2/receipts/gptp/summary.txt` line 1 names `tools/logcmp.py`. The tool that ran is `tools/logcmp4.py`.
- Exact fix, in the next packet's index: "tools/logcmp4.py (round 3's logcmp.py masks, plus this round's clone paths) removes only host text".

### Suggestions (do not affect the verdict)

- **S1 - Conformance: align the amended wording.**
  - The issue body's criterion 2 drops the comment's "favourable and unfavourable" and adds "because they track host contention".
  - Using the comment's sentence verbatim in the body would leave one text for the gate.
- **S2 - Docs: publish cycles beside CPU in the PR.**
  - The amended criterion says cycles are "recorded and published for every pair". They are in `summary.txt`, but the PR table has no cycles column and does not link the summary.
  - Add the column (1.666/2.165, 2.398/1.997/1.815 and 1.693/1.752 T) or a link.
- **S3 - Tests: guard each half of the generator fix.**
  - M1 and M2 each survive alone, because on bash each half compensates for the other.
  - The PR's "Planted defects" item 10 is honest that both are planted together. A per-half check (see F1) would keep either half from silently regressing.
- **S4 - Tests: make the two closed races deterministic.**
  - M4 and M5 survive a single suite run. The author's evidence is observational: failures before the fix (`passes-test-pt1.log`, `passes-test-pt-r4.log`) and six green runs after.
  - Deterministic options:
    - a direct check that a finished `run` ignores SIGUSR1: hold the process at exit and send it;
    - a check that a signal delivered while the child is spawning is forwarded: for example, a stub `Popen` wrapper that raises the signal before returning.
- **Retained from R925-2:** S2 (core flag not discriminated), S3 (a wrapper crash prints a traceback, not the serial `mkdir` text), S4 (a self-contained comparer). Retained from R926-2: S1 (progressive printing).

### Recorded but not raised

- **Comment rule.** The new comments (`pass_run.py:126`, `:141`, `:165`, `:239`; `passes_test.py:323`, `:330`) state behaviour and reason. None carries a bench lane label, lane name, review round, reviewer ID or comment ID. No RESIDUE.
- **TERM to `pass_run run` during the generator.** The generator is not in `child[]`, so a signal sent to the wrapper alone is not forwarded to it. The generator runs to completion (seconds), and then the wrapper dies of the signal. This was the same before the delta: the shell now forks the generator rather than exec'ing it, but neither level was forwarded. Group signals (check 4) reach it.

## 5. Lens evidence

- **Conformance.** Criterion 1:
  - Bash: 69/69, including the new generator-SIGSEGV plan under no option, `-s`, `-i` and `-k` at `-j4`, and at `-j1`.
  - Exec-ing shell (emulated): the generator-SIGSEGV plan diverges (**F1**).

  Criterion 2 is amended by a public OWNER decision and met: instructions +0.293 % and +0.040 %. CPU is published per pair; one figure is misrounded (**F2**). **UNCLEAN** (F1).
- **RTL.** The delta touches no HDL, generator or microcode. `make lint` rc 0 at head. **CLEAN.**
- **Robustness.**
  - The races are closed in code and look correct:
    - `SIG_IGN` is set before the record is written, and CPython leaves an `IgnoreHandler` signal alone at finalization;
    - the forward after `Popen` covers the spawn window.
  - The `chdir(STATE)` re-raise is correct.
  - The generator signal path is wrong on exec-ing shells (**F1**). **UNCLEAN** (F1).
- **Tests.**
  - The new plan and check 6 are real. M3 is caught.
  - M1 and M2 each survive, and the fallback branch cannot be exercised on bash (**F1**, S3).
  - M4 and M5 survive single runs (S4). **UNCLEAN** (F1).
- **Docs.**
  - `TEST_DEVELOPER.md:75/77/79` is correct against my `-i` and no-option receipt. `make docs` rc 0.
  - PR body: **F2** (figure); R1 and R2 are wording (RESIDUE).
  - The F1 comment and PR sentence follow F1. **UNCLEAN** (F1, F2).

## 6. Reviewer-owned ledger

| Lens | CLEAN/UNCLEAN | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN (F1) | issue #111 body and amendment 7145509264 (OWNER); serial recipe at `1213ac5`; `summary.txt`; PR Measured section; head passes-test; E1 emulation | R925-3 (delta `661e4c3..f1b566a`); unchanged coverage carried from R925-2 | f1b566a881573611637e7bd6ecd257799b8c991c |
| RTL | CLEAN | delta file list (no HDL/ucode/generator); `make lint` rc 0 | R925-3; R925-2 verdict carried for untouched RTL | f1b566a881573611637e7bd6ecd257799b8c991c |
| Robustness | UNCLEAN (F1) | `pass_run.py:120-173`, `:202-241`; M4/M5; E1; fork-instruction probe | R925-3 | f1b566a881573611637e7bd6ecd257799b8c991c |
| Tests | UNCLEAN (F1) | `passes_test.py` delta (plan, GEN stub, check 6); head run 69/69; M1-M5; E1; `author-r4` receipts (pt-s1..s6 PASS 69, plant-gen 5 FAIL, plant-cwd 1 FAIL) | R925-3 | f1b566a881573611637e7bd6ecd257799b8c991c |
| Docs | UNCLEAN (F1, F2) | `docs/TEST_DEVELOPER.md:60-84`; `receipts/ignore-errors.txt`; `make docs` rc 0; PR body; `passes_test.py` docstring; new comments against the comment rule | R925-3 | f1b566a881573611637e7bd6ecd257799b8c991c |

## 7. Real limits

- **F1 is shown by emulation, not on a real dash.** There is no dash or busybox on this host, and installing one is not allowed. The probe's shim execs a one-command `-c` line, which is what dash (0.5.11 and later) does for the last command of `-c`. Both recipes ran under the same shim. Whether the real builder's `/bin/sh` behaves so was not observed.
- **File `core_pattern` not executed.** This host's `core_pattern` pipes to `systemd-coredump`, and changing it needs privilege. R925-2-F1's resolution therefore rests on code, check 6 and M3.
- **Races.** The two closed races were not reproduced deterministically. M4 and M5 surviving one run each is expected for races.
- **Measurements.** They are the author's, at `661e4c3` on a shared host. I recomputed them from the published summary and did not re-measure. My fork probe bounds `f1b566a8`'s work effect at about zero per generator line.
- **Execution evidence.** No manager source bank exists at this head, and none is claimed or inferred. This repository tracks no hosted workflows, so no hosted job exists to distinguish. Physical calibration was NOT RUN, and field skips are not hardware proof.
- **Clone state.** It was restored and verified (`receipts/restore-check.txt`):
  - HEAD `f1b566a8…`, tree `c4cd0d38…`, and the index tree equals HEAD's;
  - there are no porcelain lines, ignored files included, and `git diff HEAD` is empty for bytes and modes;
  - the repository has no submodule gitlinks (0 entries of mode 160000), so none were required.

## 8. Order of reading

- My own pass came first: the delta, my probes, then the verdict and ledger, written to this file as a draft.
- Only then did I read the other reviewer's R926-2 and R926-3 findings, to resolve them in §3.
- My own R925-2 report was read after the diff pass.

## 9. Pending manager duties

- Validate the current-dev merge candidate (source base `1213ac5`, live dev `e275d795`) on the builder and native banks at the merge turn, and link the receipts.
- **Check the builder's `/bin/sh`.** If it execs the last command of `-c` (dash), expect the new generator-SIGSEGV plan of `passes-test` to fail there until F1 is fixed.
- Carry R925-3-R1, R2 and R3 to the residue checklist.
- Hosted/act acceptance; the existing source-comment labels tracked by #746.

## 10. Packet contents

`MANIFEST.sha256` lists every published receipt and script. Disposable trees and downloaded evidence copies stay under `scratch/` and are not published.

R925-3 FINISHED
