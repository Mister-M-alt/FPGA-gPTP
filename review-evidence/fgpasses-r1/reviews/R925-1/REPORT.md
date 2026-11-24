[R925] NEGATIVE - exact head bbda770befae8748c1139c4e843c5874c5330048

# R925-1: independent review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111)

- **Head**: `bbda770befae8748c1139c4e843c5874c5330048`, tree `f4ea8ea4b503f8680d571c14394eb7235650ee77`. This is
  one commit on base `1213ac5b9e09b8759ba76cc70c53652b5e108996` (#108).
- **Delta**: `tb/verilator/engine/Makefile` (+27 -11) and `docs/TEST_DEVELOPER.md` (+8).
- **Role**: internal independent reviewer, cleared context, working in its own detached clone. No source edits,
  commits, pushes or GitHub writes. No other reviewer's report was read.
- **Verdict**: NEGATIVE. One MAJOR finding and two MINOR findings are open (F1-F3).
  - **What works**:
    - The clean transcripts are byte-identical.
    - A planted check failure keeps its verdict and the non-zero exit.
    - There are no file races.
    - INT and TERM stop all four passes.
  - **What fails**:
    - The recipe does not stay within the caller's job budget, which the scope of #111 requires.
    - The transcript still differs from the serial run under `make -s`, under `make -i`, and when a pass is
      killed by a signal.

## 1. Authorities reconstructed

| Authority | What it fixes for this review |
|---|---|
| AGENTS.md / CONTRIBUTING.md | Neither file exists at this head (`git ls-files`). The contributor-facing guides are the repository README, `docs/README.md` and `docs/TEST_DEVELOPER.md`. |
| Issue #111 body (frozen) | **Scope**: "run the engine suite's four passes concurrently **within the caller's job budget**, print each pass's output in the serial order under its serial heading, keep every pass's verdict and the suite's exit code." **Acceptance 1**: the transcript (host text removed) and the exit code are identical to the serial run's at the same head, both clean and with a planted defect in one pass. **Acceptance 2**: wall time falls by the measured amount, and CPU stays within a few percent. |
| Issue #111 comments | There are none, so no later maintainer or manager scope decision exists. |
| PR #112 body and comments | The body gives the author's description, the disclosed failure-only differences and the measurements. The only comments are two review-start notices (R925-1 and R926-1). There are no reviews and no review comments. |
| Owner comment rule (2026-10-15) | New source comments state behaviour and reason with issue or requirement IDs. They show no lane labels, review rounds, reviewer IDs or comment IDs. |
| Interfaces touched | The transcript and exit status of the `run` recipe, which `make -C ... all` banks consume. `mutants.py` runs its own two passes through `subprocess` (`tb/verilator/engine/mutants.py:640-650`) and does not use `run`. The RTL, the generator and the harness are untouched: `git diff --stat 1213ac5..bbda770 -- hdl bench syn scripts` is empty. |
| Public evidence | `review-evidence/fgpasses-r1/author` at `0e37e261`, fetched read-only into a disposable directory. It contains REPORT section 5, `receipts/gptp/{serial,parallel}/{log,time,perf}`, `fail-test.log`, `term-test.log` and `tools/{gprun3.sh,logcmp.py}`. |

**Prior public review findings on PR #112**: none exist at this head. There are no reviews and no review comments,
and the only issue comments are the two start notices. There is nothing to resolve or retain.

## 2. Own executable evidence (this packet)

**Setup**:
- All probes ran in disposable `git archive` copies of the exact head under `scratch/`.
- The serial variants (`S-*`) use the engine Makefile from base `1213ac5`. The parallel variants (`P-*`) use the
  Makefile at head. Nothing else differs between them.
- Verilator is the pinned 5.050 wrapper (`Verilator 5.050 2026-07-01 rev v5.050`, wrapper sha256
  `905795b9...e92f`).
- Each run is `make -j1 run`, pinned with `taskset`. The runs used 16 CPUs in all and ran at the same time.
- The host is shared and was at load ~150. There was a single run per variant.

| Pair (receipts/compare.txt) | Normalised transcript | make status | Wall / CPU (user+sys) |
|---|---|---|---|
| S-clean (1 CPU) vs P-clean (4 CPUs) | 167 = 167 lines, **byte-identical** | 0 / 0 | 1266.9 s / 827.0 s vs 561.1 s / 859.0 s (2.26x faster; CPU +3.9 %) |
| S-clean vs P1cpu-clean (4 passes on 1 CPU) | **byte-identical** | 0 / 0 | 878.0 s / 831.3 s (CPU +0.5 %) |
| S-fail vs P-fail (planted failing check in pass 1, `seedrun/`) | Identical except make's recipe line (`Makefile:55` vs `Makefile:65`) | 2 / 2, recipe status 1 / 1. Pass 1's `FAIL planted seedrun defect` and `2200 checks: 2199 PASS, 1 FAIL` survive, and passes 2-3 print in neither | 939.4 s / 551.2 s vs 579.5 s / 860.0 s |
| S-abort vs P-abort (planted SIGABRT in pass 2, `syncseedrun/`) | **Differs**: `Aborted (core dumped)` vs `Error 134` (F3) | 2 / 2 | 899.7 s / 555.5 s vs 434.6 s / 572.2 s |

**Normalisation**:
- The normaliser (`scripts/norm.py`) drops only host text:
  - the echoed `verilator --cc` line;
  - the compiler, ccache and includer lines it runs (checkout path, CPU count);
  - make's directory chatter;
  - Verilator's build statistics.
- The author's figures check out against their receipts:
  - wall time: 2721.59 s to 974.61 s;
  - CPU: 817.72 to 836.79 CPU-s (+2.33 %) (`receipts/figures.txt`).
- The host load differs, so I did not try to reproduce the absolute figures. My ratio (2.26x on 4 CPUs under
  contention) is consistent with "about its longest pass".

**Races**:
- After the build, the tree gains only two kinds of file (`receipts/files-written-after-build.txt`):
  - the three seeded images, which are written before any pass starts;
  - `obj_dir/pass0..3.out`, one per pass.
- The four images are distinct (`receipts/images.sha256`).
- Neither `sim_main.cpp` nor `verilator_harness.hpp` opens a file.
- The tracked `gptp_ucode.hex` was unchanged after a run.
- There is no shared scratch file or output file.

**Recipe logic with a stub harness** (`scripts/stubtest.sh`): the exact recipes run with `VERILATOR=true` and a
stub that writes to stdout and stderr in turn.
- **Normal exits.** With exits 0, 1, 2, 3, 5, 7 and 9 in any pass, the transcripts are identical once make's
  recipe line is masked. The first failing pass in order sets the status (`receipts/stubtest-default.txt`).
- **Signal deaths** produce different transcripts (F3).
- **`make -s` and `make -i`** produce different transcripts (F2) (`receipts/stubtest-silent.txt`,
  `receipts/stubtest-ignore-errors.txt`).

**Signals** (`scripts/inttrace.sh`, `receipts/inttrace.txt`): the recipe shell was traced, and make started with
INT and QUIT at their defaults, as it does from a terminal.

| Signal sent | Result |
|---|---|
| INT to the recipe shell | All four passes killed; make reports `Error 130` |
| INT to make's whole process group (Ctrl-C) | All four passes killed |
| TERM to the recipe shell | All four passes killed; make reports `Error 143` |
| QUIT to the group | The passes survive (F4) |

A note on method: if make is launched in the background from a script, INT is already ignored on entry, so the
INT trap cannot be installed. The serial recipe behaves the same way in that case and would not stop either.

**Job budget** (`receipts/job-budget.txt`, sampled every 10 s): at `make -j1`, each parallel tree (P-clean, P-fail,
P1cpu-clean) had **4 live simulators**. Each serial tree had 1 (F1).

**Gates at head** (on a copy of head): `make docs` rc 0 and `make lint` rc 0 (`receipts/gates-rc.txt`, with the
logs beside it).

**Hosted checks**: the exact head has 0 check runs, and its combined status is `pending` with 0 contexts. The tree
contains no workflow. No hosted job executed, so there is nothing to credit.

## 3. Findings

### F1 - MAJOR - Conformance, Robustness, Tests, Docs: the four passes ignore the caller's job budget

**Where**:
- `tb/verilator/engine/Makefile:65-72`: the four `&` launches in one recipe line.
- `docs/TEST_DEVELOPER.md:62-68`.
- `tb/verilator/engine/Makefile:50-57`.

**Authority**: the scope of issue #111, "concurrently within the caller's job budget".

**Evidence**:
- **Four passes at `-j1`.** Under `make -j1 run`, four simulators run at once in every parallel tree
  (`receipts/job-budget.txt`). The author's own measurement shows the same thing: `receipts/tools/gprun3.sh`
  exports `MAKEFLAGS='-j1 ...'`, and the parallel run still used four cores.
- **No budget check in the recipe.** The recipe never consults make's `-j` or jobserver, nor the CPU affinity.
  Under a caller's `-jN`, `run` holds one job slot but loads four CPUs, which makes N+3 CPU-bound processes.
- **Measured effect on other work.**
  - The test: run on one shared, loaded CPU, with the CPU work equal (831 vs 827 CPU-s).
  - The result: four passes on that CPU took 878 s, against 1267 s for the serial run.
  - The reason: on a loaded CPU, four tasks get a larger share of the scheduler than one task does. The extra
    share comes from the other work on that CPU.
- **No serial option in the guide.** For the mutants, the guide documents `--jobs` and says "one job keeps the
  serial order". It gives the suite no serial switch, and it does not say that `-j` does not govern the passes.

**Impact**:
- The issue's only resource constraint is not met, so "Closes #111" would close the issue with that constraint
  unmet.
- The motivating context is a loaded shared host running a `-jN` bank. On that host, each engine run uses three
  more CPUs than make granted.

**Required outcome**, either of:
- **Option 1: keep the passes within the caller's budget.**
  - For example, make each pass its own make target that writes its output and status to its own file. make's
    `-j` and jobserver then schedule the passes.
  - `run` prints them in the serial order and exits at the first failing one.
  - `make run` at `-j1` then runs one pass at a time, and `-j4` runs all four at once.
- **Option 2: get a recorded maintainer decision.** The decision, recorded on #111, would accept a fixed four-way
  fan-out. The guide and the Makefile comment would then state it and name the serial alternative.

**Verification**:
- The sampler shows at most N live simulators at `-jN`, for N = 1, 2 and 4.
- The clean and planted transcripts stay identical (`scripts/campaign.sh`, `scripts/stubtest.sh`).
- Wall time at `-j4` stays near the longest pass.

### F2 - MINOR - Conformance, Tests: the transcript differs from the serial run under `make -s` and `make -i`

**Where**:
- `tb/verilator/engine/Makefile:64`: `@echo ./obj_dir/Vengine_sim`.
- `tb/verilator/engine/Makefile:65-79`: all four passes run in one recipe line.

**Authority**: acceptance 1 of issue #111 (the transcript is identical to the serial run's), and the scope item
"keep every pass's verdict".

**Evidence**:
- **`make -s`.** The serial recipe prints no command echo, but the parallel `@echo` still prints
  `./obj_dir/Vengine_sim`. Every plan differs by that one line (`receipts/stubtest-silent.txt`).
- **`make -i`.**
  - Serial: the recipe ignores a failing pass's line, then runs and prints every later pass with its verdict.
  - Parallel: the recipe runs all four passes but prints nothing after the first failing one. The later passes'
    verdicts are lost, including any failures of their own (`receipts/stubtest-ignore-errors.txt`, plans 2-4
    and 6).
- The PR body discloses neither difference.

**Impact**:
- Under standard make options, the transcript is not the serial one.
- Under `-i`, a later failing pass's verdict is hidden.

**Required outcome**:
- Echo the command only when make would echo it. For example, use
  `$(if $(findstring s,$(firstword -$(MAKEFLAGS))),,@echo ./obj_dir/Vengine_sim)`, or let make echo a real recipe
  line.
- Under `-i` (an `i` in make's flag word), print every pass.
- Alternatively, record both differences as accepted on #111 or #112.

**Verification**: `STUB_MAKEFLAGS=-s scripts/stubtest.sh` and `STUB_MAKEFLAGS=-i scripts/stubtest.sh` report
IDENTICAL for every plan once make's recipe line number is masked.

### F3 - MINOR - Conformance, Robustness, Tests: a pass killed by a signal is reported as `Error 128+n`, not by its signal name

**Where**: `tb/verilator/engine/Makefile:72-79` (`exit $$rN`).

**Authority**: acceptance 1 of issue #111, the planted-defect transcript.

**Evidence**:
- **Real harness**, with a planted SIGABRT in pass 2 (`receipts/compare.txt`, `receipts/runs/S-abort`,
  `receipts/runs/P-abort`):
  - the serial run ends `make: *** [Makefile:59: run] Aborted (core dumped)`;
  - the parallel run ends `make: *** [Makefile:65: run] Error 134`.
- **Stub harness** (`receipts/stubtest-default.txt`, plans 7-9):
  - `Segmentation fault (core dumped)` becomes `Error 139`;
  - `Killed` becomes `Error 137`.
- **What survives.** The verdict lines and make's exit status 2 survive. But a crash, an abort or an OOM kill no
  longer reads as one.
- **PR claim.** The PR body says "So the transcript is the serial one, byte for byte". It discloses the
  `Error <status>` form, but not that signals become numbers.

**Impact**: a planted defect of the crash class (a harness or model segfault, an abort, an OOM kill) gives a
transcript that differs from the serial one, and the diagnostic loses the signal name.

**Required outcome**, either of:
- After printing the failing pass, re-raise its signal when its status is above 128, so that make reports the same
  death. For example: `trap - INT TERM; kill -s $(( r - 128 )) $$$$`.
- Record the difference as accepted, and correct the byte-for-byte claim in the PR.

**Verification**: stub plans 7-9 and the real S-abort/P-abort pair compare IDENTICAL, with only make's recipe line
number masked.

### F4 - SUGGESTION - Robustness: QUIT (Ctrl-\) does not stop the passes

- **Where**: `tb/verilator/engine/Makefile:66-67`.
- **Evidence**:
  - The asynchronous passes start with QUIT ignored, and the recipe traps only INT and TERM.
  - QUIT sent to the terminal's process group left all four passes running, and make waited for them
    (`receipts/inttrace.txt`, "QUIT to group").
  - In the serial recipe, QUIT reaches the single foreground simulator and stops it.
- **Note**: the Makefile comment claims only INT and TERM, so the comment is accurate.
- **Suggestion**: trap QUIT (and HUP) the same way.

### F5 - SUGGESTION - Robustness, Tests: on a failure, every pass still runs to its end before anything prints

- **Where**: `tb/verilator/engine/Makefile:72`.
- **Evidence**:
  - P-fail used 860 CPU-s, against 551 CPU-s for S-fail (+56 %).
  - The first verdict waits for the slowest pass.
- **Suggestions**:
  - Wait in the serial order: print each pass as soon as it and every earlier pass have finished, and stop the
    later passes at the first failure. The transcript stays the same, and it prints progressively.
  - Add a stub-driven test of print order and exit status, in the manner of `mutants-order-test`. It would keep
    F2 and F3 from regressing.

### F6 - RESIDUE - Docs: the new Makefile comment cites no issue ID

- **Where**: `tb/verilator/engine/Makefile:50`.
- **Authority**: the owner comment rule of 2026-10-15. Source comments state behaviour and reason with issue IDs,
  and the surrounding comment blocks cite #82, #100, #102 and #104.
- **Scan result**: the added lines contain no lane label, review round, reviewer ID or comment ID.
- **Exact fix**: change `# The four passes are independent:` to `# #111: the four passes are independent:`.
- **Effect on the verdict**: none, because this is wording only.

### F7 - RESIDUE - PR body: stale provenance text

- **Where**: the PR #112 body.
- **Evidence**: the PR is open and closes #111, so two passages no longer hold:
  - "Branch: ... in a scratch clone of Mister-M-alt/FPGA-gPTP. Not pushed. No FPGA-gPTP Issue exists for it: it
    comes from ..."
  - "Nothing was pushed and no PR was opened; the owner of this repository decides."
- **Exact fix**:
  - Replace the first passage with "Branch: `engine-run-passes-at-once` at `bbda770` on main `1213ac5` (#108),
    tracked by #111; it comes from ...".
  - Delete the "Nothing was pushed" bullet.
- **Effect on the verdict**: none, because this is wording only.

### Recorded but not raised

- **Line number in make's error line.** For every failing pass, make names `Makefile:65` instead of that pass's own
  recipe line. The PR body discloses this, and it follows from any edit to the recipe. I treated it as
  recipe-location text rather than suite transcript. The manager may rule otherwise.
- **Generator refusal order.** If the generator refuses a seeded image, the run now stops before pass 0 prints.
  The PR discloses this.
- **The "never more" timing claim.** The PR says that on fewer cores the run "takes up to the serial time and never
  more". My contended-CPU result does not contradict this (878 s against 1267 s). On an idle single core, the
  PR's own +2.3 % CPU figure suggests the run would take about 2 % longer than serial. This is not a finding.

## 4. Lens evidence

- **Conformance**:
  - The scope and acceptance come from #111.
  - **Acceptance 1:**
    - met for the clean case and the planted check failure: the transcripts are identical and the exit statuses
      are kept;
    - not met under `-s` or `-i` (F2);
    - not met for signal deaths (F3).
  - **Acceptance 2:** the wall and CPU figures check out against the receipts.
  - **Job-budget scope:** not met (F1).
- **RTL**:
  - The delta changes no RTL, generator, harness or image.
  - The tracked image was unchanged after a run.
  - `make lint` returns rc 0.
  - All 4 × 2199 + 61 checks pass at head, with byte-identical lines.
- **Robustness**:
  - **Signals:** INT and TERM stop all passes; QUIT does not (F4).
  - **Races:** none found.
  - **Status propagation:** correct for normal exits, but a signal death is reported as a number instead of the
    signal name (F3).
  - **Job budget:** exceeded (F1).
  - **Failure cost:** all passes run to the end even after a failure (F5).
- **Tests**:
  - I re-checked the author's receipts. After path substitution, the serial and parallel logs differ only in
    Verilator's walltime statistics line.
  - I ran my own real-harness campaign (7 runs) and the stub campaigns.
  - The author's proof covers failures by exit status only. It does not cover `-s`, `-i`, signals or the job
    budget (F1-F3).
  - No permanent test guards the behaviour (F5).
- **Docs**:
  - `docs/TEST_DEVELOPER.md:62-68` adds four sentences. They are accurate for what they state, and `make docs`
    returns rc 0.
  - The guide is silent on the job budget and offers no serial switch (F1).
  - The new comment lacks an issue ID (F6).
  - The PR body is stale (F7).

## 5. Reviewer-owned ledger

| lens | CLEAN/UNCLEAN | examined artifacts | covering round | exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN (F1, F2, F3) | #111 scope and acceptance, PR #112 body, `Makefile:39-79`, receipts/compare.txt, stubtest-*.txt, job-budget.txt, author time/perf receipts | R925-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| RTL | CLEAN | delta file list (no hdl/generator/harness change), images.sha256, tracked image after a run, gate-lint.log, 4-pass check tallies | R925-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| Robustness | UNCLEAN (F1, F3) | `Makefile:65-79`, inttrace.txt, sigtest.txt, files-written-after-build.txt, stub signal plans, Verilator 5.050 `vl_fatal` (exits 1, does not abort) | R925-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| Tests | UNCLEAN (F1, F2, F3) | author serial/parallel logs, fail-test.log, term-test.log, logcmp.py, gprun3.sh; own 7-run campaign and stub campaigns | R925-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| Docs | UNCLEAN (F1); RESIDUE F6, F7 | `docs/TEST_DEVELOPER.md:45-75`, `tb/verilator/engine/README.md`, Makefile comments `:39-57`, PR body, gate-docs.log | R925-1 | bbda770befae8748c1139c4e843c5874c5330048 |

**Clone integrity after the probes** (`receipts/clone-integrity.txt`):
- HEAD is `bbda770b...`, and `git write-tree` gives `f4ea8ea4...`.
- All 120 tracked files hash to their index blobs, with matching modes.
- The index matches the tree of HEAD (modes and blobs).
- There are no untracked or ignored files.
- No submodule gitlinks are required, because there is no `.gitmodules` at this head.

## 6. Real limits

- **Shell.** `/bin/sh` on this host is bash, and dash is not installed. The traps, `wait` and `$!` were exercised
  only under bash. POSIX dash behaviour was not tested.
- **Timing.** There was one run per variant, on a host at load ~150. My timings show direction and ratios, not the
  author's absolute figures.
- **Terminal.** Behaviour on a tty was not exercised, including line buffering and the loss of live per-pass
  progress while all four passes run.
- **Wider suites.** `make all` (the mutants arms) and the parent bank were not run. `mutants.py` does not use the
  `run` recipe.
- **Abort plant.** The planted abort is in the harness. In Verilator 5.050 a failing assertion (`$error` or
  `$stop`) exits with status 1, because `vl_fatal` calls `std::exit(1)` unless debug is on. That path therefore
  behaves like the planted check failure.
- **Hardware.** Physical calibration NOT RUN. No hardware was involved, and no field skip counts as hardware proof.
- **Manager source bank.** None exists at this head, and none is claimed or inferred.

## 7. Pending manager duties

- At the merge turn, build and validate the current-dev merge candidate with the builder and native banks:
  - source base `1213ac5b9e09b8759ba76cc70c53652b5e108996`;
  - live dev `e275d7950ef3385753e6a15d2e191ba855b171ed`.

  Then link the receipts on the PR.
- Hosted and act acceptance. No hosted job has executed at this head (0 check runs).
- Carry F6 and F7 to the residue checklist.
- Rule on the recorded make line-number difference if it is not to be accepted.
- Obtain the second independent review. Merge requires two independent positive reviews and the full completion
  bar.

## 8. Packet contents

**`scripts/`**:
- tree setup: `mktree.sh`, `plant.py`;
- running and sampling: `runone.sh`, `sample.sh`, `wait_rc.sh`, `campaign.sh`;
- comparison: `norm.py`, `compare.sh`;
- stub tests: `stub_sim.sh`, `stubtest.sh`, `sigtest.sh`, `inttrace.sh`.

**`receipts/`**:
- summaries: `compare.txt`, `figures.txt`, `job-budget.txt`;
- real-harness runs: `runs/<variant>/{log,log.normalised,rc,time}`, `runs/samples.log`;
- stub runs: `stubtest-{default,silent,ignore-errors}.txt`, `stub/*.log`;
- signals: `inttrace.txt`, `sigtest.txt`;
- races: `files-written-after-build.txt`, `images.sha256`;
- gates: `gates-rc.txt`, `gate-docs.log`, `gate-lint.log`;
- clone check: `clone-integrity.txt`.

**Notes on the receipts**:
- `sigtest.txt` comes from an early run whose INT rows are confounded: make was launched in the background, so INT
  was ignored on entry. Its HUP row stands (HUP to the group stopped all passes). It is kept for completeness, and
  `inttrace.txt` supersedes it for INT, TERM and QUIT.
- In the raw logs, home-directory paths are replaced with `$HOME` and the packet path with `$PACKET`.

R925-1 FINISHED
