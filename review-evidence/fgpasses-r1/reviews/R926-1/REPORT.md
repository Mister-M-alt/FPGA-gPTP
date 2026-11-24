[R926] NEGATIVE - exact head bbda770befae8748c1139c4e843c5874c5330048

The new recipe preserves ordinary serial output and failing-pass status, but violates the caller's job budget and can return success after losing a pass's buffered transcript. One MAJOR and one MINOR remain open. All five lenses were applied independently; no source fixes or public writes were made.

Reviewed tree: `f4ea8ea4b503f8680d571c14394eb7235650ee77`. Base: `1213ac5b9e09b8759ba76cc70c53652b5e108996`. One commit changes only `tb/verilator/engine/Makefile` and `docs/TEST_DEVELOPER.md` (35 insertions, 11 deletions). RTL, harness, image generator and mutation drivers are unchanged.

**Authority and independence.** Read the supplied repository instructions; no tracked AGENTS.md or CONTRIBUTING.md exists in this checkout, and none was found in the inspected ancestor directories. Reconstructed the README/documentation map, [issue #111](https://github.com/Mister-M-alt/FPGA-gPTP/issues/111), public scope and PR description, integration/test/source-evidence guides, the exact diff and history, then the [published author packet](https://github.com/Mister-M-alt/FPGA-gPTP/tree/0e37e261d07b7fd332590bfe57ae90ddaad2dc57/review-evidence/fgpasses-r1/author), specifically REPORT section 5 and `receipts/gptp/`.

Issue #111 explicitly requires concurrency within the caller's job budget, serial-order output and preserved verdicts, clean and with a planted pass failure. Acceptance also calls for the reported wall reduction with CPU within a few percent. No issue comments modified that scope. Existing interface authorities in `docs/INTEGRATION.md`, `docs/SOURCE_EVIDENCE.md` and `tb/check_phc_contract.py` remain applicable; no protocol or electrical interface requirement changes. The review-start authority is [the public announcement](https://github.com/Mister-M-alt/FPGA-gPTP/pull/112#issuecomment-7140409057).

The independent verdict and ledger were written in `receipts/independent-verdict.md` before the final public FINDINGS check. The final timeline contained no prior public FINDINGS to resolve or retain: zero issue comments and two review-start announcements on the PR. No manager execution-evidence comments were present. No other reviewer's report or private author material was read.

**R926-1-01 — MAJOR — Conformance, Robustness, Tests.**

- Artifact: `tb/verilator/engine/Makefile:68` through the four launches at line 71.
- Authority/evidence: issue #111's caller-budget scope. `receipts/probe-results.json`, `parallel-clean-j1.events.json` and `parallel-clean-j2.events.json` show four overlapping pass lifetimes at both `-j1` and `-j2`; the serial controls peak at one. Compilation was bypassed to isolate the new launch logic. Unchanged pre-existing build flags are not the basis of this finding.
- Impact: one scheduled recipe starts four CPU workloads without reserving additional caller slots. A caller choosing one or two jobs is oversubscribed; enclosing work can also consume remaining slots while these four run.
- Required outcome: schedule passes within the caller's global available budget, including recursive invocation and competing targets, retaining serial-order printing and failure priority. Merely capping children at a parsed `-j` value is insufficient when sibling work already occupies slots.
- Verification: add persistent low-cost controls at `-j1`, `-j2` and a larger budget, plus recursive and competing-target cases. Assert aggregate active work never exceeds the caller's budget. Rerun clean/failing comparisons and the performance pair with sufficient slots.

**R926-1-02 — MINOR — Conformance, Robustness, Tests.**

- Artifact: `tb/verilator/engine/Makefile:73`, and analogous transcript reads at lines 75, 77 and 79.
- Authority/evidence: issue #111 requires pass transcripts and verdicts to survive. `receipts/parallel-read-fault.log` and `.rc` show a deliberately failed read of `obj_dir/pass1.out` returning 74; the recipe prints later passes and returns zero. Pass 1's entire output is absent. `probe.py` places a read-failure stand-in on PATH without changing the recipe or simulator statuses.
- Impact: a buffered-transcript read/output error can produce a successful suite with missing checks and verdicts. Each read's status is discarded by the following test/echo/exit; final success depends only on simulation status.
- Required outcome: fail when a required transcript cannot be emitted, retain a clear diagnostic, and preserve the earliest failing simulation's diagnostic/status on the ordinary path.
- Verification: inject failure while emitting each transcript. An otherwise-clean suite must be nonzero. Normal and planted-pass-failure transcripts must still match the serial reference after documented host-only normalization.

**R926-1-03 — RESIDUE — Docs.**

- Artifact: [PR #112 body](https://github.com/Mister-M-alt/FPGA-gPTP/pull/112), opening status paragraph and final “Not done here” bullet.
- Authority/evidence: the published PR and its `Closes #111` line contradict stale statements that no issue exists, the branch was not pushed and no PR was opened.
- Impact: obsolete handoff wording only; no measurement, test, verdict, clause claim or executable behavior changes.
- Exact required fix: replace the opening unpublished-status sentences with “Branch `engine-run-passes-at-once` is published at `bbda770befae8748c1139c4e843c5874c5330048` in this PR, closing #111.” Delete the final bullet stating that nothing was pushed and no PR was opened.
- Verification: reread the PR body against its published head and linked issue. Manager carries this on the residue checklist.

**R926-1-04 — RESIDUE — Docs.**

- Artifact: the new source-comment paragraph at `tb/verilator/engine/Makefile:50`.
- Authority/evidence: the supplied source-comment rule requires behavior and reason to be tied to issue/requirement IDs. This paragraph explains behavior and reason but omits its owning #111 reference. No forbidden review identifiers or lane labels were introduced in source comments.
- Impact: comment traceability only; no executable or claim change.
- Exact required fix: change the first line to `# #111: The four passes are independent: each reads its own image from its own`, leaving the remaining explanation unchanged.
- Verification: inspect the comment-only diff and confirm recipe bytes are unchanged. Manager carries this on the residue checklist.

**Evidence and coverage.** The published clean serial/parallel logs were independently compared in strict order, retaining all image-generation, simulator, heading, check, figure and verdict lines. Only the eleven build-command/statistics lines between image generation and simulator invocation were removed from each log. All 170 retained lines match byte for byte, SHA-256 `ae968df76bb48c7726c94f7a39947953d124151bf37dcce9fa0266fcfe9bb460`. Tallies are 2199/2199/2199/61 checks, all passing; both recorded exits are zero. This comparison does not accept multiset or reordered equality. The author helper has broader fallback modes; none was used here. See `check_evidence.py`, `receipts/public-evidence-audit.json` and both normalized logs. Thirteen downloaded public files were checked against published blob IDs; hashes are in `receipts/public-source-hashes.json`.

Public timing receipts record serial wall 2721.59 s, CPU 817.72 s; parallel wall 974.61 s, CPU 836.79 s: 2.79249× speedup and CPU +2.33209%. This is one published pair on a contended host, with one core for serial and four for parallel, not an independently repeated performance distribution or hardware result. The serial reference uses the base recipe with unchanged simulation sources. The published failing receipt uses a stand-in executable rather than a planted RTL defect.

Reviewer execution used exact base/head recipes in disposable directories, the same stand-in executable, and the real unchanged ROM generator. Eighteen executions cover clean runs at three job budgets, each of four failing passes, simultaneous failures in passes 1 and 2, and transcript-read failure. Both variants return zero when clean and make status 2 for a failing pass, retaining pass status 3 in the diagnostic. Multiple failures select pass 1's status 3 ahead of pass 2's status 7. Ordinary clean/failing output matches after replacing only the generator checkout path and changed recipe-line location. Later output is suppressed after the first failure, although later passes have already executed. Event receipts prove out-of-order completion and ordered publication. These are orchestration controls, not additional RTL simulation coverage.

The four passes read separately generated images in the engine root, `seedrun`, `syncseedrun` and `p1run`; generation finishes before launch. Output files `pass0.out` through `pass3.out` are distinct. `sim_main.cpp` keeps harness state within each process and contains no shared file-writing path. ROM reads at `hdl/ucpu/KL_gptp_ucpu.sv:107` and `hdl/top/KL_gptp_engine.sv:203` resolve relative to each process's directory. Event image hashes and arguments distinguish all four configurations, including the priority1-255 argument. No between-pass shared scratch/output race was found for one invocation. Simultaneous independent invocations in the same checkout were not tested or claimed safe. The public termination receipt records Error 143; cleanup was assessed from the trap/exec structure and public evidence, not independently repeated with live simulations.

Focused reviewer gates passed: documentation/diagram checks and selftests, source anchors and selftest, PHC contract, engine/bench lint, and the existing mutation-order selftest (10 checks; 168 ordered stand-in mutation verdicts). That last test covers the separate mutation driver, not the new four-pass scheduler. No persistent scheduler regression was added in this PR. Version identity 5.050 was verified before lint. Independent focused commands were joined concurrently with `-j16`; probe pairs had at most five simultaneous pass children and all were joined before proceeding. Memory use remained far below 12 GB. No full bank, hardware execution, shared installation or background orphan was used.

| lens | CLEAN/UNCLEAN | examined artifacts | covering round | exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN | Frozen #111 scope; Makefile:58–79; strict clean/failure comparisons; public timing; findings 01/02 | R926-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| RTL | CLEAN | Unchanged RTL/harness/generator; relative ROM reads; PHC contract/lint; per-process state and image arguments | R926-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| Robustness | UNCLEAN | Launches/waits; status precedence; isolated files; job-budget and transcript-read probes; findings 01/02 | R926-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| Tests | UNCLEAN | 18 recipe executions; published real clean pair; mutation-order control; missing budget/read-error regressions; findings 01/02 | R926-1 | bbda770befae8748c1139c4e843c5874c5330048 |
| Docs | CLEAN | README/map; integration/test/source guides; new comments; PR body; documentation receipts; residue 03/04 only | R926-1 | bbda770befae8748c1139c4e843c5874c5330048 |

**Limits and pending manager duties.** No independent full real engine A/B campaign, full banks, hosted replay or physical tests were run. Exact-head read-only queries returned no PR-triggered workflow runs, commit statuses or check runs. Absence is neither executed acceptance nor a skipped passing context. Source-head execution evidence is the author's public receipts; no manager source bank exists or is inferred. The manager owns hosted/replay acceptance and, after fixes and independent positive reviews, must build and validate the final current-dev merge candidate with builder/native banks and publish receipts on the PR. Source base is `1213ac5b9e09b8759ba76cc70c53652b5e108996`; supplied live dev is `e275d7950ef3385753e6a15d2e191ba855b171ed`. Source validation cannot stand in for that candidate. Physical calibration is NOT RUN; field skips are not hardware proof.

The checkout was never edited. `verify_checkout.py` verified all 120 tracked files against exact blob bytes and executable modes, the original index and expected tree, and clean status. The repository has zero gitlinks; no required submodule link is omitted. See `receipts/checkout-integrity.json`. Disposable copies and fetched inputs remain under `scratch/`, excluded from publication. `MANIFEST.sha256` lists publishable scripts and receipts using packet-relative paths. Scripts accept explicit checkout/packet locations; `check_evidence.py` accepts the public author's directory as input. Report text uses neutral role labels.

R926-1 FINISHED
