# Read measurements

This tutorial shows how to inspect measurements, verify metadata, and validate soil survey inputs before running analytics.

## Physical background

Not applicable for pure data inspection. This tutorial focuses on data integrity and validation.

## Function overview
- `read_measurements_by` loads measurements and nested items.
- `read_items_by` filters items by type, frequency, and distance.
- `distance_profile_value` provides a quick validation check for impedance data.
- `soil_resistivity_curve` exposes spacing and apparent resistivity points for surveys.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `read_measurements_by` | filters | list of measurements | Load measurements with items and location. |
| `read_items_by` | filters | list of items | Filter items by type or frequency. |
| `distance_profile_value` | measurement id, algorithm | dict | Quick impedance sanity check. |
| `soil_resistivity_curve` | measurement id, method | list of points | View spacing vs apparent resistivity. |

## General workflow

### Scenario A: staged fault test QA
1. List measurements and identify the staged fault test.
2. Filter impedance items by frequency.
3. Verify distances and units.
4. Run a distance-profile reduction to check the curve.

### Scenario B: soil survey QA
1. List soil survey measurements.
2. Read soil resistivity items.
3. Verify spacings and units.
4. Build a spacing curve for review.

## Python API examples

### Scenario A: staged fault test QA
```python
from groundmeas.db import connect_db, read_measurements_by, read_items_by
from groundmeas.analytics import distance_profile_value

connect_db("groundmeas.db")

meas, _ = read_measurements_by(method="staged_fault_test")
mid = meas[0]["id"]

items, _ = read_items_by(
    measurement_id=mid,
    measurement_type="earthing_impedance",
    frequency_hz=50.0,
)
print([it["measurement_distance_m"] for it in items])

check = distance_profile_value(mid, algorithm="minimum_gradient")
print(check["result_value"], check["result_distance_m"])
```

### Scenario B: soil survey QA
```python
from groundmeas.db import connect_db, read_measurements_by
from groundmeas.analytics import soil_resistivity_curve

connect_db("groundmeas.db")

meas, _ = read_measurements_by(method="wenner")
soil_id = meas[0]["id"]

curve = soil_resistivity_curve(soil_id, method="wenner")
print(curve)
```

## CLI examples

### Scenario A: staged fault test QA
```bash
gm-cli list-measurements

gm-cli list-items MEAS_ID --type earthing_impedance

gm-cli distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient
```

### Scenario B: soil survey QA
```bash
gm-cli list-measurements

gm-cli list-items SOIL_MEAS_ID --type soil_resistivity

gm-cli soil-profile SOIL_MEAS_ID --method wenner
```

## Additional notes
- Missing `measurement_distance_m` causes distance-based analytics to skip items.
- If units are inconsistent, `value_kind="auto"` can misclassify resistance vs resistivity.
- For Schlumberger, confirm whether spacing is AB or AB/2 before interpreting results.
- For QA, compare multiple reduction algorithms (maximum, 62_percent, minimum_gradient, minimum_stddev, inverse); see [Distance profile reduction](15_analytics.md#distance-profile-reduction).
