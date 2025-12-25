# Analytics

Groundmeas provides physics-aware analytics for impedance profiles, touch voltages, shield currents, and model fitting. Functions are available via both the Python API (`groundmeas.analytics`) and CLI commands.

## Core formulas

Earthing impedance:

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

Earth Potential Rise:

$$
EPR = Z_E \cdot I_E
$$

Rho–f model:

$$
Z(\rho, f) = k_1 \cdot \rho + (k_2 + j k_3) \cdot f + (k_4 + j k_5) \cdot \rho \cdot f
$$

Inverse extrapolation (Fall-of-Potential):

$$
\frac{1}{Z} = a \cdot \frac{1}{d} + b
$$

## Distance profile reduction
Function: `distance_profile_value(measurement_id, measurement_type="earthing_impedance", algorithm=..., window=3)`

Algorithms and when to use them:
- `maximum`: conservative; picks the largest measured value.
- `62_percent`: classic Fall-of-Potential for homogeneous soil; needs `distance_to_current_injection_m`.
- `minimum_gradient`: finds the flattest segment (|dZ/dd| minimal); good for mildly noisy curves.
- `minimum_stddev`: sliding window with lowest variance, then takes its peak; robust to noise/outliers.
- `inverse`: fits the inverse relation above and evaluates at infinite distance; use when measurements extend far from the electrode.

CLI: `gm-cli distance-profile MEAS_ID --type earthing_impedance --algorithm minimum_gradient`

## Impedance and real/imag over frequency
Functions:
- `impedance_over_frequency(measurement_ids)`
- `real_imag_over_frequency(measurement_ids)`

CLI:
- `gm-cli impedance-over-frequency MEAS_ID [--json-out file]`
- `gm-cli real-imag-over-frequency MEAS_ID [--json-out file]`

Use cases: plotting Bode-like curves, preparing data for the rho–f fit, comparing multiple measurements.

## Rho–f fitting
Function: `rho_f_model(measurement_ids)` → `(k1, k2, k3, k4, k5)`

Requirements: overlapping impedance data (real/imag) and soil resistivity items. The least-squares fit enforces a real impedance at f=0 via the k1·rho term.

CLI: `gm-cli rho-f-model ID1 ID2 ... [--json-out file]`

## Touch voltages and EPR
Function: `voltage_vt_epr(measurement_ids, frequency=50)`

Inputs:
- `earthing_impedance` at the specified frequency
- `earthing_current` at the same frequency
- Optional: `prospective_touch_voltage`, `touch_voltage`

Outputs per measurement:
- `epr`
- `vtp_min`, `vtp_max` (if prospective touch voltage present)
- `vt_min`, `vt_max` (if touch voltage present)

CLI: `gm-cli voltage-vt-epr MEAS_ID --frequency 50 [--json-out file]`

## Shield currents and split factor
Functions:
- `shield_currents_for_location(location_id, frequency_hz=None)`
- `calculate_split_factor(earth_fault_current_id, shield_current_ids)`

Purpose: quantify how much of the earth fault current is diverted through cable shields versus the local earthing system.

CLI:
- `gm-cli shield-currents LOCATION_ID [--frequency Hz]`
- `gm-cli calculate-split-factor --earth-fault-id ID --shield-id ID1 --shield-id ID2 ...`

Output includes magnitude/angle and real/imag components for shield sum, earth fault current, and local earthing current, plus the split factor.

## Distance-based mappings
Functions:
- `value_over_distance(measurement_ids, measurement_type="earthing_impedance")`
- `value_over_distance_detailed(...)`

Use for plotting Fall-of-Potential or soil profiles. See plotting helpers below.

## Plotting helpers (analytics outputs)
- `plot_imp_over_f`, `plot_rho_f_model`, `plot_voltage_vt_epr`, `plot_value_over_distance` (Matplotlib)
- Plotly equivalents in `groundmeas.vis_plotly` for interactive use and in the dashboard.

CLI plot commands:
- `plot-impedance`
- `plot-rho-f-model`
- `plot-voltage-vt-epr`

## Example (Python)
```python
from groundmeas.db import connect_db
from groundmeas.analytics import (
    distance_profile_value,
    impedance_over_frequency,
    rho_f_model,
    voltage_vt_epr,
)

connect_db("groundmeas.db")

dp = distance_profile_value(1, measurement_type="earthing_impedance", algorithm="minimum_gradient")
print("Characteristic impedance:", dp["result_value"], "at", dp["result_distance_m"], "m")

imp = impedance_over_frequency([1,2])
coeffs = rho_f_model([1,2])
print("Rho–f coefficients:", coeffs)

vt = voltage_vt_epr(1, frequency=50.0)
print("EPR and touch voltages:", vt)
```
