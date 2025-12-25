# Quickstart (CLI and Python)

Goal: create a database, add a measurement with 10 earthing-impedance items at different distances, read data, import/export JSON, run analytics with two methods, and plot impedance vs distance.

## CLI route
```bash
# 1) Create/connect a database (auto-created)
gm-cli --db ./groundmeas.db list-measurements

# 2) Add a measurement interactively (location, method, asset, etc.)
gm-cli --db ./groundmeas.db add-measurement
```

```bash
# 3) Add 10 earthing_impedance items with varying distance
for d in 10 20 30 40 50 60 70 80 90 100; do
  gm-cli --db ./groundmeas.db add-item MEAS_ID \
    --type earthing_impedance \
    # you'll be prompted for frequency/value/angle; enter e.g. 50 Hz and a magnitude
    # enter measurement distance m when prompted (use $d)
done
```

```bash
# 4) Read back items
gm-cli --db ./groundmeas.db list-items MEAS_ID

# 5) Import from JSON (file or folder)
gm-cli --db ./groundmeas.db import-json data/example_measurement.json

# 6) Export to JSON
gm-cli --db ./groundmeas.db export-json export/out.json --measurement-id MEAS_ID

# 7) Analytics: distance-profile with two methods
gm-cli --db ./groundmeas.db distance-profile MEAS_ID --type earthing_impedance --algorithm maximum
gm-cli --db ./groundmeas.db distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient

# 8) Plot impedance vs distance (static)
gm-cli --db ./groundmeas.db plot-impedance MEAS_ID --out plots/impedance.png
```

## Python route
```python
from groundmeas.db import connect_db, create_measurement, create_item, read_items_by
from groundmeas.analytics import distance_profile_value, value_over_distance
from groundmeas.plots import plot_value_over_distance

# 1) Connect DB
connect_db("groundmeas.db")

# 2) Create a measurement with a location
mid = create_measurement({
    "method": "staged_fault_test",
    "asset_type": "substation",
    "voltage_level_kv": 10.0,
    "fault_resistance_ohm": 1.0,
    "description": "Quickstart example",
    "location": {"name": "Site A", "latitude": 51.0, "longitude": 10.0}
})

# 3) Add 10 earthing_impedance items
for idx, dist in enumerate(range(10, 110, 10)):
    create_item({
        "measurement_type": "earthing_impedance",
        "frequency_hz": 50.0,
        "value": 0.3 + 0.02 * idx,   # sample magnitudes
        "value_angle_deg": 0.0,
        "unit": "Ω",
        "measurement_distance_m": float(dist),
        "distance_to_current_injection_m": 150.0,
    }, measurement_id=mid)

# 4) Read items back
items, _ = read_items_by(measurement_id=mid, measurement_type="earthing_impedance")
print(items)

# 5) Import / Export (helpers)
from groundmeas.export import export_measurements_to_json
export_measurements_to_json("export/out.json", id__in=[mid])

# 6) Analytics with two methods
res_max = distance_profile_value(mid, algorithm="maximum")
res_grad = distance_profile_value(mid, algorithm="minimum_gradient")
print("Maximum:", res_max["result_value"], res_max["result_distance_m"])
print("Min gradient:", res_grad["result_value"], res_grad["result_distance_m"])

# 7) Plot impedance vs distance (Matplotlib)
fig = plot_value_over_distance(mid, measurement_type="earthing_impedance")
fig.savefig("plots/impedance_distance.png")
```

Next steps: see the tutorials for deeper workflows and the reference files for full argument lists.
