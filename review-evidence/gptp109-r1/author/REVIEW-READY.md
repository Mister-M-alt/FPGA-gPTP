# [A836] FPGA-gPTP #109, round 1: REVIEW READY

- Repository: Mister-M-alt/FPGA-gPTP. Branch `109-negative-delay-clamp`, base `main` 1213ac5b, head 8e4889b. Local only, not pushed.
- Commits:
  - f3c33d0 Count a negative link delay of any magnitude as a good exchange and use it signed, floored at -800 ns (#109)
  - 124683a Document the link delay verdict and its -800 ns floor, and retire NPD_LO_C (#109)
  - 8e4889b Declare the #109 over-statement constants one per line (Rule 11 of the consumer)
- PR body: `PR-BODY.md` (Closes #109). Receipts: `receipts/INDEX.md`.

## What changed
- `hdl/ucode/gen_gptp_ucode.py`:
  - `_pdpost_corrected_delay` floors D at -NPD_HI_C, branch-free, before both writes (S_PDELAY, publish word 3).
  - `_pdpost_verdict` judges D bad only above NPD_HI_C.
  - NPD_LO_C is removed. The ROM stays word-neutral (1,013 and 1,014 words), with the same leg map.
- The four tracked ROM images are regenerated from the generator with their Makefiles' arguments.
- `tb/verilator/engine/sim_main.cpp`:
  - New peer modes: PD_SET (exact D) and PD_WIRE (raw timestamp fields).
  - Phases 62-64.
  - Phase 22 and 7b wording.
- `tb/verilator/engine/p109_mutants.py` adds eight controls. `mutants.py` imports them, and `#109 ` joins the named-check prefixes.
- `docs/INTEGRATION.md` gains a "Link delay verdict" section and loses the NPD_LO_C row.
- `scripts/check_docs.py` drops NPD_LO_C from CONSTANTS.
- `docs/SOURCE_EVIDENCE.md` re-pins one generator line (it moved one line up).

## Ruling conformance (issuecomment-7123290416)
- (a) Any negative D is a good exchange. +800 is good and 801 is bad. The other conditions are unchanged, and NPD_LO_C is retired everywhere it was named.
- (b) `S_PDELAY = max(D, -NPD_HI_C)`. There is no clamp to 0 in the engine.
- (c) The publish register stays signed. It carries the floored value, which is required so that the 32-bit word keeps its sign for D below -2^31.
  The parent's KL_gptp_shadow.sv remains the only clamp to 0.

## Decisions for the reviewer
- The publish word carries the floored value (-800 below the floor), not the raw D. The PR body explains why.
  The control "the engine publishes the unfloored delay" pins this choice.
- A bad verdict (D > 800) still clears asCapable on that exchange, as at 1213ac5b and as 802.1AS-2011 Figure 11-8 specifies.
  "After the allowed faults" applies only to lost responses (LOST_CLEARS_AT_C), unchanged.
- The "most negative value the datapath can produce" is tested from the wire: t2 at the most negative fold and t3 at the most positive.
  The plane computes -2,147,483,641,057,566,821 ns, within 2^33 ns of the wire's bound, because the ratio window that the same t3 corrupts adds a correction of at most 2^34.
  The sign test covers every 64-bit D by construction.
- There was no "-81 clears" test to invert (searched this repo and the parent). Phases 62 and 63 carry the inverted expectation, and phase 22 is kept.

## Process notes (honest record)
- One arm slice (0:7) ran at 4 jobs beside one parent simulation, i.e. 5 legs for about 11 minutes, because of a leg-count bug in my scratch runner. It was fixed for every later slice.
- milan_dp's gptp harness does not compile under the system Verilator 5.054, at sim_gptp.cpp:1551, unrelated to this change. All parent gates ran under the parent's CI pin, 5.050.
- Scratch probes in the parent were made a separate probe-only build after inline probes perturbed a later, timing-sensitive AECP counter check. The isolation is in receipts/parent.txt.

## Results (receipts/INDEX.md)

- Reproduction at 1213ac5b: 24 FAIL. Every D below -80 loses asCapable, is refused on the wire and loses the grandmaster. -3 and -80 pass.
- Engine suite at 8e4889b: 2296/2296 (shipping), 2296/2296 (request seed), 2296/2296 (Sync seed), 61/61 (priority1 255).
- Engine mutation arm: 175/175 caught, 0 survivors. The eight #109 controls each fail every check they name.
- Repository gates: contract, lint, docs, ucpu, parser (+controls), gaskets (+controls), tsngen (+controls) and bench all pass.
- OOC: engine and ucpu identical before and after (5,375 LUT / 3,617 FF / WNS +2.093 ns). The delta is zero.
- Parent, scratch, Verilator 5.050:
  - milan_dp gptp 212/212 and gptp-lat 212/212.
  - gptp_shadow 332/332, with lifecycle and 9 controls.
  - gptp_plane, gptp_tables and gptp_txts pass.
  - milan_dp_gm_steps: 196 checks and 5 controls.
  - milan_dp_gptp: 151/151 plus 54 control checks.
  - Builder tests and the submodule-scanning ratchets pass.
  - The imported-gPTP docs, submodule docs and diagram gates pass once the bump's links and diagram are regenerated.
  - CSR 0x6E4 reads 0 at -40, -263 and -5,000,000 ns with asCapable held. At 1213ac5b, asCapable is lost at -263 and -5 ms.

