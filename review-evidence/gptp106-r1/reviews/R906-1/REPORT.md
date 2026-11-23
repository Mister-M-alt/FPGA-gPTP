[R906] NEGATIVE - exact head a728cc3ce9d0342aa596c8170fecf1284c0b604c

External independent review, R906-1, issue #106 / PR #108, including #107. Tree `d99b9b065b9acebdae5d39519023b785e249222c`; source base `1616fc8f062fbf58c35ad31674b5b233207bbdb8`; six commits, sixteen changed files. All five lenses were applied independently. One open MAJOR and one open MINOR finding prevent approval. No independent functional defect was identified in the immediate Announce or oscillator-restoration changes within the frozen scope.

**R906-1-F1 | MAJOR | Conformance, RTL, Tests, Docs | OPEN**

Artifact: [routes.txt](https://github.com/Mister-M-alt/FPGA-gPTP/blob/42e140e6768105b5b53231367046800f630b834e/review-evidence/gptp106-r1/author/receipts/routes.txt), 8x8 totals and hierarchical rows; [public handoff](https://github.com/Mister-M-alt/FPGA-gPTP/blob/42e140e6768105b5b53231367046800f630b834e/review-evidence/gptp106-r1/author/HANDOFF-r2.md), opening all-gates-pass statement. A local copy of the measurements is `receipts/published/routes.txt`.

Authority/evidence: the frozen owner rule requires neither the 1x1 nor 8x8 image to grow. [Parent #818](https://github.com/kebag-logic/milan-fpga/issues/818) changes timing acceptance to the build floor at every corner; it leaves resource tolerances unchanged. Both compared images use ExtraTimingOpt placement, AreaOptimized_high synthesis, ExploreArea optimization, single-thread synthesis, the same device and implementation release. Published parent base `854bd7236792ce1adbd10c43b13a6a5002ad3bb6` carries donor `1616fc8f`; parent head `2cf4b61406cfdd5b51f59823de47820f586480f4` carries the reviewed donor head.

| Same-directive 8x8 measurement | Base LUT | Head LUT | Change |
|---|---:|---:|---:|
| Entire image | 42,998 | 43,586 | +588 (+1.37%) |
| KL_mbx_cdc | 5,558 | 7,150 | +1,592 |
| u_edit, inside that mailbox | 3,746 | 5,318 | +1,572 |
| csr | 4,107 | 2,765 | -1,342 |
| g_gptp_plane.u_gptp_shadow | 5,863 | 6,103 | +240 |
| u_engine, inside that plane | 3,820 | 3,740 | -80 |
| Plane-local logic, excluding child cells | 1,778 | 2,113 | +335 |

Rows include hierarchy and must not be summed indiscriminately. The mailbox/CSR movements alone do not explain the complete +588 net increase. The 1x1 engine also shrinks 80 LUT, and standalone engine synthesis shrinks 20 LUT. These observations support global synthesis/mapping variation rather than 588 LUT of new gPTP logic. They do not demonstrate a no-growth final image or establish a quantified repeatability allowance. Unchanged RTL can map differently when the surrounding netlist changes; one base/head pair cannot separate repeatability variance from an indirect, reproducible increase.

Judgment: likely synthesis/mapping variation in resource distribution, but a real measured +588-LUT image increase under the stated rule. Timing success and lower slice/FF counts do not cancel it. This is not evidence of feature-local RTL bloat, and it is not grounds to waive the image-level requirement.

Impact: an acceptance gate remains unmet. Tests lacks a controlled comparison establishing qualifying area; Docs carries an all-gates-pass claim beyond the evidence. Because this changes a gate verdict, it is not wording-only RESIDUE.

Required outcome: publish a controlled base/head comparison with generated-input identity, identical recipe/directive, total and hierarchical utilization, establishing a qualifying no-growth image. Report the gate as unmet until then. Any allowance for measured variation requires an explicit public owner amendment and subsequent review; this review supplies no waiver. No unrelated mailbox/CSR rewrite is prescribed.

Verification: compare both shapes against the accepted baseline, account for total LUT changes without double-counting nested cells, preserve #818 at every corner, and make the public gate verdict agree with the measurements.

**R906-1-F2 | MINOR | Tests, Docs | OPEN**

Artifact: `tb/verilator/engine/sim_main.cpp:8307`, with `:8322`, `:8142` and `:8186`.

Authority/evidence: the newly added phase-61 description says each master is followed for 30 seconds. Each case actually calls `p107_follow(c.tag, 120)`. Each pair advances a nominal 125-ms service interval (`run_svc(250000)` at 2 MHz), followed by frame handling and short waits. That is 15 seconds of nominal intervals plus service overhead, not 30 seconds. The last 80 pairs supply the graded averaging window. The frozen acceptance requires the stated rate/TLV checks; it does not require a new 30-second dwell.

Impact: a reviewer is told twice the nominal observation duration implemented by the test. This is a numerical test-evidence claim, so the owner's wording-only RESIDUE exception does not apply. The passing rate/TLV results themselves are not invalidated.

Required outcome/exact fix: replace `each for 30 s` with `each for 120 Sync pairs, grading the last 80 pairs`. No behavioral test extension is needed to meet the frozen acceptance.

Verification: compare the corrected comment with the call argument, pair interval and averaging-window condition, then run the applicable documentation checks. `receipts/duration-check.txt` retains the source evidence. This finding was independently noticed during the final documentation audit after the initial verdict had been recorded; no prior review finding supplied it.

**Authorities and independent reconstruction**

The checkout contains no tracked AGENTS.md/CONTRIBUTING.md and no nested submodules. The supplied workspace instructions, docs/README and README were examined, followed by issue acceptance, public scope rulings, integration/interface guides, the complete diff and six-commit history, then the public author evidence. Parent public AGENTS.md, CONTRIBUTING.md and REQUIREMENTS.md at live dev `e275d7950ef3385753e6a15d2e191ba855b171ed`, and the interface document pinned by the donor at `ac2c5e77`, supplied surrounding rules. REQ-PTP-01/05/07/08/09 and REQ-VER-01/04 are relevant. No private author material or other checkout was used.

[Issue #106](https://github.com/Mister-M-alt/FPGA-gPTP/issues/106) requires transmitted master Announces after receipt timeout, including the tie, and one-second cadence from regaining mastership. Its authorities are IEEE 802.1AS-2011 Figures 10-13/10-15 and Milan v1.2 4.2.6.2.3/Table 4.2; the project explicitly chooses expiry at the instant.

[The #107 ruling](https://github.com/Mister-M-alt/FPGA-gPTP/issues/107#issuecomment-7101407241) sets D1=C, D2=no servo change, D3=unchanged grading, A1=qualification setup. Clause authorities: IEEE 802.1AS-2020 10.1.2.1, 10.2.4.14, 10.2.8.2.1 j)-l), 11.4.4.3.9 and B.1.1. This review checks the frozen interpretation and project interfaces; it is not a fresh certification of the complete standards.

**Conformance and RTL**

`hdl/ucode/gen_gptp_ucode.py:1994`, `:2036`, `:2486`: BECOME removes the deferred first-Announce arm. SELF commits its publication and branches to ANNTX, retaining role/asCapable/credit checks and the one-second timer arm. Dispatch waits for the serializer, preventing a queued better Announce from erasing that first transmission. Existing receipt-watch arbitration is unchanged. Tests explicitly allow millisecond quantization with the 2,999-ms earliest bound; this is not a claim of physical sub-millisecond deadline precision.

`hdl/top/KL_gptp_engine.sv:958`, `:1283`: word 3 always writes the zero low word and clears slew qualification on the same transaction. BECOME shifts the signed integrator into the upper word. The TLV path uses that word only after a slave word-0 rate, clearing history at mastership and reset. Signed width/product/arithmetic-shift handling preserves either sign; generator range assertions bound the operand. The product finishes before the later Follow_Up reads it. The single BECOME write still counts gmTimeBaseIndicator. No clock/CDC boundary changes.

All four tracked ROMs regenerate byte-for-byte at 1,013 real words, identity words included. `mutants.py` is exactly 1,000 lines. A syntax-tree comparison excluding docstrings confirms that only BECOME and SELF change semantically in the generator; the servo functions are unchanged under D2. Published OOC: engine LUT 5,395 -> 5,375; FF 3,620 -> 3,617; unchanged 1.5 BRAM/6 DSP; WNS +2.043 -> +2.093 ns. MicroCPU unchanged. These are author post-synthesis receipts, not reviewer-run routes.

Published routes satisfy #818 at both slow and both fast corners, with zero failing endpoints and routing errors. Worst setup/hold: 1x1 base +0.158/+0.033 ns, head +0.276/+0.036; 8x8 base +0.064/+0.027, head +0.244/+0.036. The 1x1 image improves by 322 LUT/4 FF/3 slices. The 8x8 image has 107 fewer FF and 459 fewer slices, equal BRAM/DSP, but F1 remains.

**Robustness and Tests**

`tb/verilator/engine/sim_main.cpp:7977`, `:8043`: phases 57/58 identify actual completed transmitted frames by source and GM identity and use accepted first-octet cycles. They cover ten gaps/phases, immediate regain, four subsequent one-second intervals and a better-Announce race. `p106_mutants.py` restores deferred transmission or suppresses cadence. `mutants.py:878` requires every named failure; build failure or unrelated failure cannot count as a catch.

`sim_main.cpp:7620`, `:8232`, `:8263`, `:8311`: unfollowed replacement master, +/-10 and +/-100 ppm follow, +60-ppm/90-us transient takeover, subsequent +10-ppm follow, and three Follow_Ups under +/-8-ns origin noise. The seven `p107_mutants.py` controls cover retained rate, conditional word 3, wrong TLV sign/source/scale, stale history, and insufficient clamp. Phase-52 controls track the new layout. Published exact-head evidence: 167/167 controls caught and a passing positive control; 2,199/2,199 on three engine image variants and 61/61 on the non-GM-capable variant. These are author executions, not a manager source bank or locally repeated full bank.

Parent takeover evidence: 252/252 at this pin; the same harness at the old pin fails exactly two oscillator-policy checks. Both +/-100-ppm takeovers retain MEDIA_UNLOCKED, have no lost/refused/slipped samples in the takeover window, no PHC step, and one uncertainty episode. Holds are 165,528 and 254,168 cycles versus a compressed quarter tick of 131,072. This is a simulation model, not measured physical 0.25-second holdover. The CRF servo is not modeled; media evidence is the Stream Input counter and presentation model.

Both earlier failed runs are disclosed. The public patch clears an inherited origin override and reanchors the timeline after a settime trial; then it retries unanswered GET_COUNTERS while retaining final validity/counter checks and printing retries. The unanswered reads also occur at base. Pre-takeover follow slips (head 2, base 13) are outside the graded takeover window, not proof of a slip-free whole campaign. Parent gptp/gptp-lat: 212/212 each; gptp_shadow: 327/327 for each sign; gm_steps: 196/196 and five controls caught. See `receipts/published/parent-*.txt` and public `tools-r2/parent-scratch-gate.patch`.

Reviewer executions completed successfully (`receipts/local-results.json` and raw logs/rc files): the exact-head engine passes 2,199/2,199; the same head harness on base RTL/ROM produces 2,174 PASS and 25 expected FAIL. All eight timeout-gap cases through 3.002 seconds fail at base and pass at head, as do the regain-at-once/race checks. Base still follows +/-10 and +/-100 ppm; its other failures concern the deliberately changed mastership-rate/TLV contract. Both explicit #106 mutations are caught by every check they name. This establishes the wire fix's load-bearing checks locally, independently of the author's arm receipt.

The local documentation/diagram/source-anchor and PHC contract checks also pass. The scoped 5.050 executable identity was verified before use and retained in `receipts/compiler-identity.txt`. Independent runs used concurrent foreground orchestration, bounded compiler jobs and disposable trees only. The seven #107 mutation results and seeded/non-GM image passes are reviewed published author evidence, not locally repeated campaigns. No full parent, processor-bank, portability, builder or implementation campaign was run. `receipts/execution-summary.txt` extracts tallies and failures without replacing the raw logs.

**Docs and explicit limitations**

`docs/INTEGRATION.md:414` states the remaining phase authority as `200 - |rate|` ppm. The public near-clamp experiment supports roughly 5-17 seconds at 197 ppm and 50 seconds from +199 to -199; it is documented behavior, not a newly graded gate. Mastership/slew/TLV text and HDL_DEVELOPER match the new interface; SOURCE_EVIDENCE anchors pass. Added source comments contain no prohibited bench/review labels or issue-comment IDs. Existing out-of-scope residue is not a new finding.

The transient TLV limitation is explicit: phase 60 reports -439,804,752 (about -200 ppm) after a +60-ppm GM, whose ideal change is about -131,941,270. The phase jump wound the integrator. This case is printed, not graded as accurate frequency estimation. D2 explicitly leaves anti-windup outside this round; D3 is exercised by the settled noisy cases. This review does not turn that disclosure into full transient conformance. A1 remains a qualification-harness duty.

**Prior findings and public state**

`receipts/independent-verdict.md` records the independent verdict and ledger before PR discussion/prior-findings inspection. Subsequent public queries returned two review-start comments, zero submitted reviews, zero review threads and no prior FINDINGS to resolve or retain. The pre-PR D1/D2/D3/A1 ruling is applied as described above. `receipts/public-state.json` retains the snapshot. The PR-filtered exact-head workflow query returned no runs; no executed or skipped hosted context is claimed. Hosted/act acceptance remains with the manager.

**Reviewer-owned ledger**

| Lens | CLEAN/UNCLEAN | Examined artifacts and result | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | UNCLEAN | #106 acceptance; #107 ruling; BECOME/SELF/ANNTX; REQ-PTP interfaces; image no-growth unmet (F1) | R906-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| RTL | UNCLEAN | Engine word-3/TLV/reset and dispatch; generated ROMs; OOC/routes; image increase (F1) | R906-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| Robustness | CLEAN | Phases 52/57-61; credit/port-disabled/warm-reset paths; stale history; takeover patch and reruns | R906-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| Tests | UNCLEAN | Wire/PHC checks; p100/p106/p107 named controls; author parent/engine receipts; insufficient no-growth evidence (F1), overstated observation duration (F2) | R906-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |
| Docs | UNCLEAN | Integration/development/source-evidence guides; near-clamp/transient disclosure; gate-pass claim exceeds evidence (F1), phase-61 duration (F2) | R906-1 | a728cc3ce9d0342aa596c8170fecf1284c0b604c |

**Manager duties, real limits and integrity**

No manager source bank exists at this head and none is inferred. Source validation is the author's published receipts plus the identified reviewer probes. The final current-dev integration candidate is separate, on live dev `e275d7950ef3385753e6a15d2e191ba855b171ed`; the manager owns builder/native banks and publishing their receipts.

PR metadata says mergeable=false. Main `7cfd6a025698de9e3536006eefb46f0fb114692a` includes #102/#104 concurrency/caching/path-control changes overlapping `tb/verilator/engine/mutants.py`; `receipts/main-mutants.diff` records them. The merge turn must preserve those changes plus the new imports and all-named-check enforcement, then run applicable order and ratchet checks on the resolved candidate. No merge was attempted here.

Physical calibration: NOT RUN. Field skips and digital simulation are not hardware proof. No hardware, workflow replication, shared installation, source fix, commit, push, GitHub write or other-checkout edit was performed. All disposable trees are under unpublished `scratch/`. The audit checks all 117 tracked blob bytes and modes, the index, clean status, exact head/tree and zero nested gitlinks. Parent gitlinks are claims from public receipts, not inspected private integration trees. All 38 public packet hashes match the publication manifest.

Portable scripts: `reproduce.py --repo REPO --verilator EXECUTABLE --jobs 2`; `audit.py REPO`. Prepare the public packet by archiving `review-evidence/gptp106-r1` from `42e140e6768105b5b53231367046800f630b834e` into `scratch/public`. `MANIFEST.sha256` lists publishable receipts/scripts; scratch is excluded.

R906-1 FINISHED
