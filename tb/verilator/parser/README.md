<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# tb/verilator/parser — 802.1AS field extraction

Builds Announce (with a 2-hop path trace TLV), Sync, Follow_Up (with the
information TLV) and Pdelay_Resp frames byte-by-byte in C++ — an
independent re-implementation of the 802.1AS-2011 wire layout — and
checks every message-bank word the parser writes, plus the end-of-frame
event and its sequenceId. Also proves the drop arms: wrong EtherType,
transportSpecific ≠ 1, PTP version ≠ 2, a foreign domainNumber
(802.1AS-2011 8.1 and IEEE 1588-2008 9.5.1: a Sync in domain 5, a
better-priority Announce in domain 1, a Pdelay_Resp in domain 255, and
the two header-only types whose only barrier after the arm is the
end-of-frame gate, a Pdelay_Req in domain 0x10 and a Signaling in
domain 0x80, each first accepted in domain 0 so the refusal cannot pass
vacuously; every arm is refused with no event, no message-bank write
and exactly one counted drop, because the arm sits at header byte 4
ahead of every bank write), truncation below the per-type minimum, and
rx_err, each of which must produce no event and one drop count. 51
checks, mutation-proven: the domain arm removed fails 16, the compare
narrowed to its low nibble fails 7 (the zero-low-nibble values 0x10 and
0x80 catch it), and the end-of-frame gate without its bad_r term, a
drop that still dispatches, fails 5.

This suite is what caught the three field-straddle bugs (announce
currentUtcOffset outside the 8-byte accumulator window, the stepsRemoved
slice, the un-gated Follow_Up TLV) and the end-of-frame race that the
one-cycle finalization now closes — the reason last-byte field writes and
the hop-count word cannot fight for the single bank lane.

`make` — exit 0 = PASS.
