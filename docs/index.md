# Groundmeas

Groundmeas is a toolkit for managing, analyzing, and visualizing grounding (earthing) measurements. It combines a SQLite data layer, a Python API, a CLI, a Streamlit dashboard, and physics-aware analytics for field work and reporting.

## What this guide covers
- Quickstart for CLI and Python workflows
- Data model for locations, measurements, and measurement items
- Step-by-step tutorials for creating, reading, editing, and importing data
- Analytics for impedance, touch voltages, split factor, and soil modeling
- Dashboard usage and plotting
- Import of OMICRON COMPANO 100 and HGT1 exports
- Tower campaigns: evaluation, assessment and protocols for overhead-line towers (`gm-cli towers`)
- API and CLI reference

## Quick mental model
- You create a measurement with a method and optional location.
- You add measurement items (impedance, current, voltage, soil resistivity) with metadata.
- Analytics functions read items from the database and compute results.
- Plot helpers and the dashboard visualize those results.

## Physical background

Earthing impedance relates Earth Potential Rise to injected current.

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

Earth Potential Rise is computed from impedance and current.

$$
EPR = Z_E \cdot I_E
$$

The rho-f model links impedance to soil resistivity and frequency.

$$
Z(\rho, f) = k_1 \cdot \rho + (k_2 + j k_3) \cdot f + (k_4 + j k_5) \cdot \rho \cdot f
$$

Soil resistivity surveys use Wenner or Schlumberger arrays and feed the multilayer soil model used later in analytics.

## Minimal example

```python
import groundmeas as gm

gm.connect_db("groundmeas.db")
measurements, _ = gm.read_measurements_by()
for meas in measurements:
    print(meas["id"], gm.impedance_over_frequency(meas["id"]))
```

See `02_quickstart.md` for a CLI walk-through and `21_ref_api.md` for
the full API surface.

## Tower campaigns

`gm-cli towers` evaluates earthing measurements of overhead-line towers
(OMICRON COMPANO 100 and HGT1): 62 % earthing impedance, touch and step
voltages at the earth-fault current, assessment against the permissible
touch voltage (EN 50522 / EN 50341), JSON/Excel results and HTML/PDF
protocols. It was the separate package `tower-grounding-measurement`; see
[Tower campaigns](towers/index.md).

```console
$ gm-cli towers demo demo
$ gm-cli towers run --config demo/config.json --no-pdf
```

## Navigation
- Quickstart: `02_quickstart.md`
- Tutorials: `10_tutorial_intro.md` and the tutorial series
- Instrument import: `17_instrument_import.md`
- Tower campaigns: `towers/index.md`
- Reference: `20_ref_intro.md`, `21_ref_api.md`, `22_ref_cli.md`
- Contributing: `99_contributing.md`
