# groundmeas: Grounding System Measurements & Analysis

**groundmeas** is a Python package for collecting, storing, analyzing, and visualizing earthing (grounding) measurement data.

---

## Project Description

groundmeas provides:

* **Database models & CRUD** via SQLModel/SQLAlchemy (`Location`, `Measurement`, `MeasurementItem`).
* **Export utilities** to JSON, CSV, and XML.
* **Analytics routines** for impedance-over-frequency, real–imaginary processing, rho–f model fitting, and shield-current split factors (`calculate_split_factor`).
* **Plotting helpers** for impedance vs frequency and model overlays using Matplotlib.
* **CLI** (`gm-cli`) with interactive entry, DB-backed autocomplete, listing, add-item to existing measurements, default DB config, and JSON import/export.

It’s designed to help engineers and researchers work with earthing measurement campaigns, automate data pipelines, and quickly gain insights on soil resistivity and grounding impedance behavior.

---

## Technical Background

In grounding studies, measurements of earth electrode impedance are taken over a range of frequencies, and soil resistivity measurements at various depths are collected.

* **Earthing Impedance** $Z$ vs. **Frequency** (f): typically expressed in Ω.
* **Soil Resistivity** (ρ) vs. **Depth** (d): used to model frequency‑dependent behavior.
* **rho–f Model**: fits the relationship

  $$
  Z(ρ, f) = k_1·ρ + (k_2 + j·k_3)·f + (k_4 + j·k_5)·ρ·f
  $$

where $k_1…k_5$ are real coefficients determined by least‑squares across multiple measurements.

---

## Installation

Requires Python 3.12+:

```bash
git clone https://github.com/Ce1ectric/groundmeas.git
cd groundmeas
poetry install
poetry shell
```

or using pip locally:
```bash
git clone https://github.com/Ce1ectric/groundmeas.git
cd groundmeas
pip install .
```

Or install via pip: `pip install groundmeas`.

---

## Usage
### 0. CLI quickstart

```bash
gm-cli --db path/to/data.db add-measurement   # interactive wizard with autocomplete
gm-cli --db path/to/data.db list-measurements
gm-cli --db path/to/data.db list-items 1
gm-cli --db path/to/data.db import-json notebooks/measurements/foo_measurement.json
gm-cli --db path/to/data.db export-json out.json
# Add a single item to an existing measurement
gm-cli --db path/to/data.db add-item 5
# Save a default DB path (~/.config/groundmeas/config.json) so --db is optional
gm-cli set-default-db path/to/data.db
# Enable shell completion (example for zsh)
gm-cli --install-completion zsh
```

Set `GROUNDMEAS_DB` to avoid passing `--db` each time.

### 1. Database Setup

Initialize or connect to a SQLite database (tables will be created automatically):

```python
from groundmeas.db import connect_db
connect_db("mydata.db", echo=True)
```

### 2. Creating Measurements

Insert a measurement (optionally with nested location) and its items:

```python
from groundmeas.db import create_measurement, create_item

# Create measurement with nested Location
meas_id = create_measurement({
    "timestamp": "2025-01-01T12:00:00",
    "method": "staged_fault_test",
    "voltage_level_kv": 10.0,
    "asset_type": "substation",
    "location": {"name": "Site A", "latitude": 52.0, "longitude": 13.0},
})

# Add earthing impedance item
item_id = create_item({
    "measurement_type": "earthing_impedance",
    "frequency_hz": 50.0,
    "value": 12.3
}, measurement_id=meas_id)
```

### 3. Exporting Data

Export measurements (and nested items) to various formats:

```python
from groundmeas.export import (
    export_measurements_to_json,
    export_measurements_to_csv,
    export_measurements_to_xml,
)

export_measurements_to_json("data.json")
export_measurements_to_csv("data.csv")
export_measurements_to_xml("data.xml")
```

### 4. Analytics

Compute relevant connections between quantities of the earthing system: 
- impedance and 
- real / imaginary parts over frequency, 
- fit the rho–f model
- prospective touch voltage vs. Earth Potential Rise

```python
from groundmeas.analytics import (
    impedance_over_frequency,
    real_imag_over_frequency,
    rho_f_model,
    voltage_vt_epr,
    shield_currents_for_location,
    calculate_split_factor,
)

# Impedance vs frequency for a single measurement
imp_map = impedance_over_frequency(1)

# Real & Imag components for multiple measurements
ri_map = real_imag_over_frequency([1, 2, 3])

# Fit rho–f model across measurements [1,2,3]
k1, k2, k3, k4, k5 = rho_f_model([1, 2, 3])

# summarise the min, max measured touch voltages and the EPR for multiple measurements 
touch_min, touch_max, epr = voltage_vt_epr([1, 2, 3])

# Gather available shield currents at a site and compute split factors
candidates = shield_currents_for_location(location_id=5, frequency_hz=50.0)
# Pick the shield_current item IDs that share the same angle reference
shield_ids = [c["id"] for c in candidates]
split = calculate_split_factor(
    earth_fault_current_id=42,
    shield_current_ids=shield_ids,
)
split_factor = split["split_factor"]
local_earthing_current = split["local_earthing_current"]["value"]
```

### 5. Plotting

Visualize raw and modeled curves:

```python
from groundmeas.plots import plot_imp_over_f, plot_rho_f_model

# Raw impedance curves
fig1 = plot_imp_over_f([1, 2, 3])
fig1.show()

# Normalized at 50 Hz
fig2 = plot_imp_over_f(1, normalize_freq_hz=50)
fig2.show()

# Overlay rho–f model
fig3 = plot_rho_f_model([1,2,3], (k1,k2,k3,k4,k5), rho=[100, 200])
fig3.show()
```

## Contributing

Pull requests are welcome!
For major changes, please open an issue first to discuss.
Ensure tests pass and add new tests for your changes.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
