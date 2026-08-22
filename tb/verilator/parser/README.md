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
ahead of every bank write), truncation below the per-type minimum,
rx_err, and the Follow_Up shape (Table 11-9: 76 octets, the information
TLV of 11.4.4.3 being a field of the message, not a suffix; FPGA-gPTP
#11): the 44-octet header-and-timestamp shape and a declared
messageLength of 75 are refused at the messageLength byte with no event,
no bank write and one drop; a declared 76 cut at 75 octets is refused at
the end-of-frame gate; a TLV header wrong in exactly one of tlvType,
lengthField, organizationId or organizationSubType is refused at the
TLV arm with no event, no word-11 write and one drop; the complete
Follow_Up still dispatches with its word 11 after the arms, and one
with a second TLV appended after the information TLV (messageLength 88)
is accepted, 11.4.1 having a receiver skip a TLV it does not parse;
the messageLength bound for every other type the per-type table names
(Sync 44, Announce 64, Pdelay_Resp, Pdelay_Resp_Follow_Up and
Pdelay_Req 54, Signaling 34): a physically complete frame declaring
one octet fewer
is refused at the messageLength byte with no event, no bank write and
one drop, and the exact minimum dispatches; and the padded Sync: a
44-octet Sync leaves its MAC padded to the 60-byte Ethernet minimum
(IEEE 1588-2008 13.3.2.4 NOTE: messageLength excludes the padding), so
four padded Syncs (zero padding, padding shaped like the information
TLV's tlvType, padding 0x0008, and 74 bytes) are each accepted with
their event, their six bank words and no drop; and the Pdelay_Req
shape (11.4.5 / Table 11-11: 54 octets, the header and two reserved
fields; FPGA-gPTP #12): the issue's header-only shape, messageLength
44 and messageLength 53 are refused at the messageLength byte with no
event, no bank write and one drop, a declared 54 cut at 53 octets at
the end-of-frame gate, and the complete request still dispatches after
the arms. 140 checks,
mutation-proven: the domain arm removed fails 16, the compare narrowed
to its low nibble fails 7 (the zero-low-nibble values 0x10 and 0x80
catch it), the end-of-frame gate without its bad_r term, a drop that
still dispatches, fails 34 (the #15 round's 5: retiring the per-type
minimum flag made that term the sole barrier for every type, so every
drop arm now shows under it), the Follow_Up minimum reverted to the
44-octet shape fails 9, both TLV header arms removed fails 13, the
tlvType compared alone fails 10, the messageLength arm removed fails
18 (the `no bank write` checks that pin it ahead of the first bank
write, plus the per-type arms; the end-of-frame gate still drops the
Follow_Up shapes, so that one is visible to this suite alone), the
messageLength arm narrowed to Follow_Up fails 16 (the per-type arms;
this suite alone, every engine frame declaring its true length), and
the Follow_Up TLV block applied to Sync as well fails 3 (the 74-byte
padded Sync; the 60-byte one cannot show it, because a poison raised
on a frame's eof byte is not seen by the end-of-frame gate, which
samples bad_r as registered), the Pdelay_Req minimum reverted to the
34-octet header fails 15 (one octet short 9, grouped with Sync 12),
Signaling raised to 54 as well fails 5 (its header-only controls: the
suite pins that minimum too), and the messageLength arm narrowed to
Follow_Up and Pdelay_Req fails 16.

This suite is what caught the three field-straddle bugs (announce
currentUtcOffset outside the 8-byte accumulator window, the stepsRemoved
slice, the un-gated Follow_Up TLV) and the end-of-frame race that the
one-cycle finalization now closes — the reason last-byte field writes and
the hop-count word cannot fight for the single bank lane.

`make` — exit 0 = PASS.
