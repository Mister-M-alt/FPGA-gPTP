#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Kebag Logic
# SPDX-License-Identifier: CERN-OHL-W-2.0
"""Wire-truth verdict from an in-line TAP capture (ProfiShark shape).

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

Reads plain captures and ProfiShark live-mode captures transparently.
The ProfiShark 1G+ prepends a 28-byte header to every frame (measured
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

TSAGEN = os.environ.get("TSAGEN_DIR", "")
if not TSAGEN:
    for cand in ("~/prjs/tsn-gen", "~/tsn-gen"):
        if os.path.isdir(os.path.expanduser(cand)):
            TSAGEN = os.path.expanduser(cand)
            break
PG = os.path.join(TSAGEN, "build/traffic-gen/packet_gen") if TSAGEN else ""
YD = os.path.join(TSAGEN, "protocols/data_link/ptp") if TSAGEN else ""

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


# ---------------------------------------------------------------- capture I/O
def read_pcap(path):
    """Yield (ts_ns, frame_bytes) from classic pcap or pcapng."""
    data = open(path, "rb").read()
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
def pg_decode(mtype, mlen, hexstr):
    key = (0xB, 64) if (mtype == 0xB and mlen == 64) else mtype
    iface = IFACE.get(key)
    if iface is None:
        return None
    r = subprocess.run([PG, "--yaml-dir", YD, "--interface", iface,
                        "--hex", hexstr], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout.splitlines()[0])["fields"]


def yaml_pins():
    import yaml
    pins = {}
    for fn in os.listdir(YD):
        if not fn.endswith(".yaml"):
            continue
        doc = yaml.safe_load(open(os.path.join(YD, fn)))
        for v in doc.get("vars", []):
            exp = v.get("expected") or {}
            if "value" in exp:
                pins.setdefault(doc["service"], {})[v["var"]] = exp["value"]
    return pins


def deframe(ts_ns, raw):
    """Strip a ProfiShark live-mode header when present; returns
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture")
    ap.add_argument("--our-mac", default="02A1B2C3D4E5")
    args = ap.parse_args()
    if not (PG and os.path.isfile(PG) and os.path.isdir(YD)):
        print("SKIP: tsn-gen checkout/binary not found (set TSAGEN_DIR)")
        return 0
    our_mac = args.our_mac.replace(":", "").lower()
    pins = yaml_pins()
    svc_of = {0x0: "as_sync", 0x2: "as_pdelay_req", 0x3: "as_pdelay_resp",
              0x8: "as_follow_up", 0xA: "as_pdelay_resp_fu",
              0xB: "as_announce"}

    frames = []                                  # (ts, src, mtype, fields)
    checks = fails = others = 0
    hw_used = 0
    for ts, raw in read_pcap(args.capture):
        ts, raw, port = deframe(ts, raw)
        hw_used += port is not None
        if len(raw) < 48 or raw[12:14] != b"\x88\xf7":
            others += 1 if len(raw) >= 14 else 0
            continue
        src = raw[6:12].hex()
        mtype = raw[14] & 0xF
        mlen = (raw[16] << 8) | raw[17]
        pdu = raw[14:14 + mlen] if 14 + mlen <= len(raw) else raw[14:]
        f = pg_decode(mtype, mlen, pdu.hex())
        tag = f"{ts} {MSG_NAME.get(mtype, hex(mtype))} from " \
              f"{'US ' if src == our_mac else 'PEER'}"
        if f is None:
            fails += 1
            checks += 1
            print(f"FAIL {tag}: undecodable ({mlen}B)")
            continue
        # enforce the YAML pins on every frame OUR node transmitted;
        # peer deviations are reported but not counted as our failure
        want = pins.get(svc_of.get(mtype, ""), {})
        for name, v in want.items():
            if name.startswith("message_length") and f.get(name) != mlen:
                continue
            if name in f:
                checks += 1
                if f[name] != v:
                    if src == our_mac:
                        fails += 1
                        print(f"FAIL {tag}: {name}={f[name]} pin={v}")
                    else:
                        print(f"note {tag}: peer {name}={f[name]} pin={v}")
        # eth destination is pinned for everyone
        checks += 1
        if raw[0:6].hex() != "0180c200000e":
            fails += 1
            print(f"FAIL {tag}: DA {raw[0:6].hex()}")
        frames.append((ts, src, mtype, f))

    if not frames:
        print("no 802.1AS frames in capture")
        return 1

    def ours(mt):
        return [(ts, f) for ts, s, m, f in frames
                if m == mt and s == our_mac]

    def theirs(mt):
        return [(ts, f) for ts, s, m, f in frames
                if m == mt and s != our_mac]

    def cadence(name, lst, expect_ms):
        if len(lst) < 3:
            return
        d = [(b[0] - a[0]) / 1e6 for a, b in zip(lst, lst[1:])]
        d = [x for x in d if x < expect_ms * 4]  # ignore role-flap gaps
        if not d:
            return
        print(f"  {name}: n={len(lst)} interval mean {statistics.mean(d):.3f}"
              f" ms  min {min(d):.3f}  max {max(d):.3f}  (expect"
              f" ~{expect_ms} ms)")

    print(f"\n== capture: {len(frames)} 802.1AS frames, {others} other"
          f"{', ProfiShark hw timestamps' if hw_used else ''} ==")
    for who, get in (("US", ours), ("PEER", theirs)):
        counts = {}
        for ts, s, m, f in frames:
            if (s == our_mac) == (who == "US"):
                counts[MSG_NAME.get(m, hex(m))] = \
                    counts.get(MSG_NAME.get(m, hex(m)), 0) + 1
        print(f"{who}: {counts}")
    print("cadences (TAP timebase):")
    cadence("our sync", ours(0x0), 125)
    cadence("our announce", ours(0xB), 1000)
    cadence("our pdreq", ours(0x2), 1000)
    cadence("peer announce", theirs(0xB), 1000)
    cadence("peer pdreq", theirs(0x2), 1000)

    # FU pairing + origin sanity (our two-step)
    sy = {f["sequence_id"]: ts for ts, f in ours(0x0)}
    fu_gap = [(ts - sy[f["sequence_id"]]) / 1e3 for ts, f in ours(0x8)
              if f["sequence_id"] in sy]
    if fu_gap:
        print(f"  FU after its sync: mean {statistics.mean(fu_gap):.1f} us"
              f"  max {max(fu_gap):.1f} us  (n={len(fu_gap)})")

    # pdelay turnaround: peer req -> our resp on the wire, Milan <= 15 ms
    turn = []
    reqs = {f["sequence_id"]: ts for ts, f in theirs(0x2)}
    for ts, f in ours(0x3):
        if f["sequence_id"] in reqs:
            turn.append((ts - reqs[f["sequence_id"]]) / 1e6)
    if turn:
        print(f"  our resp turnaround: mean {statistics.mean(turn):.3f} ms"
              f"  max {max(turn):.3f} ms  (Milan allows 15)")

    # ---- timestamp calibration: our fields vs the TAP timebase ----
    # (T3-T2) from our resp+rfu fields vs the TAP's req->resp gap:
    # tap_gap - (T3-T2) = our RX-stamp-to-wire + wire-to-TX-stamp sum
    cal = []
    resp_t2 = {}
    for ts, f in ours(0x3):
        resp_t2[f["sequence_id"]] = (
            ts, f["request_receipt_seconds"] * 10**9
            + f["request_receipt_ns"])
    for ts, f in ours(0xA):
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

    # our PHC rate vs TAP clock from FU preciseOrigin deltas
    fo = [(ts, f["precise_origin_seconds"] * 10**9 + f["precise_origin_ns"])
          for ts, f in ours(0x8)]
    ppm = []
    for (ta, oa), (tb, ob) in zip(fo, fo[1:]):
        if 0 < tb - ta < 10**9:
            ppm.append(((ob - oa) - (tb - ta)) / (tb - ta) * 1e6)
    if ppm:
        print(f"  our PHC vs TAP clock: {statistics.mean(ppm):+.2f} ppm"
              f"  (n={len(ppm)})")

    print(f"\n{checks} pin checks: {checks - fails} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
