# groundmeas: Grounding System Measurements and Analysis

Groundmeas is a Python toolkit for managing, analyzing, and visualizing
grounding (earthing) measurements. It provides a SQLite data layer, a
Python API, a CLI, a Streamlit dashboard, and physics-aware analytics.

Full documentation: https://ce1ectric.github.io/groundmeas/

## Features
- SQLite + SQLModel data layer for locations, measurements, and items.
- Python API and `gm-cli` for create / read / update / delete workflows.
- Streamlit dashboard with map selection and interactive Plotly charts.
- Analytics: impedance vs frequency, distance-profile reduction, rho-f
  model, touch voltages / EPR, split factor, multilayer soil model and
  1-3 layer inversion (Wenner / Schlumberger).
- Import / export to JSON, CSV, XML and OCR import from images.
- Native import of OMICRON COMPANO 100 (XML) and HGT1 (StepTouch report)
  exports: fall-of-potential profiles at the power and both test
  frequencies, footing resistance, split-factor currents, touch voltages and
  soil resistivity (`gm-cli import-omicron`).
- Tower campaigns (`gm-cli towers`, formerly the package
  `tower-grounding-measurement`): evaluation of overhead-line towers with
  the 62 % method, touch voltages at the earth-fault current, assessment
  against the permissible touch voltage (EN 50522 / EN 50341), JSON/Excel
  results, HTML/PDF protocols in English or German and a statistics report;
  `gm-cli towers import-db` copies a campaign into the database.

## Installation

Prerequisites: Python 3.14+.

```bash
# From PyPI
pip install groundmeas
# with PDF protocols for tower campaigns (Playwright)
pip install "groundmeas[pdf]" && gm-cli towers install-browser

# Or from source
git clone https://github.com/Ce1ectric/groundmeas.git
cd groundmeas
poetry install
```

## Quick start

```bash
# Create a measurement and add items interactively
gm-cli add-measurement
gm-cli add-item MEAS_ID

# Reduce a distance profile and run a soil inversion
gm-cli distance-profile MEAS_ID --algorithm minimum_gradient
gm-cli soil-inversion SOIL_MEAS_ID --layers 2 --method wenner

# Launch the interactive dashboard
gm-cli dashboard

# Import OMICRON exports of one location
gm-cli import-omicron --location "Tower 8" --asset-type overhead_line_tower \
    --ze ZE_tower8.xml --ut UT_tower8.txt -D 100

# Evaluate a tower campaign (synthetic demo)
gm-cli towers demo demo
gm-cli towers run --config demo/config.json --no-pdf
```

```python
import groundmeas as gm

gm.connect_db("groundmeas.db")
measurements, _ = gm.read_measurements_by()
for meas in measurements:
    print(meas["id"], gm.impedance_over_frequency(meas["id"]))
```

The recommended import style is the canonical top-level package
(`import groundmeas as gm`). The pre-1.5 layout
(`from groundmeas.db import …`, `from groundmeas.analytics import …`,
`from groundmeas.plots import …`, `from groundmeas.export import …`,
`from groundmeas.models import …`, `from groundmeas.vision_import
import …`, `from groundmeas.cli import …`) still works but emits a
`DeprecationWarning` on first attribute access. See
[ADR-0001](docs/adr/0001-compatibility-shim-deprecation-strategy.md)
for the deprecation contract and the 1.5 → 1.6 → 2.0 removal timeline.

The CLI resolves the database path from `--db`, then `GROUNDMEAS_DB`,
then `~/.config/groundmeas/config.json`, then `./groundmeas.db`.

For data-model details, tutorials, API and CLI reference, and the
analytics background (impedance, rho-f model, distance-profile
algorithms, soil inversion), see the
[full documentation](https://ce1ectric.github.io/groundmeas/).

## Changelog and contributing

Release notes follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and live in `CHANGELOG.md`. Contribution and release workflow are
described in `docs/99_contributing.md`.

## License

MIT License. See `LICENSE`.
