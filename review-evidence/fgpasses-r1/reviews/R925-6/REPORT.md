[R925] NEGATIVE - exact head dfd13a1079d265d68edc806b2d8111d0e5f89493

# R925-6: narrow re-review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111)

Head `dfd13a1079d265d68edc806b2d8111d0e5f89493`, tree `2615bfb2baa70beb33b1e053522fbc3f1d4122f7`. Source base `1213ac5b9e09b8759ba76cc70c53652b5e108996`.

**Verdict: NEGATIVE, on one MINOR in the PR body's test-coverage claim.** The code is right. Every finding this round was asked to verify is closed at its cause, and I confirmed each by running it:

- R925-4-F1: check 7's reference line is exec'd. My shell probe gives `bad = 0` under host bash and under an emulated forking shell. With the `exec` stripped, the forking shell gives `bad = 2`, so the `exec` is what makes the check hold.
- R925-4-F2 and its remainder R925-5-F1: `reraise()` makes a no-core death non-dumpable. My core-limit probe is SAME at soft limits 0, 1 and 1 MiB. My hard-zero probe is SAME at (0,0), (0,∞) and (1,∞). With the `prctl` line removed, (0,0) DIFFERS.
- R925-5-F2: `passes-test` no longer crashes under `ulimit -c 0`. It passes 73/73 there.
- R1 to R6, S1 and S4: R1, R2, R3, R5, R6, S1 and S4 are closed. R4 is still open in one place, at `passes_test.py:31-32` (RESIDUE).

`passes-test` passed 73/73 on each of my three runs: two plain, one under `ulimit -c 0`. Three of my five plants are caught. `make docs` and `make lint` (pinned Verilator 5.050) exit 0.

**R925-6-F1 (MINOR, Tests and Docs).** The PR body says the suite catches fourteen planted defects. One of them, "a no-core replay lowering the core limit to 0 instead of 1", is not caught at this head. Since `dfd13a1`, the `prctl` call alone suppresses the dump, so the soft limit has no effect the suite can see. That plant passes 73/73, both at an unlimited core limit and under `ulimit -c 0`. The claim was true at `a54e9ee` but no longer holds.

## 0. Scope of this round

- **Delta.** The dispatch names "ONE manager commit dcf1caef..a54e9eee", "packet author-r6" and "72 checks". The exact head is one commit past that:
  - `a54e9ee` answers R925-4 (packet `author-r6`, 72 checks);
  - `dfd13a1` answers R925-5 (packet `author-r7`, 73 checks).

  I reviewed `git diff dcf1cae..dfd13a1`: `pass_run.py` +12/-3 and `passes_test.py` +54/-11. Both authored commits were checked against their packets' `diff.txt`. The full PR diff `1213ac5..dfd13a1` touches only `docs/TEST_DEVELOPER.md`, `tb/verilator/engine/{Makefile,pass_run.py,passes_test.py}`; the delta touches no `docs/`, `hdl/`, `syn/` or `bench/` file.
- **Named items.** R925-4-F1, F2, R1-R6, S1 and S4. I also resolve my own R925-5 findings (F1, F2, R1, S1-S4) at their cause, because they are public findings on this PR.
- **Prior lens verdicts carried.** Code the delta does not touch keeps R925-5's verdict: the `run` path, races, budget, fail-fast, Makefile and guide. RTL is carried; the delta has no RTL.
- No manager source bank runs at this head, and I claim none. The source-head execution evidence is the author's packet plus my own focused runs.

## 1. Evidence verified

### Author packet

- Evidence commit `7dfc125877731a27bf055ee6427c6af8861ae36c`, `review-evidence/fgpasses-r1`. `MANIFEST.json` has 890 entries, and all 890 `published_sha256` values match. Nothing is missing and nothing is unlisted (`receipts/packet-verify.txt`). This is a hash manifest, not a cryptographic signature.
- `author-r6/receipts/diff.txt` is byte-identical to `git diff dcf1cae..a54e9ee`, and `author-r7/receipts/diff.txt` to `git diff a54e9ee..dfd13a1`.
- Spot-checked logs:
  - `author-r6`: `pt-i1..i4`, 72 PASS each. `plant-nocore`: 1 FAIL, at `a54e9ee`.
  - `author-r7`: `pt-k1..k4`, 73 PASS each; `pt-k0` (under `ulimit -c 0`), 73 PASS. `plant-prctl` (under `ulimit -c 0`): 3 FAIL, namely check 7 SIGSEGV and both check-8 lines.
  - `author-r7` has no soft-limit plant at this head. The soft-limit plant listed in the PR is from `a54e9ee`.

### Hosted

- No check runs and no statuses exist at the exact head (0 and 0; `receipts/hosted-query.txt`). I make no hosted claim. Hosted and act acceptance belong to the manager.

### My runs at the exact head

The environment (`receipts/env.txt`): Python 3.14.10, GNU make 4.4.1, `/bin/sh` is bash, kernel 7.3.4. `core_pattern` is piped to the systemd collector. `fs.suid_dumpable` is 2. The caller's core limit is unlimited/unlimited.

| Run | rc | PASS / FAIL | Wall |
|---|---:|---:|---:|
| `make -C tb/verilator/engine passes-test` (`receipts/passes-test-run1.log`) | 0 | 73 / 0 | 98.1 s |
| the same, run 2 (`receipts/passes-test-run2.log`) | 0 | 73 / 0 | 98.4 s |
| `bash -c 'ulimit -c 0; make … passes-test'` (`receipts/passes-test-ulimit-c0.log`) | 0 | 73 / 0 | 98.5 s |
| `make docs` (`receipts/make-docs.log`) | 0 | source evidence 20 exact, 0 findings; selftests PASS | |
| `make lint`, pinned Verilator (`receipts/make-lint-pinned.log`; identity `Verilator 5.050 2026-07-01 rev v5.050`) | 0 | | |

All three suite runs ran at once, beside the five plants.

### Plants

Each plant is a copy of the engine directory running the full `passes_test.py` (`scripts/plants.sh`; `receipts/plant-*.{patch,log,rc}`; `receipts/plants-summary.txt`).

| Plant | Caller core limit | rc | Result |
|---|---|---:|---|
| `no-prctl`: the `prctl` line removed | unlimited | 1 | 2 FAIL: check 7 SIGSEGV, check 8 at limit 0 |
| `no-prctl-c0` | `ulimit -c 0` | 1 | 3 FAIL: check 7 SIGSEGV, check 8 both lines |
| `prior-reraise`: `dcf1cae`'s `reraise()` (soft 0, no `prctl`) | unlimited | 1 | 3 FAIL: check 7 SIGSEGV, check 8 both lines |
| `soft0-keep-prctl`: soft limit 0 instead of 1, `prctl` kept | unlimited | 0 | **73 PASS: survives** (F1) |
| `soft0-keep-prctl-c0` | `ulimit -c 0` | 0 | **73 PASS: survives** (F1) |

### Shell and core probes

- **`scripts/check7_shell_probe.sh`** (`receipts/check7-shell-probe.log`) runs the suite's own `gen_signal()` from copies. Only the reference Makefile names an emulated `/bin/sh` that forks its `-c` command unless the command is `exec …`:

  | Variant | Host bash | Forking shell |
  |---|---|---|
  | As written | `bad = 0` | `bad = 0` |
  | Reference `exec` stripped | `bad = 0` | `bad = 2` ("Segmentation fault" vs "… Error 139"; "Killed" vs "… Error 137") |

- **`scripts/core_limit_replay_probe.sh`** (`receipts/core-limit-replay-probe.log`): a dumpable SIGSEGV through a recipe line, and through `pass_run.py run` + `replay`, at caller soft limits of 0, 1 and 1048576 bytes. All three are **SAME**:
  - at 0 and at 1 MiB, the record has `core: true` and both sides say `(core dumped)`;
  - at 1, the record has `core: false` and both sides say `Segmentation fault`.
- **`scripts/hard_zero_probe.sh`** (`receipts/hard-zero-probe.log`): a non-dumpable SIGSEGV at (soft,hard) = (0,0), (0,∞) and (1,∞).
  - Head copy: SAME ×3.
  - Copy with the `prctl` line removed: DIFFERS at (0,0), where the replay says `Segmentation fault (core dumped)`, and is SAME at the other two.

  The suppression therefore comes from `prctl`, and it holds on a host with `fs.suid_dumpable` 2.

### Checkout integrity after all probes (`receipts/checkout-integrity.txt`)

- HEAD `dfd13a1…` and tree `2615bfb…`; `git write-tree` gives `2615bfb…`. `git status --porcelain --ignored` is empty, and `diff-index` lists 0 paths.
- The `git hash-object` IDs of all 122 working-tree files equal the HEAD blob IDs. The index has 118 files at 100644 and 4 at 100755, and 0 files have the wrong mode on disk.
- This repository has no `.gitmodules` and no gitlinks, so no submodule gitlink is required at this head.

## 2. Delta assessment

### R925-4-F1: check 7's reference line (`passes_test.py:372-373`)

- The reference is `exec python3 -c 'import ctypes, os; ctypes.CDLL(None).prctl(4, 0, 0, 0, 0); os.kill(…)'`. It dies of the signal itself on any POSIX shell, and it is non-dumpable, which matches its record's `gen_core: false`.
- My probe gives `bad = 0` on both shells. With the `exec` stripped, the forking shell gives 2 FAIL.
- The docstring's item 7 (`:34-38`) and PR body lines 70-72 state exactly this.
- **RESOLVED.**

### R925-4-F2 and R925-5-F1: a no-core replay that still dumped

- When the record has no core, `reraise()` (`pass_run.py:252-265`) now calls `prctl(PR_SET_DUMPABLE, 0)` (`:261`). It also sets the soft limit to 1 where the hard limit allows (`:258-260`).
- The kernel's core-dump path skips a process whose dumpable flag is 0, whatever the limits and the pattern. `fs.suid_dumpable` only sets the flag at a credential change; an explicit `prctl(…, 0)` overrides it.
- Executed confirmation on a piped host with `suid_dumpable` 2: both probes are SAME at every limit, including the hard-0 case R925-5-F1 named.
- The `reraise` docstring (`:253-256`) and PR body lines 112-114 describe this accurately.
- **RESOLVED** at all three limits. The file-pattern half is from kernel behaviour, not executed (§7).

### R925-5-F2: check 8 crashed under a hard core limit of 0

- `no_core_replay()`'s `caller` (`passes_test.py:394-400`) no longer sets a soft limit above the hard one. Where the hard limit is finite, it clamps the requested (1, ∞) to `(min(1, hard), hard)`.
- The serial reference is non-dumpable (`:391-392`), so the (0,0) arm is meaningful: it covers R925-5-F1's case.
- `ulimit -c 0` run: 73/73, rc 0. Check 8 is still load-bearing: `no-prctl` and `prior-reraise` are caught.
- **RESOLVED.** See S1 for the label of the clamped arm.

### Residues and suggestions named for this round

| Item | State | Evidence |
|---|---|---|
| R925-4-R1 (matrix wording, wrap) | RESOLVED | `passes_test.py:18-21`, within 80 columns |
| R925-4-R2 ("takes seconds") | RESOLVED | `:42` "about 90 seconds"; my runs took 98 s with eight suites at once |
| R925-4-R3 (check 6 function docstring) | RESOLVED | `:334-335` |
| R925-4-R4 ("a relative file core_pattern") | RESOLVED in `pass_run.py:264` and the PR body (line 109). **RETAINED** at `passes_test.py:31-32` | R925-6-R1 |
| R925-4-R5 (run counts in the PR) | RESOLVED for `f1b566a`, `dcf1cae` and `a54e9ee`. The head's count is new wording | R925-6-R2 |
| R925-4-R6 (`summary.txt` names `tools/logcmp.py`) | RESOLVED | `author-r6/REVIEW-READY.md` states that `tools/logcmp4.py` is round 4's comparison tool and removes only host text |
| R925-4-S1 (pid file outlives its pass) | TAKEN | `pass_run.py:177` unlinks it after SIGUSR1 is ignored (`:176`), before the record is written. A SIGKILLed pass leaves its file behind, which is negligible |
| R925-4-S4 (line width) | TAKEN | No line in either file exceeds 120 columns (`receipts/delta-scan.txt`). `passes_test.py:4` (82 columns, from `661e4c3`) is outside the delta |

### Comment rule

- No added line in `dcf1cae..dfd13a1` carries a bench lane label, lane name, review round, reviewer ID or issue-comment ID (`receipts/delta-scan.txt`).
- The new comments state behaviour and reason: `pass_run.py:54`, `:177`, `:253-256`, `:264`; `passes_test.py:373`, `:387-388`.
- No residue under that rule.

## 3. Prior public findings at this head

| Finding | State at this head | Evidence |
|---|---|---|
| R925-4-F1 MINOR (check 7 depends on the host shell) | RESOLVED | §2, check-7 probe |
| R925-4-F2 MINOR (a no-core replay dumps under a piped `core_pattern`) | RESOLVED | §2, core-limit probe SAME ×3 |
| R925-5-F1 MINOR (hard limit 0: a no-core replay dumps) | RESOLVED | §2, hard-zero probe SAME ×3 at head, DIFFERS without `prctl` |
| R925-5-F2 MINOR (check 8 crashes under `ulimit -c 0`) | RESOLVED | 73/73 under `ulimit -c 0` |
| R925-4-R1, R2, R3, R5, R6 RESIDUE | RESOLVED | §2 |
| R925-4-R4 / R925-5-R1 RESIDUE (`passes_test.py:31-32`) | RETAINED | R925-6-R1 |
| R925-4-S1, S4 | TAKEN | §2 |
| R925-5-S1 (run-side `gen_signal` record not exercised on bash hosts) | RETAINED | `pass_run.py:139-140` is unchanged; check 7 still crafts the record |
| R925-5-S2 / R925-4-S3 / R925-3-S4 / R926-4-S1 (deterministic race checks) | RETAINED | Unchanged |
| R925-5-S3 / R925-4-S2 (register the generator for forwarding) | RETAINED | `pass_run.py:131-135` unchanged |
| R925-5-S4 (`no_cores()` says "No core files") | RETAINED, narrowed | Check 7's reference is now non-dumpable. Check 1's SIGSEGV and SIGABRT stub plans still send cores to a piped collector under `no_cores()` (0,0) (`passes_test.py:197-201`, unchanged) |
| R925-2-S3, R925-2-S4, R925-3-S1, R925-3-S2, R926-2-S1 | RETAINED | Untouched by the delta |
| R926-1..4 MAJOR/MINOR (budget, `-s`/`-i`/`-k`, replay errors, CPU acceptance, the `-i` guide sentence) | Still RESOLVED | The delta touches none of them, and every check that covers them passes 73/73 ×3 |

I read the published reviews only after writing this round's verdict and ledger. They are under `review-evidence/fgpasses-r1/reviews/` at `7dfc125`, and the latest PR comments say the same. No other reviewer has reviewed `dcf1cae`, `a54e9ee` or `dfd13a1`; the second reviewer's last round, R926-4, is POSITIVE at `f1b566a`. The published R925-5 report is byte-identical to the one this table resolves.

## 4. Findings

### R925-6-F1 - MINOR - Tests, Docs: the PR body counts a planted defect that this head's suite does not catch

- **Where**: PR #112 body, lines 75 and 88:
  - "**Planted defects.** Fourteen are each caught by `passes_test.py`:"
  - "a no-core replay lowering the core limit to 0 instead of 1;"
- **Authority**:
  - The PR's own validation claim, and the repository's planted-defect rule (engine `Makefile`: "prove the checks above are load-bearing").
  - The owner's RESIDUE rule. This sentence states a test-coverage result and a figure ("Fourteen"), so it is not wording only.
- **Evidence**:
  - `receipts/plant-soft0-keep-prctl.log` and `receipts/plant-soft0-keep-prctl-c0.log`: replacing `soft = 1 if … else 0` with `soft = 0` (`pass_run.py:259`) leaves `passes-test` at 73/73, rc 0, both at an unlimited core limit and under `ulimit -c 0`.
  - The plant was caught at `a54e9ee` (`author-r6/receipts/passes-test-plant-nocore.log`, 1 FAIL), before `prctl` existed.
  - At `dfd13a1`, `prctl(PR_SET_DUMPABLE, 0)` (`:261`) suppresses the dump at every limit (hard-zero probe). The soft limit therefore changes nothing the suite can observe, on any Linux host.
  - `author-r7` publishes no soft-limit plant at this head.
- **Impact**: a reader is told that a fourteenth defect is guarded when it is not. The code is correct; the soft limit is now an undetectable fallback.
- **Required outcome** (either):
  - (a) In the PR body, delete the bullet "a no-core replay lowering the core limit to 0 instead of 1;" and change "Fourteen" to "Thirteen". Optionally add after the `prctl` bullet at lines 112-114: "the soft limit is a fallback the suite cannot distinguish, since `prctl` alone suppresses the dump".
  - (b) Remove the now-redundant soft-limit fallback from `reraise()` (`:258-260`), and its mentions in the docstring (`:255-256`) and PR body (`:113-114`). Then make the same change to the plant list.
- **Verification**: every bullet in the PR's planted-defect list maps to a plant that the head's suite fails. `scripts/plants.sh CLONE WORKDIR` reproduces the survivor.

### Residue (wording only; does not affect the verdict)

- **R925-6-R1 - RESIDUE - Tests/Docs (module docstring; retained R925-5-R1 and the last part of R925-4-R4).**
  - `tb/verilator/engine/passes_test.py:31-32` reads "so a file core_pattern never replaces the simulator's core". A fixed absolute pattern is not redirected by the `chdir`, as `pass_run.py:264`, `passes_test.py:334-335` and the PR body (lines 109-111) already say.
  - Exact fix: "6. A replayed signal death is re-raised from obj_dir/engine-passes/, so a relative file core_pattern never replaces the simulator's core." Re-wrap to 80 columns.
- **R925-6-R2 - RESIDUE - Docs (PR body).**
  - Lines 93-94 read "and at this head on three runs plus one under `ulimit -c 0`". `author-r7` publishes four plain runs (`pt-k1..k4`, 73 PASS each) plus `pt-k0` under `ulimit -c 0`. `author-r7/REVIEW-READY.md` has the same "three runs".
  - Exact fix: "and at this head on four runs plus one under `ulimit -c 0`".

### Suggestions (do not affect the verdict)

- **S1 - Tests (check 8's label).** Where the caller's hard core limit is finite, check 8's second arm runs at `(min(1, hard), hard)`. Under `ulimit -c 0` that is (0,0), yet `passes_test.py:415-416` prints "at core limit 1" (`receipts/passes-test-ulimit-c0.log`, and `author-r7`'s `pt-k0` and `plant-prctl`).
  - Print the limit actually set, for example `at core limit {want[0]} (hard {hard})` through a value the preexec returns, or label the arm "clamped to the hard limit".
  - PR lines 73-74 ("at caller core limits of 0 and 1") would then hold where the hard limit is at least 1.
- **S2 - Robustness (`pass_run.py:261`).** The `prctl` return value is unchecked, and `use_errno=True` is never read. Either check that the call returns 0 and raise `OSError(ctypes.get_errno(), …)`, or drop `use_errno`. On a libc without `prctl`, attribute lookup raises before the kill. That is outside this Linux-only suite, but a one-line guard would state it.
- **S3 - Robustness/Docs.** With `prctl` in place, the soft-limit lowering (`:258-260`) is belt-and-braces with no observable effect. Keep it only if the docstring calls it a fallback; F1 option (b) removes it.
- **Retained:** R925-5-S1, S2, S3, S4 (narrowed); R925-2-S3, S4; R925-3-S1, S2; R926-2-S1 (§3).

## 5. Lens evidence

| Lens | Result | Artifact-specific evidence |
|---|---|---|
| Conformance | CLEAN | #111 criterion 1: a no-core signal death replays identically to the serial line at (0,0), (0,∞), (1,∞) and at soft 0, 1 and 1 MiB (two probes, piped host). Generator signal path identical on host and forking shells. Own plans 73/73 ×3. Criterion 2 is unchanged since R925-4; the delta adds a `prctl` call only on a replay that dies |
| RTL | CLEAN | `git diff 1213ac5..dfd13a1` touches no `hdl/`, `syn/` or `bench/` file. `make lint` rc 0 with the pinned Verilator 5.050 (identity verified). Carried from R925-5 for code the delta does not touch |
| Robustness | CLEAN | `reraise()` suppresses the dump at every limit, including hard 0 (`prctl` load-bearing: the hard-zero probe DIFFERS without it). Check 8 no longer raises under `ulimit -c 0`. The pid file is unlinked once the pass ends. Races unchanged since R925-4/-5. S2 and S3 are suggestions |
| Tests | UNCLEAN (F1) | 73/73 on two plain runs and under `ulimit -c 0`. The `no-prctl`, `no-prctl-c0` and `prior-reraise` plants are caught (2, 3 and 3 FAIL). Check 7's `exec` is load-bearing on a forking shell. F1: the PR's planted-defect list includes the soft-0 plant, which survives 73/73. S1: check 8's label under a finite hard limit |
| Docs | UNCLEAN (F1) | The PR's "Fourteen … caught" and its soft-limit bullet are false at this head (F1). The `reraise` docstring, the check 7/8 docstrings and PR lines 70-74 and 112-115 are accurate. `make docs` rc 0. `docs/TEST_DEVELOPER.md` is untouched by the delta and consistent ("about 90 seconds"). Wording R1 and R2 |

## 6. Reviewer-owned ledger

| Lens | CLEAN/UNCLEAN | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | CLEAN | #111 criterion 1 against `pass_run.py` `reraise`/`replay`/`replay_gen`; PR body lines 100-115; core-limit, hard-zero and check-7 probes; three own suite runs | R925-6 | dfd13a1079d265d68edc806b2d8111d0e5f89493 |
| RTL | CLEAN | `git diff --stat 1213ac5..dfd13a1` (no HDL); `make lint` with pinned 5.050 | R925-6 (carried, no RTL delta) | dfd13a1079d265d68edc806b2d8111d0e5f89493 |
| Robustness | CLEAN | `pass_run.py:54`, `:176-177`, `:252-265`; `passes_test.py:386-417` under unlimited and hard-0 limits; plants `no-prctl`, `prior-reraise` | R925-6 | dfd13a1079d265d68edc806b2d8111d0e5f89493 |
| Tests | UNCLEAN | `passes_test.py` checks 7 and 8 and module docstring; three own runs; five plants; `author-r6`/`author-r7` logs; PR planted-defect list | R925-6 | dfd13a1079d265d68edc806b2d8111d0e5f89493 |
| Docs | UNCLEAN | Module, function and comment prose in both files; PR body (190 lines, at this head); `author-r6`/`author-r7` `REVIEW-READY.md`; `docs/TEST_DEVELOPER.md`; `make docs` | R925-6 | dfd13a1079d265d68edc806b2d8111d0e5f89493 |

## 7. Real limits

- **No file `core_pattern` was executed.** Changing it needs privilege. That `prctl(PR_SET_DUMPABLE, 0)` suppresses a file dump comes from kernel behaviour, not from a run. The piped half was executed, on a host with `fs.suid_dumpable` 2.
- **No real forking `/bin/sh` was executed.** This host's `/bin/sh` is bash, and the forking shell was emulated (named only in the reference Makefile).
- No non-Linux host was run (S2).
- The measurements are the author's, at `661e4c3`. They were recomputed in R925-4 and not rerun. No manager source bank runs at this head, and I claim none.
- Physical calibration NOT RUN. Field skips are not hardware proof. No hosted job ran at this head.
- I did not re-execute code the delta does not touch, beyond what `passes-test` covers.
- The plants and probes ran on copies under the packet's `scratch/`. The clone was verified byte-identical to the head afterwards.

## 8. Pending manager duties

- At the merge turn: validate the current-dev merge candidate on the builder and native banks (source base `1213ac5`, live dev `e275d79`) and link the receipts on the PR.
- Own hosted and act acceptance. None exists at this head.
- Carry R925-6-R1 and R2 to the residue checklist.
- Publish this packet. `MANIFEST.sha256` lists every receipt and script.

## 9. Packet contents

- `REPORT.md`.
- `scripts/`: `verify_packet.py` (usage: `verify_packet.py ROOT`), `check7_shell_probe.sh`, `core_limit_replay_probe.sh`, `hard_zero_probe.sh` and `plants.sh`. Each shell script takes the clone and a work directory as arguments.
- `receipts/`:
  - `passes-test-run1`, `passes-test-run2` and `passes-test-ulimit-c0` (`.log` and `.rc`);
  - `plant-*` (`.patch`, `.log`, `.rc`) and `plants-summary.txt`;
  - `check7-shell-probe.log`, `core-limit-replay-probe.log`, `hard-zero-probe.log`;
  - `make-docs`, `make-lint-pinned`;
  - `packet-verify.txt`, `hosted-query.txt`, `delta-scan.txt`, `checkout-integrity.txt`, `env.txt`.

R925-6 FINISHED
