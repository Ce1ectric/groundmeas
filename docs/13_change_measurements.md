# Change measurements

This tutorial shows how to update metadata, fix item values, and remove erroneous points.

## Physical background

Not applicable. This tutorial focuses on editing stored data.

## Function overview
- `update_measurement` edits measurement metadata and location.
- `update_item` edits a measurement item and its value representation.
- `delete_item` removes a single item.
- `delete_measurement` removes a measurement and its items.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `update_measurement` | measurement id, updates | bool | Update measurement fields. |
| `update_item` | item id, updates | bool | Update item fields or representation. |
| `delete_item` | item id | bool | Delete one item. |
| `delete_measurement` | measurement id | bool | Delete measurement and items. |

## General workflow

### Scenario A: staged fault test correction
1. Export a JSON snapshot as a backup.
2. Update the measurement description and operator.
3. Correct the impedance value at the wrong distance.
4. Re-run distance-profile analytics.

### Scenario B: soil survey correction
1. Export a JSON snapshot.
2. Fix an incorrect spacing or unit.
3. Remove an outlier point.
4. Rebuild the soil profile and check the curve.

## Python API examples

### Scenario A: staged fault test correction
```python
from groundmeas.db import connect_db, update_measurement, update_item
from groundmeas.analytics import distance_profile_value

connect_db("groundmeas.db")

update_measurement(1, {
    "description": "Retested after maintenance",
    "operator": "Ops Team",
})

update_item(10, {
    "measurement_type": "earthing_impedance",
    "frequency_hz": 50.0,
    "value": 0.34,
    "value_angle_deg": 0.0,
    "unit": "ohm",
    "measurement_distance_m": 50.0,
})

check = distance_profile_value(1, algorithm="minimum_gradient")
print(check["result_value"]) 
```

### Scenario B: soil survey correction
```python
from groundmeas.db import connect_db, update_item, delete_item
from groundmeas.analytics import soil_resistivity_profile

connect_db("groundmeas.db")

# Fix spacing and unit for item 21
update_item(21, {
    "measurement_type": "soil_resistivity",
    "measurement_distance_m": 4.0,
    "value": 60.0,
    "unit": "ohm-m",
})

# Remove an outlier
ok = delete_item(22)
print(ok)

profile = soil_resistivity_profile(2, method="wenner")
print(profile)
```

## CLI examples

### Scenario A: staged fault test correction
```bash
gm-cli export-json backup.json --measurement-id 1

gm-cli edit-measurement 1

gm-cli edit-item 10

gm-cli distance-profile 1 --type earthing_impedance --algorithm minimum_gradient
```

### Scenario B: soil survey correction
```bash
gm-cli export-json backup.json --measurement-id 2

gm-cli edit-item 21

gm-cli delete-item 22 --yes

gm-cli soil-profile 2 --method wenner
```

## Additional notes
- When changing value representation, clear unused fields to avoid stale values.
- Always export a backup before deleting items.
- If you adjust spacing, re-check the profile and inversion results.
