<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Independent decode suite

This suite cross-checks the engine against independent protocol decoders.

Run it directly:

```sh
make
```

Transmitted frames are decoded against external 802.1AS protocol descriptions.

Generated frames drive the engine against a Python model.

Set `TSAGEN_DIR` to the decoder checkout.

Without that checkout the suite skips and returns zero.

See the [test developer guide](../../docs/TEST_DEVELOPER.md).
