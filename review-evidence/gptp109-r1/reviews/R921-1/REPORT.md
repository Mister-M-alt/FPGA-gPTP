[R921] NEGATIVE - exact head 8e4889bba462d14d4e5a34068769872510d4775d

# R921-1: independent review of Mister-M-alt/FPGA-gPTP PR #110 (Closes #109)

- Head: `8e4889bba462d14d4e5a34068769872510d4775d`, tree `bcd69a8e01ba7856d093579faf0dfbf256e772e4`, branch `109-negative-delay-clamp` -> `main`.
- Base: `1213ac5b9e09b8759ba76cc70c53652b5e108996`.
- Reviewer: R921, internal, cleared context, round R921-1.
- Verdict: NEGATIVE, because of one MINOR (F1). F1 is a stale reproduction figure in the PR text and its receipts.
  - Engine behaviour, generator logic, tests, controls and docs are otherwise correct at this head.
  - The fix for F1 is a re-measurement and a PR-text correction. It needs no source change.

## Reconstruction (in the order required)

1. Repository guidance.
   - There is no `AGENTS.md` or `CONTRIBUTING.md` at this head.
   - I read `README.md`, `docs/README.md` (truth order and document status) and `docs/MANAGER.md` (release evidence and ROM budget).
2. Frozen scope: the #109 issue body, plus the manager's ruling issuecomment-7123290416, decided for the owner.
   - The ruling supersedes the body's acceptance item 1 ("used as 0 by the sync path").
   - What the ruling requires:
     - Any negative D is a good exchange.
     - `S_PDELAY = max(D, -NPD_HI_C)`, signed, with no clamp to 0 in the engine.
     - The publication stays signed in the engine.
     - The parent's `KL_gptp_shadow.sv` is the only clamp to 0.
     - +800 is good and above it is bad.
     - The test list in ruling item 5.
3. Authorities.
   - Milan v1.2 4.2.6.2.7 and 4.2.6.1.1.
   - 802.1AS-2011/Cor1 11.2.2, 11.2.12.6, 11.2.13.2.1 f), 11.2.15.2.4 and Figure 11-8.
   - 802.1AS-2020 11.2.2, 11.2.13.7, 11.2.14.2.1 and 11.2.19.3.4.
   - I checked these against the clause text quoted in the author's public receipt `clauses.txt` (see Limits).
   - Parent consumer: `hdl/ieee8021as/gptp_plane/KL_gptp_shadow.sv`, read at live dev `e275d795` via the API, lines 762-771.
     - That clamp, `pub_pdelay_raw_w[31] ? 0 : raw`, is the only reader of the engine word in that module.
4. The diff `1213ac5b..8e4889b` (11 files, +531/-63) and its three commits.
5. Public evidence: `review-evidence/gptp109-r1` at `90fd6083`.
   - All 12 files match their `MANIFEST.json` published sha256.
   - I also read the author's REVIEW READY comment on #109 and the PR body.
6. Prior public review findings on PR #110: none.
   - There are 0 reviews and 0 review comments.
   - The only issue comments are the R921-1 and R922-1 start notices. Nothing needed resolving or retaining.
   - I read no other reviewer's report.

## What the change does (verified by reading the generator and the ROM)

- `_pdpost_corrected_delay` (`hdl/ucode/gen_gptp_ucode.py:2260-2268`) floors D without a branch.
  - It computes `m = (D + 800) >>arith 63; D -= (D + 800) & m`. That gives D = -800 exactly when D < -800, and D otherwise.
  - It then writes the same floored, signed D to `S_PDELAY` and to publish word 3.
  - Overflow is impossible:
    - |t3 - t2| < 2^62, from the fold of int32 seconds x 1e9 plus a 32-bit ns field.
    - nrr*turn >> 30 < 2^35.
    - So |D| < 2^62 and neither `D + 800` nor `D - 801` can wrap.
  - RU is not live across the leg.
- `_pdpost_verdict` (`:2284-2287`) is bad iff bit 63 of `D - 801` is clear, i.e. D >= 801.
  - It reads the floored D. That is equivalent, because the floor never moves a value across +800.
  - The ladder, `S_PDGOT`, lostResponses and the bad-arm flag masking are unchanged.
- The Sync path (`:1069-1071`) computes `offset = rx - (origin + correction + S_PDELAY)` in signed 64 bits, so the signed use is real.
- The ROM stays word-neutral. The old verdict had 8 instructions and the new one has 4; the floor adds 4.
  - The shipping image uses 1,013 words and the seeded image 1,014.
  - The leg map is identical to the base.
  - All four tracked images regenerate byte-identically from the head generator.
- No RTL file changes.
  - `pub_pdelay_ns_o` is `st_wdata_w[31:0]` (`hdl/top/KL_gptp_engine.sv:1221`).
  - No ROM code reads `RG_PUB|3` back.

**The floored publication, judged against the ruling.** I judge it consistent with the ruling's intent and with the parent.

- The ruling requires the publication to stay signed in the engine, and the floored value is signed.
- The parent clamps on bit 31. So for every D in (-2^31, 0) the CSR reads 0 whether the engine publishes raw D or the floored value.
- Below -2^31 ns, a raw 64-bit D truncated to 32 bits can arrive with bit 31 clear. The parent would then publish a bogus positive delay.
  - At base, the wire minimum published `0x9DCD1F9B`.
  - The floor guarantees that every negative D reaches the parent as a negative 32-bit word, so the parent's clamp to 0 stays the only clamp, as the ruling requires.
- The "published and used values differ by design" statement (ruling item 5) is met at the parent boundary: the CSR reads 0 and the servo uses the signed value.
  - `docs/INTEGRATION.md:954-992` states this.

## Executed evidence (reviewer runs, exact head, Verilator 5.050 pin verified)

The Verilator identity was checked as `Verilator 5.050 2026-07-01 rev v5.050` through the pinned wrapper. All builds ran in `git archive` extractions under `scratch/`.

| Run | Result | Receipt |
|---|---|---|
| Engine suite, `make run`, four passes | 2296/2296, 2296/2296, 2296/2296, 61/61, rc 0 | `receipts/head_suite.txt` |
| Reproduction: head harness and RTL, base generator ROM, shipping pass | 2265 PASS, **31 FAIL** (all `#109`), rc 2 | `receipts/repro_suite.txt` |
| `make docs`, `make contract`, `make lint` | rc 0, 0, 0 | `receipts/docs.txt`, `contract.txt`, `lint.txt` |
| ROM images regenerated and compared | engine, ucpu/ooc and tsngen images byte-identical; 1013/1014 words; leg map same as base | `receipts/summary.txt` |
| The 8 #109 controls (`p109_mutants.py`) | control PASS; 8/8 caught, each failing every check it names | `receipts/arm_p109.txt` |
| Existing controls on the Pdelay, ladder and asCapable path | 27/27 caught; control PASS | `receipts/arm_related.txt` |
| Existing controls on the Sync, servo and receipt path | 21/21 caught; control PASS | `receipts/arm_sync.txt` |
| Arm structure | 175 entries: 167 base entries unchanged, 8 added, 0 pattern mismatches | `receipts/summary.txt` |
| Reviewer probes R1-R5 (not part of the PR) | R1 floor -801, R2 engine clamps its publication, R3 logical-shift mask, R4 only the publication floored: all caught. R5 (verdict reads bit 31): **survived**, see S1 | `receipts/arm_probes.txt` |

The ruling's test list against the head results:

- -3, -80, -81 and -263 keep asCapable, are published as computed, enter the next offset exactly and cause no step.
- The case of both constants over-stated by 400 ns measures 0. Clamping the used value to 0 is caught (offset -300, i.e. `0xFFFFFED4`).
- -800, -801, -5 ms and the wire minimum are used and published as -800, keep asCapable and cause no step.
  - The wire minimum computes -2,147,483,641,057,566,821 ns, inside the stated bound.
- 800 keeps asCapable. 801 clears it and its Follow_Up is not used.
- Phase 22 (-49 ns) is kept.
- The base harness had no "-81 clears" test or mutant. I checked the base `sim_main.cpp` and the arm, so the author's "inversion" statement holds.
- `NPD_LO_C` is retired consistently. It is gone from the generator, the `docs/INTEGRATION.md` table and `scripts/check_docs.py`, and no tracked file outside the history references it.
- The `docs/SOURCE_EVIDENCE.md` anchor moved from L1116 to L1115, and the source-evidence gate passes "20 exact".

## Findings

### F1 - MINOR - Tests, Docs: the published reproduction figure does not describe the committed harness

- **Where:**
  - The PR #110 body ("Against 1213ac5b these phases fail 24 checks"; "Reproduction: ... fail 24 checks").
  - The #109 REVIEW READY comment.
  - `review-evidence/gptp109-r1/author/receipts/repro_1213ac5b.txt` and `INDEX.md`.
- **Evidence:**
  - The committed harness at 8e4889b against the base ROM gives `2296 checks: 2265 PASS, 31 FAIL` (`receipts/repro_suite.txt`).
  - The 7 extra failures are `its offset uses the delay exactly` for -81, -263, over-stated, -800, -801, -5 ms and the wire minimum. Each got `0xb`, the `P109_BG_OFF` background offset, where 0 was expected.
  - The author's own receipt says its 24 came from an earlier harness, with background offset 0, "at that point of development".
- **Impact:** a measurement figure presented as the PR's reproduction does not match the committed harness. The qualitative claim holds: base fails, and -3 and -80 pass. Correcting it changes a figure, so it is not RESIDUE.
- **Required outcome:**
  - Re-run the reproduction with the committed harness.
  - Publish that receipt and correct the PR body figure (31) and its list, which should add "its offset is not exact".
  - Alternatively, state which harness revision produced 24.
- **Verification:** `receipts/repro_suite.txt` shows 31 FAIL lines, all prefixed `#109`.

### F2 - RESIDUE - Docs: unqualified clause citation right after an 802.1AS-2020 citation

- **Where:** `docs/INTEGRATION.md:978`, "That follows 11.2.13.2.1 f)."
- **Evidence:**
  - The preceding prefixed citation is "See 802.1AS-2020 11.2.2." (`:972`).
  - In 802.1AS-2020, 11.2.13.x holds the MDPdelayReq variables (for example 11.2.13.7), and the Sync receipt time is 11.2.14.2.1.
  - The intended clause is 802.1AS-2011 11.2.13.2.1 f), which matches the repository's bare-number convention (`docs/INTEGRATION.md:339`, `:1075`) and the generator's citation.
- **Why it is RESIDUE:** the clause claimed (the 2011 setMDSyncReceive f)) is correct. The fix only names the edition and changes no claim, figure, test or code.
- **Exact fix:** change it to "That follows 802.1AS-2011 11.2.13.2.1 f)."

### S1 - SUGGESTION - Tests: no trial pins the rewritten verdict's 64-bit width for a huge positive delay

- **Evidence:** reviewer probe R5 makes the verdict read bit 31 instead of bit 63 of `D - 801`. That judges every D >= 2^31 + 801 ns good, and it **survives** the full harness (`receipts/arm_probes.txt`).
- The head code is correct: I checked by reading it, and it is equivalent to the base for positive D.
- Suggested trial: a `PD_WIRE` exchange giving the most positive wire delay, expecting asCapable to fall.
- This does not block.

### S2 - SUGGESTION - Docs/HDL: generator header

- `hdl/ucode/gen_gptp_ucode.py` opens with per-issue entries for #100, #106 and #107, but none for #109.
- The v4 paragraph (`:328-330`) still describes "the Milan 4.2.6.2.7 floor". That is true as history but no longer complete.
- The phase-22 function name `accept_a_negative_delay_inside_the_milan_floor` keeps the old wording.
- A short #109 header entry would keep the header's convention.

### Comment-rule and public-text checks

- In the reviewed delta I found no bench lane labels, lane names, review rounds, reviewer IDs or issue-comment IDs in source comments.
  - "the manager's ruling" is a role label.
  - The issue-comment link is in `docs/INTEGRATION.md`, not in source, and matches three existing doc precedents.
- No private names and no assistant tool or model names appear in the delta, the commits or the PR body.
- No RESIDUE under the comment rule.

## Reviewer-owned ledger

| Lens | State | Examined artifacts | Covering round | Exact head |
|---|---|---|---|---|
| Conformance | CLEAN | Ruling items 1-5 against the generator (`:2238-2316`) and the Sync path (`:1069-1071`); Milan 4.2.6.2.7 and 4.2.6.1.1; 802.1AS-2011/Cor1 11.2.2 and Figure 11-8; 2020 11.2.2 and 11.2.13.7; the parent clamp at `KL_gptp_shadow.sv:762-771` (dev e275d795) | R921-1 | 8e4889bba462d14d4e5a34068769872510d4775d |
| RTL | CLEAN | No `.sv` change; ROM diffs in all four images; floor and verdict instruction semantics; overflow bound; register liveness; word-neutral budget and same leg map; lint rc 0; author's OOC receipt (identical before and after) | R921-1 | 8e4889bba462d14d4e5a34068769872510d4775d |
| Robustness | CLEAN | Wire-minimum path (|D| < 2^62); 32-bit publication sign for every negative D; huge positive D still bad (verdict on 64 bits); floor never rejects an exchange; parent boundary | R921-1 | 8e4889bba462d14d4e5a34068769872510d4775d |
| Tests | UNCLEAN (F1) | Phases 62-64 and the changed phase 22 and #8 comments; suite 2296x3/61; reproduction 31 FAIL; 8/8 #109 controls; 48 existing controls; probes R1-R5 | R921-1 | 8e4889bba462d14d4e5a34068769872510d4775d |
| Docs | UNCLEAN (F1; F2 is RESIDUE) | `docs/INTEGRATION.md` new section and table; `SOURCE_EVIDENCE.md` anchor; `check_docs.py` list; generator and harness comments; PR body; REVIEW READY comment; evidence INDEX | R921-1 | 8e4889bba462d14d4e5a34068769872510d4775d |

## Real limits

- **Arm coverage.** I ran 56 of the 175 arm entries myself at the exact head: all 8 new controls and 48 existing controls on the Pdelay, ladder, asCapable, Sync and servo paths.
  - The other 119 rest on the author's published `arm_full.txt` (175/175).
  - Its slice 143:150 ran on the f3c33d0 content. It differs from the head only in one harness declaration and in docs.
  - The host load average was about 200 on 32 CPUs, so a full serial pass was not feasible inside this review.
- **Out-of-context synthesis.** I did not run it, because no Vivado is installed on this host. The claim that it is unchanged rests on the author's `ooc.txt` and on the fact that no RTL changed.
- **Parent consumer gates.** I did not run them: no parent bank, by the brief.
  - I read the parent clamp. For the gates themselves (milan_dp gptp/gptp-lat 212/212, gptp_shadow 332/332, the -263 ns and -5 ms probes) I rely on the author's `parent.txt`.
  - Those ran on dev-soft-core `aa30d77f` with local-only probe commits, not on live dev `e275d795`.
- **Clause text.** I checked it against the quotations in the author's public `clauses.txt`, not against the standards themselves.
- **No manager source bank** runs at this head, and none is claimed. There are no hosted check runs or statuses at the head, and the tree has no workflows.
- **Physical calibration** was not run. Simulation is not hardware proof.

## Pending manager duties

- Build and validate the current-dev merge candidate (builder and native banks) at the merge turn. The source base is 1213ac5b and live dev is e275d795.
- Own hosted and act acceptance.
- At the parent gitlink bump:
  - Refresh the donor links and the submodule-boundaries diagram.
  - Run the imported-gPTP docs gate, the submodule docs gate and the C++ idiom ratchet.
  - Consider committing parent probes at -263 ns and -5 ms. Ruling item 5's "CSR reads 0" is shown only by local-only probes, plus the existing -40 ns probe.
- Optionally annotate #109's acceptance item 1, which the ruling supersedes.
- Carry F2 to the residue checklist.

## Packet

- `MANIFEST.sha256` lists every publishable receipt and script.
- `scripts/run_review_gates.sh` is the gate and reproduction runner.
- `scripts/run_p109_arm.py` is the arm-subset driver and holds the reviewer probes.
- `scripts/arm_patterns.py` checks the arm's structure.
- Paths in receipts are rewritten to `<PACKET>`, `<HOME>` and `<VERILATOR_PREFIX>`.
- Clone integrity after the probes:
  - HEAD and tree are exact, and `git status --porcelain --ignored` is empty.
  - Index equals HEAD and the worktree equals the index.
  - The `ls-files -s` digest equals the `ls-tree` digest.
  - The tree has no gitlinks (no submodules).

R921-1 FINISHED
