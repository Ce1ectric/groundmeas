# Tutorials overview

This tutorial series covers two primary workflows: staged fault testing and soil resistivity surveying. Each tutorial includes physical context, a step-by-step workflow, Python API and CLI examples, and practical notes.

## Physical background

Earthing impedance relates Earth Potential Rise to injected current.

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

Soil resistivity surveys use Wenner or Schlumberger arrays. Apparent resistivity for Wenner is:

$$
\rho_a = 2 \pi a R
$$

## Function overview
- Database and CRUD: `connect_db`, `create_measurement`, `create_item`, `read_items_by`.
- Impedance analytics: `distance_profile_value`, `impedance_over_frequency`.
- Soil analytics: `soil_resistivity_profile`, `invert_soil_resistivity_layers`.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `connect_db` | `path` | none | Initialize the database connection. |
| `create_measurement` | measurement dict | measurement id | Create a measurement record. |
| `create_item` | item dict, `measurement_id` | item id | Create a measurement item. |
| `distance_profile_value` | measurement id, algorithm | dict | Reduce a distance profile to one value. |
| `soil_resistivity_profile` | measurement id, method | dict | Map depth to apparent resistivity. |
| `invert_soil_resistivity_layers` | measurement id, layers | dict | Fit a layered soil model. |

## General workflow

### Scenario A: staged fault test
1. Create a measurement with method `staged_fault_test` and location.
2. Add impedance items with distance and frequency.
3. Add shield current and fault current items if available.
4. Verify data and run distance-profile analytics.

### Scenario B: soil resistivity survey
1. Create a measurement with method `wenner` or `schlumberger`.
2. Add soil resistivity items for each spacing.
3. Build a depth-resistivity profile.
4. Invert a 1 to 3 layer model.

## Python API examples

### Scenario A: staged fault test
```python
from groundmeas.db import connect_db, create_measurement, create_item
from groundmeas.analytics import distance_profile_value

connect_db("groundmeas.db")

mid = create_measurement({
    "method": "staged_fault_test",
    "asset_type": "substation",
    "description": "Staged fault test",
    "location": {"name": "Site A"},
})

for dist, val in [(10, 0.40), (30, 0.36), (50, 0.34)]:
    create_item({
        "measurement_type": "earthing_impedance",
        "frequency_hz": 50.0,
        "value": val,
        "value_angle_deg": 0.0,
        "unit": "ohm",
        "measurement_distance_m": float(dist),
        "distance_to_current_injection_m": 200.0,
    }, measurement_id=mid)

result = distance_profile_value(mid, algorithm="minimum_gradient")
print(result["result_value"], result["result_distance_m"])
```

### Scenario B: soil survey
```python
from groundmeas.db import connect_db, create_measurement, create_item
from groundmeas.analytics import soil_resistivity_profile, invert_soil_resistivity_layers

connect_db("groundmeas.db")

soil_id = create_measurement({
    "method": "wenner",
    "asset_type": "substation",
    "description": "Wenner survey",
    "location": {"name": "Site A"},
})

for spacing, rho_a in [(1.0, 80.0), (2.0, 70.0), (4.0, 55.0)]:
    create_item({
        "measurement_type": "soil_resistivity",
        "value": rho_a,
        "unit": "ohm-m",
        "measurement_distance_m": spacing,
    }, measurement_id=soil_id)

profile = soil_resistivity_profile(soil_id, method="wenner")
print(profile)

inv = invert_soil_resistivity_layers(soil_id, method="wenner", layers=2)
print(inv["rho_layers"], inv["thicknesses_m"])
```

## CLI examples

### Scenario A: staged fault test
```bash
gm-cli add-measurement

gm-cli add-item MEAS_ID

gm-cli distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient
```

### Scenario B: soil survey
```bash
gm-cli add-measurement

gm-cli add-item SOIL_MEAS_ID

gm-cli soil-profile SOIL_MEAS_ID --method wenner

gm-cli soil-inversion SOIL_MEAS_ID --layers 2 --method wenner
```

## Additional notes
- Missing `measurement_distance_m` prevents distance-based analytics.
- Schlumberger spacing defaults to AB/2 and MN/2; set `ab_is_full` or `mn_is_full` if you store full spacings.
- Use JSON export as a backup before editing or deleting data.
- For algorithm selection and behavior details, see the [Distance profile reduction](15_analytics.md#distance-profile-reduction) section.
