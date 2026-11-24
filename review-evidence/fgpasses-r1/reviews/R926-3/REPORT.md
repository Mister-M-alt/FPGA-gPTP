[R926] POSITIVE - exact head 0ba80c4f1a7e506a9bc727f162582bfc6212f771

Both named findings are resolved: R926-2-F1 by an explicit public maintainer acceptance amendment and verified measurements satisfying it; R926-2-F2 by the requested documentation correction, supported by the failure receipts and a passing documentation gate. All five lenses are CLEAN within this narrow re-review. One nonblocking PR wording residue and the existing optional suggestion remain.

Reviewed tree: `2d30c9a8563b133c5c14bbb9cb761b5ae6382952`. Source base: `1213ac5b9e09b8759ba76cc70c53652b5e108996`. Previous reviewed head: `661e4c3a45904d2d8f3e061c67103a945651d9ff`. The sole subsequent commit changes `docs/TEST_DEVELOPER.md`: one replacement sentence and one added sentence. Executable files, RTL, interfaces, generator, harness, flags and test definitions are byte-identical to the previous reviewed head.

**Authority and independence.** The supplied instructions and referenced command instructions were read first. No repository AGENTS.md or CONTRIBUTING.md, or ancestor AGENTS.md in the inspected checkout ancestry, was present. Reconstruction used the repository README, `docs/README.md`, the current test guide, `docs/INTEGRATION.md` and `docs/SOURCE_EVIDENCE.md`; then the public issue body, amendment and review-start decision; then cumulative base-to-head changes and the three-commit history, with emphasis on the one-commit delta. Existing interface authorities have no changed dependency in this delta. The independent diff pass preceded reading the prior external findings. Only this reviewer's previous report and receipts were consulted for prior dispositions; no other reviewer's report or private author material was read.

[Issue #111](https://github.com/Mister-M-alt/FPGA-gPTP/issues/111) retains caller-budget concurrency, serial-order output, preserved pass verdicts and exits, clean/planted transcript equivalence and wall reduction. Its [public amendment](https://github.com/Mister-M-alt/FPGA-gPTP/issues/111#issuecomment-7145509264) explicitly replaces the CPU-time gate with retired user instructions within +1% at matching `-j1` and `-j4` flags. The amendment is by the repository OWNER, also the issue author, and expressly says it changes acceptance in response to F1. The issue body was updated accordingly. This is the public maintainer decision permitted by F1's required outcome. It is not merely an explanation in the PR. The [review-start record](https://github.com/Mister-M-alt/FPGA-gPTP/pull/112#issuecomment-7145548085) pins the reviewed head and tree. The available issue/PR timeline contains no manager source-bank execution receipt; none is inferred.

**R926-2-F1 — MAJOR — Conformance, Tests — RESOLVED.**

- Artifact: amended issue #111 criterion 2; PR #112 “Measured”; `author-r2/receipts/gptp/summary.txt`, all nine arms' `head`, `perf` and `time` files in the [pinned public packet](https://github.com/Mister-M-alt/FPGA-gPTP/tree/4fb9a5ee3369635112520f1f9db91393003b39b8/review-evidence/fgpasses-r1).
- Authority/evidence: the public amendment defines the replacement metric and tolerance. The wrapper records counters around the complete four-pass `make run` command, with matching caller flags. Every arm identifies the expected base or previous executable head; the current delta changes no executable byte. Independent arithmetic from raw counters is below. CPU seconds and cycles exist for every arm, including the unfavorable pair and planted abort.
- Impact addressed: the earlier CPU-bound acceptance gap is closed by the explicitly permitted acceptance change. These observations do not prove the old CPU-seconds bound or establish a particular causal explanation for shared-host variation.
- Required outcome: satisfied by the public maintainer decision, matching-flag measurements within +1%, and a PR Measured section that links the amendment, states the metric and threshold, and retains favorable and unfavorable CPU figures as nongating evidence.
- Verification: `receipts/packet-integrity.json`, `measurement-audit.json`, `verification.log` and preserved raw measurement receipts. No new performance campaign or bank run was needed. Historical timings remain executions at `661e4c3`; they are not relabeled as fresh executions at `0ba80c4f`.

| Matching pair | Retired user instructions, base → head | Change | CPU seconds, base → head | Wall speedup |
|---|---:|---:|---:|---:|
| First `-j4` | 7,518,255,745,307 → 7,540,329,160,123 | +0.293598% | 451.63 → 588.38 | 2.0489× |
| Second `-j4` | 7,518,254,937,328 → 7,540,328,960,677 | +0.293606% | 650.60 → 542.93 | 2.9493× |
| Second `-j4`, alternate cores | 7,518,254,937,328 → 7,540,329,035,912 | +0.293607% | 650.60 → 493.12 | 3.6008× |
| `-j1` | 7,518,256,289,086 → 7,521,158,053,895 | +0.038596% | 458.77 → 475.07 | 0.9658× |
| Planted abort, `-j4` | 2,469,385,704,454 → 2,482,567,508,212 | +0.533809% | 227.42 → 155.32 | 1.4749× |

Clean arms return zero; both abort arms return 2. CPU changes for the three clean `-j4` comparisons are +30.2792%, −16.5493%, −24.2053%; `-j1` is +3.5530%. Serial-budget execution does not claim wall acceleration. The Measured section faithfully makes instructions the gate, publishes the adverse CPU observation and identifies the earlier pre-correction timings as historical.

**R926-2-F2 — MINOR — Conformance, Docs — RESOLVED.**

- Artifact: `docs/TEST_DEVELOPER.md:75`, `:77`, `:79`; `tb/verilator/engine/Makefile:64`; `pass_run.py:121`, `:159`, `:213`; previous `reviews/R926-2/receipts/ignore-errors.{stdout,stderr,rc}` and the published 63-check gate receipt.
- Authority/evidence: the revised sentences exactly distinguish ordinary failure from `-i`: without it, the first failing pass sets status and stops later passes; with it, failures are ignored and later passes continue. The previous independent receipt shows a pass-1 failure, its `(ignored)` diagnostic, both subsequent passes and zero status. Its published hashes were verified.
- Impact addressed: the guide now describes the actual verdict and cancellation contract for the explicitly named flag. This was a behavioral documentation defect, not merely stylistic wording.
- Required outcome: the previously requested three sentences are present and the docs gate is green.
- Verification: fresh focused probes against both the serial reference and unchanged current scheduler give equal stdout, stderr and status. With `-j4 -i`, pass 1 fails, passes 2/3 print and status is zero; ordinary `-j4` returns 2 and omits later pass output. Raw and normalized streams are retained under `receipts/ignore-errors.*` and `ordinary-failure.*`. Fresh `make -j16 docs` returns zero: nine pinned diagram assets, ten diagram selftest arms, fourteen current/eighteen historical pages, 127 documentation selftest arms, twenty exact source anchors and seven source-evidence selftest arms.

**R926-3-R1 — RESIDUE — Docs — OPEN, nonblocking.**

- Artifact: PR #112 opening branch paragraph and commit list, before “What changes”.
- Authority/evidence: it still says “two commits” and names `661e4c3a45904d2d8f3e061c67103a945651d9ff` as head; public PR metadata and local history show three commits and the reviewed `0ba80c4f` head. See `receipts/public-record.json` and `history.txt`.
- Impact: stale introductory wording. The current source identity is unambiguous in PR metadata and the review-start record, and the historical measurement attribution remains correct. No measurement, acceptance claim, test, code or verdict changes.
- Exact required fix: replace that paragraph with “Branch `engine-run-passes-at-once`: three commits on main `1213ac5` (#108), head `0ba80c4f1a7e506a9bc727f162582bfc6212f771`.” Add “`0ba80c4f` documents the `-i` exception to first-failure handling.” to its commit list. Keep historical measured-run identities intact.
- Verification: compare the corrected opening against the three-commit history and current PR head. Manager carries this wording item to the residue checklist.

**R926-2-S1 — SUGGESTION — Robustness, Tests — RETAINED, optional.** Artifact: `tb/verilator/engine/Makefile:70` and the PR's disclosed output-timing limitation. All four prerequisite passes complete before first replay; users cannot see an early completed pass while later work continues. Progressive serial-order publication remains an optional follow-up, requiring first-output timing, ordering, job-budget and failure checks if implemented. It is outside this delta and amended acceptance and leaves both lenses clean.

Earlier closed findings retain their previous dispositions because their causes and dependencies are unchanged: pass job-budget accounting; silent/ignored/keep-going transcript fidelity; signal/core diagnostics; replay-read failure handling; signal forwarding; fail-fast coverage; and issue references in source comments. Earlier PR identity wording closure now has the narrow residue above. No source comment is added in this delta, so there is no new lane label, review identifier, review-round or issue-comment-ID residue. This re-review does not reopen unchanged executable scope.

**Evidence integrity and spot-checks.** All 53 selected archive blobs match the pinned Git tree, including the manifest itself; all 52 selected files covered by that manifest match its published SHA-256 values. The archive API reports `verified=false`, reason `unsigned`, and no signature payload. No detached signature is supplied in the inspected packet inventory. Accordingly, published-byte integrity is verified; a cryptographically verified signing identity is not claimed. This limitation also existed in the prior review and is not a new acceptance defect.

The complete first `-j4` log pair independently compares equal in order across 181 retained lines, normalizing only checkout include paths and removing one compiler timing-statistics line. The jobserver warning and build commands remain. Other full transcript claims retain their earlier coverage; tails and author assertions are not promoted into new full-log verification. The unchanged published pass gate contains 63 passing checks. The full gate and previous fault campaigns were not rerun for this two-sentence change; only the two relevant ordinary/ignored failure cases were freshly exercised. The current author packet's documentation receipt is a tail, so the full independent docs run provides the stronger current check.

**Reviewer-owned ledger.** All rows below concern the exact current head; carry-forward identifies the earlier coverage rather than claiming new full executions.

| lens | CLEAN/UNCLEAN | examined artifacts | covering round | exact head |
|---|---|---|---|---|
| Conformance | CLEAN | Amended issue body and OWNER decision; PR Measured; all matching-flag raw counters/timings; docs delta; ordinary/ignored failures | R926-3 resolves F1/F2; unchanged acceptance coverage carried from R926-2 | `0ba80c4f1a7e506a9bc727f162582bfc6212f771` |
| RTL | CLEAN | Cumulative diff and current delta; unchanged `hdl/`, generator, harness, pass image paths and arguments; interface/source guides | R926-2 CLEAN carried; R926-3 byte/dependency check | `0ba80c4f1a7e506a9bc727f162582bfc6212f771` |
| Robustness | CLEAN | Unchanged failure marks, ignore-error guards, signal/core replay and pass targets; fresh ordinary/ignored failure receipts | R926-2 CLEAN carried; R926-3 targeted check | `0ba80c4f1a7e506a9bc727f162582bfc6212f771` |
| Tests | CLEAN | 63-check published gate; archive hashes; whole-command measurement wrapper; raw arithmetic; complete-log spot-check; fresh two-case probes | R926-3 resolves F1; other executable coverage carried from R926-2 | `0ba80c4f1a7e506a9bc727f162582bfc6212f771` |
| Docs | CLEAN | README/map/interface/source authorities; test guide:75/77/79; PR Measured and opening; fresh docs/diagram/source gates | R926-3 resolves F2; R1 is wording-only residue | `0ba80c4f1a7e506a9bc727f162582bfc6212f771` |

**Limits and pending manager duties.** This review ran no full parent, processor, synthesis or builder banks, no real simulation timing campaign, hosted replay, hardware work or shared installation. No simulation compiler was invoked. No hosted job execution or skipped context is asserted from this review. Hosted/replay acceptance remains manager-owned. Prior cancellation limitations, the unchanged compile command's unbounded job setting, and simultaneous independent invocations in one checkout remain outside this narrow closure.

There is no manager source bank at this exact head. Author source validation is distinct from the final current-dev candidate. At the merge turn, the manager must build and validate that candidate with builder and native banks and link the receipts on the PR. Source base is `1213ac5b9e09b8759ba76cc70c53652b5e108996`; supplied live dev is `e275d7950ef3385753e6a15d2e191ba855b171ed`. Two independent positive reviews and the remaining completion bar still apply. Physical calibration is **NOT RUN**; field skips are not hardware proof.

The checkout was never edited. Verification confirms detached exact head/tree, all 122 tracked entries' actual bytes and modes, an index identical to the tree, clean status and zero gitlinks; no required submodule link is missing. All processes completed in foreground-driven commands, within the job and memory constraints. Disposable trees and downloaded inputs live only under packet `scratch/`, which is excluded from publication. `fetch_public.py`, `verify_review.py` and `reproduce.sh` accept explicit paths and reproduce the scoped checks. `MANIFEST.sha256` lists every publishable receipt and script with packet-relative paths. No source fixes, commits, pushes, external writes, author contact or sub-agents were used.

R926-3 FINISHED
