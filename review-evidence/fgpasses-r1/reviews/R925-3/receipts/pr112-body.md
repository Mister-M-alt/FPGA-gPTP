[A839]

Closes #111.

Run the engine suite's four passes as four make jobs, within the caller's job budget, printed and ended as the
serial run printed and ended them.

Branch `engine-run-passes-at-once`: two commits on main `1213ac5` (#108), head
`661e4c3a45904d2d8f3e061c67103a945651d9ff`.

- `bbda770` ran the four passes at once inside one recipe.
- `661e4c3` makes each pass its own make job, answering the round-1 reviews.

The change comes from kebag-logic/milan-fpga's CICD lane (#998), where `make -C gptp-processor all` is the
slowest unit of the native bank.

## What changes

`tb/verilator/engine/Makefile`, target `run`, now four double-colon `run::` rules, plus the new
`tb/verilator/engine/pass_run.py`.

- **The passes are make jobs.** `engine-pass0` … `engine-pass3` are targets of their own, so make schedules them
  within the caller's job budget:
  - `make run` or `make -j1 run` runs one at a time;
  - `make -j4 run` runs all four at once;
  - under a parent `$(MAKE)`, each pass is one job of the parent's jobserver.

  `pass_run.py run` writes the pass's image and runs the pass exactly as the serial recipe ran it: the simulator
  itself for pass 0, the serial line's own `cd DIR && ../obj_dir/Vengine_sim …` through `/bin/sh` for passes 1-3.
  It keeps standard output and standard error apart, and records the exit status, or the signal and whether it
  dumped core. It always exits 0, so a failing pass never stops make before the passes print.
- **The serial transcript, from make itself.**
  - `run`'s rules replay each pass from their own recipe lines, in the serial order and under the serial echo
    lines. Make runs double-colon rules in order, so every message make prints names `run`, as before.
  - Each replay line ends as the serial line ended: with the generator's or the simulator's exit status, or by
    re-raising the same signal. Make therefore reports `Error 1`, `Aborted (core dumped)`, `Segmentation fault`
    or `Killed`, as it did.
  - `-s` hides the `./obj_dir/Vengine_sim` echo, as make hid it. Under `-i` every pass runs, and each failure is
    `(ignored)` right after its output. Under `-k` nothing prints after the first failure, as the serial recipe
    stopped there.
- **Fail fast.** Unless make runs with `-i`, the first failing pass in order stops every later pass (their output
  was never printed). A later pass that has not started never starts.
- **Signals.**
  - INT, TERM, QUIT and HUP to a pass reach its simulator, and to every process below it in case `/bin/sh` did not
    exec it. The pass then dies of the same signal.
  - TERM to make alone, or any of the four to make's process group, leaves no simulator running.
  - QUIT now stops the passes: they were async children that ignored it.
- **Errors in the replay itself.** A transcript that cannot be printed fails its line with a diagnostic,
  `engine pass N: its transcript could not be printed`.
- **`make passes-test`.** It is in `all`, beside `mutants-order-test`, and takes about 90 s. `passes_test.py`
  runs this Makefile against a reference whose `run` is the serial recipe, both with a stub Verilator, a stub
  generator and a stub simulator. Its 69 checks:
  - the transcript, standard output and standard error apart, and the exit status equal the serial recipe's;
  - this holds for eleven plans (clean; a failing pass at positions 0, 1 and 3; two failing passes; SIGSEGV,
    SIGABRT and SIGKILL deaths; a refused image; an image generator killed by SIGSEGV; a failed build), each under no option, `-s`, `-i` and `-k` at
    `-j4`, and each again at `-j1` with no option;
  - only the tree's own path and make's recipe line numbers are masked;
  - the clean `-j4` run must finish its passes out of order;
  - budget: at most 1, 2 and 4 passes at once at `-j1`, `-j2` and `-j4`, the 4 reached; under a parent `make -j3`
    with two other jobs, 3 at once in all, reached;
  - fail fast: at `-j4` passes 2 and 3 are stopped, and at `-j1` they never start;
  - INT, TERM, QUIT and HUP to make's group, and TERM to make alone, leave no simulator;
  - an unreadable kept transcript fails the run after pass 0 printed, with the diagnostic;
  - a replayed signal death is re-raised from `obj_dir/engine-passes/`.
- **Planted defects.** Eleven are each caught by `passes_test.py`:
  - the four passes in one job (the previous commit's shape, caught by the budget checks);
  - the echo under `-s`;
  - `-i` not passed;
  - the `-k` suppression removed;
  - a signal death replayed as status 128+n;
  - no fail-fast stop;
  - a print failure ignored;
  - signals not forwarded;
  - standard error merged into standard output;
  - the image generator run without the serial line's redirection, its signal death replayed as 256-n;
  - the replay re-raising in make's directory.
- **Races closed.** A pass that has ended ignores the stop signal, so a later stop cannot kill it while Python
  shuts down. A signal that arrives before the simulator's process is known is forwarded once it is.
  `passes-test` is green on six runs in a row.
- `docs/TEST_DEVELOPER.md` describes the passes as make jobs and adds `passes-test`. The new Makefile comments
  cite #111.

Nothing else changes: no check, image, generator argument, harness flag or mutant.

## Behaviour that differs from the serial recipe

- **Line numbers.** make's error lines name the new recipe line numbers.
- **Interrupts.** On an INT or TERM, make prints one `Interrupt` or `Terminated` line per running pass target
  (`engine-passN`), where the serial recipe printed one for `run`. It prints no partial pass output; the serial
  recipe had printed what pass 0 had written so far. Make's exit status is the same: it dies of that signal.
- **Core dumps.** A replayed signal death that dumped core re-raises the signal so that make still prints
  `(core dumped)`. This leaves one more core: the replaying `python3`'s.
  - Where `core_pattern` pipes cores, that is one more core record.
  - Where `core_pattern` is a file such as `core`, the replay re-raises from `obj_dir/engine-passes/`. Its core
    lands there, in the ignored build tree, and never replaces the simulator's core.
  - `passes-test` checks the replay's working directory.
- **Output timing.** Output appears when the passes have finished, not as the first pass runs. Printing
  progressively would need `run`'s rules to start their passes one rule at a time, since make runs a double-colon
  rule's prerequisites only once the earlier rules are done. That would serialise the passes.
- **Callers.** A caller that wants the passes at once must give make the job slots: `make -j4`, or a parent
  `$(MAKE)` with four free slots. A bank that runs `make -C gptp-processor all` without `-j` now gets the serial
  time.

## Measured (kebag-logic/milan-fpga's shared build host, 2026-11-24)

The setup:

- Each arm had its own clone and was pinned to one thread per physical core, with no other work of this lane on
  the siblings.
- `MAKEFLAGS='-jN --no-print-directory'`, the shared ccache, pinned Verilator 5.050, GNU make 4.4.1.
- The host was shared and its load varied: the same serial arm on the same CPU took 453 s, then 653 s. So the
  work measure is instructions, and the wall clock is compared within concurrent pairs.

| `make -C tb/verilator/engine run` | wall | CPU (user+sys) | instructions | exit |
|---|---:|---:|---:|---:|
| main, `-j4` (serial recipe) | 453.3 s | 451.6 s | 7.518 T | 0 |
| this branch, `-j4`, run concurrently | **221.3 s (2.05×)** | 588.4 s | 7.540 T | 0 |
| main, `-j4`, a second pair | 653.0 s | 650.6 s | 7.518 T | 0 |
| this branch, `-j4`, same pair | **221.4 s (2.95×)** | 542.9 s | 7.540 T | 0 |
| this branch, `-j4`, same pair, other cores | 181.4 s | 493.1 s | 7.540 T | 0 |
| main, `-j1` | 460.6 s | 458.8 s | 7.518 T | 0 |
| this branch, `-j1` (the budget honoured: one at a time) | 477.0 s | 475.1 s | 7.521 T | 0 |

- **Work (#111 criterion 2, [amended](https://github.com/Mister-M-alt/FPGA-gPTP/issues/111#issuecomment-7145509264)).** Retired user
  instructions are +0.29 % at `-j4` and +0.04 % at `-j1`, from the wrappers. Both are within the +1 % bound.
- **CPU (recorded, not the gate).** CPU seconds track host contention, not work.
  - At `-j4`, the pairs gave +30.3 %, −16.5 % and −24.2 % at identical instruction counts.
  - The `-j1` pair, the same work one pass at a time, is +3.5 %.
- **Wall.** The wall time is about the longest pass, which varies between pass 0 and passes 1-2.
- **Earlier figures.** Round 3's single pair, under heavier load and before the budget was honoured, measured
  2721.6 s → 974.6 s (2.79×).

The transcripts at matching flags are IDENTICAL once only host text is removed:

- 171 normalised lines at `-j4` (three head arms against two base arms);
- 170 at `-j1`.

At `-j4` both recipes print one more line than at `-j1`: `make[1]: warning: jobserver unavailable: using -j1`,
from the make that Verilator's `--build` starts on the unchanged build line.

A planted abort at the start of pass 1 (the real harness, both recipes, `-j4`) gives the same transcript:

- pass 0's 2199 checks, the request-counter echo line and `planted: pass 1 aborts`, then
  `make: *** [Makefile:NN: run] Aborted (core dumped)`, exit 2;
- only NN differs (55 → 74).

The branch's run took 154.9 s against 228.4 s; passes 2 and 3 were stopped.

## How to validate

```sh
git checkout engine-run-passes-at-once
make -C tb/verilator/engine passes-test                      # engine passes test: PASS (69 checks, ~90 s)
make -C tb/verilator/engine clean
make -j4 -C tb/verilator/engine run > /tmp/par.log 2>&1; echo "rc=$?"     # 0, about its longest pass
git checkout 1213ac5 -- tb/verilator/engine/Makefile
make -C tb/verilator/engine clean
make -j4 -C tb/verilator/engine run > /tmp/ser.log 2>&1; echo "rc=$?"     # 0, the serial time
git checkout engine-run-passes-at-once -- tb/verilator/engine/Makefile
diff <(grep -v -e '^- Verilator' -e 'g++' -e 'verilator --cc' /tmp/ser.log) \
     <(grep -v -e '^- Verilator' -e 'g++' -e 'verilator --cc' /tmp/par.log) && echo IDENTICAL
make docs lint                                                        # both exit 0 at this head
```

## Not done here

- Progressive printing (above).
- The parser arm (`tb/verilator/parser/mutants.py`, 34 mutants run one at a time with no ccache) has the shape
  #102/#104 fixed for the engine arm. Porting it is a separate change.
- The unchanged build line's `--build -j 0` still sizes its own compile by the CPU count, not by the caller's
  budget.

