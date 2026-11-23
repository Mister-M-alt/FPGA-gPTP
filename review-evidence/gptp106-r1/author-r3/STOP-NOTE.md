[A831] STOP: #106/#107 (PR #108) at `331e27d` grows the 8x8/1if image by 455 LUT. The no-growth rule needs an owner ruling.

Every other finding is closed, and main is merged (`331e27d`; `hdl/` is unchanged from `a728cc3`). The gates pass at the merged head:
- the engine suite, 2,199 ×3 and 61;
- the mutation arm, 167 of 167 caught;
- the parent consumer gates and ratchets.

The image rule was measured as #818 route sets, controlled:
- Base is 1616fc8f and head is this branch, on the same parent, recipe and tool.
- The shipping route is placed at ExtraPostPlacementOpt; AltSpreadLogic_high and ExtraTimingOpt are placed from its synthesis checkpoint.
- The generated inputs differ only in the engine RTL and the gPTP microcode image.
- The qualifying image is the best worst-corner WNS meeting WNS ≥ +0.030 ns and WHS ≥ 0 at every corner. Figures are routed.

| Shape | Base qualifying | Head qualifying | LUT | FF | BRAM | Rule |
|---|---|---|---|---|---|---|
| 1x1/1if | ExtraTimingOpt, 32,777 LUT | ExtraTimingOpt, 32,455 LUT | −322 | −4 | = | met |
| 8x8/1if | ExtraPostPlacementOpt, 43,022 LUT | ExtraPostPlacementOpt, 43,477 LUT | +455 | −110 | = | not met |

- At 8x8, every head directive grows against the base's qualifying image: +455, +514 and +567 LUT.
- The growth is reproducible. Synthesis and the ExtraTimingOpt placement repeat the earlier routes exactly on both sides, and the synthesised 8x8 head is already +615 LUT.
- The engine, the only changed cell, is −74 LUT. The net growth is in cells whose RTL is identical: the mailbox edit window +1,569 against the CSR block −1,338, the gPTP wrapper's own logic +335, the datapath's own logic +220.

No RTL was changed to chase the count. Only the owner can amend the rule.
