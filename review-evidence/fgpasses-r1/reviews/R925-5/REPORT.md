[R925] NEGATIVE - exact head a54e9eee922cb632364e864b2bce6aaf06c9c6ea

# R925-5: narrow re-review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111)

Head `a54e9eee922cb632364e864b2bce6aaf06c9c6ea`, tree `5599752c284f56ca643f6fada9f0cf960a1d28bd`. Source base `1213ac5b9e09b8759ba76cc70c53652b5e108996`.

**Verdict: NEGATIVE.** Every finding this round was asked to verify is closed at its cause, and I confirmed each by execution:

- R925-3-F1 (a generator shell's signal death);
- R925-3-F2 (+3.6 %);
- R925-3-R1 and R2;
- R925-4-F1 (check 7 on any shell);
- the main case of R925-4-F2 (a one-byte limit on a piped `core_pattern`).

`passes-test` passes 72 of 72 on two runs of mine. Each of my four plants that targets the delta is caught; the fifth survives, as expected (S1). `make docs` and `make lint` exit 0.

Two new MINOR findings remain. Both come from the case where the caller's **hard** core limit is 0, which is what bash's `ulimit -c 0` sets:

- **F1 (MINOR).** `reraise()` falls back to a soft limit of 0 when the hard limit is 0. A limit of 0 still dumps to a piped `core_pattern`. So a death recorded without a core replays as `Segmentation fault (core dumped)`, where the serial line reported `Segmentation fault`. The PR body says this case "dumps neither to a pipe nor to a file". This is the remainder of R925-4-F2.
- **F2 (MINOR).** Under the same caller limit, the new check 8 cannot set its one-byte limit (soft above hard). Its `preexec_fn` raises, and `passes-test` exits 2 with a traceback after 71 PASS. `passes-test` is in the engine suite's `all`.

## 0. Scope of this round

- **Delta.** The dispatch names "ONE manager commit f1b566a8..dcf1caef" and "71 checks". The exact head is one commit past that:
  - `dcf1cae` answers R925-3;
  - `a54e9ee` answers R925-4.
- **What I reviewed.** I judged the whole delta since my previously reviewed heads, `f1b566a..a54e9ee`: `pass_run.py` +33/−14 and `passes_test.py` +75/−8. At this head the suite has 72 checks.
  - I verified the R925-3 items the dispatch names, and every R925-4 item, since `a54e9ee` answers them.
  - Code outside the delta keeps its prior lens verdicts.
- **Authorities:**
  - #111: the body, and the issue author's criterion-2 amendment, issuecomment-7145509264.
  - The PR body at head.
  - `docs/README.md` (truth order) and `docs/TEST_DEVELOPER.md`.
  - The repository has no `AGENTS.md` or `CONTRIBUTING.md`.
- **Order of reading.** I read the other reviewer's findings (R926-1..4) only after I had written my own verdict and ledger to this file. They are resolved in §3. F2 came from a probe of my own after that point. Nothing in those reports bears on it.

## 1. Evidence verified

### Author packet

- **Evidence commit.** `254f65e92e6fc2dbb8473a6b2427d7d51f2ba5d5`, `review-evidence/fgpasses-r1`.
- **Manifest.** `MANIFEST.json` has 831 entries, and all 831 `published_sha256` values match. Nothing is missing and nothing is unlisted (`receipts/packet-verify.txt`).
- **No signature.** Both the evidence commit and the source head are **unsigned** (API `verified=false`, reason `unsigned`). Integrity rests on the hash manifest, not on a cryptographic signature.
- **Diffs.** `author-r5/receipts/diff.txt` is byte-identical to `git diff f1b566a..dcf1cae`. `author-r6/receipts/diff.txt` is byte-identical to `git diff dcf1cae..a54e9ee` (`receipts/author-packet-check.txt`).
- **Receipts, spot-checked:**
  - `author-r5`: `pt-g1..g3` give 71 PASS and 0 FAIL each. The gensig plant gives 2 FAIL.
  - `author-r6`: `pt-i1..i4` give 72 PASS and 0 FAIL each. The nocore plant gives 1 FAIL: check 8 sees `(core dumped)` where the serial line has none.

### Hosted

- No check runs and no statuses exist at the exact head (0 and 0), and the repository tracks no workflow (`receipts/hosted-query.txt`).
- I make no hosted claim. Hosted and act acceptance belong to the manager.

### My runs at the exact head

The host has Python 3.14.10, GNU make 4.4.1, `/bin/sh` = bash, and a `core_pattern` that pipes to the host's core collector (`receipts/env.txt`).

| Run | rc | PASS / FAIL | Wall |
|---|---:|---:|---:|
| `make passes-test`, run 1 of two at once (`receipts/passes-test-run1.log`) | 0 | 72 / 0 | 95.8 s |
| `make passes-test`, run 2 of two at once (`receipts/passes-test-run2.log`) | 0 | 72 / 0 | 95.8 s |
| `make passes-test` under `ulimit -c 0` (`receipts/passes-test-ulimit-c0.log`) | **2** | 71 / 0, then a traceback in check 8 | (F2) |
| `make docs` | 0 | | |
| `make lint`, with the pinned Verilator first on PATH (it reports `Verilator 5.050 2026-07-01 rev v5.050`; binary sha256 `905795b9…`) | 0 | | |

### Plants

Each plant is a copy of the engine directory with the full `passes_test.py` (`scripts/plants.sh`, `receipts/plant-*`):

| Plant | rc | Result |
|---|---:|---|
| `no-gen-reraise`: `replay_gen` without its re-raise | 1 | 2 FAIL: check 7, SIGSEGV and SIGKILL |
| `limit-zero`: `reraise()` lowers the soft limit to 0, the pre-`a54e9ee` shape | 1 | 1 FAIL: check 8 (`(core dumped)` against none) |
| `no-chdir`: `reraise()` without `os.chdir(STATE)` | 1 | 1 FAIL: check 6 |
| `gen-no-redirect`: the generator run without `" >/dev/null"` | 1 | 5 FAIL: the generator-SIGSEGV plan at `-j4` (none, `-s`, `-i`, `-k`) and at `-j1` |
| `no-gen-record`: `run()` no longer records `gen_signal`/`gen_core` | 0 | **survives**, 72 PASS. On bash the generator's shell forks, so this half is not reached (S1). Under an exec-ing shell it is caught (below) |

### Shell and core probes

Each script takes the clone and a work directory as arguments.

- **`scripts/check7_shell_probe.sh`** (`receipts/check7-shell-probe.log`). It runs the suite's own `gen_signal()` (check 7) and `no_core_replay()` (check 8) from copies, under host bash and under an emulated `/bin/sh` that forks its `-c` command:
  - As written at head, both shells give `bad = 0` for both checks.
  - With `exec ` removed from the reference lines, the forking shell gives 2 FAIL in check 7 and 1 in check 8. The `exec` is load-bearing.
- **`scripts/core_limit_replay_probe.sh`** (`receipts/core-limit-replay-probe.log`, unchanged from R925-4). A SIGSEGV goes through a recipe line and through `run` + `replay`, at caller soft limits of 0, 1 and 1 MiB (hard unlimited). All three are **SAME**. At 1 byte the record is `{"signal": 11, "core": false}` and both sides end `Segmentation fault`.
- **`scripts/gen_signal_shell_probe.sh`** (`receipts/gen-signal-shell-probe.log`). It runs end to end: `run --gen` then `replay-gen` against the serial generator line, with make's `SHELL` and pass_run's `/bin/sh` the same shell:
  - **host bash** (which forks the redirected line): the record is `{"gen": 139}` with no `gen_signal`. Both sides end `Error 139`. **YES**: the 128+n is kept.
  - **an exec-ing shell**: the record is `{"gen_signal": 11, "gen_core": true, "gen": 0}`. Both sides end `Segmentation fault (core dumped)`. **YES**.
  - **a forking emulated shell**: both sides end `Error 139`. The only difference is the pid inside the emulated shell's own message, an artefact of the emulation.
- **`scripts/exec-sh-probe.sh`** (the R925-3 probe, updated to this head's `passes_test.py`). Every check-1 plan runs under an emulated `/bin/sh` that execs a one-command `-c` line, as make's `SHELL` and as pass_run's `/bin/sh` (`receipts/e1-*`):
  - **Head: 55 of 56.** All 21 comparisons of R925-3's four plans pass, including the generator-SIGSEGV plan 5/5.
  - **The one FAIL is an artefact of the emulation.** It is `build fails, -j4 -i`. A `SHELL` other than `/bin/sh` turns off make's direct exec of the metachar-free `./obj_dir/Vengine_sim` line. So the serial side prints the shell's "No such file or directory" text, while pass_run prints make's own. On a real host, `SHELL` is `/bin/sh` and make execs that line directly. R925-3's probe left this plan out for that reason.
  - **The `no-gen-record` plant under the exec-ing shell: 6 FAIL**, the generator plan 5/5 plus the same artefact. The recording half is load-bearing wherever the shell execs.
- **`scripts/hard_zero_probe.sh`** (`receipts/hard-zero-probe.log`). It compares a non-dumpable process (`prctl(PR_SET_DUMPABLE, 0)`) that dies of SIGSEGV, serially and through `run` + `replay`, at caller limits (soft, hard) of (0, 0), (0, ∞) and (1, ∞):
  - **Head:** (0, 0) **DIFFERS**: `Segmentation fault` serially, `Segmentation fault (core dumped)` replayed. The other two are SAME.
  - **A copy whose `reraise()` also calls `prctl(PR_SET_DUMPABLE, 0)` when the record has no core:** SAME at all three. This is F1.

### Checkout integrity after all probes (`receipts/checkout-integrity.txt`)

- HEAD is `a54e9ee…`, the tree is `5599752c…`, and the index tree equals HEAD's.
- There are no porcelain lines, ignored files included, and `git diff HEAD` is empty for bytes and modes.
- All 122 tracked blobs re-hash to their index object IDs.
- The repository has 0 gitlinks (mode 160000), so none are required.
- Every plant and probe ran on copies under `scratch/`. The `passes-test` runs in the clone wrote only to `TMPDIR` under `scratch/`.

## 2. Delta assessment

### R925-3-F1: a generator whose shell died of a signal

- **Recording.** `pass_run.py:129-139` runs the serial line through the same `/bin/sh`, then reads the raw wait status:
  - `WIFSIGNALED` records `gen_signal` and `gen_core`, with `gen` = 0;
  - `WIFEXITED` keeps the shell's own status, so a forking shell's 128+n is kept.
  - No 128+n is synthesized anywhere: the only `128` in the file is the comment at `:127`.
- **Stop.** `:140` stops the later passes on any non-zero `returncode`, the signal case included.
- **Replay.** `replay_gen` (`:221-225`) marks the stop and re-raises through the shared `reraise()` (`:250-260`), as `replay` does (`:245-246`).
- **Tests.** Check 7 (`passes_test.py:358-382`) is caught by `no-gen-reraise`. My exec-shell probe gives R925-3's 21/21.
- **RESOLVED.**

### R925-3-F2: the `-j1` CPU figure

- The PR body, Measured: "The `-j1` pair … is +3.6 %". From `summary.txt`, 475.07 / 458.77 = +3.553 %.
- **RESOLVED.**

### R925-3-R1: the body opening

- The opening reads "six commits on main `1213ac5` (#108), head `a54e9eee…`" and lists all six commits with accurate one-line summaries.
- The Measured heading names `1213ac5` against `661e4c3`, and says "later commits add no user work". That holds: the delta only swaps `subprocess.run` for `Popen` and `waitpid` on the same line, and adds one `unlink` and one `setrlimit`.
- **RESOLVED.**

### R925-3-R2: the docstring check list

- `passes_test.py:14-42` lists checks 1-8.
- Item 1 names "an image generator killed by SIGSEGV" and gives the exact matrix.
- The last line reads "about 90 seconds".
- **RESOLVED.** One word from R925-4-R4 is still missing; see R1.

### R925-4-F1: check 7's reference line

- Both reference lines (`:372`, `:402`) are `exec python3 -c …`, so the reference dies of the signal itself on any POSIX shell.
- My probe gives `bad = 0` on both shells. Without `exec`, the forking shell gives 2 FAIL.
- The docstring's item 7 and PR body lines 71-73 now state exactly this.
- **RESOLVED.**

### R925-4-F2: a no-core replay under a piped `core_pattern`

- `reraise()` (`:254-256`) lowers the soft limit to 1 when the hard limit allows it. The kernel skips a piped dump at exactly 1, and rejects a file dump below the smallest dump size.
- Check 8 (`:385-409`) discriminates on piped hosts: `limit-zero` is caught.
- The core-limit probe is SAME at all three soft limits.
- **RESOLVED where the hard limit is at least 1.** It is not resolved where the hard limit is 0: F1.

### R925-4-S1: pid-file removal (`pass_run.py:175`)

- The pid file is removed after `SIGUSR1` is set to ignored and before the process exits. A later `stop_later` therefore cannot find the pid while the kernel could recycle it.
- The only exception is a pass killed by SIGKILL, whose file stays behind. That is negligible.
- **TAKEN.**

### Comment rule

- No added line in `f1b566a..a54e9ee` carries a bench lane label, lane name, review round, reviewer ID or comment ID (`receipts/delta-scan.txt`).
- The new comments and docstrings (`pass_run.py:126-128`, `:175`, `:251-253`, `:259`; `passes_test.py:359-360`, `:386-387`) state behaviour and reason.
- No residue under that rule.

### Width (R925-4-S4)

- No line in either file exceeds 120 columns. **TAKEN.**

## 3. Prior public findings at this head

| Finding | State at this head | Evidence |
|---|---|---|
| R925-3-F1 MINOR (generator shell's signal death replayed as 128+n) | RESOLVED | §2. The exec-shell probe gives 21/21 of its own comparisons. Plants: `no-gen-reraise` 2 FAIL; `no-gen-record` caught under the exec-ing shell |
| R925-3-F2 MINOR (`-j1` CPU misrounded) | RESOLVED | "+3.6 %" |
| R925-3-R1 / R926-3-R1 RESIDUE (stale PR opening) | RESOLVED | Six commits and head `a54e9ee…` |
| R925-3-R2 RESIDUE (docstring check list) | RESOLVED | Items 1-8 and "about 90 seconds" |
| R925-3-R3 / R925-4-R6 / R925-2-R2 RESIDUE (`summary.txt` names `tools/logcmp.py`) | RESOLVED | `author-r6/REVIEW-READY.md` states that `tools/logcmp4.py` is round 4's comparison tool (round 3's masks plus that round's clone paths) and that it removes only host text, which is the requested index statement |
| R925-2-R1 RESIDUE ("it takes seconds") | RESOLVED | `passes_test.py:42` "about 90 seconds" |
| R925-4-F1 MINOR (check 7 depends on the host shell) | RESOLVED | §2. Check-7 probe |
| R925-4-F2 MINOR (a no-core replay dumps under a piped `core_pattern`) | RESOLVED for hard limit ≥ 1. **RETAINED in part as R925-5-F1** for hard limit 0 | §2. Core-limit probe SAME ×3. Hard-zero probe DIFFERS at (0, 0) |
| R925-4-R1 RESIDUE (matrix wording) | RESOLVED | `passes_test.py:18-19` |
| R925-4-R2 RESIDUE (duration) | RESOLVED | `:42` |
| R925-4-R3 RESIDUE (check 6 function docstring) | RESOLVED | `:334-335` |
| R925-4-R4 RESIDUE ("a relative file core_pattern") | RESOLVED in `pass_run.py:259`, `passes_test.py:334` and the PR body. **RETAINED** at `passes_test.py:32-33` | R925-5-R1 |
| R925-4-R5 RESIDUE (run counts in the PR) | RESOLVED | "six runs in a row at `f1b566a`, on three at `dcf1cae`, and on four at this head", matching `pt-s1..6` (69), `pt-g1..3` (71) and `pt-i1..4` (72) |
| R925-4-S1 (pid file outlives its pass) | TAKEN | §2 |
| R925-4-S2 (generator not registered for forwarding) | RETAINED as S3 | Unchanged |
| R925-4-S3 / R925-3-S4 / R926-4-S1 (deterministic race checks) | RETAINED as S2 | Unchanged |
| R925-4-S4 (line width) | TAKEN | §2 |
| R925-2-S2 / R926-4 retained (core-flag branch not discriminated) | TAKEN on piped hosts | Check 6 (core) and check 8 (no core) each fail on a planted defect |
| R925-2-S3 (wrapper crash text), R925-2-S4 (self-contained comparer) | RETAINED | Untouched |
| R925-3-S1 (criterion-2 wording: body against amendment), R925-3-S2 (cycles column) | RETAINED | Unchanged |
| R926-2-S1 (progressive printing) | RETAINED | Disclosed under "Output timing" |
| R926-4 note (publication commit unsigned) | CONFIRMED, not a finding | §1 |
| R926-1..4 MAJOR/MINOR (budget, `-s`/`-i`/`-k`, replay errors, CPU acceptance, the `-i` guide sentence) | Still RESOLVED | The delta touches none of them. Every one of those checks passes 72/72 ×2 |

## 4. Findings

### R925-5-F1 - MINOR - Conformance, Robustness, Docs: under a hard core limit of 0, a no-core death replays with a dump on a piped `core_pattern`

- **Where**:
  - `tb/verilator/engine/pass_run.py:254-256`: `(1 if hard == resource.RLIM_INFINITY or hard >= 1 else 0, hard)`.
  - The `reraise()` docstring at `:251`, "dumping core only if it did".
  - PR body lines 111-112: "A death that did not dump core is re-raised under a one-byte soft core limit (or 0 where the hard limit is 0), so it dumps neither to a pipe nor to a file."
  - Both callers: `replay` `:246` and `replay_gen` `:224`.
- **Authority**:
  - #111 criterion 1: the transcript and exit code are identical to the serial run's.
  - `reraise()`'s own contract.
  - R925-4-F2's required outcome: "Re-raise a no-core record without a dump on piped and file `core_pattern`s alike … Or narrow the docstring and PR to the hosts where it holds."
- **Evidence** (`scripts/hard_zero_probe.sh`, `receipts/hard-zero-probe.log`):
  - The caller's limit is (0, 0), which is what bash's `ulimit -c 0` sets, and this host's `core_pattern` is piped.
  - A SIGSEGV death that did not dump (a non-dumpable process) records `{"signal": 11, "core": false}`.
  - The serial line ends `make: *** […] Segmentation fault`. The replay ends `Segmentation fault (core dumped)`, and the collector receives one core that the serial run did not produce.
  - The docstring's own last clause says that 0 "would still dump to a pipe". The PR sentence contradicts it.
  - A copy whose `reraise()` also calls `prctl(PR_SET_DUMPABLE, 0)` when the record has no core is SAME at (0, 0), (0, ∞) and (1, ∞).
- **Impact**: the case is narrow. It needs all three of:
  - a hard core limit of 0;
  - a piped `core_pattern` (the common systemd default);
  - an original death that did not dump although a dump was possible, for example a non-dumpable process or a collector that failed.

  When all three hold, make's line for that pass gains `(core dumped)`, and an unwanted core record is created. Clean runs and the stub suite's plans are unaffected. Still, the PR states the case as handled, and the fallback was added in this delta.
- **Required outcome** (either):
  - (a) In `reraise()`, when `core` is false, also make the process non-dumpable before the kill, for example `ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)` (`PR_SET_DUMPABLE` = 4). That suppresses the dump on every `core_pattern` whatever the limits. The one-byte limit can stay as a fallback.
  - (b) Narrow the docstring and the PR to where the behaviour holds. For example, in the PR: "… under a one-byte soft core limit, so it dumps neither to a pipe nor to a file. Where the hard limit is 0 the soft limit stays 0, which still dumps to a piped `core_pattern`." In the docstring, replace "dumping core only if it did" with "dumping core only if it did, except where a hard limit of 0 meets a piped core_pattern".
- **Verification**:
  - For (a): `scripts/hard_zero_probe.sh CLONE WORKDIR` reports SAME at all three limits for the head copy, and `passes-test` stays 72/72.
  - For (b): the text matches that probe's DIFFER line.

### R925-5-F2 - MINOR - Tests, Robustness: check 8 crashes `passes-test` under a hard core limit of 0

- **Where**: `tb/verilator/engine/passes_test.py:388-389` (`one_byte`): `resource.setrlimit(resource.RLIMIT_CORE, (1, resource.getrlimit(resource.RLIMIT_CORE)[1]))`, used as `preexec_fn` at `:405`.
- **Authority**:
  - `passes-test` is in the engine suite's `all` (`Makefile:37`), so it runs in every bank that runs `make -C tb/verilator/engine` (and the parent `gptp-processor all`).
  - The PR body's validation line: "engine passes test: PASS (72 checks, ~90 s)".
- **Evidence** (`receipts/passes-test-ulimit-c0.log`):
  - `bash -c 'ulimit -c 0; make passes-test'` gives caller soft 0 and hard 0.
  - Checks 1-7 pass: 71 PASS. Then setting a soft limit of 1 above a hard limit of 0 raises `ValueError` in the child.
  - `subprocess` reports `SubprocessError: Exception occurred in preexec_fn`. The suite prints no verdict line, and make ends `Error 1`, exit 2.
  - The other checks' `no_cores()` only lowers the limit, so they are unaffected.
- **Impact**: on any bank or developer shell that runs the engine suite with `ulimit -c 0`, a common way to suppress cores in CI, the suite fails with a traceback although the product is correct. A false FAIL in a suite that every bank runs.
- **Required outcome**:
  - When the hard core limit is below 1 (and not unlimited), check 8 cannot set up its condition. It should report that it does not apply, with the reason, and not raise. For example, print `[PASS] … not applicable: the caller's hard core limit is 0`, or a separate SKIP line the tally accepts.
  - If F1 is fixed by (a), check 8 can instead cover the hard-0 case too: a non-dumpable serial reference under (0, 0).
- **Verification**:
  - `bash -c 'ulimit -c 0; make -C tb/verilator/engine passes-test'` exits 0 with check 8's line stating its outcome.
  - A plain run stays 72/72.
  - The `limit-zero` plant is still caught when the hard limit is unlimited.

### Residue (wording only; does not affect the verdict)

- **R925-5-R1 - RESIDUE - Tests/Docs (module docstring; retained part of R925-4-R4).** `tb/verilator/engine/passes_test.py:32-33` reads "so a file core_pattern never replaces the simulator's core". A fixed absolute pattern is not redirected by the `chdir`, as `pass_run.py:259`, `:334` and the PR body now say. Exact fix: "6. A replayed signal death is re-raised from obj_dir/engine-passes/, so a relative file core_pattern never replaces the simulator's core." Re-wrap to 80 columns.

### Suggestions (do not affect the verdict)

- **S1 - Tests: the run-side `gen_signal` record is not exercised on bash hosts.**
  - The `no-gen-record` plant survives 72/72 here, because bash forks the redirected generator line. It is caught only under an exec-ing shell (6 FAIL in `receipts/e1-exec-sh-no-gen-record.log`).
  - Check 7 covers the replay half with a crafted record, which is what R925-3-F1 asked for. The recording half (`pass_run.py:137-138`) has no host-independent guard.
  - Option: a check that runs `pass_run.py run 1 --gen "exec python3 -c 'import os; os.kill(os.getpid(), 11)'" --shell true`. The shell's `exec` builtin makes it die of the signal on any shell. Then assert the record (`gen_signal` 11) and that `replay-gen` ends as the exec'd serial line.
- **S2 - Tests (retained R925-3-S4 / R925-4-S3 / R926-4-S1).** Make the two race fixes deterministic in the suite. R925-4's `race_probe.py` has both shapes.
- **S3 - Robustness (retained R925-4-S2).** Register the generator so that `forward` and `stop` reach it (`pass_run.py:129-139`).
- **S4 - Tests (unchanged code).** `passes_test.py:198`'s `no_cores()` says "No core files", but a limit of (0, 0) still dumps to a piped `core_pattern`. On this host, each SIGSEGV and SIGABRT plan of check 1 and check 7's SIGSEGV arm send cores to the host's collector. Either say so ("no core files where core_pattern is a file") or make the stubs non-dumpable.
- **Retained:** R925-2-S3 and S4, R925-3-S1 and S2, and R926-2-S1, as in §3.

## 5. Lens evidence

| Lens | Result | Artifact-specific evidence |
|---|---|---|
| Conformance | UNCLEAN (F1) | #111 criterion 1: own plans 72/72 ×2. The generator signal path is identical under host bash (128+n kept) and under an exec-ing shell (signal re-raised). A no-core replay is identical at hard limit ≥ 1, but not at hard limit 0 on a piped `core_pattern` (F1). Criterion 2: unchanged since R925-4. Instructions +0.293 % and +0.040 % at `661e4c3`, and the delta adds no user work |
| RTL | CLEAN | `git diff 1213ac5..HEAD` touches no `hdl/`, `syn/` or `bench/` file. `make lint` rc 0 with the pinned Verilator 5.050 (identity verified). The delta is Python test tooling only |
| Robustness | UNCLEAN (F1, F2) | `reraise()` is correct for hard ≥ 1 (probe SAME ×3) and wrong for hard 0 (F1). The pid-file removal is correct. The races are unchanged since R925-4, where probes A and B closed them. The suite crashes under `ulimit -c 0` (F2) |
| Tests | UNCLEAN (F2) | Two own runs 72/72. Four of five plants caught (2, 1, 1 and 5 FAIL); `no-gen-record` survives on bash (S1). Check 7 and 8 hold on host and forking shells, and `exec` is load-bearing. Check 8 crashes under a hard core limit of 0 (F2) |
| Docs | UNCLEAN (F1) | The PR body's no-core sentence and the `reraise` summary overclaim the hard-0 case (F1). R925-3 and R925-4 wording is fixed except R1. `make docs` rc 0. `docs/TEST_DEVELOPER.md` is untouched by the delta and still consistent ("about 90 seconds"). PR figures verified |

## 6. Reviewer-owned ledger

| Lens | CLEAN/UNCLEAN | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN (F1) | #111 body and amendment; PR body at head; `pass_run.py` `run`/`replay_gen`/`replay`/`reraise`; `passes_test.py` plans; gen-signal, core-limit and hard-zero probes | R925-5 (delta `f1b566a..a54e9ee`); criterion-2 arithmetic carried from R925-4 | a54e9eee922cb632364e864b2bce6aaf06c9c6ea |
| RTL | CLEAN | `git diff --stat 1213ac5..HEAD` (no HDL); `make lint`, pinned 5.050 | R925-5 (carried, no RTL delta) | a54e9eee922cb632364e864b2bce6aaf06c9c6ea |
| Robustness | UNCLEAN (F1, F2) | `pass_run.py:94-260`; five plants; hard-zero probe; `passes-test` under `ulimit -c 0`; races carried from R925-4 | R925-5 | a54e9eee922cb632364e864b2bce6aaf06c9c6ea |
| Tests | UNCLEAN (F2) | `passes_test.py` checks 1-8; two own runs; five plants; check-7/8 shell probe; exec-shell probe (head and plant); packet runs `pt-g1..3` and `pt-i1..4` and the plants | R925-5 | a54e9eee922cb632364e864b2bce6aaf06c9c6ea |
| Docs | UNCLEAN (F1) | Module, function and comment prose in both files; PR body; `docs/TEST_DEVELOPER.md`; `make docs`; comment-rule and width scan | R925-5 | a54e9eee922cb632364e864b2bce6aaf06c9c6ea |

## 7. Real limits

- **No real dash or other non-bash `/bin/sh` was executed.** None is installed here, and installing one is not allowed. The exec-ing and forking shells are emulations:
  - Which real shells fork or exec a redirected `-c` line is stated from release history.
  - One FAIL in the exec-shell probe comes from the emulation itself, because a non-`/bin/sh` `SHELL` turns off make's direct exec. It is explained in §1.
- **No file `core_pattern` was executed.** Changing it needs privilege. The file half of the one-byte argument, and of F1's remedy (a), comes from kernel behaviour, not from tests.
- **Non-dumpable stand-in.** F1's trigger is shown with a process that makes itself non-dumpable. I did not reproduce a failing core collector.
- **Measurements.** They are the author's, at `661e4c3` on a shared host. They were recomputed in R925-3 and R925-4, not re-measured.
- **Races.** I did not re-run the race probes, because the delta does not touch those lines. The pid unlink was checked by reading the code.
- **No manager source bank** runs at this head, and I claim or infer none.
- **Hardware.** Physical calibration NOT RUN. Field skips are not hardware proof. No hosted job exists at this head.

## 8. Pending manager duties

- At the merge turn: validate the current-dev merge candidate (source base `1213ac5`, live dev `e275d79`) on the builder and native banks, and link the receipts on the PR.
- **Report whether those banks run with a hard core limit of 0** (`ulimit -c 0`). If they do, F2 fails `passes-test` in the engine `all` until it is fixed.
- Report whether their `core_pattern` is piped (F1).
- Own hosted and act acceptance; none exists at this head.
- Carry R925-5-R1 to the residue checklist. The existing source-comment labels are tracked by #746.
- Publish this packet: `MANIFEST.sha256` lists every receipt and script.

## 9. Packet contents

- **`REPORT.md`.**
- **`scripts/`:**
  - `plants.sh`;
  - `check7_shell_probe.sh`;
  - `exec-sh-probe.sh`;
  - `gen_signal_shell_probe.sh`;
  - `core_limit_replay_probe.sh`;
  - `hard_zero_probe.sh`;
  - `verify_packet.py`.

  Each takes the clone and a work directory, plus a receipts directory where it writes one.
- **`receipts/`**, listed in `MANIFEST.sha256`:
  - `passes-test-run1..2` and `passes-test-ulimit-c0`;
  - `plant-*` and `plants-summary.txt`;
  - `e1-*`;
  - `check7-shell-probe.log`, `core-limit-replay-probe.log`, `gen-signal-shell-probe.log` and `hard-zero-probe.log`;
  - `make-docs` and `make-lint-pinned`;
  - `packet-verify.txt`, `author-packet-check.txt`, `hosted-query.txt`, `delta-scan.txt`, `checkout-integrity.txt` and `env.txt`.
- Disposable trees and the downloaded evidence copy stay under `scratch/` and are not published.

R925-5 FINISHED
