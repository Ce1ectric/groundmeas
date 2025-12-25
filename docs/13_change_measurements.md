# Change measurements

Scenario continuation: adjust impedance values after a retest and remove an erroneous point.

## CLI
| Task | Command | Notes |
| --- | --- | --- |
| Edit measurement metadata | `gm-cli edit-measurement MEAS_ID` | Update description, operator, voltage, method, location. |
| Edit an item | `gm-cli edit-item ITEM_ID` | Auto-detects polar vs rectangular. Change value, frequency, distance, unit, description. |
| Delete an item | `gm-cli delete-item ITEM_ID [--yes/-y]` | Remove an erroneous data point. |
| Delete a measurement | `gm-cli delete-measurement MEAS_ID [--yes/-y]` | Removes the measurement and its items. |

## Python API
```python
from groundmeas.db import connect_db, update_measurement, update_item, delete_item
connect_db("groundmeas.db")

# Update measurement description and voltage
update_measurement(1, {
    "description": "Retested after maintenance",
    "voltage_level_kv": 18.0,
})

# Convert an impedance point to rectangular form
update_item(10, {
    "measurement_type": "earthing_impedance",
    "frequency_hz": 50.0,
    "value": None,
    "value_angle_deg": None,
    "value_real": 0.28,
    "value_imag": 0.04,
    "unit": "Ω",
    "measurement_distance_m": 70.0,
})

# Delete an outlier item
delete_item(11)
```

### Tips
- When switching representations, set the unused fields to `None` to avoid stale values.
- Keep frequencies consistent for comparable datasets.
- Use `--yes/-y` flags in CLI when scripting to skip confirmations.
