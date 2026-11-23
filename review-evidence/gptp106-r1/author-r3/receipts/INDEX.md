# [A831] round 3 receipts

Unpacked files only, no archives. Every file here passes `privacy.scrub_redact(b) == b` (`tools/lane/privcheck.py`; its result is the last line of `privacy.txt`).

| File | What |
|---|---|
| `routes-r3.txt` | The image rule. Per side and shape, the #818 route set: every signoff corner, the routed and placed utilisation, the route status, the gate's `best()` pick and the floors. Then the qualifying head against the qualifying base, with the routed hierarchy split into disjoint pieces and the shared-LUT reconciliation, the gPTP plane and engine rows, and the depth-1 rows (`tools/route/routes3.py`) |
| `route-inputs.txt` | Generated-input identity: each export's provenance, the gate-style digest of every input per route with the base/head lines that differ, the comment-free body hash of the generated top across all eight exports, and the inputs digested again after the 1x1 exports (`inputs3.py`, `body3.py`) |
| `route-repeat.txt` | Repeatability: each synthesis and each ExtraTimingOpt placement, round 2 against round 3, row for row; the synthesised images, base against head (`repeat3.py`) |
| `routes/<shape>-<side>-<directive>/` | The reports each route's figures are read from: routed and placed utilisation, routed hierarchy, route status, the timing summary of the run and of each signoff corner (Vivado's host header line removed), and the run's start, end and slot (`collect3.sh`) |
| `routes/prep/` | The four exports' logs (`prep3.sh`) and the four route chains' logs (`chain3.sh`) |
| `envelope.txt` | The trim envelope per clock (50, 100, 125 and 2 MHz) against B.1.1's two corners, from the generator's own `ppm_addend()` (`tools/lane/envelope.py`) |
| `merge.txt` | The merge of main: parents and merge base, the conflict and its resolution, the resolved `mutants.py` against main, the module lengths, main's order test on the merged arm, and the unchanged `hdl/` tree |
| `gates-331e27d.txt` | The processor gates at `331e27d`: rc lines, the engine tallies, the INFO lines against `a728cc3`'s, the other suites' tallies, then the mutation arm's every verdict line and both halves' tallies (`gates3.sh`, `leg4.sh`, `armslice3.py`) |
| `parent-r3.txt` | The parent consumer gates with its gitlink at `331e27d`: the summary, each leg's tallies, the stopped ax1x1gptp leg, and the four ratchets (`parent3.sh`) |
| `tools/route/`, `tools/lane/` | Every script this round ran, as run (home paths scrubbed) |
| `privacy.txt` | The privacy check over this directory |
