<!-- SPDX-License-Identifier: CERN-OHL-W-2.0 -->
# Diagram generation

Every diagram has an editable source.

Generated artifacts remain committed for convenient reading.

Each PNG embeds its editable source digest.

Embedded digests reject stale or swapped previews.

Visual inspection verifies layout and rendered meaning.

## Architecture

| Asset | Purpose |
|---|---|
| `gptp_architecture.drawio` | Editable architecture source |
| `gptp_architecture.svg` | Browser and print vector output |
| `gptp_architecture.png` | Repository preview output |

The checker binds module labels to current RTL.

## Timing

| Source | SVG | PNG |
|---|---|---|
| `wavedrom/rx_accept.json` | `wavedrom/rx_accept.svg` | `wavedrom/rx_accept.png` |
| `wavedrom/tx_backpressure.json` | `wavedrom/tx_backpressure.svg` | `wavedrom/tx_backpressure.png` |

WaveDrom sources describe current handshake timing.

## Generate

Install WaveDrom outside the repository.

```sh
python3 -m venv /tmp/fpga-gptp-wavedrom
/tmp/fpga-gptp-wavedrom/bin/pip install wavedrom==2.0.3.post3
python3 scripts/generate_diagrams.py \
  --render \
  --wavedrom /tmp/fpga-gptp-wavedrom/bin/wavedrompy
```

Draw.io must exist on the command path.

Generated files update their source bindings and manifest.

## Check

```sh
python3 scripts/generate_diagrams.py --check
python3 scripts/generate_diagrams.py --selftest
```

The checker verifies these properties:

- RTL evidence tokens still exist.
- Draw.io labels match instantiated modules.
- WaveDrom sources match HDL invariants.
- Embedded PNG hashes match their editable sources.
- Manifest hashes pin every committed diagram asset.
- PNG dimensions remain readable.
- SVG files retain valid viewboxes.

## Inspect

Render previews beneath `/tmp`.

```sh
drawio --export --format pdf \
  --output /tmp/gptp-architecture.pdf \
  docs/diagrams/gptp_architecture.drawio
pdftoppm -png -f 1 -singlefile \
  /tmp/gptp-architecture.pdf \
  /tmp/gptp-architecture-print
```

Inspect both PNG outputs visually.

Check labels, arrows, spacing, and clipping.
