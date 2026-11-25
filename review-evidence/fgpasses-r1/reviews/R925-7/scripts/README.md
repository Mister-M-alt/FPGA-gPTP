Reviewer scripts (portable; paths are arguments).

- `probe_nocore.py PASS_RUN SCRATCH`: replays a `{signal: SIGSEGV, core: false}` record through
  `pass_run.py replay 0` at caller core limits (0,0), (0,inf), (1,inf), (inf,inf) (those the caller's
  hard limit allows) and prints the kernel's core-dumped bit and make's message, against an exec'd
  non-dumpable and a dumpable reference. Exit 0 when the replay matches the non-dumpable reference.
- `check8_only.py ENGINE_DIR SCRATCH`: runs `passes_test.py`'s check 8 (`no_core_replay`) alone under
  the caller's current core limits.
- `plant_noprctl.sh CLONE WORKDIR`: removes the `prctl` call from a disposable copy and runs `passes-test`.
