# Data models

Groundmeas stores data in SQLite via SQLModel with three core entities: **Location**, **Measurement**, and **MeasurementItem**. The relationships are simple:
- A **Location** can have many **Measurements**.
- A **Measurement** belongs to one **Location** (optional) and has many **MeasurementItems**.
- A **MeasurementItem** always belongs to one **Measurement**.

## Location
- `id` (int, PK)
- `name` (str)
- `latitude`, `longitude`, `altitude` (float, optional)
- Back-reference: `measurements`

## Measurement
- `id` (int, PK)
- `timestamp` (UTC, auto)
- `location_id` / `location` (FK to `Location`, optional)
- `method`: `staged_fault_test` | `injection_remote_substation` | `injection_earth_electrode`
- `asset_type`: `substation` | `overhead_line_tower` | `cable` | `cable_cabinet` | `house` | `pole_mounted_transformer` | `mv_lv_earthing_system`
- `voltage_level_kv`, `fault_resistance_ohm` (optional)
- `operator`, `description` (optional)
- `items`: list of `MeasurementItem`

## MeasurementItem
Supports polar or rectangular representation; the model enforces consistency with an event hook.
- `id` (int, PK)
- `measurement_id` / `measurement` (FK to `Measurement`)
- `measurement_type`:
  - Voltages/potentials: `prospective_touch_voltage`, `touch_voltage`, `earth_potential_rise`, `step_voltage`, `transferred_potential`
  - Currents: `earth_fault_current`, `earthing_current`, `shield_current`
  - Impedance/resistance: `earthing_resistance`, `earthing_impedance`
  - Soil: `soil_resistivity`
- Value fields (polar): `value`, `value_angle_deg`
- Value fields (rectangular): `value_real`, `value_imag`
- Metadata: `unit`, `frequency_hz`, `measurement_distance_m`, `distance_to_current_injection_m`, `additional_resistance_ohm`, `input_impedance_ohm`, `description`

## Consistency rules
- If only `value_real`/`value_imag` are provided, magnitude and angle are computed automatically.
- If `value` and `value_angle_deg` are provided, real/imag parts are computed.
- At least one representation must be present or insertion raises `ValueError`.

## Relationships and usage
- A `Measurement` can exist without a `Location`, but typical workflows create both.
- Items are always attached to a `Measurement`.
- The CLI and API mirror this structure: create a measurement (optionally with location), then create items.
