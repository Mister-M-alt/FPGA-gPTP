<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Glossary

These terms carry one meaning across every current guide.

Clause numbers cite IEEE 802.1AS-2011 unless marked otherwise.

Cor1 and Cor2 are that edition's two corrigenda.

Milan means the Milan v1.2 specification, chapter 4.

## Protocol terms

| Term | Meaning | Reference |
|---|---|---|
| asCapable | Port verdict that peer-delay exchanges with the neighbour work | 10.2.4.1, 11.2.2 |
| BTCA | Best master selection over received priority vectors | 10.3, Milan 4.2.6.1 |
| Cease | Pdelay_Req pause after repeated multiple responders | Milan 4.2.6.2.5 |
| Follow_Up companion | Two-step message carrying the precise transmit time | 11.4.3 |
| gmPresent | True when the grandmaster's priority1 is below 255 | 10.3.12.1.4 g) |
| Grandmaster | Clock whose time the whole domain follows | 10.3 |
| pathTrace | Clock identities from grandmaster to this system | 10.3.8.21 |
| Pdelay exchange | Request, response and response Follow_Up for link delay | 11.2.15, 11.2.16 |
| portEnabled | MAC operational and administratively enabled, as one level | 10.2.4.11 |
| priority1 | First announced selection field; lower wins | 8.6.2.1 |
| syncReceiptTimeout | Interval after which a silent Sync source ages | 10.6.3.1, Milan Table 4.2 |
| thisClock | Clock identity of this time-aware system | 10.2.3.22 |
| Usable Sync pair | A Sync with its own matching Follow_Up | 11.2.13 |

## Engine terms

| Term | Meaning | Where |
|---|---|---|
| Claim | Scratch record of an egress timestamp still owed | [HDL guide](HDL_DEVELOPER.md#egress-result-ownership) |
| Cold start | FPGA configuration, which also clears scratch | [Integration guide](INTEGRATION.md#clock-and-reset) |
| Commit | `pub_commit_o` pulse exposing one staged publication | [Integration guide](INTEGRATION.md#publication) |
| Credit | `tx_credit_i` level permitting initiating transmissions | [Integration guide](INTEGRATION.md#transmit-admission-credit) |
| Image | Generated microcode ROM file for one configuration | [Integration guide](INTEGRATION.md#microcode-configuration) |
| Initiating beat | A Pdelay_Req, Sync or Announce transmission | [Integration guide](INTEGRATION.md#transmit-admission-credit) |
| Leg | Shared microcode routine packed into a ROM gap | [Manager guide](MANAGER.md#current-rom-budget) |
| Link-up pair | First Sync pair after asCapable rises | [Integration guide](INTEGRATION.md#link-up) |
| Locked | Servo state after any consumed Sync pair | [Integration guide](INTEGRATION.md#locked) |
| NOTEN | Microcode leg run on each portEnabled edge | [HDL guide](HDL_DEVELOPER.md#port-enable) |
| Option-off | Parent build with `GPTP_PLANE_EN_P=0`; verification only | [Integration guide](INTEGRATION.md#option-off-behavior) |
| PHC | Parent-owned hardware clock this engine steers | [Integration guide](INTEGRATION.md#phc-control) |
| Scratch | Sixty-four protocol words that survive warm reset | [HDL guide](HDL_DEVELOPER.md#state-regions) |
| Slew | Offset correction applied through the rate trim | [Integration guide](INTEGRATION.md#slew-active-level) |
| Step | One phase jump written through `phc_step_o` | [Integration guide](INTEGRATION.md#pulse-semantics) |
| sync-ok | Publication flags bit 3, the synchronization verdict | [Integration guide](INTEGRATION.md#grandmaster-synchronization) |
| Warm reset | `rst_n` pulse without FPGA reconfiguration | [Integration guide](INTEGRATION.md#clock-and-reset) |

Values live in the [protocol constants](INTEGRATION.md#protocol-constants) table.
