<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Gasket suite

This suite verifies the bench MII gaskets in loopback.

Run it directly:

```sh
make
```

The chain mirrors the bench top's transmit and receive path.

Corrupted nibbles prove the frame-check drop arm.

Planted defects then prove its checks load-bearing.

This RTL serves the bench only, never the product engine.

See the [test developer guide](../../../docs/TEST_DEVELOPER.md).
