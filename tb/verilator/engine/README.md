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
| 1, 3, 6, 7 | Table 11-7 `controlField`: Sync = 0, Follow_Up = 2, Announce and every Pdelay message = 5 |
| 1, 2 | asCapable is NOT set after one good exchange (4.2.6.2.4) |
| 1a | a Pdelay_Req sourced from OUR OWN clockIdentity draws no Pdelay_Resp and no frame at all, moves no counter and no flag, and cannot steal the egress timestamp the boot request is waiting for: phase 2's published delay is the oracle, 600 ns if it was ignored and 500,600 ns if it was answered (IEEE 1588-2008 9.5.2.2; Figure 11-9 carries no such condition, #26) |
| 1b | a Follow_Up for the boot request (sequence 0) ahead of any Resp, sourced from the zero identity a never-armed pairing holds, is ignored: "armed with sequence 0" is not "nothing armed" (11.2.15.3) |
| 1c | peer Pdelay_Reqs arriving 10, 2,000 and 200,000 cycles into our own request's outstanding interval each draw a Pdelay_Resp and none takes the egress timestamp our request is waiting for. A fourth request differs only in the high byte of sequenceId. A fifth reuses our sequenceId zero exactly: its response stamp arrives first and still builds its own Resp_FU; that unclaimed type-A frame's later stamp cannot consume our type-2 request claim; the true request stamp then preserves phase 2's 600 ns delay. The full `{messageType, sequenceId}` identity, not event order or sequence alone, is the oracle (#28) |
| 7 | while grandmaster, a Sync claim and a peer Pdelay_Resp claim carry the same sequenceId. The response stamp arrives first and builds the mandatory Resp_FU with its own timestamp, not a Sync Follow_Up; the unclaimed Resp_FU stamp is ignored; the Sync stamp still builds its own Follow_Up with its own preciseOriginTimestamp (802.1AS-2011 11.2.14.2.3 and 11.2.16, #28) |
| 2b | a Pdelay_Resp and its Follow_Up sourced from OUR OWN clockIdentity, answering the outstanding request with our requestingPortIdentity and a delay under the threshold, are ignored: the published delay and asCapable both hold, and the exchange that would have been the second never happened (IEEE 1588-2008 9.5.2.2, 802.1AS-2011 Figure 11-8, #23) |
| 3a | a requester whose clockIdentity differs from ours in only its low half, and one differing in only its high half, are both neighbours and are both answered with their own sequence, their own requestingPortIdentity and their Resp_FU: the refusal above is 64 bits wide, and a compare narrowed to either half refuses one of them (#26) |
| 3b | a foreign-domain Pdelay_Req (domain 0x10) draws no Pdelay_Resp and counts one drop; a domain-0 request right after it is answered with its own sequence and its Resp_FU |
| 3c | a header-only Pdelay_Req (messageLength 34 in a 48-byte frame) and a declared 54 cut at 53 octets draw no Pdelay_Resp and count one drop each; the complete request right after them is answered with its own sequence and its Resp_FU (Table 11-11, #12) |
| 3d | an unlisted messageType (0x1, 0xD, 0xF) with a valid header draws no frame at all over a proven-quiet window and counts one drop each, and the flags do not move: 802.1AS-2011 Tables 10-5 and 11-3 name the seven types a gPTP port carries and the NOTE under Table 11-3 says the others are not used in this standard, IEEE 1588-2008 Table 19 assigning three of them to Delay_Req, Delay_Resp and Management (#22) |
| 4 | it IS set at the second; pdelay matches the nrr-corrected model |
| 5 | become-master waits for asCapable |
| 7b | 802.1AS-2011 11.2.15.3 (Figure 11-8): a Pdelay_Resp_Follow_Up pairs with ONE Pdelay_Resp for the outstanding request. Before any Resp, with a stale sequenceId (the parent campaign's 0xEEEE probe), behind a stale-sequence Resp (0xEEEE, and the outstanding sequence with its high byte flipped), from another responder, duplicated, or for a superseded request it leaves pdelay and asCapable unmoved (a wrongly consumed one would publish -400 ns and clear asCapable); the paired Follow_Up and the next exchange compute the model value |
| 8b | a BETTER Announce in a foreign domain never reaches BTCA: GM, parent, flags and the raw published vector hold and the drop is counted (802.1AS-2011 8.1, IEEE 1588-2008 9.5.1) |
| 8c..8m | 802.1AS-2011 10.3.10.2.1 qualifyAnnounce: a priority1-1 Announce from our own clockIdentity (a), with stepsRemoved 255, 0x0100 or 0xFFFF (b: the 16-bit field, not its low byte), or with our identity in its path trace (c: the second hop, the eighth retained hop, the tenth of twelve beyond the public cap, the FIRST hop of two with a bridge behind us, the only hop) is refused ahead of every write: GM, parent, flags and the raw published vector hold. The twelve-hop case is the first nonzero PathTrace after reset and proves the deferred count belongs to that event while the parser's complete-wire loop bit sees identities beyond retained word 23. The first-hop shape is the ordinary loop of our own Announce returned through a bridge |
| 8h, 8k, 8l, 8n | controls adopt the maximum 179-identity PathTrace allowed by the declared untagged Ethernet payload, proving every identity was checked before the first eight publish; two smaller valid sequences whose head equals GM while their source and a later hop differ from ours in one 32-bit half only prove the compares are 64 bits wide; a fixed competing Announce without PathTrace adopts with honest raw count zero and all tails zero (10.3.10.2.1(d), 10.3.13.2.1(f)); each announcer's degrade hands mastership straight back (10.3.5) |
| 9 | adoption publishes a four-entry canonical path; unrelated worse Announces with and without PathTrace each reach `they_win` and re-commit without replacing selected path A with B or raw zero. A twelve-entry refresh clamps to eight, a three-entry refresh clears inactive tails, then an exact eight-entry refill makes the fixed no-PathTrace transition prove all seven tails clear beside raw count zero. A complete unknown-only suffix also publishes raw zero, while an unknown TLV before a valid PathTrace is skipped and the later path becomes selected. TLV-shaped physical padding remains count zero. A partial generic header, odd unknown length, TLV crossing messageLength, physical truncation, duplicate PathTrace, length 9, N != stepsRemoved+1 and a head unequal to GM each produce no commit and one parser drop. Behind a stalled response, same-sequence A owns the frozen context while literal EOF/SOF-adjacent B/C are counted drops; both nonempty and raw-empty A snapshots remain coherent and the first post-release C is accepted |
| 10, 12 | sync-ok rises on a completed pair, falls at 375 ms (Table 4.2) |
| 11 | a Follow_Up later than 125 ms pairs with nothing (Table 4.2) |
| 11b | a Sync/Follow_Up pair in a foreign domain never steers: offset, PHC writes and flags hold, both drops are counted, and the foreign Sync leaves no pending slot for a domain-0 Follow_Up |
| 11c | a Follow_Up without its information TLV never steers (Table 11-9: 76 octets, the TLV of 11.4.4.3 a field of the message): the 44-octet shape, a declared 76 cut at 75 octets and a 76-octet frame with tlvType 0x0008 each count one drop and leave the offset, the PHC writes and the flags unmoved, none consumes the pending Sync, and the complete Follow_Up that follows pairs with it and re-bases the PHC |
| 11d | a Sync padded to the 60-byte Ethernet minimum, and one padded to 74 bytes, are accepted with no drop, and their Follow_Ups pair and re-base the PHC (IEEE 1588-2008 13.3.2.4 NOTE: octets past messageLength are padding) |
| 10, 13 | offsets beyond 20 us re-base the modeled PHC by their exact negation, and the step's addend write is the bare surviving integrator |
| 14 | a +5 us offset SLEWS: the PI addend equals the integer mirror |
| 15 | closed loop: a +140 ppm master (above half the clamp on purpose) locks under 200 ns after one re-base, the addend carrying its rate |
| 16, 17 | a Follow_Up pairs only with its Sync's sequenceId AND sourcePortIdentity (11.4.4) |
| 18 | gmId tie -> stepsRemoved (shorter wins, longer loses) -> sourcePortIdentity tiebreak switches the parent with NO sync-ok flicker |
| 18b | a delayed dispatch reads the complete frozen context its event names: a worse announce beside a parent Sync REJECTS, never a wrongful takeover |
| 19 | a parent degrading below us yields mastership IMMEDIATELY (10.3.5) |
| 20 | every two-step Sync carries ten zero reserved bytes (Table 11-8); phase 7 proves its Follow_Up still carries the live egress timestamp |
| 21 | an asCapable fall stops sync consumption and steering; recovery resumes it |
| 21b | become resets the best record: no ghost GM outlives the receipt timeout |
| 21c | the priority vector outranks the identity in the compare order |
| 21d | the same delayed shape with a BETTER announce ADOPTS from its frozen context; no live-bank sequence guard is part of the proof |
| 22 | negative pdelay in [-80, 0) keeps asCapable (4.2.6.2.7) |
| 23 | over 800 ns clears it (neighborPropDelayThresh, 4.2.6.1.1) |
| 24 | recovery needs two good exchanges again |
| 25 | the FOURTH lost response clears it (802.1AS-2011 11.2.12.4) |
| 26 | a ratio window wider than 2^32 ns is skipped, not divided stale |
| 26b | a completed exchange cannot be completed again (Figure 11-8 as corrected by Cor2-2015): with asCapable down and one exchange in, the identical Resp + Follow_Up pair replayed is not a second exchange (asCapable holds down, Milan 4.2.6.2.4) and a replay with t4 skewed +2 us cannot move the published delay |
| 27 | the Milan 4.2.6.2.5 cease rule: three multi-identity intervals stop Pdelay_Req and drop asCapable, the cadence countdown resumes them, the ladder re-earns; SAME-identity duplicates are not a storm; replayed forged response pairs (t3 skewed) can neither climb nor publish mid-cease |
| 27b | a second identity answering AFTER the first responder's Follow_Up (the exchange already completed, so its Pdelay_Resp takes the handler's post-completion path) still counts for the Milan 4.2.6.2.5 cease: asCapable falls, no requests over the window, the countdown resumes them, the ladder re-earns |
| boot, 28 | before ROM init installs the local clockIdentity, a first-event nine-hop self path is parser-refused. After warm reset, a valid better no-PathTrace Announce first commits the expected GM/parent with count zero and seven zero tails, with no mixed snapshot in that selected epoch; the write-snooped identity remains valid and a later ninth-hop self loop is accepted by the parser but refused by qualification. The cease countdown still lives in reset-surviving scratch and boot re-arms the cadence |
| 29 | a chasing Follow_Up cannot steal the Resp's arrival stamp: the ingress timestamp stages at sof and commits at EOF into the bank the frame occupies (the parent fabric bench's finding -- a single register loses to back-to-back delivery) |
| 30 | a zero-gap 1-byte runt cannot poison the predecessor's stamp: the commit is length-qualified (>= 3 bytes -- no event-carrying frame is shorter, and a runt's eof can land before the predecessor's bank flip) |
| 31 | warm reset withholds the boundary return of an outstanding Pdelay_Req, Pdelay_Resp and master Sync in turn. The two reset-surviving scratch claims read empty after reset, a fresh response pair completes, and the hardware bootstrap re-arms both request and Announce-receipt timers so master Sync cadence returns without a bitstream reload (#41) |
| 32 | `tx_ready_i` is low at the first byte, in the body, for one cycle and for many cycles; capture advances only on valid/ready. Two different peer requests enter before response 1's boundary stamp, response 2 waits while two accepted Signaling frames reuse both ping-pong banks, and each response still carries its exact ingress `requestReceiptTimestamp` and gets the Follow_Up carrying its own requester identity, port and exact egress stamp with zero event drops (#40, #33) |

The same 656-check workload runs against three generated images: the shipping
image, `S_MYSEQ` seeded to `0x200000`, and `S_SSEQ` seeded to `0x10000`. The
last image reaches Sync 65,536 immediately; without the 16-bit bound, its
first type-0 return cannot match the aliased type-1 claim and the cadence
stops (#39).

Every planted mutation turns the run red. The historical enumeration below
has an inherited one-entry headline/prose shortfall: the headline moved from
thirty-one to thirty-six and then to forty on rounds that each named three new
mutations, so it has run ahead of the prose since before the field campaign.
The arithmetic was exact from forty-one through the pre-PathTrace rounds; the
later PathTrace and TLV-walker controls are tabulated separately below. The
list: (the own-source rule removed, its
identity compare narrowed to 32 bits, the stepsRemoved bound off by one
in either direction, its compare narrowed to a byte, a dead path-trace
compare, the hop compare narrowed to 32 bits, the hop read from the next
bank word, the hop-count gate removed, a walk one hop past the count, a
one-hop walk, the state-port base left offset after the walk, a
Pdelay_Resp taken for any sequenceId, its sequence compare narrowed to a
byte, the arm cleared on the Resp itself, a Follow_Up taken with nothing
armed, the armed bit dropped from its compare, the pairing not consumed,
the responder identity not paired, the arm surviving the next request, a
completed exchange armed again, the completed path skipping the identity
bookkeeping, the self-sourced response admitted, its thisClock compare
applied to requestingPortIdentity instead, that compare narrowed to 32
bits, the self-sourced request answered, its own compare narrowed to the
low half and narrowed to the high half, the response's egress-timestamp
claim written into the timer transmitter's cell so the two share one
again, the stamp's sequenceId ignored so the first claim present takes
it, the response leaving no claim at all, the stamp compare narrowed to
the low 8 bits, the claim tag left unbounded so the request counter's
bit 21 reads as the Sync flag, the returned messageType forced to zero,
the type bits removed from both event and claims to restore
sequenceId-only credit, the Sync claim tag left unbounded so counter bit
16 reads as messageType 1, a second Pdelay request dispatched while the
first response claim is live, the timer claim's reset-valid read override
disabled, the responder claim validity held through reset, the warm-reset
Announce-watch bootstrap removed, `tx_ready_i` ignored, the shared TX control value,
ladder trigger, both pdelay
thresholds, all three timeout values, a dead ratio divide, a deleted
staleness guard, the fall-at-three lost count, a dropped adopt-side
sync void, a dead step threshold, both servo sign errors, a dead
integrator, a halved integrator clamp, a step that loses the rate
estimate, both pairing bypasses, an inverted steps compare, a dropped
parent update, a non-zero Sync reserved body, a reverted consumption gate, a
removed dispatch seq guard, a dropped become-side best reset, a
swapped vector/identity compare order, a 30-interval cease threshold,
duplicates counted as a storm, a dead resume countdown, a removed
mid-cease completion gate, and twelve RTL mutations: the read bank
tied to the write bank, the ingress stamp reverted to a single
register, the runt length qualification removed, the parser's
domainNumber drop arm removed, its compare narrowed to the low nibble,
the end-of-frame gate's bad_r term dropped so a refused frame still
dispatches, the Follow_Up minimum reverted to the 44-octet
header-and-timestamp shape, the information TLV header arms removed,
the Follow_Up TLV block applied to Sync as well, the Pdelay_Req
minimum reverted to the 34-octet header, and the unlisted messageType
arm removed, so a frame no handler claims dispatches into the timer
program, the queued Pdelay request snapshot bypassed so two accepted
Signaling chasers erase its handler input, only that snapshot's ingress
timestamp bypassed back to the live bank, inactive public PathTrace tails left
unchanged on a shorter selection, later frames allowed to overwrite the owned
Announce context, and the owned-context Announce admission/drop gate disabled).

The eight new negative controls fail independently. The first seven recorded
results predate the two permanent `requestReceiptTimestamp` assertions:
removing the Sync bound gives 360 PASS / 28 FAIL of 388 checks reached in the
high-Sync image; letting request 2 pass a live response owner gives 397 / 3 of
400; bypassing request 2's whole event snapshot after the two accepted chasers
gives 399 / 2 of 401; exposing the stale timer claim after reset gives 400 / 8
of 408; retaining the stale response-owner validity gives 377 / 16 of 393;
omitting the warm slot-2 bootstrap gives 403 / 3 of 406; and advancing the
serializer while ready is low gives 384 / 9 of 393. With the new assertions,
bypassing only request 2's saved ingress timestamp gives 407 / 1 of 408 and
names the corrupted `requestReceiptTimestamp`. The differing reached totals
are expected: a missing cadence or response removes later frame-dependent
assertions; every mutation returns non-zero and names its first violated
invariant.

The original three PathTrace/context mutations remain independently red on
their 471-check baseline: removing inactive-tail zeroing gives 465 PASS / 6
FAIL; allowing later frames to overwrite the frozen context gives 466 / 5;
disabling the Announce admission/drop gate gives 469 / 2. Seven strict
present-TLV controls on the pre-adjudication 514-check workload remove, in
turn, deferred owner capture (513 / 1), either declared-boundary guard set
(508 / 6 each), lengthField alignment (508 / 6), all-hop self comparison
(437 / 77), N = stepsRemoved+1 (508 / 6), and cold local-clock validity
(513 / 1).

The current generic-walker controls are independently red on the 268-check
parser workload: stopping after the first nonzero TLV value reaches 255 PASS /
13 FAIL, changing exact-fit containment from `>` to `>=` reaches 234 / 34,
and removing singular-PathTrace rejection reaches 259 / 9. On the 656-check
engine workload, removing inactive-tail zeroing first names five stale-tail
failures in the count-eight-to-short transition and then terminates at the
independent `raw empty ... nonzero tail` RTL assertion on the next count-zero
COMMIT. The production form was restored before the exact-head merge bar and
OOC measurement.

## Engine input-drive ledger

| input | engine-bench drive | why |
|---|---|---|
| `clk_i` | live | toggled every modeled cycle |
| `rst_n` | live | cold reset plus warm reset during cease and with outstanding request, response and Sync ownership |
| `rx_valid_i`, `rx_data_i`, `rx_sof_i`, `rx_eof_i` | live | byte-level frames, zero-gap successors, truncations and runts |
| `rx_err_i` | constant 0 here, by design | the parent supplies only FCS-clean frames and also ties it low; the parser suite drives the error arm directly (#35 records the remaining mid-frame behavior) |
| `rx_ts_i` | live | independently selected ingress timestamp per injected frame |
| `tx_ready_i` | live | phase 32 drives first-beat, body, one-cycle and long stalls; capture advances only on a valid/ready handshake (#33) |
| `txts_valid_i`, `txts_ns_i`, `txts_seq_i`, `txts_type_i` | live | automatic and deliberately reordered/withheld returns carry the selected frame's exact stamp and complete header tag; #31 bounds the remaining one-entry behavior |

There are no other engine inputs. Constant `rx_err_i` is therefore an explicit
parent-interface contract with direct lower-level coverage, not an accidental
blind spot; every remaining functional input changes in this workload and is
read by logic the DUT executes.

```sh
make        # regenerates gptp_ucode.hex from hdl/ucode/, builds, runs
```

Exit 0 = PASS; the tally line is the record.
