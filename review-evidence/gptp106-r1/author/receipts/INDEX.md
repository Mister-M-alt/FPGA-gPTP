# [A831] round 2 receipts

Every file here passes `privacy.scrub_redact(b) == b`, on the raw bytes and on each member of the compressed file. The checker is `tools-r2.tar.gz:lane/privcheck.py`; its result is the last line of `gates.txt`.

| File | What |
|---|---|
| `gates.txt` | One line per gate at the final head `a728cc3`: the processor gates, the full engine mutation arm (by slice), the parent gates, OOC, the routes, and the privacy check |
| `gates-processor.txt` | The processor gates at `a728cc3` (gate worktree): rc lines, engine tallies of the four passes, the #100/#106/#107 INFO lines, the other suites' tallies |
| `arm-a728cc3.txt` | The engine mutation arm at `a728cc3`, every control's verdict line through the arm's own `run_mutant()` (167 controls and the positive control) |
| `controls-107-first-run.txt` | The first run of the seven #107 controls and the three changed #100 controls, before the commit, each with the failed lines of the checks it names |
| `ooc-r2.txt` | Engine and µCPU OOC, 1616fc8f against `a728cc3`, and the utilisation-report diff |
| `near-clamp-C.txt` | Documented behaviour under D1 = C: ±197 and ±199 ppm grandmasters followed from mastership, with settling times and a pair-by-pair trace (not graded; `tools-r2.tar.gz:near-clamp-experiment.patch`) |
| `parent-takeover-gate.txt` | The takeover gate (the gmstep leg plus the #107 takeover phase) at the head: the final run, the two earlier tries and their harness defects, and the same harness at the base pin as the control |
| `parent-gm_steps.txt` | milan_dp_gm_steps: the clean gmstep leg and its five controls |
| `parent-gptp_shadow.txt` | gptp_shadow: the standard gate (+100 ppm master) and the −100 ppm variant, with the counter's addend before and after the takeover |
| `parent-milan_dp-gptp.txt` | milan_dp gptp and gptp-lat legs |
| `parent-ratchets.txt` | The parent's Python, SystemVerilog and C++ ratchets at the pin commit, and the arm module's length |
| `routes.txt` | The four routes (head and base, 1x1/1if and 8x8/1if): signoff per corner, route status, placed utilisation, the deltas and the gPTP plane's cells |
| `tools-r2.tar.gz` | The scripts used here (gate legs, arm slices, parent legs, route recipe and summaries, privacy checker), the scratch parent's takeover-gate patch and the near-clamp experiment patch; home paths scrubbed |
