[R925] NEGATIVE - exact head 661e4c3a45904d2d8f3e061c67103a945651d9ff

# R925-2: independent re-review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111), round 2

- **Head**: `661e4c3a45904d2d8f3e061c67103a945651d9ff`, tree `97405b32d95b1b4397f77052d0faef868da20c2e`.
  Base `1213ac5b9e09b8759ba76cc70c53652b5e108996` (#108). Previously reviewed head `bbda770befae8748c1139c4e843c5874c5330048`.
- **Delta judged**: the one commit `bbda770..661e4c3`: `tb/verilator/engine/Makefile` (+49 -30),
  new `tb/verilator/engine/pass_run.py` (264 lines), new `tb/verilator/engine/passes_test.py` (329 lines),
  `docs/TEST_DEVELOPER.md` (+19 -6). No RTL, harness, generator, mutant or build-flag change.
- **Role**: internal independent reviewer, cleared context, own detached clone. No source edits, commits, pushes or
  GitHub writes. No other reviewer's round-2 report was read; the round-1 public findings were read only after my
  own pass over the delta.
- **Verdict**: NEGATIVE. Three MINOR findings are open (F1-F3). Every round-1 MAJOR and MINOR finding (R925-1 F1-F3,
  R926-1-01/02) is resolved at its cause, and the suggestions F4/F5 are taken.
  - **What works** (own execution): the passes are make jobs and stay in the caller's budget (real harness: peak 2
    simulators at `-j2`, 4 at `-j4`; the stub test: 1/2/4 and a parent `-j3` with two other jobs). Real-harness
    transcripts are IDENTICAL to the serial recipe's at matching flags. The 63-check `passes-test` passes in 90.4 s.
    Independent planted defects are caught. `make docs` and `make lint` pass.
  - **What is open**:
    - F1: a replayed core-dumping death writes the interpreter's core where the simulator's core was.
    - F2: a generator killed by a signal is replayed as `Error 245`, where the serial line said `Error 139`.
    - F3: the PR's CPU summary ("rise by 20-30 %") does not match its own concurrent pairs, and acceptance 2 is
      about CPU.

## 1. Authorities reconstructed

| Authority | What it fixes for this review |
|---|---|
| AGENTS.md / CONTRIBUTING.md | Neither is tracked at this head (`git ls-files`). The contributor guides are `README.md`, `docs/README.md` (truth order: RTL, then executable tests, then role guides) and `docs/TEST_DEVELOPER.md`. |
| Issue #111 (frozen body; no maintainer comments) | **Scope**: run the four passes "concurrently within the caller's job budget", print each pass "in the serial order under its serial heading", "keep every pass's verdict and the suite's exit code". **Acceptance 1**: transcript (host text removed) and exit code identical to the serial run's, clean and with a planted defect in one pass. **Acceptance 2**: wall time falls by the measured amount; "CPU stays within a few percent". |
| PR #112 body | Claims checked in §4 and §5: the pass targets, the replay rules, `-s`/`-i`/`-k`, fail fast, signals, the 63 checks, the nine planted defects, the measured table, the "Behaviour that differs" list. |
| Round-1 public findings | R925-1 F1 MAJOR, F2/F3 MINOR, F4/F5 SUGGESTION, F6/F7 RESIDUE; R926-1-01 MAJOR, -02 MINOR, -03/-04 RESIDUE. Resolved in §3. |
| Author evidence | `review-evidence/fgpasses-r1/author-r2` at `fab17af4fdfd59955b6e8ad671ac127bcb3af403`: REPORT.md §3 and `receipts/gptp/`. The 53 files I fetched all match the packet's `MANIFEST.json` published SHA-256 (`receipts/packet-verify.txt`). Four of them are path-redacted, with original and published hashes both recorded. |
| Owner comment rule (2026-10-15) | The added source comments cite #111. They contain no lane label, review round, reviewer ID or comment ID (grep of the added lines). |

## 2. Own executable evidence (this packet)

All of it was run at the exact head in this clone, or in extractions of it under `scratch/`. Pinned Verilator is
5.050 (`--version`: `Verilator 5.050 2026-07-01 rev v5.050`). GNU make is 4.4.1. The host was shared, with load
40-46 on 32 CPUs.

| Probe | Result | Receipt |
|---|---|---|
| `make -C tb/verilator/engine passes-test` | rc 0, 63 `[PASS]`, `engine passes test: PASS`, 90.36 s | `receipts/passes-test-head.log` |
| Real harness, three arms run concurrently on CPUs 0-15: base `-j4`, head `-j4`, head `-j2`, each extracted fresh by `git archive`, with a private cache. A sampler counted the live simulators whose cwd lies in each tree. | base 821.5 s, peak 1. Head `-j4` 276.3 s (2.97x), peak **4**. Head `-j2` 540.8 s, peak **2**. All rc 0. base vs head `-j4` and base vs head `-j2`: **IDENTICAL**, 171 normalised lines, the same sha256 `957c238f…` | `receipts/real-compare.txt`, `receipts/real/*/` |
| The author's published `c-base-j4/log` vs `c-head-j4/log`, through my own normaliser (`scripts/compare_real.py`), not the author's | IDENTICAL, 173 lines | `receipts/real-compare.txt` |
| Reviewer-written planted defects (`scripts/my_plants.sh`), each run through `passes_test.py` | CAUGHT: `MAKEFLAGS += -j4` in the Makefile (the parent-budget check); `.NOTPARALLEL:` (9 checks: out of order, budget reach, fail fast, signals); a signal death replayed as exit 1 (10); the `-k` replay suppression disabled (7); the generator status dropped in `replay-gen` (5). MISSED: the core-limit branch forced either way (2 plants), and the late-start re-check at `pass_run.py:136` removed. See S1/S2. | `receipts/plants/` |
| Extra plans beyond `passes_test.py` (`scripts/extra_plans.py`, using the test's own stubs and comparison): 7 plans x 12 flag sets, including the top image (`run`'s first prerequisite) refused, pass 0 SIGSEGV/SIGABRT, pass 3 image refused, passes 0 and 3 failing, pass 2 failing before pass 1; `-j2`, `-j3`, `-k -s`, `-i -k`, `-i -s`, `-j1 -k`, `-j1 -i`, `--no-print-directory`, `-w`, `-Otarget`, `-Oline` | 73 identical. The other 11 differ only in the recipe line number of the `gptp_ucode.hex` rule (`Makefile:98` → `:127`), the disclosed line-number difference that `norm()` masks only for `run`. | `receipts/extra-plans.log` |
| A target-specific `export` on a double-colon target (the #104 `CCACHE_BASEDIR`) | Reaches every `run::` rule and its prerequisites, so the ccache keying is unchanged | `receipts/doublecolon-export.txt`, `scripts/doublecolon-export.mk` |
| How a generator killed by a signal ends: serial line vs `pass_run.py` | serial `make: *** [Makefile:2: all] Error 139`; `pass_run.py`'s `subprocess.run(["/bin/sh","-c",GEN])` gives returncode -11, and `sys.exit(-11)` exits 245 | `receipts/gen-signal.txt`, `scripts/gen-signal.sh` |
| Flag detection `$(findstring i/s,$(firstword -$(MAKEFLAGS)))` under `-j4`, `--no-print-directory`, `MAKEFLAGS='-j4 --no-print-directory'`, `-k`, `-is`, `-O`, `--trace`, `-l`, `-I`, `-W`, `--debug` | Detects only a real `-i`/`-s`; long options never land in the first word | `receipts/flag-detect.txt`, `scripts/flag-detect.mk` |
| `make docs`, `make lint` (pinned Verilator) | both rc 0 | `receipts/gate-docs.log`, `receipts/gate-lint.log` |
| Clone integrity after the probes | HEAD, tree and index tree are `97405b32…`. The worktree and index match HEAD in bytes and modes. Nothing is untracked or ignored. No gitlinks, no `.gitmodules`. | `receipts/clone-integrity.txt` |

## 3. Prior findings at this head

| Prior finding | Status | Evidence at this head |
|---|---|---|
| R925-1 F1 MAJOR / R926-1-01 MAJOR: passes ignore the caller's budget | **RESOLVED** | Each pass is its own target, `engine-pass0..3` (`Makefile:65-93`). Make runs a double-colon rule's prerequisites only after the earlier rule finishes, so the passes start after the build. Stub budget checks: 1/2/4 at `-j1/-j2/-j4`, reached; a parent `make -j3` with two other jobs peaks at 3 in all. Real harness (own): peak 2 at `-j2`, 4 at `-j4`. Planted "all four in one job" (author) and `.NOTPARALLEL` / `MAKEFLAGS += -j4` (own) are all caught. |
| R925-1 F2 MINOR: transcript differs under `-s` and `-i` | **RESOLVED** | The echo is conditional on `s` (`Makefile:71`). `--ignore-errors` follows `i` (`Makefile:64`; `pass_run.py:121,159,198,213`). 20 `-s`/`-i` comparisons in `passes-test`, plus my `-i -s`, `-i -k`, `-j1 -i` and `-k -s` cases, are identical. |
| R925-1 F3 MINOR: signal deaths as `Error 128+n` | **RESOLVED** for the simulator (`pass_run.py:228-233` re-raises; SIGSEGV/SIGABRT/SIGKILL plans identical; my exit-1 plant caught by 10 checks; the author's real abort pair reads `Aborted (core dumped)` on both sides). The generator path has a residual divergence of the same kind: **F2**. |
| R925-1 F4 SUGGESTION: QUIT | **TAKEN** | QUIT, INT, TERM and HUP are forwarded (`pass_run.py:53,105-118`). `passes-test`: QUIT to the group leaves 0 simulators. |
| R925-1 F5 SUGGESTION: fail fast / order test | **TAKEN**, with progressive printing declined and disclosed (PR "Output timing") | `stop_later` and SIGUSR1 (`pass_run.py:110-114,170-177`). Fail-fast checks at `-j4`/`-j1` pass. The stub-driven order test exists (`passes_test.py`). |
| R925-1 F6 / R926-1-04 RESIDUE: no issue ID in the comment | **RESOLVED** | `Makefile:50` starts `# #111:`, as does `Makefile:95`. |
| R925-1 F7 / R926-1-03 RESIDUE: stale PR provenance | **RESOLVED** | The PR body now reads "Branch `engine-run-passes-at-once`: two commits on main `1213ac5` (#108), head `661e4c3…`". No "not pushed" text remains. |
| R926-1-02 MINOR: a lost transcript can still pass | **RESOLVED** | `replay` fails with `engine pass N: its transcript could not be printed` (`pass_run.py:222-225`), and `load` fails without a record (`:187-193`). The unreadable-transcript check passes, and the author's plant of it is caught. |

## 4. Findings

### R925-2-F1 - MINOR - Robustness, Docs: a replayed core-dumping death writes the interpreter's core over the simulator's

- **Where**:
  - `tb/verilator/engine/pass_run.py:228-233`. When the record says the pass dumped core, `replay` leaves the core
    limit alone and kills itself in make's working directory, `tb/verilator/engine`.
  - The PR body, "Behaviour that differs from the serial recipe", item "Core dumps".
- **Authority**:
  - Issue #111's scope is that only the scheduling changes. The PR body promises that the listed differences are
    the only ones.
  - The core(5) and fs/coredump.c semantics: with a file `core_pattern` such as the kernel default `core`, the dump
    goes to the dying process's cwd, and an existing file of that name is unlinked and replaced.
- **Evidence** (code and kernel semantics; not executed, because this host's `core_pattern` pipes to a handler and
  changing it needs privilege):
  - The setup: `core_pattern=core`, `core_uses_pid=0`, `ulimit -c` above 0, and pass 0's simulator aborts.
  - The serial recipe left the simulator's `tb/verilator/engine/core`.
  - The replay's `python3` then dies of the same signal in the same directory. Its core replaces the simulator's.
  - With `core_uses_pid=1`, or for passes 1-3 (whose simulators dump in the ignored `seedrun/` etc.), there is one
    more core file of the interpreter in `tb/verilator/engine/`. That path is not covered by `.gitignore`.
  - The PR discloses only the piped case ("one more core record").
- **Impact**:
  - A developer who enables cores to debug a pass-0 crash gets an interpreter core in its place, in exactly the
    planted-crash case acceptance 1 covers.
  - In the other cases, a new untracked file appears in the tree.
- **Required outcome**, both of:
  - Re-raise from a directory where the replay's core cannot replace the simulator's and stays out of the tracked
    tree, for example `os.chdir(STATE)` (inside ignored `obj_dir/`) just before `os.kill` in `replay`.
  - State the file-pattern behaviour in the PR's "Core dumps" item.
- **Verification**:
  - On a host with `core_pattern=core` and `ulimit -c unlimited`, a planted pass-0 SIGABRT (real harness or stub)
    leaves `tb/verilator/engine/core` as the simulator's core (`file core` names `Vengine_sim`), and
    `git status --short` shows nothing new.
  - Alternatively, a `passes-test` check that the re-raising replay's cwd (`/proc/<pid>/cwd`) is under `obj_dir/`.

### R925-2-F2 - MINOR - Conformance, Robustness, Tests: a generator killed by a signal is replayed as `Error 245`, not the serial `Error 139`

- **Where**:
  - `tb/verilator/engine/pass_run.py:126-129`. The generator runs as `/bin/sh -c GEN` with stdout set to DEVNULL,
    which drops the serial line's own `>/dev/null`. So the shell execs the generator, and `returncode` is negative
    on a signal death.
  - `pass_run.py:208`: `replay_gen` returns that negative number, and `sys.exit(-11)` exits 245.
- **Authority**:
  - Issue #111 acceptance 1 (transcript and exit status as the serial run's, with a planted defect in one pass).
  - The PR claim "Each replay line ends as the serial line ended: with the generator's or the simulator's exit
    status".
- **Evidence** (`scratch/gensig` probe, reproduced in §2):
  - The serial-form line `@python3 … >/dev/null`, killed by SIGSEGV, gives `make: *** [Makefile:2: all] Error 139`.
  - `pass_run.py`'s call gives returncode -11, and the replay exits 245.
  - The same mapping turns an OOM `SIGKILL` (`Error 137` serially) into `Error 247`.
  - No `passes-test` plan kills the generator.
- **Impact**:
  - The verdict and make's exit 2 survive.
  - make's message for that pass's line no longer matches the serial one, and the explicit fidelity claim is false
    for this case.
- **Required outcome**: record the generator status as the serial line had it. Either run the serial line itself
  (`… -o DIR/gptp_ucode.hex >/dev/null` through `/bin/sh`, standard error captured), or map a negative return code
  `-n` to `128 + n`. Add a plan whose generator dies of a signal.
- **Verification**: the new plan compares identical to the serial recipe at `-j4` and `-j1`, under no option, `-s`,
  `-i` and `-k`.

### R925-2-F3 - MINOR - Conformance, Docs: the CPU figure for acceptance 2 does not match the PR's own concurrent pairs

- **Where**:
  - The PR body, "Measured" → "CPU": "The CPU seconds of four simulators at once on a loaded host rise by 20-30 %".
  - The same sentence in the author's REPORT §3.2 ("CPU seconds +20-30 % at `-j4`").
- **Authority**:
  - Issue #111 acceptance 2, "CPU stays within a few percent".
  - The PR's own method: "the wall clock is compared within concurrent pairs", because the same serial arm took
    453 s, then 653 s.
- **Evidence** (`receipts/cpu-figures.txt`, from the author's `receipts/gptp/summary.txt`):

  | Comparison | CPU seconds |
  |---|---:|
  | Pair 1, head vs base | **+30.3 %** |
  | Pair 2, head vs base | **-16.5 %** |
  | Pair 2, the second head vs base | **-24.2 %** |
  | `-j1` pair | +3.6 % (the PR says +3.5 %) |
  | Pair 2's heads against pair 1's base (cross-pair) | +20.2 %, +9.2 % |

  - The "20-30 %" only appears if pair 2's heads are compared with pair 1's base, which the PR's method rules out.
  - The same base work took 451.6 vs 650.6 CPU-s in the two pairs (+44 %). So CPU seconds on this host track its
    load, and the work measure is instructions, which are +0.29 %.
- **Impact**:
  - The one acceptance criterion about CPU is argued from a figure that misreports the table. A reader cannot tell
    whether acceptance 2 is claimed as met (by instructions) or as failed (by CPU seconds).
  - This is a measurement claim, so it is not RESIDUE.
- **Required outcome**: report CPU seconds per concurrent pair (+30.3 %, -16.5 %, -24.2 % at `-j4`; +3.6 % at
  `-j1`). State that on this host CPU seconds are load-dominated. State that acceptance 2 is claimed on the work
  measure (instructions +0.29 % at `-j4`, +0.04 % at `-j1`). Make the same correction in the evidence REPORT.
- **Verification**: reread the PR's CPU bullet against `summary.txt`; every percentage is within one concurrent pair.

### R925-2-R1 - RESIDUE - Docs: stale duration in the test's docstring

- **Where**: `tb/verilator/engine/passes_test.py:31`, "Nothing is built or simulated; it takes seconds."
- **Evidence**: the Makefile (`:63`, `:96`), `docs/TEST_DEVELOPER.md` and the PR say about 90 s. Measured: 90.36 s
  (own) and 95.98 s (author).
- **Exact fix**: "Nothing is built or simulated; it takes about 90 seconds."
- **Effect on the verdict**: none, because this is wording only.

### R925-2-R2 - RESIDUE - evidence packet: the comparison tool is named by the wrong file

- **Where**: `author-r2/receipts/gptp/summary.txt`, line 1: "tools/logcmp.py (round 3's, unchanged) removes only
  host text".
- **Evidence**: the packet ships `tools/logcmp4.py`, which imports round 3's `logcmp.py` from an unpublished path.
- **Exact fix**: "tools/logcmp4.py (round 3's logcmp.py masks, plus this round's clone paths) removes only host
  text".
- **Effect on the verdict**: none. My own normaliser reproduces the author's IDENTICAL result on the published logs.

### Suggestions (do not affect the verdict)

- **S1 - Robustness, Tests: a signal that lands while the simulator is being spawned is not forwarded.**
  - `pass_run.py:133-137` re-checks `stopped` after `Popen`, but not `received`. An INT/TERM that arrives between
    the check at `:133` and `child.append` leaves the simulator running its whole pass while make waits.
  - Suggested fix: after the append, `if received: signal_all(child[0].pid, received[0])`.
  - My plant that removes the analogous `stopped` re-check (`:136`) is MISSED by `passes-test`. The window is
    narrow; a comment naming it would help.
- **S2 - Tests: the core-flag branch is not discriminated.**
  - Forcing `pass_run.py:229` either way (core limit always lowered, or never) is MISSED. On a piped
    `core_pattern`, a zero core limit does not stop the dump, and `no_cores()` sets that limit for every run.
  - Suggestion: say in the docstring that "(core dumped)" fidelity is host-dependent and checked only by the real
    abort pair. Or add a direct `replay` check with a crafted record `{"signal": 6, "core": false}` that asserts
    `WCOREDUMP` is clear on hosts where it can be.
- **S3 - Tests: wrapper failures outside the replay.**
  - A crash of `pass_run.py run` itself (an unwritable `obj_dir`, a file named `seedrun`) fails `engine-passN` with
    a Python traceback, not the serial `mkdir` message.
  - It fails safely: no false pass is possible, because `replay` without a record exits 1.
  - A one-line note in the PR's "Behaviour that differs" list would complete it.
- **S4 - Evidence: a self-contained comparer.**
  - `tools/logcmp4.py` cannot run from the public packet: it loads `logcmp.py` from an unpublished path.
  - Shipping the imported masks, or a standalone comparer such as `scripts/compare_real.py` here, would make the
    IDENTICAL claims reproducible from the packet alone.

### Recorded but not raised

- **Recipe line numbers** in make's own messages. They are disclosed, and they now differ also for the
  `gptp_ucode.hex` rule (98 → 127) because the Makefile grew. This is recipe-location text, as in round 1.
- **The build line's `--build -j 0`** sizes its own compile by CPU count, and its sub-make lacks `+` (the jobserver
  warning in the author's logs). Both are unchanged from base and disclosed under "Not done here".
- **`passes-test` under `make -jN all`** starts its own `make -j4`/`-j3` stub runs with `MAKEFLAGS` cleared. They
  are sleeping stubs and use no real CPU. This is not a budget problem.
- **`make -n run`** prints the wrapper commands rather than the serial lines. This is a dry-run diagnostic only.
- **Callers.** Without `-j` (or a parent jobserver) the suite now takes the serial time. This is disclosed, and it
  is consistent with the "within the caller's job budget" scope. See the manager duties.

## 5. Lens evidence

- **Conformance**:
  - Scope items 1-3 are met. Own evidence: the budget (stub and real), the serial order, the verdicts and the exit
    code, identical under every flag set tried apart from recipe line numbers.
  - Acceptance 1 is met for the clean run (own real-harness pair) and for a planted pass failure (63-check stub
    matrix, the author's real abort pair). It is open for the generator-signal case (F2).
  - Acceptance 2, wall: met (2.97x own; 2.05x/2.95x/3.60x author). Acceptance 2, CPU: argued from a misreported
    figure (F3). UNCLEAN.
- **RTL**: no RTL, generated microcode, harness or ROM change in the delta (`git diff --stat`). The delta does not
  change anything the RTL verdict depends on. `make lint` rc 0. CLEAN, as in round 1.
- **Robustness**: I checked all of these:
  - fail-fast races (the re-checks at `:121`, `:136`, `stop` under `failed_before`);
  - no false pass on any path (a missing record exits 1; every `.stop` has a failing replay before it);
  - `-k` after a build failure or a refused top image;
  - signal forwarding to the whole process tree, with ignored signals respected;
  - flag detection against long options;
  - the #104 cache variable on double-colon rules.

  Open: F1 (core overwrite) and F2 (generator status). S1 is noted. UNCLEAN.
- **Tests**:
  - `passes-test` reproduces 63/63.
  - The author's nine plants are verified from the receipts. Five independent plants are caught.
  - 84 extra cases run against the test's own reference.
  - The `SERIAL` reference in `passes_test.py:51-67` is byte-identical to base `1213ac5`'s recipe (checked
    programmatically).
  - The gap for F2 (no generator-signal plan) is part of F2. S2 is noted. UNCLEAN through F2.
- **Docs**:
  - `docs/TEST_DEVELOPER.md:52,63-79,99-103` matches the behaviour I observed. The engine README and the document
    map need no change. `make docs` rc 0.
  - The PR body's claims were checked against code and receipts. F1 (incomplete core disclosure) and F3 (CPU
    figure) are open, plus residue R1/R2. UNCLEAN.

## 6. Reviewer-owned ledger

| Lens | CLEAN/UNCLEAN | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN (F2, F3) | Issue #111 scope/acceptance; PR body; `Makefile:50-98`; real-harness pair (own) and author pairs; stub matrix + extra plans | R925-2 | 661e4c3a45904d2d8f3e061c67103a945651d9ff |
| RTL | CLEAN | `git diff --stat 1213ac5..661e4c3` (no `hdl/`, harness or generator change); `make lint` rc 0 | R925-2 (verdict carried from R925-1; delta does not touch its dependencies) | 661e4c3a45904d2d8f3e061c67103a945651d9ff |
| Robustness | UNCLEAN (F1, F2) | `pass_run.py` whole; `Makefile:64-93`; signal, fail-fast, `-k`, flag-detection and double-colon-export probes; core semantics | R925-2 | 661e4c3a45904d2d8f3e061c67103a945651d9ff |
| Tests | UNCLEAN (F2) | `passes_test.py` whole (63 checks, `SERIAL` fidelity); own run 63/63; author plants 9/9 (receipt); own 8 plants (5 caught, 3 missed → S1/S2); 84 extra cases | R925-2 | 661e4c3a45904d2d8f3e061c67103a945651d9ff |
| Docs | UNCLEAN (F1, F3; residue R1, R2) | `docs/TEST_DEVELOPER.md`, engine README, Makefile comments, `pass_run.py`/`passes_test.py` docstrings, PR body, author REPORT §3 and `summary.txt`; `make docs` rc 0 | R925-2 | 661e4c3a45904d2d8f3e061c67103a945651d9ff |

## 7. Real limits

- **F1 not executed.** It is derived from code and kernel core-dump semantics. This host's `core_pattern` pipes to a
  handler, and changing it needs privilege, which this review does not have.
- **No CPU-second or instruction measurement of my own.** My three real arms shared 16 CPUs of a host at load 40-46.
  Their walls (821.5 / 276.3 / 540.8 s) are within-run comparisons only.
- **Coarse sampler.** The simulator sampler polled about every 0.4 s under load (`receipts/real/*/samples`). Passes
  last minutes, so a peak above budget would have been seen, but sub-second overlaps would not.
- **No full bank.** No full parent, PP, gPTP, Yosys or builder bank was run. No hosted or act job was run. No
  hardware was used, and physical calibration was NOT RUN.
- **No source bank of the manager exists at this head**, and none is claimed. The execution evidence is my own
  probes, plus the author's published gate receipts (`receipts/gptp/`, verified against the packet manifest).

## 8. Pending manager duties

- Build and validate the current-dev merge candidate (source base `1213ac5`, live dev `e275d795…`) with the
  builder and native banks at the merge turn, and link those receipts.
- Make sure the parent bank gives this suite job slots: `-j4`, or a parent jobserver with four free slots.
  Otherwise the bank keeps the serial time the PR discloses.
- Carry R925-2-R1 and R925-2-R2 on the residue checklist.
- Own hosted and act acceptance. Obtain the second independent review.

## 9. Packet contents

- `REPORT.md` (this file).
- `MANIFEST.sha256`: every published receipt and script.
- `scripts/`:
  - `real_arm.sh`: real-harness arm with the simulator sampler.
  - `compare_real.py`: host-text normaliser and comparer.
  - `my_plants.sh`: reviewer planted defects.
  - `extra_plans.py`: extra plans and flags against the test's reference.
  - `doublecolon-export.mk`: the target-specific export probe.
  - `flag-detect.mk`: the `-i`/`-s` flag-word probe.
  - `gen-signal.sh`: the generator-signal probe.
- `receipts/`:
  - `packet-verify.txt`, `clone-integrity.txt`, `passes-test-head.log`, `extra-plans.log`, `plants/`;
  - `real/{base-j4,head-j4,head-j2}/`, `real-compare.txt`, `cpu-figures.txt`, `doublecolon-export.txt`;
  - `flag-detect.txt`, `gen-signal.txt`, `gate-docs.log`, `gate-lint.log`.

  Home and packet paths are masked.

R925-2 FINISHED
