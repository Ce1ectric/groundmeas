# Create measurements

Real-world scenario: staged fault test at a 20 kV substation with Fall-of-Potential points (10–150 m) and shield current capture.

## CLI (field entry)
| Task | Command | Notes/arguments |
| --- | --- | --- |
| Create measurement | `gm-cli add-measurement` | Enter location (e.g., “Substation West”, lat/lon), method `staged_fault_test`, asset `substation`, `voltage_level_kv=20`, `fault_resistance_ohm=1`, operator, notes. Add initial items in the wizard or later. |
| Add impedance points | `gm-cli add-item MEAS_ID` | For each distance (10, 30, 50, …, 150 m): choose `earthing_impedance`, set `frequency_hz=50`, value/angle or real/imag, `measurement_distance_m`, `distance_to_current_injection_m` (e.g., 200 m). |
| Add shield current | `gm-cli add-item MEAS_ID` | Type `shield_current`, `frequency_hz=50`, magnitude/angle or real/imag, unit `A`. |

Tips: Use `--db PATH` or `GROUNDMEAS_DB`. Autocomplete reuses prior locations/operators/units.

## Python API (scripted)
```python
from groundmeas.db import connect_db, create_measurement, create_item

connect_db("groundmeas.db")

# Measurement metadata
mid = create_measurement({
    "method": "staged_fault_test",
    "asset_type": "substation",
    "voltage_level_kv": 20.0,
    "fault_resistance_ohm": 1.0,
    "operator": "Ops Team",
    "description": "Staged fault, Substation West",
    "location": {"name": "Substation West", "latitude": 50.12, "longitude": 8.65}
})

# Fall-of-Potential impedance points
distances = [10, 30, 50, 70, 90, 110, 130, 150]
for idx, dist in enumerate(distances):
    create_item({
        "measurement_type": "earthing_impedance",
        "frequency_hz": 50.0,
        "value": 0.35 + 0.01 * idx,   # sample increasing values
        "value_angle_deg": 0.0,
        "unit": "Ω",
        "measurement_distance_m": float(dist),
        "distance_to_current_injection_m": 200.0,
    }, measurement_id=mid)

# Shield current at 50 Hz
create_item({
    "measurement_type": "shield_current",
    "frequency_hz": 50.0,
    "value": 45.0,
    "value_angle_deg": -10.0,
    "unit": "A",
}, measurement_id=mid)
```

## Supported item types (measurement_type)
| Category | Types |
| --- | --- |
| Impedance/resistance | `earthing_impedance`, `earthing_resistance` |
| Currents | `earth_fault_current`, `earthing_current`, `shield_current` |
| Voltages/potentials | `prospective_touch_voltage`, `touch_voltage`, `earth_potential_rise`, `step_voltage`, `transferred_potential` |
| Soil | `soil_resistivity` |

## Value representations
| Representation | Fields | Notes |
| --- | --- | --- |
| Polar | `value`, `value_angle_deg` | Magnitude and optional phase angle. |
| Rectangular | `value_real`, `value_imag` | Real/imag parts; magnitude/angle auto-computed. |

The model auto-computes the missing counterpart. At least one representation is required.

## Recommended metadata
| Field | Why |
| --- | --- |
| `frequency_hz` | Aligns impedance/current/voltage for analysis. |
| `measurement_distance_m` | Needed for Fall-of-Potential and soil profiles. |
| `distance_to_current_injection_m` | Required for the 62% algorithm. |
| `unit` | Always set (`Ω`, `A`, `V`, `m`, etc.). |
