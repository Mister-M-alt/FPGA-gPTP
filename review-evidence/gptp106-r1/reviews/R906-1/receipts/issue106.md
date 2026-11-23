Found by the in-house qualification on milan-fpga's merged split image (dev-soft-core), 8x8/1if. The same failure was on the 11-15 1x1/1if image, so it predates the flip. Follow-up to #100 item 3.

**Observed.** The test machine announces a better grandmaster with Announces exactly 3.0 s apart, the timeout instant of a 1 s announce interval. In 3 of 6 and 4 of 7 gaps (3.000-3.010 s), the capture had no required master announcement from the board after the instant. When an Announce lands on the board's own timeout instant (gaps of 3.000-3.001 s), it failed in 7 of 7, in both passes.

Seen once in two passes: on regaining the grandmaster role, the board sent one Announce at once and then nothing for 3.0 s. The sequence numbers are continuous, so this is not capture loss.

**Clauses.** Milan v1.2 4.2.6.2.3 and Table 4.2; IEEE 802.1AS-2011 Figures 10-13 and 10-15 (announceReceiptTimeout). The project rule is that the timeout wins at the instant, graded on the wire.

**Where to look (cause not isolated).**
- `hdl/top/KL_gptp_engine.sv` (the receipt watch, and expiry before receive);
- `hdl/ucode/gen_gptp_ucode.py` (becoming grandmaster).

**Acceptance.**
- In both scenarios, the board's master announcement appears after the timeout instant in every gap.
- On regaining the grandmaster role, Announces go out 1 s apart from the first.
- Tests check the wire output, not only the internal role counter.

