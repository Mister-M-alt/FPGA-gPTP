issue #111 body, updated 2026-11-24T21:52:48Z

## Objective and observed evidence

The engine suite (`make -C gptp-processor all`, its `tb/verilator/engine` passes) runs its four passes one after another. In a parent merge candidate's native bank on a loaded host the whole `gptp-processor all` command took 21,472 s. Running the four passes at once was measured at 974.6 s against 2,721.6 s wall, CPU +2.3 %, with the transcript identical once each pass is printed in the serial order.

## Scope

In scope: run the engine suite's four passes concurrently within the caller's job budget, print each pass's output in the serial order under its serial heading, keep every pass's verdict and the suite's exit code.

## Acceptance criteria

1. The suite's transcript (host text removed) and exit code are identical to the serial run's at the same head, clean and with a planted defect in one pass.
2. Wall time falls by the measured amount. The work does not grow, measured as retired user instructions (`perf stat -e instructions:u`) over the whole suite: at matching flags (`-j1` and `-j4`) the head stays within +1 % of the serial recipe. CPU seconds and cycles are recorded and published for every pair but are not the gate, because they track host contention (amended 2026-11-24, see the amendment comment).


