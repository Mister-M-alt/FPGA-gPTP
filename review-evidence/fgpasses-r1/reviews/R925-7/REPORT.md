[R925] POSITIVE - exact head a2352e723b481b011b32b0f6892a7920a079443b

# R925-7: narrow re-review of Mister-M-alt/FPGA-gPTP PR #112 (Closes #111)

Head `a2352e723b481b011b32b0f6892a7920a079443b`, tree `30a802e3f0acb6f0e63bd5a094e645e93f0efb7d`. Source base `1213ac5b9e09b8759ba76cc70c53652b5e108996`. Live dev `e275d7950ef3385753e6a15d2e191ba855b171ed` is not used here; the manager builds the merge candidate.

**Verdict: POSITIVE.** Both findings this round was asked to verify are closed at their cause at this head:

- **R925-5-F1: RESOLVED.** `reraise()` (`pass_run.py:252-261`) now makes a death recorded without a core non-dumpable through `prctl(PR_SET_DUMPABLE, 0)` (`:257`). My probe compares the replay of `{signal: SIGSEGV, core: false}` with an exec'd non-dumpable reference at caller limits (0,0), (0,∞), (1,∞) and (∞,∞). It matches at all four, both in the kernel's core bit and in make's message. It also matches under `ulimit -c 0`. With the `prctl` line removed, it DIFFERS at (0,0), (0,∞) and (∞,∞). The probe ran on a host with a piped `core_pattern` and `fs.suid_dumpable` = 2.
- **R925-5-F2: RESOLVED.** Check 8 (`passes_test.py:386-419`) compares the replay with an exec'd non-dumpable serial line (`:391-392`) at caller limits (0,0) and (1,∞). Where the hard limit is finite, the second arm is clamped and labelled as clamped. `passes-test` passed 73/73 on both of my runs at this head, one of them under `ulimit -c 0`. Run alone, check 8 does not crash at hard limits of ∞, 4 MiB, 1 KiB or 0. Check 7's reference (`:371-373`) is non-dumpable, as its `gen_core: false` record says.

The `prctl` plant is caught at this head: 2 FAIL at an unlimited hard limit (check 7, and check 8 at 0), and 3 FAIL under `ulimit -c 0` (the author's `author-r8` receipt). `make docs` exits 0. `make lint` (pinned Verilator 5.050) exits 0 with no errors or warnings. No MINOR or higher finding is open. The four suggestions below do not affect the verdict.

## 0. Scope of this round

- The brief names the manager commit `a54e9eee..dfd13a10` and packet `author-r7`. The exact head is one commit later: `a2352e7` sits on `dfd13a1` and drops the soft-limit fallback (option (b) of R925-6-F1). Its packet is `author-r8`. I reviewed both commits (`git diff a54e9ee..a2352e7`: `pass_run.py` +6/-5, `passes_test.py` +38/-27) and both packets.
- Code outside this delta keeps its prior lens verdict. The delta changes nothing that code depends on: it adds a `prctl` call only on the path where a replay dies, and changes check 7's reference line and check 8.
- I wrote my verdict and ledger before reading the R925-5 and R925-6 reports. The prior-findings table (§3) was written after that.

## 1. Evidence verified

### Author packets (evidence commit `13546f4cf18fd813de8a5c3577fefccb5fb36a6d`)

- All 14 files under `author-r7/` and `author-r8/` match their `published_sha256` in `review-evidence/fgpasses-r1/MANIFEST.json`, and none is path-redacted. The evidence commit is not git-signed; integrity rests on the manifest.
- `author-r8/receipts/diff.txt` is byte-identical to `git diff dfd13a1..a2352e7`.
- `author-r8` publishes `pt-l1` and `pt-l2` (73 PASS each), `pt-l0` under `ulimit -c 0` (73 PASS; the second check-8 arm is labelled "0 (clamped to the hard limit)"), and `plant-prctl2` (3 FAIL under `ulimit -c 0`: check 7 SIGSEGV and both check-8 arms).
- `author-r7` (at `dfd13a1`): `pt-k0..k4` and `plant-prctl`. These are superseded by `author-r8` at this head.

### Hosted

At the exact head, the check-runs API lists no runs, and the combined status is `pending` with no contexts. There is no hosted execution evidence at this head. Hosted and act acceptance belong to the manager.

### My runs at the exact head (Linux 7.3 x86_64, GNU Make 4.4.1, Python 3.14; `core_pattern` piped to systemd-coredump; `suid_dumpable` 2)

| Run | Result | Receipt |
|---|---|---|
| `make passes-test`, caller limit (∞,∞) | 73 PASS, rc 0, 96.8 s | `receipts/passes-test-head-run1.log` |
| `make passes-test` under `ulimit -c 0` | 73 PASS, rc 0, 96.8 s; second check-8 arm labelled "0 (clamped to the hard limit)" | `receipts/passes-test-head-ulimit-c0.log` |
| `probe_nocore.py`, hard ∞ | PASS at (0,0), (0,∞), (1,∞), (∞,∞): replay (11, no core) = non-dumpable reference. The dumpable reference dumps at (0,0), (0,∞), (∞,∞), so the probe can tell the two apart | `receipts/probe-head-hardinf.log` |
| `probe_nocore.py` under `ulimit -c 0` | PASS at (0,0) | `receipts/probe-head-ulimit-c0.log` |
| Check 8 alone at hard ∞, 4 MiB, 1 KiB, 0 (soft 0) | PASS ×2 at each, rc 0, no traceback | `receipts/check8-hard-limits.log` |
| `make docs` | rc 0 | `receipts/make-docs.log` |
| `make lint` (pinned 5.050; the wrapper reports `Verilator 5.050 2026-07-01 rev v5.050`) | rc 0, 0 `%Error`, 0 `%Warning` | `receipts/make-lint.log` |

I ran the two `passes-test` runs and the plant run concurrently.

### Plant: `prctl` removed (`receipts/plant-noprctl.diff`, `scripts/plant_noprctl.sh`)

- `probe_nocore.py`, hard ∞: **3 FAIL**. It DIFFERS at (0,0), (0,∞) and (∞,∞) with "Segmentation fault (core dumped)", and is the same at (1,∞), where the kernel skips a pipe (`receipts/probe-plant-noprctl-hardinf.log`).
- `probe_nocore.py` under `ulimit -c 0`: **1 FAIL** at (0,0) (`receipts/probe-plant-noprctl-ulimit-c0.log`).
- `passes-test`, hard ∞: **2 FAIL**. Check 7 SIGSEGV fails, and check 8 fails at limit 0. Check 8 at limit 1 passes (`receipts/passes-test-plant-noprctl-hardinf.log`).

### Delta scan (`receipts/delta-scan.txt`)

- No line in either file exceeds 120 columns. The module docstring stays within 80 columns.
- No added line carries a lane label, lane name, review round, reviewer ID or issue-comment ID.
- One unused import, `resource` in `pass_run.py:45`, was left by `a2352e7`. See S2.

### Checkout integrity after all probes (`receipts/checkout-integrity.txt`)

- HEAD `a2352e7…` and tree `30a802e…`. `git write-tree` equals the HEAD tree. The worktree equals the index, and the index equals HEAD.
- `git status --ignored` is empty. A `__pycache__/` that my check-8 import wrote in the clone was removed.
- The repository has no submodules, so no gitlinks need checking.
- All plants ran in disposable copies under `scratch/`.

## 2. Delta assessment

### R925-5-F1: a no-core replay must not dump at any caller limit (`pass_run.py:252-261`)

- `prctl(PR_SET_DUMPABLE, 0)` clears the mm's dumpable flag. The kernel's core-dump path gives up when that flag is 0, before it looks at the limit or the pattern. `fs.suid_dumpable` only sets the flag at exec or a credential change.
- Executed confirmation is above: with `suid_dumpable` 2 on a piped host, there is no dump at any limit.
- The soft-limit fallback is gone (`a2352e7`). The docstring at `:253-255` now says only what the code does.
- The file-pattern half rests on kernel behaviour and was not executed (§6).
- `prctl` is called only when `core` is false. A record with `core: true` still dumps as before (check 6 and prior rounds).

### R925-5-F2: check 8 at caller limits 0 and 1 against a non-dumpable serial line (`passes_test.py:386-419`)

- The serial reference execs `python3`, which makes itself non-dumpable and then kills itself with SIGSEGV. The comparison is therefore like with like: a no-core record against a no-core serial death.
- `caller` never sets a soft limit above the hard one. Under (1,∞) with a finite hard limit it uses `(min(1, hard), hard)`. My check-8-only runs show no crash at any of the four hard limits.
- The label (`:415-417`) says "clamped to the hard limit" when the hard limit is finite. See S3 for its wording when the hard limit is at least 1.
- Check 7's reference (`:371-373`) now uses the same non-dumpable line, with the comment "no core, as the record says".

### Docs and the PR body

- Module docstring items 6-8 (`passes_test.py:32-42`) match the code: "relative file core_pattern", "under caller core limits of 0 and of 1, on a piped core_pattern too".
- PR body lines 16-18 list all three latest commits. Lines 74-75 describe check 8. Lines 76-89 list thirteen plants with no soft-limit plant. Lines 93-94 read "at this head on two plus one under `ulimit -c 0`", which matches `author-r8`. Lines 112-113 describe the `prctl` behaviour.
- The test guide and the Makefile carry no core-limit wording to update.

## 3. Prior public findings at this head

I read these after writing my verdict and ledger. The sources are `review-evidence/fgpasses-r1/reviews/R925-5/` and `R925-6/` at `13546f4`, and the PR comments up to the R925-7 start comment. The last report from the second reviewer (R926-4) is POSITIVE at `f1b566a`, and nothing in it touches this delta.

| Finding | State at this head | Evidence |
|---|---|---|
| R925-5-F1 MINOR (hard limit 0: a no-core replay dumps to a pipe) | RESOLVED | §1 probe at (0,0), (0,∞), (1,∞), (∞,∞) and under `ulimit -c 0`; the plant DIFFERS |
| R925-5-F2 MINOR (check 8 crashes under `ulimit -c 0`) | RESOLVED | 73/73 under `ulimit -c 0`; check 8 alone at four hard limits |
| R925-6-F1 MINOR (the body counts a soft-limit plant the suite cannot catch) | RESOLVED, option (b) | The fallback is removed (`pass_run.py:256-257`). The body says "Thirteen", lists 13 plants and has no soft-limit plant. I re-verified the `prctl` plant (2 FAIL; 3 FAIL in `author-r8` under `ulimit -c 0`). This round did not re-run the other 12; their coverage is retained from prior rounds |
| R925-6-R1 RESIDUE (docstring item 6, "file core_pattern") | RESOLVED | `passes_test.py:32-33` "relative file core_pattern" |
| R925-6-R2 RESIDUE (run count at the head) | RESOLVED | Body lines 93-94 "two plus one under `ulimit -c 0`" = `author-r8` `pt-l1`, `pt-l2`, `pt-l0` |
| R925-6-S1 (label of the clamped check-8 arm) | TAKEN | `passes_test.py:416-417`. See S3 for the wording when the hard limit is at least 1 |
| R925-6-S2 (`prctl` return unchecked; `use_errno` never read) | RETAINED | `pass_run.py:257` is unchanged in that respect; carried as S4 below |
| R925-6-S3 (redundant soft-limit lowering) | TAKEN | Removed in `a2352e7` |
| R925-4-F1, R925-4-F2 MINOR | Still RESOLVED | Check 7 and check 8 pass ×2; the probe above |
| R925-5-S1, S2, S3, S4 (narrowed); R925-2-S3, S4; R925-3-S1, S2; R926-2-S1; R926-4-S1 | RETAINED | Untouched by this delta |
| R926-1..4 and R925-1..3 MAJOR/MINOR (budget, `-s`/`-i`/`-k`, replay errors, CPU acceptance, the `-i` guide sentence, generator signal) | Still RESOLVED | The delta touches none of them, and the checks covering them pass 73/73 ×2 |

## 4. Findings

No BLOCKER, MAJOR, MINOR or RESIDUE is open.

### Suggestions (do not affect the verdict)

- **R925-7-S1 - SUGGESTION - Tests, Docs (the `prctl` plant is caught only on a piped `core_pattern`).**
  - **Where:** `passes_test.py:393` (check 8's limits); check 7's `no_cores()` (0,0) (`:197-201`); PR body line 89, "a no-core replay left dumpable (caught under `ulimit -c 0`)".
  - **Evidence:** on a file `core_pattern` (e.g. `core`), the kernel writes no dump below the binary format's minimum dump size, which is one page. So soft limits 0 and 1, the only ones checks 7 and 8 use, never dump there, dumpable or not. With `prctl` removed, both checks would still pass on such a host. On this piped host the plant is caught at any hard limit (2 FAIL at hard ∞, `receipts/passes-test-plant-noprctl-hardinf.log`), not only under `ulimit -c 0`. The file-host case comes from kernel behaviour; changing `core_pattern` needs privilege, so it was not executed.
  - **Impact:** coverage only. The code is correct on both kinds of pattern (§2). On a file-pattern host, the suite does not guard the line that makes the replay match there.
  - **Optional outcome:** add a third check-8 arm at soft = hard, where the hard limit is unlimited or at least 4096. Such a dumpable death dumps under either kind of pattern, so the plant fails on any host, while the head still passes, because both forms are non-dumpable. Alternatively, qualify body line 89 as "(caught on a piped `core_pattern`, at any core limit)".
  - **Verification:** `scripts/plant_noprctl.sh` fails the new arm at hard ∞ and the head passes.
- **R925-7-S2 - SUGGESTION - Robustness (dead import).** `pass_run.py:45` `import resource` has been unused since `a2352e7` removed its last use, the soft-limit fallback (`receipts/delta-scan.txt`, AST scan). No repository gate checks Python imports. Fix: delete the line. Verification: `passes-test` 73/73.
- **R925-7-S3 - SUGGESTION - Tests (label wording when the hard limit is finite and at least 1).**
  - **Where:** `passes_test.py:416-417`. With a hard limit of 4 MiB, the arm prints "at core limit 1 (clamped to the hard limit)" (`receipts/check8-hard-limits.log`). The soft limit 1 is set as asked; only the hard limit stays at the caller's value instead of ∞.
  - **Optional fix:** print `f"{min(1, hard)} (hard limit {hard})"` in the finite case. This keeps "0 (hard limit 0)" readable under `ulimit -c 0`.
- **R925-7-S4 (R925-6-S2 retained) - SUGGESTION - Robustness.** At `pass_run.py:257` the `prctl` return value is unchecked, and `use_errno=True` is never read. If a sandbox's seccomp policy refused the call, the replay would quietly dump again. Fix: `if ...prctl(...) != 0: raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE)")`, or drop `use_errno`.
- **Retained, untouched by the delta:** R925-5-S1, S2, S3, S4; R925-2-S3, S4; R925-3-S1, S2; R926-2-S1; R926-4-S1 (§3).

## 5. Reviewer-owned ledger

| Lens | CLEAN/UNCLEAN | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | CLEAN | #111 criterion 1 (identical transcript and exit code): a no-core replay is identical to the non-dumpable serial line at (0,0), (0,∞), (1,∞), (∞,∞) and under `ulimit -c 0` (`probe-head-*.log`). Checks 7 and 8 match make's message and status. Criterion 2 (retired instructions) is unaffected: the delta adds one syscall, only on a replay that is about to die | R925-7 (delta); R926-4 / R925-4 (criterion 2) | a2352e723b481b011b32b0f6892a7920a079443b |
| RTL | CLEAN | No HDL in the delta. `make lint`, pinned 5.050: rc 0, 0 errors, 0 warnings (`make-lint.log`) | R925-7 (lint); prior verdict kept | a2352e723b481b011b32b0f6892a7920a079443b |
| Robustness | CLEAN | `reraise()` `:252-261` (`prctl` before the kill, `chdir` unchanged). `suid_dumpable` 2 host. Check 8's `caller` at four hard limits, no crash (`check8-hard-limits.log`). S2 and S4 are suggestions | R925-7 | a2352e723b481b011b32b0f6892a7920a079443b |
| Tests | CLEAN | `passes-test` 73/73 ×2, one under `ulimit -c 0`. `prctl` plant: 2 FAIL (hard ∞), 1 FAIL (probe, `ulimit -c 0`), 3 FAIL (`author-r8`, `ulimit -c 0`). Check 7 and check 8 references are non-dumpable. S1 and S3 are suggestions | R925-7 | a2352e723b481b011b32b0f6892a7920a079443b |
| Docs | CLEAN | `pass_run.py:253-255` and `passes_test.py:32-42,387-388` docstrings. PR body lines 16-18, 74-94, 112-113. `make docs` rc 0. No comment-rule instance in the delta (`delta-scan.txt`). `docs/TEST_DEVELOPER.md` is not in the delta and keeps its prior verdict | R925-7 | a2352e723b481b011b32b0f6892a7920a079443b |

## 6. Real limits

- **File `core_pattern`:** behaviour there is argued from the kernel's core-dump path, not executed. Changing `core_pattern` needs privilege; this host pipes cores to systemd-coredump.
- **`prctl` failure:** the path where `prctl` fails (seccomp, or a libc without `prctl`) was not exercised.
- **Platforms:** one host only (Linux 7.3, x86_64, GNU Make 4.4.1, Python 3.14). No other kernel, libc or `/bin/sh` was run this round.
- **Plants:** of the thirteen planted defects in the PR body, only the `prctl` plant was re-run this round. The others are retained from prior rounds' receipts.
- **Evidence integrity:** the evidence commit is unsigned, so packet integrity rests on `MANIFEST.json` hashes.
- **Hardware and calibration:** physical calibration was NOT RUN. No hardware was used. Field skips are not hardware proof.
- **Out of scope:** no manager source bank exists at this head, and none is claimed. I ran no full parent, PP, gPTP, Yosys or builder bank.

## 7. Pending manager duties

- Build and validate the current-dev merge candidate (source base `1213ac5…`, live dev `e275d79…`) with the builder and native banks, and link the receipts on the PR.
- Hosted and act acceptance at the merge candidate. No hosted runs are recorded at this head.
- Carry R925-7-S1..S4 and the retained suggestions to the author as optional work. There are no residue items for the residue checklist.

R925-7 FINISHED
