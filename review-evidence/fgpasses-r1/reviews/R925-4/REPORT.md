[R925] NEGATIVE - exact head dcf1caef6966221fda86684bf6406fe3134a0b11

# R925-4: narrow re-review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111)

Head `dcf1caef6966221fda86684bf6406fe3134a0b11`, tree `16df30e4f04c0f88c4097995b1624574fb850c19`. Source base `1213ac5b9e09b8759ba76cc70c53652b5e108996`.

**Verdict: NEGATIVE.** The round's named items are all closed at their cause, and I confirmed each by execution:

- R925-2-F1, F2 and F3.
- R925-3-F1 and F2.
- The two race fixes.

`passes-test` passes 71 of 71 on three runs of mine. The three plants are each caught, and `make docs` and `make lint` exit 0.

Two new MINOR findings in the delta stay open. Each was shown by a probe:

- **F1 (MINOR).** Check 7's serial reference line depends on how the host's `/bin/sh` runs it. The docstring and PR body say the check "holds on any host's `/bin/sh`". On a `/bin/sh` that forks a single `-c` command, check 7 fails even though the product is correct there. That would also fail the engine suite's `all`.
- **F2 (MINOR).** The new `reraise()` says it re-raises "dumping core only if it did". On a piped `core_pattern`, a soft core limit of 0 does not stop the dump. So with a caller's 1-byte soft limit, the serial line reports `Segmentation fault` and the replay reports `Segmentation fault (core dumped)`. The replay also sends one more core to the collector.

## 0. Scope of this round

- The dispatch names "ONE manager commit 0ba80c4f..f1b566a8" and "69 checks". The exact head is two commits past `0ba80c4f`:
  - `f1b566a` answers R925-2.
  - `dcf1cae` answers R925-3.
- I reviewed the whole delta `0ba80c4f..dcf1caef`: `pass_run.py` +33/−11 and `passes_test.py` +63/−4. At this head the suite has 71 checks, not 69.
- Code outside that delta keeps its prior lens verdicts. The exceptions are named below where the delta changes what the code depends on.
- Authorities:
  - #111: the body, and the maintainer's criterion-2 amendment (issuecomment-7145509264).
  - The PR body at head.
  - `docs/README.md` (truth order) and `docs/TEST_DEVELOPER.md`.
  - The repository has no `AGENTS.md` or `CONTRIBUTING.md`.
- Prior public findings were read only after my own verdict and ledger were written to this file. They are resolved in §3.

## 1. Evidence verified

- **Packet.** Evidence commit `28ad4f06326e6ad089cc33006ea63c9ba05ba67e`, `review-evidence/fgpasses-r1`.
  - `MANIFEST.json` has 784 entries, and all 784 `published_sha256` values match. Nothing is missing and nothing is unlisted (`receipts/packet-verify.txt`). This is a hash manifest, not a cryptographic signature.
  - `author-r4/receipts/diff.txt` is byte-identical to `git diff 0ba80c4..f1b566a`.
  - `author-r5/receipts/diff.txt` is byte-identical to `git diff f1b566a..dcf1cae`.
- **Packet receipts, spot-checked:**
  - `author-r4`: six runs at `f1b566a` with 69 PASS and 0 FAIL each.
  - `author-r4` plants: generator (5 FAIL) and cwd (1 FAIL).
  - `author-r4` race observations: `pt1` (a late stop), and `pt-r4` (TERM to make hung).
  - `author-r5`: three runs at head with 71 PASS each, and the gensig plant (2 FAIL).
- **Hosted.** No check runs and no statuses exist at the exact head (0 and 0; `receipts/hosted-query.txt`). No hosted claim is made. Hosted and act acceptance belong to the manager.
- **Own runs at exact head** (Python 3.14.10, GNU make 4.4.1, `/bin/sh` = bash):

| Run | rc | PASS / FAIL | Wall |
|---|---:|---:|---:|
| `make passes-test`, alone (`receipts/passes-test-run1.log`) | 0 | 71 / 0 | 95.6 s |
| `make passes-test`, run 2 of two at once (`receipts/passes-test-run2.log`) | 0 | 71 / 0 | 95.9 s |
| `make passes-test`, run 3 of two at once (`receipts/passes-test-run3.log`) | 0 | 71 / 0 | 95.8 s |
| `make docs` | 0 | | |
| `make lint`, system Verilator | 0 | | |
| `make lint`, pinned Verilator (reports `Verilator 5.050 2026-07-01 rev v5.050`) | 0 | | |

- **Own plants.** Each is a copy of the engine directory with the full `passes_test.py` (`scripts/plants.sh`, `receipts/plant-*`):

| Plant | rc | Result |
|---|---:|---|
| `no-chdir`: `reraise()` without its `os.chdir(STATE)` | 1 | 1 FAIL, check 6 ("re-raised from …/cwd") |
| `no-gen-reraise`: `replay_gen` without its re-raise | 1 | 2 FAIL, check 7 SIGSEGV and SIGKILL |
| `gen-no-redirect`: generator without `" >/dev/null"` | 1 | 5 FAIL, the generator-SIGSEGV plan at `-j4` none/-s/-i/-k and at `-j1` |

- **Own race probes.** `scripts/race_probe.py`, `receipts/race-probe.log`. Each probe runs the head and a copy with that one fix deleted:

| Probe | Head | Fix deleted |
|---|---|---|
| Late stop (A): a pass whose simulator ends at once gets one SIGUSR1 per ms, from the moment its pid file exists until it exits | 150/150 exit 0 with record | without `SIG_IGN` at `:174`: 150/150 died of SIGUSR1 (rc −10) |
| Early signal (B): SIGTERM raised inside `subprocess.Popen` after the simulator (`sleep` ~30 s) is forked but before `child.append` | 15/15 died of TERM within 0.17 s, simulator stopped | without the forward at `:148-149`: 15/15 hung past 10 s |

  - An unthrottled flood (about 3,500 SIGUSR1 per run) makes Python's handler re-enter itself until it raises RecursionError, and the process then dies of SIGUSR1 at shutdown. pass_run.py never sees that delivery: `stop_later` sends a pass at most three stops. The probe therefore uses 1 ms spacing, as its docstring records.
- **Shell and core probes:** `scripts/gen_signal_shell_probe.sh`, `scripts/check7_shell_probe.sh` and `scripts/core_limit_replay_probe.sh`, with receipts of the same names. They are used in F1 and F2.
- **Checkout integrity after all probes** (`receipts/checkout-integrity.txt`):
  - HEAD and the index tree are `16df30e4…`.
  - The worktree and index equal HEAD, with no untracked or ignored files.
  - The repository has no gitlinks (no `160000` entries), so it requires none.
  - All plants and probes ran on copies under `scratch/`.

## 2. Delta assessment: the named items

### R925-2-F1: re-raise from `obj_dir/engine-passes`

- `pass_run.py:249-256` `reraise()` is now shared by `replay` (`:244-245`) and `replay_gen` (`:222-223`). It `chdir`s to `STATE` right before `os.kill`.
- Check 6 (`passes_test.py:328-349`) runs pass_run's own replay with only `os.kill` intercepted, and records the cwd. It passes at head, and my `no-chdir` plant fails it.
- The PR body's "Core dumps" item states both cases:
  - Piped: one more core record.
  - A file such as `core`: the core lands in the ignored build tree.
- RESOLVED. The comment wording residue is R4.

### R925-2-F2: generator run as the serial line with its redirection

- `pass_run.py:129` runs `["/bin/sh", "-c", generate + " >/dev/null"]`, the serial line `Makefile@1213ac5:53/57/61` through the same shell.
- A shell that forks reports 128+n, which is kept as `gen`. A shell that dies of the signal is recorded as `gen_signal` and `gen_core` (`:137-139`), and re-raised at replay (`:220-224`).
- The plan "pass 1 image generator SIGSEGV" passes at `-j4` under none, `-s`, `-i` and `-k`, and at `-j1`, in all three of my runs (`passes-test-run*.log:48-52`). My `gen-no-redirect` plant fails it 5/5.
- On this host, bash forks the redirected line (Error 139 both sides), so the plan exercises the 128+n path. The re-raise path is exercised only by check 7's crafted record.
- RESOLVED. R925-3-F1's correction of the fallback is in §3. Check 7's portability is F1.

### R925-2-F3: the body's CPU paragraph and amended criterion 2

- The #111 body's criterion 2 now gates on `instructions:u` within +1 % at `-j1` and `-j4`, and the amendment comment is public.
- Recomputed from `author-r2/receipts/gptp/summary.txt`:
  - Instructions: +0.293 % at `-j4` and +0.040 % at `-j1`.
  - CPU, per `-j4` pair: +30.28 %, −16.55 % and −24.21 %.
  - CPU at `-j1`: +3.55 %, which rounds to +3.6 %.
  - Wall: 2.048× and 2.949×.
- The body matches to its stated precision.
- RESOLVED. These measurements ran at `661e4c3`. "Later commits add no user work" is consistent with the delta: it swaps `subprocess.run` for `Popen` and `waitpid` on the same line.

### Race fix (a): SIGUSR1 ignored once a pass has ended (`pass_run.py:173-174`)

- Python's shutdown resets only handlers that are Python functions. A `SIG_IGN` disposition survives.
- After `:174`, a stop cannot terminate the pass. Before `:174`, the `stop` handler runs, and it only marks the record and signals a live child.
- The stop handler is installed (`:119`) before the pid file is written (`:120`), so no stop can find the pass at default disposition at startup.
- Probe A: head 150/150, and the fix deleted fails 150/150.
- **Correct and complete; it cannot kill a pass that has ended.**
- Residual (SUGGESTION S1, unchanged code): a pass's pid file outlives its process. A later `stop_later` can therefore signal a pid the kernel has since recycled.

### Race fix (b): a signal before the child is registered is forwarded after (`pass_run.py:148-149`)

The window runs from the `not received` guard (`:143`) to `child.append` (`:145`):

- A signal in that window is kept in `received` by `forward` (`:105-108`), which finds `child` empty.
- `:148-149` forwards it once `Popen` has returned. By then the child has exec'd, because `Popen` returns only after exec.
- A signal arriving later goes through `forward` with `child[0]` live.

Probe B: head 15/15, and the fix deleted fails 15/15.

**Correct and complete for the simulator: no signal is lost in that window.** The generator is still not in `child` (S2, same as before the delta). TERM to the wrapper alone lets the generator finish, which takes seconds, before the pass dies of TERM. Group signals reach the generator directly, and no simulator is left in either case.

## 3. Prior public findings at this head

| Finding | State at this head | Evidence |
|---|---|---|
| R925-2-F1 MINOR (interpreter core over the simulator's) | RESOLVED | §2. Check 6 PASS ×3, plant caught |
| R925-2-F2 MINOR (generator death replayed as Error 245) | RESOLVED | §2. Plan PASS 5/5 ×3, plant caught |
| R925-2-F3 MINOR (CPU figures per pair) | RESOLVED | §2. Recomputed |
| R925-2-R1 RESIDUE (`passes_test.py` "it takes seconds") | RETAINED as R2 | Now `passes_test.py:37` |
| R925-2-R2 / R925-3-R3 RESIDUE (`summary.txt` names `tools/logcmp.py`; the tool that ran is `tools/logcmp4.py`) | RETAINED as R6 | `author-r2/receipts/gptp/summary.txt:1` unchanged |
| R925-2-S1 (signal during spawn not forwarded) | TAKEN | Race fix (b); probe B |
| R925-2-S2 (core-flag branch not discriminated) | ESCALATED to F2 | The product consequence is now demonstrated, in the new `reraise()` and its new generator path |
| R925-2-S3 (wrapper crash prints a traceback), R925-2-S4 (self-contained comparer) | RETAINED as suggestions | Untouched by the delta |
| R925-3-F1 MINOR (generator shell signal death replayed as 128+n) | RESOLVED | `:137-139` and `:220-224`. No 128+n synthesis remains, and check 7 plus its plant is in place (2 FAIL). Check 7's host dependence is new: F1 |
| R925-3-F2 MINOR (`-j1` CPU misrounded) | RESOLVED | Body "+3.6 %"; 475.07/458.77 = +3.553 % |
| R925-3-R1 / R926-3-R1 RESIDUE (stale PR opening) | RESOLVED | Body lists five commits and head `dcf1cae…`; the Measured heading names `1213ac5` against `661e4c3` |
| R925-3-R2 RESIDUE (docstring check list) | RESOLVED except the duration | Items 6 and 7 and the SIGSEGV plan are listed; the duration is R2 |
| R925-3-S1 (align criterion-2 wording between the #111 body and the amendment comment) | RETAINED | The body still differs ("because they track host contention" against "favourable and unfavourable") |
| R925-3-S2 (cycles column) | RETAINED | The PR table still has no cycles column or summary link |
| R925-3-S3 (guard each half of the generator fix) | TAKEN | Redirection half: plan, plant 5 FAIL alone. Re-raise half: check 7, plant 2 FAIL alone |
| R925-3-S4 (deterministic race checks) | RETAINED as S3 | The suite still covers both races only by repetition. `scripts/race_probe.py` gives a deterministic shape for each |
| R926-2-S1 (progressive printing) | RETAINED | Disclosed under "Output timing" |
| R926-4 (POSITIVE at `f1b566a`), R926-3 (POSITIVE at `0ba80c4`) | No open MINOR+ | Their open residues are covered above |

## 4. Findings

### R925-4-F1 - MINOR - Tests, Robustness, Docs: check 7's serial reference depends on how the host's `/bin/sh` runs the line

- **Where**:
  - `tb/verilator/engine/passes_test.py:366-367`: the reference recipe `@python3 -c 'import os; os.kill(os.getpid(), N)'`.
  - The claims at `passes_test.py:35-36` ("so the check holds on any host's /bin/sh") and `:354`.
  - the PR body's `make passes-test` bullet, body line 69 ("so the check holds on any host's `/bin/sh`").
- **Authority**:
  - The check's own stated purpose: a host-independent check of the `gen_signal` re-raise.
  - The suite contract: `passes-test` is in the engine `all` (`Makefile:37`), so a false FAIL fails the engine suite.
- **Evidence**:
  - The reference line has shell syntax (quotes), so make runs it through `/bin/sh -c`. The replay line (`python3 …/pass_run.py replay-gen 1`) has none, so make runs it directly.
  - On a `/bin/sh` that forks a single `-c` command and reports a signal death as 128+n, the two arms differ:
    - The reference ends `Error 139` / `Error 137`.
    - The crafted `gen_signal` replay ends `Segmentation fault (core dumped)` / `Killed`.
  - Dash before 0.5.11 is such a shell, per its release history; that version was not executed here.
  - `scripts/check7_shell_probe.sh` runs the suite's own `gen_signal()` from copies. Only the reference Makefile names an emulated forking shell; the replay Makefile is padded one line so recipe line numbers match. Results (`receipts/check7-shell-probe.log`):
    - As written: host bash `bad = 0`; forking shell `bad = 2` ("Segmentation fault (core dumped)" vs "… Error 139", "Killed" vs "… Error 137").
    - Reference prefixed by `exec`: `bad = 0` on both shells.
  - The product is right on such a host. `scripts/gen_signal_shell_probe.sh` (`receipts/gen-signal-shell-probe.log`) shows:
    - A forking shell records `{"gen": 139}`, with no `gen_signal`, and both serial and replay end `Error 139`.
    - The only difference is the pid inside the emulated shell's own message, an artefact of the emulation.
  - The false FAIL is therefore in the test, not the product.
- **Impact**: on a host whose `/bin/sh` forks the line, `passes-test`, and with it `make -C tb/verilator/engine all` (and so `make -C gptp-processor all` in the parent bank), fails although the product is correct. The published portability claim is false.
- **Required outcome**:
  - Make the reference line die of the signal itself on any POSIX `/bin/sh`. Two ways:
    - `exec python3 -c '…'`, as in the verified variant;
    - a script file run with no shell syntax, which make runs directly.
  - Alternatively, derive the expected line from how the host shell actually ended a probe line.
  - Keep the docstring and PR claims only if they then hold.
- **Verification**: `scripts/check7_shell_probe.sh CLONE WORKDIR` gives `bad = 0` for both shells, and `passes-test` stays 71/71 on bash.

### R925-4-F2 - MINOR - Conformance, Robustness, Docs: a no-core replay still dumps core under a piped `core_pattern`

- **Where**:
  - `tb/verilator/engine/pass_run.py:249-252` (`reraise`): `if not core: setrlimit(RLIMIT_CORE, (0, hard))`.
  - Its docstring at `:250`, "dumping core only if it did".
  - Both callers: `replay` `:245`, and the new generator path `replay_gen` `:223`.
- **Authority**:
  - #111 criterion 1: transcript and exit code identical to the serial run's with a planted defect.
  - `reraise()`'s own contract.
  - The PR body: "Each replay line ends as the serial line ended".
- **Evidence**:
  - On this host, `core_pattern` pipes cores (`receipts/core-limit-probe.log`). A process that sets a soft core limit of 0 and then raises SIGSEGV still ends `(core dumped)`. A limit of 1 byte ends without a dump.
  - `scripts/core_limit_replay_probe.sh` (`receipts/core-limit-replay-probe.log`) runs a SIGSEGV through a recipe line and through `pass_run.py run` + `replay` at caller soft limits of 0, 1 and 1 MiB bytes. At 1 byte:
    - The pass records `{"signal": 11, "core": false}`.
    - The serial line reports `Segmentation fault`.
    - The replay reports `Segmentation fault (core dumped)`, and the collector receives a core the caller had suppressed.
  - At 0 and 1 MiB both sides match.
  - The same mismatch arises for any original death that did not dump on a piped host, for example a non-dumpable process.
  - R925-2-S2 noted the zero limit as a test-coverage gap. This round moved the logic into `reraise()`, stated the contract, and extended it to the generator.
- **Impact**: the case is narrow. It needs a piped `core_pattern` plus an original death without a dump. There, a replayed signal death's make line differs from the serial one (`(core dumped)` added), and one unwanted core record is created. Clean runs are unaffected.
- **Required outcome**:
  - Re-raise a no-core record without a dump on piped and file `core_pattern`s alike. For example, lower the soft limit to 1 instead of 0: the kernel's piped path skips a dump at exactly 1, and its file path rejects a limit below the minimum dump size. The file path was not executed here.
  - Or narrow the docstring and PR to the hosts where it holds.
  - Add a check with a crafted `{"signal": 11, "core": false}` record replayed under a 1-byte caller limit against a serial line under the same limit, so it discriminates on piped hosts.
- **Verification**: `scripts/core_limit_replay_probe.sh CLONE WORKDIR` reports SAME at all three limits. With the change reverted, the new check fails on a piped host.

### Residue (wording only; does not affect the verdict)

- **R925-4-R1 - RESIDUE - Tests/Docs (test docstring).** `passes_test.py:17-18` "each with no option, -s, -i and -k, and at -j4 and -j1" overstates the matrix: `-j1` runs with no option only (`passes-test-run1.log`). Exact fix: "each with no option, -s, -i and -k at -j4, and again at -j1 with no option". Re-wrap `:18`, which this delta lengthened to 116 columns in an 80-column docstring.
- **R925-4-R2 - RESIDUE - Tests/Docs (retained R925-2-R1).** `passes_test.py:37` "Nothing is built or simulated; it takes seconds." Exact fix: "Nothing is built or simulated; it takes about 90 seconds." That matches `Makefile:63`, `:96` and `docs/TEST_DEVELOPER.md`, and the measured 95.6 s.
- **R925-4-R3 - RESIDUE - Tests (function docstring).** `passes_test.py:329` "re-raised from obj_dir/, so a file core_pattern keeps the simulator's core". Exact fix: "re-raised from obj_dir/engine-passes/, so a relative file core_pattern keeps the simulator's core".
- **R925-4-R4 - RESIDUE - Docs (source comment, docstring, PR body).** `pass_run.py:255` "a file core_pattern writes this process's core here, never over the simulator's" holds only for a relative pattern. A fixed absolute pattern such as `/tmp/core` is not redirected by `chdir`. Exact fix: "a relative file core_pattern writes this process's core here, never over the simulator's". The same change ("a relative file core_pattern") applies to `passes_test.py:31-32` and to the PR body's "Where `core_pattern` is a file such as `core`" → "Where `core_pattern` is a relative file name such as `core`".
- **R925-4-R5 - RESIDUE - Docs (PR body).** "`passes-test` is green on six runs in a row." The six runs were at `f1b566a` (69 checks). At this head the published runs are three (71 checks). Exact fix: "`passes-test` was green on six runs in a row at `f1b566a` and on three at `dcf1cae`."
- **R925-4-R6 - RESIDUE - evidence packet (retained R925-2-R2 / R925-3-R3).** `author-r2/receipts/gptp/summary.txt:1` names `tools/logcmp.py`. Exact fix, in the next packet's index: "tools/logcmp4.py (round 3's logcmp.py masks, plus this round's clone paths) removes only host text".

### Suggestions (do not affect the verdict)

- **S1 - Robustness (unchanged code).** Unlink `obj_dir/engine-passes/N.pid` once pass N is over, after `pass_run.py:174`. A later `stop_later` (`:184-191`) then cannot send SIGUSR1 to a pid the kernel may have recycled. That is negligible on one host, but the signal's default action would terminate whatever process holds the pid.
- **S2 - Robustness (carried from R925-3 "recorded but not raised").** While the generator runs, register it so that `forward` and `stop` reach it (`pass_run.py:129-139`). TERM to the wrapper alone would then not wait for the generator to finish.
- **S3 - Tests (retained R925-3-S4).** Make both race fixes deterministic in the suite. `scripts/race_probe.py` has both shapes:
  - SIGUSR1 at 1 ms spacing across a pass's exit;
  - a `Popen` wrapper that raises TERM before registration.
- **S4 - Tests (style).** `passes_test.py:329`, `:373` and `:382` run 121, 122 and 132 columns. The rest of both files stays within 120.
- **Retained:** R925-2-S3 and S4, R925-3-S1 and S2, and R926-2-S1, as in §3.
- **Comment rule.** The delta's new comments (`pass_run.py:126-128`, `:149`, `:173`, `:250`, `:255`; `passes_test.py:336`) state behaviour and reason. None carries a bench lane label, lane name, review round, reviewer ID or comment ID (`git diff 0ba80c4..HEAD` added-line scan: no match). No residue under that rule.

## 5. Lens evidence

| Lens | Result | Artifact-specific evidence |
|---|---|---|
| Conformance | UNCLEAN (F2) | #111 criterion 1: own transcript plans 71/71 ×3, including the new generator plan under none/-s/-i/-k at `-j4` and at `-j1`. F2 breaks transcript identity under a piped `core_pattern` with a death that did not dump. Criterion 2: instructions +0.293 % and +0.040 %, recomputed |
| RTL | CLEAN | `git diff 1213ac5..HEAD` touches no `hdl/`, `syn/` or `bench/` file. `make lint` rc 0 with pinned Verilator 5.050 (identity verified) and with the system one. The delta is Python test tooling only |
| Robustness | UNCLEAN (F1, F2) | Race (a) and race (b) closed (probes A and B, head against fix deleted). F1: suite false FAIL on a forking `/bin/sh`. F2: unwanted core and transcript change. S1 and S2 noted |
| Tests | UNCLEAN (F1) | Three own runs 71/71. Three plants caught (1, 2 and 5 FAIL). Check 6's probe is faithful (cwd recorded at the real `os.kill`). Check 7 is host-shell dependent (F1). Races covered only by repetition (S3) |
| Docs | UNCLEAN (F1, F2) | False claims in prose: check 7 "any host's /bin/sh" (F1); `reraise` "dumping core only if it did" (F2). `make docs` rc 0. `docs/TEST_DEVELOPER.md` unchanged by the delta and consistent ("about 90 seconds"). PR figures verified. Wording R1-R6 |

## 6. Reviewer-owned ledger

| Lens | CLEAN/UNCLEAN | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN | #111 body and amendment; PR body; `pass_run.py` `run`/`replay_gen`/`replay`/`reraise`; `passes_test.py` plans; `author-r2` `summary.txt` | R925-4 | dcf1caef6966221fda86684bf6406fe3134a0b11 |
| RTL | CLEAN | `git diff --stat 1213ac5..HEAD` (no HDL); `make lint` pinned 5.050 and system | R925-4 (carried, no RTL delta) | dcf1caef6966221fda86684bf6406fe3134a0b11 |
| Robustness | UNCLEAN | `pass_run.py:94-191`, `:249-256`; race probes A and B; shell and core probes | R925-4 | dcf1caef6966221fda86684bf6406fe3134a0b11 |
| Tests | UNCLEAN | `passes_test.py` checks 1-7, three own runs, three plants, packet runs `pt-s1..6` and `pt-g1..3` | R925-4 | dcf1caef6966221fda86684bf6406fe3134a0b11 |
| Docs | UNCLEAN | Module, function and comment prose in both files; PR body; `docs/TEST_DEVELOPER.md`; `make docs` | R925-4 | dcf1caef6966221fda86684bf6406fe3134a0b11 |

## 7. Real limits

- **No dash or other forking `/bin/sh` was executed.** This host's `/bin/sh` is bash. Both shell behaviours were emulated: a wrapper shell named only in the reference Makefile, and a copy of `pass_run.py` pointed at it.
  - Which real shells fork or exec is stated from release history, not run.
  - Whether a current dash execs the redirected generator line, which would exercise the `gen_signal` path end to end, was not run.
- **No file `core_pattern` was executed.** Changing it needs privilege. The F2 remedy's file-pattern half is from kernel behaviour, not tested.
- The race probes intercept or flood from outside. They do not trace interpreter shutdown itself.
- The measurements are the author's, at `661e4c3`. I recomputed them but did not rerun them. No manager source bank runs at this head, and I claim none.
- Physical calibration NOT RUN. Field skips are not hardware proof. No hosted job ran at this head.
- This review did not re-execute code untouched by the delta beyond what `passes-test` covers.

## 8. Pending manager duties

- At the merge turn: validate the current-dev merge candidate on the builder and native banks (source base `1213ac5`, live dev `e275d79`) and link the receipts on the PR.
- Report whether those banks' `/bin/sh` forks single `-c` commands, as old dash does; there F1 fails `passes-test` in the engine `all`.
- Report whether their `core_pattern` is piped (F2).
- Own hosted and act acceptance; none exists at this head.
- Carry R1-R6 to the residue checklist.
- Publish this packet: `MANIFEST.sha256` lists every receipt and script.

## 9. Packet contents

- `REPORT.md`.
- `scripts/`: `race_probe.py`, `gen_signal_shell_probe.sh`, `check7_shell_probe.sh`, `core_limit_replay_probe.sh`, `plants.sh`, `verify_packet.py`. Each takes the clone and a work directory as arguments.
- `receipts/`, listed in `MANIFEST.sha256`:
  - `passes-test-run1..3`, plus `plant-*` logs, patches and rcs;
  - `race-probe.log`, `check7-shell-probe.log`, `gen-signal-shell-probe.log`, `core-limit-probe.log`, `core-limit-replay-probe.log`;
  - `make-docs`, `make-lint`, `make-lint-pinned`;
  - `packet-verify.txt`, `hosted-query.txt`, `checkout-integrity.txt`, `env.txt`.

R925-4 FINISHED
