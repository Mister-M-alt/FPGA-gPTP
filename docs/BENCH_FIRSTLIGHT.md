<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# First light — Arty A7-100T vs STM32, 2026-08-14

The gPTP plane's first exchange with real silicon: `bench/arty/` (no SoC,
no software — MII gaskets + PHC + KL_gptp_engine + a 1 Hz UART truth
line) against a gPTP-enabled STM32 (ST OUI 00:80:E1) on a direct
100BASE-TX cable.

Build: `bench/arty/build.sh` → 3,726 LUT total (engine 2,944), 1.5 BRAM
tiles, WNS +0.375 ns, zero critical warnings, part xc7a100tcsg324-1.
Load: `openFPGALoader -b arty --ftdi-serial 210319AFEED0 bench_arty.bit`;
truth line on the FT2232's channel B at 115200.

## The wire truth (verbatim UART)

~10 s after configuration (auto-negotiation + PHY reset eat the first
seconds), steady state:

```
S=0A G=0280E1FFFE6F14AB P=0280E1FFFE6F14AB F=01 D=000002A3 O=00000000 R=0020 C=0000 Q=0000 E=0000 T=0019
...
S=1F G=0280E1FFFE6F14AB P=0280E1FFFE6F14AB F=01 D=000002AD O=00000000 R=0074 C=0000 Q=0000 E=0000 T=0058
```

| field | meaning | verdict |
|---|---|---|
| G = P = 0280E1FFFE6F14AB | GM + parent adopted from the STM32's real Announce (its MAC as EUI-64) | **announce receive + adopt WORKS** |
| F = 01 | gm_present | held for the whole run |
| D = 0x2A3…0x2B7 | meanLinkDelay 675…695 ns, re-measured every second | **the full four-timestamp Pdelay exchange WORKS both ways**: our Req out, its Resp + Resp_FU in, µcode math right; ±10 ns second-to-second scatter; the absolute value carries the uncompensated PHY/MII ingress+egress latencies |
| R +4/s, C = 0, Q = 0 | its announce (1/s) + pdelay traffic, zero CRC errors, zero parser drops | RX gasket + CRC residue convention correct |
| T +3/s | our Pdelay_Req plus our two-step Resp + Resp_FU answering the STM32's own requests — which it keeps issuing every second | **the STM32 accepts our responder** |
| O = 0 | no Sync/Follow_Up seen (the R rate accounts for announce+pdelay only) | the STM32 is not sending Sync — see open items |

## What this proves

A 2,944-LUT fabric plane with zero software exchanged live 802.1AS with
third-party silicon on first load: both Pdelay roles complete and
accepted, announce adopted, wire-clean CRC in both directions, and a
per-second link-delay measurement. This is the on-silicon validation the
no-DDR3 resource study's gPTP line item needed.

## Open items, honestly

1. **No Sync from the peer.** The STM32 announces and runs pdelay but
   never sends Sync/Follow_Up, so the offset path (proven in the 49-check
   engine suite) has no wire exercise yet. Likely its stack gates Sync on
   its own asCapable evaluation or sync TX is disabled in its config —
   check the ST side. Our path trace / signaling handling is also
   untested on the wire.
2. **Latency compensation is zero.** D carries the full PHY+gasket
   latencies; the parent project's tap-measured ingressLatency discipline
   (AX 1,490 ns / Arty 3,511 ns for its GMII path) has no MII equivalent
   measured yet — calibrate before quoting D as cable delay.
3. **Timestamp point jitter**: the PHC is latched in the sys domain from
   a synchronized SFD toggle (two-flop + edge), so ±1 sys cycle (10 ns)
   plus MII nibble phase (±40 ns) rides every stamp. Good enough for
   first light; the parent's ptp_ts_top capture is the real instrument.
4. **BTCA, asCapable, receipt-timeout state machines of record** are the
   next µcode round (this round adopts the last announcer and never
   qualifies the link) — the 802.1AS-2011 clause 10/11 set, with the
   Milan v1.2 Table 4.1/4.2 profile numbers.
5. The bench answers ANY Pdelay_Req without qualifying the requester,
   and the single TX-pending slot means a colliding cadence drops one
   exchange (by design, counted).
