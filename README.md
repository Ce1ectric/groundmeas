# groundmeas: Grounding System Measurements and Analysis

Groundmeas is a Python toolkit for managing, analyzing, and visualizing grounding (earthing) measurements. It provides a SQLite data layer, a Python API, a CLI, a Streamlit dashboard, and physics-aware analytics for field work and reporting.

Documentation: https://ce1ectric.github.io/groundmeas/

## Features
- Data management with SQLite and SQLModel.
- CLI workflows for creating, editing, importing, and exporting measurements.
- Streamlit dashboard with map selection and interactive plots.
- Analytics for impedance profiles, touch voltages, split factors, and multilayer soil models.
- Distance-profile reduction with maximum, 62 percent, minimum gradient, minimum stddev, and inverse (1/Z) methods.
- Apparent resistivity simulation and 1-3 layer inversion for Wenner and Schlumberger surveys.
- Import and export to JSON, CSV, XML, plus OCR import from images.

## Physical background

Earthing impedance relates Earth Potential Rise to injected current.

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

The rho-f model links impedance to soil resistivity and frequency.

$$
Z(\rho, f) = k_1 \cdot \rho + (k_2 + j k_3) \cdot f + (k_4 + j k_5) \cdot \rho \cdot f
$$

Inverse extrapolation for Fall-of-Potential uses:

$$
\frac{1}{Z} = a \cdot \frac{1}{d} + b
$$

## Installation

Prerequisites: Python 3.14+

### Using Poetry (recommended)
```bash
git clone https://github.com/Ce1ectric/groundmeas.git
cd groundmeas
poetry install
poetry shell
```

### Using pip
```bash
pip install groundmeas
```

## Quick usage

### CLI
```bash
# Create or connect to a database
# Default order: GROUNDMEAS_DB, ~/.config/groundmeas/config.json, ./groundmeas.db

gm-cli list-measurements

# Create a measurement and add items interactively
gm-cli add-measurement
gm-cli add-item MEAS_ID

# Run a distance-profile reduction
gm-cli distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient

# Soil survey: profile and inversion
gm-cli soil-profile SOIL_MEAS_ID --method wenner
gm-cli soil-inversion SOIL_MEAS_ID --layers 2 --method wenner
```

### Python API
```python
from groundmeas.db import connect_db, read_measurements_by
from groundmeas.analytics import impedance_over_frequency

connect_db("groundmeas.db")
measurements, _ = read_measurements_by()

for meas in measurements:
    z_f = impedance_over_frequency(meas["id"])
    print(meas["id"], z_f)
```

## Project structure
```
groundmeas/
|-- src/groundmeas/
|   |-- core/          # DB connection + models
|   |-- services/      # Analytics, export, OCR import
|   |-- visualization/ # Matplotlib, Plotly, map
|   `-- ui/            # CLI and dashboard
|-- docs/              # MkDocs documentation
|-- tests/             # Pytest suite
`-- pyproject.toml
```

## License

MIT License. See `LICENSE`.
