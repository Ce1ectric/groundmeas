# Quickstart (CLI and Python)

Goal: create a database, add a measurement with impedance items, run a basic distance-profile analysis, and then run a small soil resistivity survey with a layered-earth inversion.

## CLI route
```bash
# 1) Create or connect to a database (auto-created)
gm-cli --db ./groundmeas.db list-measurements

# 2) Add a measurement interactively (location, method, asset, and metadata)
gm-cli --db ./groundmeas.db add-measurement

# 3) Add items interactively (repeat for each distance)
gm-cli --db ./groundmeas.db add-item MEAS_ID

# 4) Read items back
gm-cli --db ./groundmeas.db list-items MEAS_ID

# 5) Run two distance-profile algorithms
gm-cli --db ./groundmeas.db distance-profile MEAS_ID --type earthing_impedance --algorithm maximum
gm-cli --db ./groundmeas.db distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient

# 6) Plot impedance vs distance (static)
gm-cli --db ./groundmeas.db plot-impedance MEAS_ID --out plots/impedance.png
```

Optional soil survey flow:
```bash
# 7) Create a soil survey measurement (method wenner or schlumberger)
gm-cli --db ./groundmeas.db add-measurement

# 8) Add soil_resistivity items (spacing in measurement_distance_m)
#    Use add-item for each spacing in your survey

gm-cli --db ./groundmeas.db add-item SOIL_MEAS_ID

# 9) Build a depth-resistivity profile
#    Wenner default uses spacing as a; Schlumberger defaults to AB/2 and MN/2

gm-cli --db ./groundmeas.db soil-profile SOIL_MEAS_ID --method wenner

# 10) Invert a 1-3 layer model

gm-cli --db ./groundmeas.db soil-inversion SOIL_MEAS_ID --layers 2 --method wenner

# 11) Plot the inversion fit

gm-cli --db ./groundmeas.db plot-soil-inversion SOIL_MEAS_ID --layers 2 --out plots/soil_inversion.png
```

## Python route
```python
from groundmeas.db import connect_db, create_measurement, create_item, read_items_by
from groundmeas.analytics import distance_profile_value
from groundmeas.plots import plot_value_over_distance

connect_db("groundmeas.db")

# 1) Create a staged fault test measurement
mid = create_measurement({
    "method": "staged_fault_test",
    "asset_type": "substation",
    "voltage_level_kv": 10.0,
    "fault_resistance_ohm": 1.0,
    "description": "Quickstart example",
    "location": {"name": "Site A", "latitude": 51.0, "longitude": 10.0}
})

# 2) Add impedance items at multiple distances
for idx, dist in enumerate(range(10, 110, 10)):
    create_item({
        "measurement_type": "earthing_impedance",
        "frequency_hz": 50.0,
        "value": 0.3 + 0.02 * idx,
        "value_angle_deg": 0.0,
        "unit": "ohm",
        "measurement_distance_m": float(dist),
        "distance_to_current_injection_m": 150.0,
    }, measurement_id=mid)

# 3) Analyze distance profile
res = distance_profile_value(mid, algorithm="minimum_gradient")
print(res["result_value"], res["result_distance_m"])

# 4) Plot impedance vs distance
fig = plot_value_over_distance(mid, measurement_type="earthing_impedance")
fig.savefig("plots/impedance_distance.png")
```

Optional soil survey (Python):
```python
from groundmeas.analytics import soil_resistivity_profile, invert_soil_resistivity_layers

soil_id = create_measurement({
    "method": "wenner",
    "asset_type": "substation",
    "description": "Wenner soil survey",
    "location": {"name": "Site A"}
})

spacings = [1.0, 2.0, 4.0, 8.0, 16.0]
values = [80.0, 75.0, 65.0, 55.0, 50.0]
for spacing, rho_a in zip(spacings, values):
    create_item({
        "measurement_type": "soil_resistivity",
        "value": rho_a,
        "unit": "ohm-m",
        "measurement_distance_m": spacing,
    }, measurement_id=soil_id)

profile = soil_resistivity_profile(soil_id, method="wenner")
print(profile[:3])

inv = invert_soil_resistivity_layers(soil_id, method="wenner", layers=2)
print(inv["rho_layers"], inv["thicknesses_m"])
```

Next steps: follow the tutorials for realistic, field-level workflows and check the reference pages for full inputs and outputs.
