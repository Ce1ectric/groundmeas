# Create measurements

This tutorial covers how to create measurements for two real-world scenarios: a staged fault test and a soil resistivity survey.

## Physical background

Earthing impedance relates Earth Potential Rise to injected current.

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

Soil resistivity surveys estimate apparent resistivity. Wenner array formula:

$$
\rho_a = 2 \pi a R
$$

Schlumberger array formula:

$$
\rho_a = \pi \frac{AB^2 - MN^2}{4 MN} R
$$

## Function overview
- `create_measurement` creates a measurement record.
- `create_item` stores impedance, current, voltage, or soil resistivity items.
- `read_items_by` helps verify inserted items.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `create_measurement` | measurement dict | measurement id | Create a measurement with optional location. |
| `create_item` | item dict, `measurement_id` | item id | Create an item linked to a measurement. |
| `read_items_by` | filters | list of items | Read items for verification. |

## General workflow

### Scenario A: staged fault test
1. Create a measurement with method `staged_fault_test` and location metadata.
2. Add `earthing_impedance` items for each distance.
3. Add `shield_current` or `earth_fault_current` if available.
4. Verify item count and distances.

### Scenario B: soil resistivity survey
1. Create a measurement with method `wenner` or `schlumberger`.
2. Add `soil_resistivity` items at each spacing.
3. Store spacing in `measurement_distance_m`.
4. Store MN spacing in `distance_to_current_injection_m` for Schlumberger if needed.

## Python API examples

### Scenario A: staged fault test
```python
from groundmeas.db import connect_db, create_measurement, create_item, read_items_by

connect_db("groundmeas.db")

mid = create_measurement({
    "method": "staged_fault_test",
    "asset_type": "substation",
    "voltage_level_kv": 20.0,
    "fault_resistance_ohm": 1.0,
    "description": "Staged fault test",
    "location": {"name": "Substation West"},
})

for dist, value in [(10, 0.40), (30, 0.36), (50, 0.34)]:
    create_item({
        "measurement_type": "earthing_impedance",
        "frequency_hz": 50.0,
        "value": value,
        "value_angle_deg": 0.0,
        "unit": "ohm",
        "measurement_distance_m": float(dist),
        "distance_to_current_injection_m": 200.0,
    }, measurement_id=mid)

create_item({
    "measurement_type": "shield_current",
    "frequency_hz": 50.0,
    "value": 45.0,
    "value_angle_deg": -10.0,
    "unit": "A",
}, measurement_id=mid)

items, _ = read_items_by(measurement_id=mid)
print(len(items))
```

### Scenario B: soil resistivity survey
```python
from groundmeas.db import connect_db, create_measurement, create_item

connect_db("groundmeas.db")

soil_id = create_measurement({
    "method": "schlumberger",
    "asset_type": "substation",
    "description": "Schlumberger survey",
    "location": {"name": "Substation West"},
})

# Store AB/2 in measurement_distance_m, MN/2 in distance_to_current_injection_m
for ab2, mn2, r in [(1.0, 0.5, 12.0), (2.0, 0.5, 10.5), (4.0, 0.5, 9.0)]:
    create_item({
        "measurement_type": "soil_resistivity",
        "value": r,
        "unit": "ohm",
        "measurement_distance_m": ab2,
        "distance_to_current_injection_m": mn2,
    }, measurement_id=soil_id)
```

## CLI examples

### Scenario A: staged fault test
```bash
gm-cli add-measurement

# Add impedance points
for d in 10 30 50; do
  gm-cli add-item MEAS_ID
  # choose earthing_impedance, set frequency 50, value, and distance $d
  # set distance_to_current_injection_m to 200
done

gm-cli add-item MEAS_ID
# choose shield_current and enter value
```

### Scenario B: soil resistivity survey
```bash
gm-cli add-measurement

# Add soil resistivity items for each spacing
for a in 1 2 4; do
  gm-cli add-item SOIL_MEAS_ID
  # choose soil_resistivity, set value, and spacing $a
done
```

## Additional notes
- Use consistent units (ohm, ohm-m) across a survey.
- For Schlumberger, confirm whether you store full or half spacings.
- If you accidentally mix resistivity and resistance values, set `value_kind` later when analyzing.
