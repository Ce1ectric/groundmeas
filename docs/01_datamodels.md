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

### Units

`unit` is free text, and the value is stored exactly as entered
(`118.1` with `mΩ`, `2.5` with `kA`). The analytics convert every item to
the SI base unit of its quantity before calculating, so one measurement may
mix `Ω` and `mΩ`, or `A` and `kA`. Results are always in base units.

| `measurement_type` | quantity | base unit | accepted units (examples) |
| --- | --- | --- | --- |
| `earthing_impedance`, `earthing_resistance` | resistance | Ω | `µΩ`, `mΩ`, `Ω`, `kΩ`, `MΩ`, `ohm`, `mOhm`, `kOhm`, `V/A` |
| `earth_fault_current`, `earthing_current`, `shield_current` | current | A | `µA`, `mA`, `A`, `kA` |
| `prospective_touch_voltage`, `touch_voltage`, `earth_potential_rise`, `step_voltage`, `transferred_potential` | voltage | V | `µV`, `mV`, `V`, `kV` |
| `soil_resistivity` | resistivity or resistance | Ωm or Ω | `Ωm`, `Ω·m`, `ohm-m`, `kΩm`, `Ωcm`; resistances as above |

Spelling is tolerant: micro may be written `µ` (micro sign), `μ` (Greek
mu) or `u`; ohm as `Ω`, `Ω` (ohm sign), `Ohm`, `ohm` or `ohms`; products
with or without separator (`Ω m`, `Ω·m`, `Ohm-m`, `Ohmm`). SI prefixes are
case-sensitive (`m` milli, `M` mega); `MA` and `MV` are rejected because
they are almost certainly a typing error for `mA` / `mV`.

An item without unit is taken to be in the base unit. An item whose unit is
unknown or belongs to another quantity (for example `A` on a
`touch_voltage`) is used as stored, and the analytics emit a
`groundmeas.core.units.UnitWarning`. Fix such items with
`gm-cli edit-item`. The CLI suggests the base unit of the measurement type and
warns about units it cannot convert. The rules are implemented in
`groundmeas.core.units`. For example, `parse_unit("mOhm").factor` is `0.001`.

### Soil resistivity data conventions
- Wenner: store spacing `a` in `measurement_distance_m`.
- Schlumberger: by default store AB/2 in `measurement_distance_m` and MN/2 in `distance_to_current_injection_m`.
- If you store full AB or full MN, set `ab_is_full=True` or `mn_is_full=True` in analytics and CLI.
- If the stored value is resistivity, use a resistivity unit such as `ohm-m`, `Ωm` or `kΩm`.
- If the stored value is resistance, use a resistance unit such as `ohm`, `Ω` or `mΩ`. With the default `value_kind="auto"` the unit decides; `value_kind="resistance"` / `"resistivity"` overrides it.

## Consistency rules
- If only `value_real` and `value_imag` are provided, magnitude and angle are computed automatically.
- If `value` and `value_angle_deg` are provided, real and imag parts are computed.
- At least one representation must be present or insertion raises `ValueError`.

## Relationships and usage
- A `Measurement` can exist without a `Location`, but most workflows create both.
- Items are always attached to a `Measurement`.
- The CLI and API mirror this structure: create a measurement, then create items.

## Physical context

A `Measurement` represents one field campaign at a `Location` (a site
identified by name and optional GPS coordinates). The campaign records
electrical quantities — voltages, currents, impedances, soil
resistivities — as a list of `MeasurementItem` rows. Each item carries
the physical value alongside its frequency, distances (`measurement_distance_m`,
`distance_to_current_injection_m`), unit and an optional description.
The polar / rectangular dual representation lets the same row carry
either magnitude/angle or real/imag, which is useful because field
instruments report one or the other depending on the test mode. The
`asset_type` and `method` enumerations encode the test geometry
(staged fault, current injection, Wenner or Schlumberger soil survey)
so analytics can dispatch to the correct reduction or inversion.

## Examples

Create a measurement with a nested location and a couple of items:

```python
from groundmeas import (
    connect_db, disconnect_db, create_measurement, create_item,
    read_measurements_by,
)

connect_db("groundmeas.db")
# call disconnect_db() before connect_db() again, or pass force=True.

# 1. Measurement at a substation site (location auto-created).
mid = create_measurement({
    "method": "staged_fault_test",
    "asset_type": "substation",
    "voltage_level_kv": 20.0,
    "operator": "Field team A",
    "location": {
        "name": "UMS Foo",
        "latitude": 51.5,
        "longitude": 10.2,
    },
})

# 2. An impedance item in polar form (magnitude + phase).
create_item({
    "measurement_type": "earthing_impedance",
    "value": 0.35,
    "value_angle_deg": 5.0,
    "unit": "ohm",
    "frequency_hz": 50.0,
    "measurement_distance_m": 30.0,
}, measurement_id=mid)

# 3. A Wenner soil-resistivity row with spacing in measurement_distance_m.
create_item({
    "measurement_type": "soil_resistivity",
    "value": 120.0,
    "unit": "ohm-m",
    "measurement_distance_m": 2.0,  # Wenner spacing a
}, measurement_id=mid)

# 4. Read everything for this site back.
meas, _ = read_measurements_by(asset_type="substation")
print(meas[0]["id"], len(meas[0]["items"]))
```

## API reference

The hand-curated table reference for every function is in
[Reference → API](21_ref_api.md). The `Location`, `Measurement` and
`MeasurementItem` Pydantic / SQLModel classes are re-exported on the
top-level package — for the field-by-field signature, see the
generated source via `help(groundmeas.Measurement)`.
