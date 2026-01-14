# Data models

Groundmeas stores data in SQLite via SQLModel with three core entities: Location, Measurement, and MeasurementItem.

## Location
Fields:
- `id` (int, primary key)
- `name` (str)
- `latitude`, `longitude`, `altitude` (float, optional)
- Back-reference: `measurements`

## Measurement
Fields:
- `id` (int, primary key)
- `timestamp` (UTC, auto)
- `location_id` / `location` (optional)
- `method`: `staged_fault_test`, `injection_remote_substation`, `injection_earth_electrode`, `wenner`, `schlumberger`
- `asset_type`: `substation`, `overhead_line_tower`, `cable`, `cable_cabinet`, `house`, `pole_mounted_transformer`, `mv_lv_earthing_system`
- `voltage_level_kv`, `fault_resistance_ohm` (optional)
- `operator`, `description` (optional)
- `items`: list of `MeasurementItem`

## MeasurementItem
Supports polar or rectangular representation. The model enforces consistency with an event hook.

Fields:
- `id` (int, primary key)
- `measurement_id` / `measurement` (FK to `Measurement`)
- `measurement_type`:
  - Voltages: `prospective_touch_voltage`, `touch_voltage`, `earth_potential_rise`, `step_voltage`, `transferred_potential`
  - Currents: `earth_fault_current`, `earthing_current`, `shield_current`
  - Impedance and resistance: `earthing_impedance`, `earthing_resistance`
  - Soil: `soil_resistivity`
- Value fields (polar): `value`, `value_angle_deg`
- Value fields (rectangular): `value_real`, `value_imag`
- Metadata: `unit`, `frequency_hz`, `measurement_distance_m`, `distance_to_current_injection_m`, `additional_resistance_ohm`, `input_impedance_ohm`, `description`

### Soil resistivity data conventions
- Wenner: store spacing `a` in `measurement_distance_m`.
- Schlumberger: by default store AB/2 in `measurement_distance_m` and MN/2 in `distance_to_current_injection_m`.
- If you store full AB or full MN, set `ab_is_full=True` or `mn_is_full=True` in analytics and CLI.
- If the stored value is resistivity, use a unit like `ohm-m`.
- If the stored value is resistance, use a unit like `ohm` and set `value_kind="resistance"` when analyzing.

## Consistency rules
- If only `value_real` and `value_imag` are provided, magnitude and angle are computed automatically.
- If `value` and `value_angle_deg` are provided, real and imag parts are computed.
- At least one representation must be present or insertion raises `ValueError`.

## Relationships and usage
- A `Measurement` can exist without a `Location`, but most workflows create both.
- Items are always attached to a `Measurement`.
- The CLI and API mirror this structure: create a measurement, then create items.
