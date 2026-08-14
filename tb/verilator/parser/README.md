<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# tb/verilator/parser — 802.1AS field extraction

Builds Announce (with a 2-hop path trace TLV), Sync, Follow_Up (with the
information TLV) and Pdelay_Resp frames byte-by-byte in C++ — an
independent re-implementation of the 802.1AS-2011 wire layout — and
checks every message-bank word the parser writes, plus the end-of-frame
event and its sequenceId. Also proves the drop arms: wrong EtherType,
transportSpecific ≠ 1, PTP version ≠ 2, truncation below the per-type
minimum, and rx_err, each of which must produce no event and one drop
count. 31 checks, mutation-proven.

This suite is what caught the three field-straddle bugs (announce
currentUtcOffset outside the 8-byte accumulator window, the stepsRemoved
slice, the un-gated Follow_Up TLV) and the end-of-frame race that the
one-cycle finalization now closes — the reason last-byte field writes and
the hop-count word cannot fight for the single bank lane.

`make` — exit 0 = PASS.
