# Analytics

This tutorial provides detailed, function-by-function guidance for the analytics module. Each section includes background, inputs and outputs, workflows, Python API examples, CLI examples, and practical notes.

## Impedance over frequency

### Physical background
Impedance varies with frequency due to inductive and capacitive effects. Frequency curves are used for comparing measurements and fitting the rho-f model.

### Function overview
- `impedance_over_frequency` maps frequency to impedance magnitude.
- `real_imag_over_frequency` maps frequency to real and imaginary components.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `impedance_over_frequency` | measurement id or list | dict | Map frequency to impedance magnitude. |
| `real_imag_over_frequency` | measurement id or list | dict | Map frequency to real and imaginary values. |

### General workflow
1. Ensure impedance items have `frequency_hz` populated.
2. Query impedance or real/imag maps.
3. Compare curves across measurements.
4. Use the result for plotting or further modeling.

### Python API examples

Scenario A: single measurement
```python
from groundmeas.db import connect_db
from groundmeas.analytics import impedance_over_frequency

connect_db("groundmeas.db")

imp_map = impedance_over_frequency(1)
print(imp_map)
```

Scenario B: multiple measurements and real/imag
```python
from groundmeas.db import connect_db
from groundmeas.analytics import real_imag_over_frequency

connect_db("groundmeas.db")

ri_map = real_imag_over_frequency([1, 2, 3])
print(ri_map[1])
```

### CLI examples

Scenario A: single measurement
```bash
gm-cli impedance-over-frequency 1
```

Scenario B: multiple measurements
```bash
gm-cli real-imag-over-frequency 1 2 3 --json-out out.json
```

### Additional notes
- Missing `frequency_hz` values are skipped.
- If impedance values are stored as real and imag, ensure the `value` field is populated or use the real/imag function.
- Use the Plotly dashboard for quick visual comparison.

## Distance profile reduction

### Physical background
Fall-of-Potential tests measure impedance versus distance. A reduction algorithm extracts the characteristic impedance from the curve.

Inverse extrapolation formula:

$$
\frac{1}{Z} = a \cdot \frac{1}{d} + b
$$

### Function overview
- `distance_profile_value` reduces a distance profile to one value using several algorithms.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `distance_profile_value` | measurement id, algorithm, window | dict | Return characteristic value and metadata. |

### General workflow
1. Verify impedance items have `measurement_distance_m` and `value`.
2. Choose a reduction algorithm.
3. Run the reduction and inspect result distance.
4. Compare with other algorithms if needed.

### Python API examples

Scenario A: maximum method
```python
from groundmeas.db import connect_db
from groundmeas.analytics import distance_profile_value

connect_db("groundmeas.db")

result = distance_profile_value(1, algorithm="maximum")
print(result["result_value"], result["result_distance_m"])
```

Scenario B: 62 percent method
```python
from groundmeas.db import connect_db
from groundmeas.analytics import distance_profile_value

connect_db("groundmeas.db")

result = distance_profile_value(1, algorithm="62_percent")
print(result)
```

### CLI examples

Scenario A: minimum gradient
```bash
gm-cli distance-profile 1 --type earthing_impedance --algorithm minimum_gradient
```

Scenario B: inverse extrapolation
```bash
gm-cli distance-profile 1 --type earthing_impedance --algorithm inverse
```

### Additional notes
- The 62 percent method requires `distance_to_current_injection_m`.
- Use `minimum_stddev` when noise is high.
- Results depend on distance coverage; short curves can bias the fit.

## Rho-f model fitting

### Physical background
The rho-f model links impedance to soil resistivity and frequency. It uses complex coefficients fitted from data.

$$
Z(\rho, f) = k_1 \cdot \rho + (k_2 + j k_3) \cdot f + (k_4 + j k_5) \cdot \rho \cdot f
$$

### Function overview
- `rho_f_model` fits k1 to k5 from impedance and soil resistivity data.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `rho_f_model` | measurement ids | tuple | Fit coefficients k1 to k5. |

### General workflow
1. Ensure impedance data and soil resistivity data overlap in frequency.
2. Call the fit function with one or more measurements.
3. Validate coefficients by plotting model curves.

### Python API examples

Scenario A: single measurement
```python
from groundmeas.db import connect_db
from groundmeas.analytics import rho_f_model

connect_db("groundmeas.db")

k1, k2, k3, k4, k5 = rho_f_model([1])
print(k1, k2, k3, k4, k5)
```

Scenario B: combined fit
```python
from groundmeas.db import connect_db
from groundmeas.analytics import rho_f_model

connect_db("groundmeas.db")

coeffs = rho_f_model([1, 2, 3])
print(coeffs)
```

### CLI examples

Scenario A: one measurement
```bash
gm-cli rho-f-model 1
```

Scenario B: multiple measurements
```bash
gm-cli rho-f-model 1 2 3 --json-out rho_f.json
```

### Additional notes
- The fit requires real and imag impedance values plus soil resistivity values.
- If frequencies do not overlap, the fit may fail or return poor coefficients.
- Use `plot-rho-f-model` to inspect the fit visually.

## Voltage, touch voltage, and EPR

### Physical background
Earth Potential Rise follows impedance and current.

$$
EPR = Z_E \cdot I_E
$$

### Function overview
- `voltage_vt_epr` computes EPR and touch voltage summaries per measurement.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `voltage_vt_epr` | measurement id or list, frequency | dict | EPR and touch voltage summary. |

### General workflow
1. Ensure impedance and current items share the same frequency.
2. Call the function with one or more measurements.
3. Inspect EPR and voltage ranges.

### Python API examples

Scenario A: single measurement
```python
from groundmeas.db import connect_db
from groundmeas.analytics import voltage_vt_epr

connect_db("groundmeas.db")

summary = voltage_vt_epr(1, frequency=50.0)
print(summary)
```

Scenario B: multiple measurements
```python
from groundmeas.db import connect_db
from groundmeas.analytics import voltage_vt_epr

connect_db("groundmeas.db")

summary = voltage_vt_epr([1, 2], frequency=50.0)
print(summary)
```

### CLI examples

Scenario A: one measurement
```bash
gm-cli voltage-vt-epr 1 --frequency 50
```

Scenario B: multiple measurements
```bash
gm-cli voltage-vt-epr 1 2 --frequency 50 --json-out vt.json
```

### Additional notes
- If current or impedance data is missing, outputs will be incomplete.
- Use consistent units for current and impedance values.

## Shield currents and split factor

### Physical background
Earth fault current can split between cable shields and the local earthing system. The split factor quantifies that ratio.

### Function overview
- `shield_currents_for_location` lists shield current items for a location.
- `calculate_split_factor` computes the split factor and derived currents.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `shield_currents_for_location` | location id, frequency | list | Shield current items. |
| `calculate_split_factor` | earth fault item id, shield item ids | dict | Split factor and current components. |

### General workflow
1. Identify a location and available shield current items.
2. Select the earth fault current item.
3. Compute the split factor using selected shield currents.

### Python API examples

Scenario A: list shield currents
```python
from groundmeas.db import connect_db
from groundmeas.analytics import shield_currents_for_location

connect_db("groundmeas.db")

shield_items = shield_currents_for_location(location_id=1, frequency_hz=50.0)
print(shield_items)
```

Scenario B: compute split factor
```python
from groundmeas.db import connect_db
from groundmeas.analytics import calculate_split_factor

connect_db("groundmeas.db")

result = calculate_split_factor(
    earth_fault_current_id=100,
    shield_current_ids=[201, 202],
)
print(result)
```

### CLI examples

Scenario A: list shield currents
```bash
gm-cli shield-currents 1 --frequency 50
```

Scenario B: split factor
```bash
gm-cli calculate-split-factor --earth-fault-id 100 --shield-id 201 --shield-id 202
```

### Additional notes
- Use consistent reference direction and frequency across shield current items.
- Mixed polar and rectangular values are supported, but avoid mixing units.

## Value over distance mappings

### Physical background
Not applicable. These functions provide distance-based mappings for plotting and QA.

### Function overview
- `value_over_distance` returns a simple distance to value map.
- `value_over_distance_detailed` returns distance, value, and frequency points.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `value_over_distance` | measurement id or list, type | dict | Distance to value map. |
| `value_over_distance_detailed` | measurement id or list, type | list or dict | Detailed points with frequency. |

### General workflow
1. Filter by measurement type (impedance, resistance, soil resistivity).
2. Use the simple map for quick plots or checks.
3. Use the detailed map when frequency separation matters.

### Python API examples

Scenario A: simple map
```python
from groundmeas.db import connect_db
from groundmeas.analytics import value_over_distance

connect_db("groundmeas.db")

dist_map = value_over_distance(1, measurement_type="earthing_impedance")
print(dist_map)
```

Scenario B: detailed map
```python
from groundmeas.db import connect_db
from groundmeas.analytics import value_over_distance_detailed

connect_db("groundmeas.db")

points = value_over_distance_detailed([1, 2], measurement_type="earthing_impedance")
print(points[1][:3])
```

### CLI examples

Scenario A: export and inspect
```bash
gm-cli export-json out.json --measurement-id 1
```

Scenario B: list items for a specific type
```bash
gm-cli list-items 1 --type earthing_impedance
```

### Additional notes
- There is no direct CLI command for these functions; use export or list-items for equivalent data.
- Missing `measurement_distance_m` values are ignored.

## Soil resistivity profiles

### Physical background
Wenner and Schlumberger arrays estimate apparent resistivity from field measurements.

Wenner:

$$
\rho_a = 2 \pi a R
$$

Schlumberger:

$$
\rho_a = \pi \frac{AB^2 - MN^2}{4 MN} R
$$

### Function overview
- `soil_resistivity_profile_detailed` returns depth and spacing detail.
- `soil_resistivity_profile` returns depth to resistivity map.
- `soil_resistivity_curve` returns spacing to resistivity points.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `soil_resistivity_profile_detailed` | measurement id, method, options | list | Detailed depth and spacing points. |
| `soil_resistivity_profile` | measurement id, method, options | dict | Depth to resistivity map. |
| `soil_resistivity_curve` | measurement id, method, options | list | Spacing to resistivity points. |

### General workflow
1. Store soil resistivity or resistance values with spacing.
2. Choose Wenner or Schlumberger method.
3. Build a depth profile for QA.
4. Use the spacing curve for inversion.

### Python API examples

Scenario A: Wenner resistivity values
```python
from groundmeas.db import connect_db
from groundmeas.analytics import soil_resistivity_profile

connect_db("groundmeas.db")

profile = soil_resistivity_profile(2, method="wenner")
print(profile)
```

Scenario B: Schlumberger resistance values
```python
from groundmeas.db import connect_db
from groundmeas.analytics import soil_resistivity_profile_detailed

connect_db("groundmeas.db")

profile = soil_resistivity_profile_detailed(
    measurement_id=3,
    method="schlumberger",
    value_kind="resistance",
    ab_is_full=False,
    mn_is_full=False,
)
print(profile[:3])
```

### CLI examples

Scenario A: Wenner profile
```bash
gm-cli soil-profile 2 --method wenner
```

Scenario B: Schlumberger profile with resistance values
```bash
gm-cli soil-profile 3 --method schlumberger --value-kind resistance
```

### Additional notes
- By default, Schlumberger spacing uses AB/2 and MN/2. Set `ab_is_full` or `mn_is_full` if you store full spacings.
- If units are missing, `value_kind=auto` assumes resistance.

## Layered earth model and inversion

### Physical background
Layered earth models approximate soil resistivity changes with depth. Apparent resistivity curves are simulated with digital filters or an integral engine.

### Function overview
- `LayeredEarthModel` validates layer resistivities and thicknesses.
- `multilayer_soil_model` builds a layer table for reporting.
- `layered_earth_forward` simulates apparent resistivity for Wenner or Schlumberger.
- `invert_layered_earth` inverts spacing and apparent resistivity arrays.
- `invert_soil_resistivity_layers` inverts directly from stored soil items.

### Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `LayeredEarthModel` | `rho_layers`, `thicknesses_m` | object | Validated layered earth model. |
| `multilayer_soil_model` | `rho_layers`, `thicknesses_m` | dict | Layer table and parameters. |
| `layered_earth_forward` | spacings, model params | list | Simulated apparent resistivity curve. |
| `invert_layered_earth` | spacings, observed rho, params | dict | Fitted layers and misfit stats. |
| `invert_soil_resistivity_layers` | measurement id, params | dict | Invert from stored soil survey. |

### General workflow
1. Choose 1 to 3 layers based on curve complexity.
2. Set initial resistivities and thicknesses.
3. Simulate the curve to sanity check the model.
4. Run inversion and inspect misfit.
5. Increase layer count only if needed.

### Python API examples

Scenario A: forward simulation
```python
from groundmeas.analytics import layered_earth_forward

spacings = [1.0, 2.0, 4.0, 8.0]
resistivities = [100.0, 30.0]
thicknesses = [2.0]

pred = layered_earth_forward(
    spacings_m=spacings,
    rho_layers=resistivities,
    thicknesses_m=thicknesses,
    method="wenner",
)
print(pred)
```

Scenario B: inversion from stored survey
```python
from groundmeas.db import connect_db
from groundmeas.analytics import invert_soil_resistivity_layers

connect_db("groundmeas.db")

inv = invert_soil_resistivity_layers(
    measurement_id=2,
    method="wenner",
    layers=2,
    initial_rho=[120.0, 35.0],
    initial_thicknesses=[2.5],
    max_iter=40,
    damping=0.1,
)
print(inv["rho_layers"], inv["thicknesses_m"], inv["misfit"])
```

### CLI examples

Scenario A: simulate a model
```bash
gm-cli soil-model --rho 100 --rho 30 --thickness 2 \
  --method wenner --spacing 1 --spacing 2 --spacing 4
```

Scenario B: invert a model
```bash
gm-cli soil-inversion 2 --layers 2 --method wenner \
  --initial-rho 120 --initial-rho 35 \
  --initial-thickness 2.5
```

### Additional notes
- The filter forward engine assumes MN is small compared to AB for Schlumberger.
- Use `forward=integral` when MN is not negligible (requires SciPy).
- Inversion can be sensitive to initial guesses; start with 1 layer and add complexity gradually.
- Use `backend="mlx"` on Apple hardware if MLX is installed for speed.
