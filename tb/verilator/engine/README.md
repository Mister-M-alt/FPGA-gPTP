<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# engine -- whole-plane protocol round-trip

Drives `KL_gptp_engine` (parser + µCPU + TX slot + timer + region map)
through a full 802.1AS life: boot cadence, both Pdelay roles byte-exact,
the asCapable ladder up and down, announce receipt timeout into
grandmaster capability, Announce/Sync/Follow_Up as master byte-exact,
BTCA both directions against a scripted peer, and the slave sync path
with its receipt timeouts.

The harness is the peer: an auto-responder answers every Pdelay_Req the
DUT transmits (its clock runs +2^-13 against ours), and a pdelay model
mirrors the SPEC formulae (the successive-response neighborRateRatio of
802.1AS-2011 11.2.15.3 as a Q2.30 ratio and the corrected link delay)
in exact integer arithmetic, never reading DUT internals. Every Milan
v1.2 4.2.6 profile number is pinned by a phase that fails if it drifts:

| phase | claim |
|---|---|
| 1, 2 | asCapable is NOT set after one good exchange (4.2.6.2.4) |
| 4 | it IS set at the second; pdelay matches the nrr-corrected model |
| 5 | become-master waits for asCapable |
| 10, 12 | sync-ok rises on a completed pair, falls at 375 ms (Table 4.2) |
| 11 | a Follow_Up later than 125 ms pairs with nothing (Table 4.2) |
| 10, 13 | offsets beyond 20 us re-base the modeled PHC by their exact negation, and the step's addend write is the bare surviving integrator |
| 14 | a +5 us offset SLEWS: the PI addend equals the integer mirror |
| 15 | closed loop: a +140 ppm master (above half the clamp on purpose) locks under 200 ns after one re-base, the addend carrying its rate |
| 16, 17 | a Follow_Up pairs only with its Sync's sequenceId AND sourcePortIdentity (11.4.4) |
| 18 | gmId tie -> stepsRemoved (shorter wins, longer loses) -> sourcePortIdentity tiebreak switches the parent with NO sync-ok flicker |
| 18b | a delayed dispatch reads the frame its event names (the second bank): a worse announce beside a parent Sync REJECTS, never a wrongful takeover |
| 19 | a parent degrading below us yields mastership IMMEDIATELY (10.3.5) |
| 20 | the Sync originTimestamp carries the live PHC (11.4.3; gather sel 0 consumes phc_ns_i) |
| 21 | an asCapable fall stops sync consumption and steering; recovery resumes it |
| 21b | become resets the best record: no ghost GM outlives the receipt timeout |
| 21c | the priority vector outranks the identity in the compare order |
| 21d | the same delayed shape with a BETTER announce ADOPTS: the torn-read window is retired, the v6 seq guard stays belt-and-braces |
| 22 | negative pdelay in [-80, 0) keeps asCapable (4.2.6.2.7) |
| 23 | over 800 ns clears it (neighborPropDelayThresh, 4.2.6.1.1) |
| 24 | recovery needs two good exchanges again |
| 25 | the FOURTH lost response clears it (802.1AS-2011 11.2.12.4) |
| 26 | a ratio window wider than 2^32 ns is skipped, not divided stale |
| 27 | the Milan 4.2.6.2.5 cease rule: three multi-identity intervals stop Pdelay_Req and drop asCapable, the cadence countdown resumes them, the ladder re-earns; SAME-identity duplicates are not a storm; replayed forged response pairs cannot climb mid-cease |
| 28 | a warm reset during a cease still resumes: the countdown lives in reset-surviving scratch and the boot re-arms the cadence |
| 29 | a chasing Follow_Up cannot steal the Resp's arrival stamp: the ingress timestamp stages at sof and commits at EOF into the bank the frame occupies (the parent fabric bench's finding -- a single register loses to back-to-back delivery) |

All thirty-two planted mutations (ladder trigger, both pdelay
thresholds, all three timeout values, a dead ratio divide, a deleted
staleness guard, the fall-at-three lost count, a dropped adopt-side
sync void, a dead step threshold, both servo sign errors, a dead
integrator, a halved integrator clamp, a step that loses the rate
estimate, both pairing bypasses, an inverted steps compare, a dropped
parent update, a zeroed origin gather, a reverted consumption gate, a
removed dispatch seq guard, a dropped become-side best reset, a
swapped vector/identity compare order, a 30-interval cease threshold,
duplicates counted as a storm, a dead resume countdown, a removed
mid-cease completion gate, and two RTL mutations: the read bank tied
to the write bank, and the ingress stamp reverted to a single
register) turn the run red.

```sh
make        # regenerates gptp_ucode.hex from hdl/ucode/, builds, runs
```

Exit 0 = PASS; the tally line is the record.
