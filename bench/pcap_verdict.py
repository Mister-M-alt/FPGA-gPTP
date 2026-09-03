#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Wire-truth verdict from an in-line TAP capture.

Reads a pcap or pcapng (nanosecond-aware), takes every EtherType 0x88F7
frame, decodes it through tsn-gen's packet_gen against the 802.1AS
YAMLs and enforces every field the standard pins — the same independent
judge as tb/tsngen, now applied to REAL wire bytes. On top of the
per-frame bit verdict it derives what only a TAP timebase can show:

  * cadences from capture timestamps: Sync ~125 ms, Announce ~1 s,
    Pdelay ~1 s (Milan v1.2 Table 4.1), FU-after-Sync gap, and the
    pdelay response turnaround against the Milan 15 ms allowance
  * role flaps: mastership windows reconstructed from who announces
  * timestamp calibration deltas (the MII latency round's input):
      - our (T3-T2) from Pdelay_Resp/_FU fields  vs  the TAP's
        req->resp wire delta: the difference is our RX+TX timestamp
        point latency sum (plus 2x wire, minus nothing else)
      - our FU preciseOrigin deltas between consecutive Syncs  vs  the
        TAP's Sync-to-Sync deltas: our PHC rate against the TAP clock

Reads plain captures and the TAP's live-mode captures transparently.
The TAP's live mode prepends a 28-byte header to every frame (measured
on the bench, 2026-08-15): u32 type, u32 length, u32 TAP port (2/3 —
the direction), then a hardware timestamp as TWO LE u32 words stored
high-first — ts_ns = (u32le@12 << 32) | u32le@16, nanosecond LSB —
then the frame. Those timestamps resolved the Arty's 1 s cadence with
a 4 ns standard deviation, so when they are present they replace the
host pcap timestamps for every derived measurement.

Usage: pcap_verdict.py <capture.pcap[ng]> [--our-mac 02A1B2C3D4E5]
Needs a tsn-gen checkout (TSAGEN_DIR, default ~/prjs/tsn-gen).
"""

import argparse
import json
import os
import statistics
import struct
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple


def _tsagen_root() -> Path | None:
    """The tsn-gen checkout to decode against, or None when there is none.

    TSAGEN_DIR is taken as given even when it names nothing, so a typo skips
    with the reason rather than silently decoding against whichever default
    checkout happens to exist.
    """
    named = os.environ.get("TSAGEN_DIR", "")
    if named:
        return Path(named)
    for cand in ("~/prjs/tsn-gen", "~/tsn-gen"):
        root = Path(cand).expanduser()
        if root.is_dir():
            return root
    return None


TSAGEN = _tsagen_root()
PG = TSAGEN / "build/traffic-gen/packet_gen" if TSAGEN else None
YD = TSAGEN / "protocols/data_link/ptp" if TSAGEN else None

IFACE = {
    0x0: "as_sync::AS_SYNC::AS_SYNC_IF",
    0x2: "as_pdelay_req::AS_PDELAY_REQ::AS_PDELAY_REQ_IF",
    0x3: "as_pdelay_resp::AS_PDELAY_RESP::AS_PDELAY_RESP_IF",
    0x8: "as_follow_up::AS_FOLLOW_UP::AS_FOLLOW_UP_IF",
    0xA: "as_pdelay_resp_fu::AS_PDELAY_RESP_FU::AS_PDELAY_RESP_FU_IF",
    0xB: "as_announce::AS_ANNOUNCE::AS_ANNOUNCE_PT1_IF",
    (0xB, 64): "as_announce::AS_ANNOUNCE::AS_ANNOUNCE_IF",
}
MSG_NAME = {0x0: "sync", 0x2: "pdreq", 0x3: "pdresp", 0x8: "fu",
            0xA: "pdrfu", 0xB: "announce", 0xC: "signaling"}

#: messageType -> the tsn-gen service whose YAML `expected` values govern it.
#: A type absent here carries no pins, so only its destination address is
#: enforced.
SVC_OF = {0x0: "as_sync", 0x2: "as_pdelay_req", 0x3: "as_pdelay_resp",
          0x8: "as_follow_up", 0xA: "as_pdelay_resp_fu", 0xB: "as_announce"}

#: One decoded capture frame: TAP timestamp, source MAC as lowercase hex,
#: messageType, and the fields packet_gen read out of the PDU.
Frame = tuple[int, str, int, dict[str, int]]


class Judged(NamedTuple):
    """One pass over a capture, before anything is derived from the timebase."""

    #: every 802.1AS frame that decoded, in capture order
    frames: list[Frame]
    #: pin comparisons made, the denominator of the verdict
    checks: int
    #: comparisons a frame OUR node transmitted lost
    fails: int
    #: frames of some other EtherType, reported but never judged
    others: int
    #: frames that carried a TAP hardware timestamp instead of a host one
    hw_used: int


# ---------------------------------------------------------------- capture I/O
def read_pcap(path: Path) -> Iterator[tuple[int, bytes]]:
    """Yield (ts_ns, frame_bytes) from classic pcap or pcapng."""
    data = path.read_bytes()
    magic = data[:4]
    if magic in (b"\xa1\xb2\xc3\xd4", b"\xd4\xc3\xb2\xa1",
                 b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1"):
        be = magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d")
        ns = magic in (b"\xa1\xb2\x3c\x4d", b"\x4d\x3c\xb2\xa1")
        e = ">" if be else "<"
        off = 24
        while off + 16 <= len(data):
            sec, sub, caplen, _ = struct.unpack_from(e + "IIII", data, off)
            off += 16
            frame = data[off:off + caplen]
            off += caplen
            yield sec * 10**9 + sub * (1 if ns else 1000), frame
        return
    if magic == b"\x0a\x0d\x0d\x0a":
        # pcapng: walk blocks, honor per-interface if_tsresol (option 9)
        endian = "<"
        if data[8:12] == b"\x4d\x3c\x2b\x1a":
            endian = ">"
        tsres = []                              # per-interface divisor to ns
        off = 0
        while off + 12 <= len(data):
            btype, blen = struct.unpack_from(endian + "II", data, off)
            if blen < 12 or off + blen > len(data):
                break
            body = data[off + 8:off + blen - 4]
            if btype == 0x00000001:             # IDB
                resol = 6                       # default 10^-6
                o = 8
                while o + 4 <= len(body):
                    ocode, olen = struct.unpack_from(endian + "HH", body, o)
                    o += 4
                    if ocode == 9 and olen >= 1:
                        resol = body[o]
                    o += (olen + 3) & ~3
                    if ocode == 0:
                        break
                if resol & 0x80:
                    div = 10**9 / (2 ** (resol & 0x7F))
                    tsres.append(("pow2", 2 ** (resol & 0x7F)))
                else:
                    tsres.append(("pow10", 10 ** resol))
            elif btype == 0x00000006:           # EPB
                iface, tsh, tsl, caplen, _ = struct.unpack_from(
                    endian + "IIIII", body, 0)
                ts = (tsh << 32) | tsl
                kind, res = tsres[iface] if iface < len(tsres) \
                    else ("pow10", 10**6)
                ts_ns = ts * 10**9 // res
                yield ts_ns, body[20:20 + caplen]
            off += blen
        return
    raise SystemExit(f"unrecognized capture format: {magic.hex()}")


# ------------------------------------------------------------------ decoding
def pg_decode(mtype: int, mlen: int, hexstr: str) -> dict[str, int] | None:
    """The fields packet_gen reads out of one PTP PDU, or None if it refuses.

    None is a verdict on the frame, not an error here: it means the
    messageType has no interface in IFACE, or the decoder could not parse
    the PDU at the length its own header claims. Both are counted as a
    failed check by the caller rather than skipped.
    """
    key = (0xB, 64) if (mtype == 0xB and mlen == 64) else mtype
    iface = IFACE.get(key)
    if iface is None:
        return None
    # `str(...)` because these two cross into an argv, where a Path would be
    # stringified anyway and by a rule this file does not own.
    r = subprocess.run([str(PG), "--yaml-dir", str(YD), "--interface", iface,
                        "--hex", hexstr], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout.splitlines()[0])["fields"]


def yaml_pins() -> dict[str, dict[str, int]]:
    """Every field value the 802.1AS YAMLs pin, as {service: {field: value}}.

    These are tsn-gen's own `expected: value` entries, so what the capture is
    judged against is the protocol description the independent decoder reads,
    never a second copy of the clause numbers kept here.
    """
    import yaml
    if YD is None:
        raise SystemExit("no tsn-gen checkout: there are no YAML pins to read")
    pins: dict[str, dict[str, int]] = {}
    for doc_path in YD.glob("*.yaml"):
        doc = yaml.safe_load(doc_path.read_text())
        for v in doc.get("vars", []):
            exp = v.get("expected") or {}
            if "value" in exp:
                pins.setdefault(doc["service"], {})[v["var"]] = exp["value"]
    return pins


def deframe(ts_ns: int, raw: bytes) -> tuple[int, bytes, int | None]:
    """Strip a TAP live-mode header when present; returns
    (best_ts_ns, frame, port_or_None). Detection is STRUCTURAL — type
    word 6 and the duplicated length field — never a payload-byte
    test: the hardware timestamp at offset 12 marches through every
    value, including 0x88F7 (which once made 78 of our own Sync frames
    decode as garbage when the old heuristic keyed on the EtherType
    position)."""
    if len(raw) >= 42 and raw[0:4] == b"\x06\x00\x00\x00" \
            and raw[20:24] == raw[24:28] \
            and struct.unpack_from("<I", raw, 20)[0] + 24 <= len(raw):
        hi = struct.unpack_from("<I", raw, 12)[0]
        lo = struct.unpack_from("<I", raw, 16)[0]
        port = struct.unpack_from("<I", raw, 8)[0]
        return (hi << 32) | lo, raw[28:], port
    return ts_ns, raw, None


# ------------------------------------------------------------- the pin verdict
def judge_frames(capture: Path, our_mac: str,
                 pins: dict[str, dict[str, int]]) -> Judged:
    """Decode every frame in the capture and enforce the YAML pins on ours.

    One line is printed per deviation as it is found: `FAIL` for a frame OUR
    node transmitted, `note` for a peer's, because a peer that disagrees with
    the standard is evidence about the peer and not a defect in this design.
    The destination address is the one field pinned for everybody. A frame
    the decoder refuses is a failed check, never a skipped one.
    """
    frames: list[Frame] = []
    checks = fails = others = hw_used = 0
    for host_ts, captured in read_pcap(capture):
        ts, raw, port = deframe(host_ts, captured)
        hw_used += port is not None
        if len(raw) < 48 or raw[12:14] != b"\x88\xf7":
            others += 1 if len(raw) >= 14 else 0
            continue
        src = raw[6:12].hex()
        mtype = raw[14] & 0xF
        mlen = (raw[16] << 8) | raw[17]
        pdu = raw[14:14 + mlen] if 14 + mlen <= len(raw) else raw[14:]
        fields = pg_decode(mtype, mlen, pdu.hex())
        tag = f"{ts} {MSG_NAME.get(mtype, hex(mtype))} from " \
              f"{'US ' if src == our_mac else 'PEER'}"
        if fields is None:
            fails += 1
            checks += 1
            print(f"FAIL {tag}: undecodable ({mlen}B)")
            continue
        for name, pin in pins.get(SVC_OF.get(mtype, ""), {}).items():
            if name.startswith("message_length") and fields.get(name) != mlen:
                continue
            if name in fields:
                checks += 1
                if fields[name] != pin:
                    if src == our_mac:
                        fails += 1
                        print(f"FAIL {tag}: {name}={fields[name]} pin={pin}")
                    else:
                        print(f"note {tag}: peer {name}={fields[name]}"
                              f" pin={pin}")
        # eth destination is pinned for everyone
        checks += 1
        if raw[0:6].hex() != "0180c200000e":
            fails += 1
            print(f"FAIL {tag}: DA {raw[0:6].hex()}")
        frames.append((ts, src, mtype, fields))
    return Judged(frames, checks, fails, others, hw_used)


# ------------------------------------------------ what only a TAP timebase says
def from_mac(frames: list[Frame], mtype: int, our_mac: str,
             sent_by_us: bool) -> list[tuple[int, dict[str, int]]]:
    """The (timestamp, fields) of one messageType, ours or everyone else's."""
    return [(ts, f) for ts, src, m, f in frames
            if m == mtype and (src == our_mac) == sent_by_us]


def cadence(name: str, lst: list[tuple[int, dict[str, int]]],
            expect_ms: float) -> None:
    """Print the interval spread between consecutive frames of one kind.

    Prints nothing below three frames, which cannot show a spread, and drops
    any gap beyond four times the expected one: those are the silences of a
    role flap, not an interval this port chose.
    """
    if len(lst) < 3:
        return
    d = [(b[0] - a[0]) / 1e6 for a, b in zip(lst, lst[1:])]
    d = [x for x in d if x < expect_ms * 4]  # ignore role-flap gaps
    if not d:
        return
    print(f"  {name}: n={len(lst)} interval mean {statistics.mean(d):.3f}"
          f" ms  min {min(d):.3f}  max {max(d):.3f}  (expect"
          f" ~{expect_ms} ms)")


def report_cadences(frames: list[Frame], our_mac: str) -> None:
    """Print every periodic message's transmit interval, ours and the peer's.

    The expectations are Milan v1.2 Table 4.1: Sync every 125 ms, Announce
    and Pdelay_Req every second.
    """
    print("cadences (TAP timebase):")
    cadence("our sync", from_mac(frames, 0x0, our_mac, True), 125)
    cadence("our announce", from_mac(frames, 0xB, our_mac, True), 1000)
    cadence("our pdreq", from_mac(frames, 0x2, our_mac, True), 1000)
    cadence("peer announce", from_mac(frames, 0xB, our_mac, False), 1000)
    cadence("peer pdreq", from_mac(frames, 0x2, our_mac, False), 1000)


def report_sync_pairing(frames: list[Frame], our_mac: str) -> None:
    """Print how far our Follow_Up trails the Sync it carries the origin for.

    Nothing is printed when no Follow_Up matched a Sync by sequenceId, and
    that silence is itself the finding: a two-step master whose pairs do not
    line up publishes an origin for a Sync nobody can attribute.
    """
    sy = {f["sequence_id"]: ts
          for ts, f in from_mac(frames, 0x0, our_mac, True)}
    fu_gap = [(ts - sy[f["sequence_id"]]) / 1e3
              for ts, f in from_mac(frames, 0x8, our_mac, True)
              if f["sequence_id"] in sy]
    if fu_gap:
        print(f"  FU after its sync: mean {statistics.mean(fu_gap):.1f} us"
              f"  max {max(fu_gap):.1f} us  (n={len(fu_gap)})")


def report_pdelay(frames: list[Frame], our_mac: str) -> None:
    """Print our Pdelay turnaround and the timestamp-point latency it implies.

    Two measurements only a TAP timebase can make. The turnaround is the
    peer's request to our response ON THE WIRE, against Milan's 15 ms
    allowance. Subtracting the (T3-T2) our own Pdelay_Resp/_FU fields claim
    leaves the sum of our RX and TX timestamp-point latencies - the number
    the MII latency calibration is after - plus two wire delays.
    """
    reqs = {f["sequence_id"]: ts
            for ts, f in from_mac(frames, 0x2, our_mac, False)}
    turn = []
    resp_t2: dict[int, tuple[int, int]] = {}
    for ts, f in from_mac(frames, 0x3, our_mac, True):
        seq = f["sequence_id"]
        resp_t2[seq] = (ts, f["request_receipt_seconds"] * 10**9
                        + f["request_receipt_ns"])
        if seq in reqs:
            turn.append((ts - reqs[seq]) / 1e6)
    if turn:
        print(f"  our resp turnaround: mean {statistics.mean(turn):.3f} ms"
              f"  max {max(turn):.3f} ms  (Milan allows 15)")
    cal = []
    for ts, f in from_mac(frames, 0xA, our_mac, True):
        seq = f["sequence_id"]
        if seq in resp_t2 and seq in reqs:
            t3 = f["response_origin_seconds"] * 10**9 \
                + f["response_origin_ns"]
            tap_gap = resp_t2[seq][0] - reqs[seq]
            cal.append(tap_gap - (t3 - resp_t2[seq][1]))
    if cal:
        print(f"  timestamp-point latency sum (tap req->resp minus our"
              f" T3-T2): mean {statistics.mean(cal):.0f} ns  spread"
              f" {min(cal)}..{max(cal)} ns  (n={len(cal)})")


def report_phc_rate(frames: list[Frame], our_mac: str) -> None:
    """Print our PHC's frequency error against the TAP clock, in ppm.

    Each consecutive pair of our Follow_Ups gives one interval our own clock
    measured, as the difference of the preciseOriginTimestamps it published,
    and one the TAP measured; the ratio is our rate. Pairs a second or more
    apart are dropped, being role-flap gaps rather than rate evidence.
    """
    fo = [(ts, f["precise_origin_seconds"] * 10**9 + f["precise_origin_ns"])
          for ts, f in from_mac(frames, 0x8, our_mac, True)]
    ppm = [((ob - oa) - (tb - ta)) / (tb - ta) * 1e6
           for (ta, oa), (tb, ob) in zip(fo, fo[1:]) if 0 < tb - ta < 10**9]
    if ppm:
        print(f"  our PHC vs TAP clock: {statistics.mean(ppm):+.2f} ppm"
              f"  (n={len(ppm)})")


def message_counts(frames: list[Frame], our_mac: str,
                   sent_by_us: bool) -> dict[str, int]:
    """How many frames of each message name one side of the link sent."""
    counts: dict[str, int] = {}
    for _, src, mtype, _ in frames:
        if (src == our_mac) == sent_by_us:
            name = MSG_NAME.get(mtype, hex(mtype))
            counts[name] = counts.get(name, 0) + 1
    return counts


def main() -> int:
    """The capture's verdict: 0 when nothing of ours failed, 1 when it did.

    Also 0 when there is no tsn-gen checkout to decode against, because a
    host without the independent decoder cannot judge the wire and must not
    report a pass it did not measure. 1 when the capture holds no 802.1AS
    frame at all, which is a capture that answers nothing.
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--our-mac", default="02A1B2C3D4E5")
    args = ap.parse_args()
    if not (PG and PG.is_file() and YD and YD.is_dir()):
        print("SKIP: tsn-gen checkout/binary not found (set TSAGEN_DIR)")
        return 0
    our_mac = args.our_mac.replace(":", "").lower()
    seen = judge_frames(Path(args.capture), our_mac, yaml_pins())
    if not seen.frames:
        print("no 802.1AS frames in capture")
        return 1

    print(f"\n== capture: {len(seen.frames)} 802.1AS frames, {seen.others}"
          f" other{', TAP hw timestamps' if seen.hw_used else ''} ==")
    for who, sent_by_us in (("US", True), ("PEER", False)):
        print(f"{who}: {message_counts(seen.frames, our_mac, sent_by_us)}")
    report_cadences(seen.frames, our_mac)
    report_sync_pairing(seen.frames, our_mac)
    report_pdelay(seen.frames, our_mac)
    report_phc_rate(seen.frames, our_mac)

    print(f"\n{seen.checks} pin checks: {seen.checks - seen.fails} PASS,"
          f" {seen.fails} FAIL")
    return 1 if seen.fails else 0


if __name__ == "__main__":
    sys.exit(main())
