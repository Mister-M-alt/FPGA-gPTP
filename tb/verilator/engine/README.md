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
| 10, 13 | offsets beyond 20 us re-base the modeled PHC (adjtime) |
| 11 | a Follow_Up later than 125 ms pairs with nothing (Table 4.2) |
| 13 | negative pdelay in [-80, 0) keeps asCapable (4.2.6.2.7) |
| 14 | over 800 ns clears it (neighborPropDelayThresh, 4.2.6.1.1) |
| 15 | recovery needs two good exchanges again |
| 13 | a +1 ms offset STEPS the phc by its negation, addend untouched |
| 14 | a +5 us offset SLEWS: the PI addend equals the integer mirror |
| 15 | closed loop: a +100 ppm master locks under 200 ns, one re-base |
| 19 | the FOURTH lost response clears it (802.1AS-2011 11.2.12.4) |
| 20 | a ratio window wider than 2^32 ns is skipped, not divided stale |

All fourteen planted mutations (ladder trigger, both thresholds, all
three timeout values, a dead ratio divide, a deleted staleness guard,
the fall-at-three lost count, a dropped adopt-side sync void, a dead
step threshold, both servo sign errors, a dead integrator) turn the run
red.

```sh
make        # regenerates gptp_ucode.hex from hdl/ucode/, builds, runs
```

Exit 0 = PASS; the tally line is the record.
