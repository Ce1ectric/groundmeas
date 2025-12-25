# Read measurements

Scenario continuation: inspect the staged fault test data, check impedance values, and verify shield currents.

## CLI
| Task | Command | Notes |
| --- | --- | --- |
| List measurements | `gm-cli list-measurements` | Shows `[id] location | method | asset | items`. |
| View items | `gm-cli list-items MEAS_ID [--type earthing_impedance]` | Tabular view of impedance points with frequency/value/angle/distance/unit. |
| Export for review | `gm-cli export-json out.json --measurement-id MEAS_ID` | JSON snapshot for offline QA. |
| Quick profile check | `gm-cli distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient` | Returns characteristic value from the curve. |

## Python API
```python
from groundmeas.db import connect_db, read_measurements_by, read_items_by
connect_db("groundmeas.db")

# All measurements
measurements, ids = read_measurements_by()

# Get one measurement with items
m, _ = read_measurements_by(id=ids[0])
print(m[0]["location"], len(m[0]["items"]))

# Items filtered by type and frequency
impedance_items, _ = read_items_by(
    measurement_id=ids[0],
    measurement_type="earthing_impedance",
    frequency_hz=50.0
)

# Verify shield currents at 50 Hz
shield_items, _ = read_items_by(
    measurement_id=ids[0],
    measurement_type="shield_current",
    frequency_hz=50.0
)
print("Shield currents:", shield_items)
```

### Filter suffixes you can use
- Equality (default): `field=value`
- `__lt`, `__lte`, `__gt`, `__gte` for ranges
- `__in` for list membership
- `__ne` for inequality

Examples:
- `read_measurements_by(asset_type="substation", voltage_level_kv__gte=10)`
- `read_items_by(measurement_id=5, measurement_type="earthing_current")`
- `read_items_by(frequency_hz__gte=1000)`
