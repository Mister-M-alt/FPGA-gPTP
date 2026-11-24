# Receipts: FPGA-gPTP #109, round 1 ([A836])

Head: 8e4889b on `109-negative-delay-clamp`, with base `main` 1213ac5b. Everything is local; nothing is pushed.
All files are plain text and under 200 KB.

| File | What it shows |
|---|---|
| `repro_1213ac5b.txt` | The new #109 phases against the 1213ac5b image: 24 FAIL. -81, -263, the over-stated constants, -800, -801, -5 ms and the wire minimum each lose asCapable and the grandmaster, and their next Follow_Up is not used. -3 and -80 pass. |
| `engine_suite.txt` | The engine suite at 8e4889b, all four passes: 2296, 2296, 2296 and 61, all passing. It also gives the 1213ac5b baseline (2199) and the wire-minimum INFO line. |
| `arm_p109_controls.txt` | The eight #109 controls, each failing every check it names. |
| `arm_full.txt` | The full engine mutation arm: 175 of 175 caught, every slice's unmutated control passing, 0 survivors. Includes the slice table and every verdict line. |
| `repo_gates.txt` | contract, lint, ucpu, parser and its controls, gaskets and its controls, tsngen and its controls, bench, `make docs`, and the ROM budget before and after (1013/1014 words, both sides). |
| `ooc.txt` | Out-of-context synthesis before and after: engine 5,375 LUT, 3,617 FF, 1.5 BRAM, 6 DSP, WNS +2.093 ns on both sides; ucpu identical too. Delta zero. |
| `parent.txt` | Parent consumer gates in the scratch clone: milan_dp gptp and gptp-lat, the probe build, gptp_shadow (run, lifecycle, controls), gptp_plane, gptp_tables, gptp_txts, milan_dp_gm_steps, milan_dp_gptp (physical leg and controls), builder tests and submodule-scanning ratchets. Also the pre-fix probe runs, the isolation of a probe side effect, and the Verilator 5.054 note. |
| `clauses.txt` | The quoted text of every cited clause from the standards on disk. 802.1AS-2011 has no 11.2.15.3.4; computePropTime is 11.2.15.2.4. |

Scratch (not copied): `$VALIDATION_STORAGE/gptp109-a836` (logs, OOC runs, arm slices); `$VALIDATION_STORAGE/scratch/gptp109-parent` (parent clone, branch `gptp109-scratch`, 7 local commits, never pushed).
