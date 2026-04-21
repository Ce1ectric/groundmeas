# Dashboard

This tutorial shows how to use the Streamlit dashboard for interactive analysis and plotting.

## Physical background

Not applicable. The dashboard is a user interface for the analytics already described in earlier tutorials.

## Function overview
- The dashboard uses plot functions such as `plot_imp_over_f_plotly` and `plot_soil_inversion_plotly`.
- It calls analytics functions such as `invert_soil_resistivity_layers` and `soil_resistivity_curve`.

## Inputs and outputs
| Function | Input | Output | Description |
| --- | --- | --- | --- |
| `plot_imp_over_f_plotly` | measurement ids | Plotly figure | Impedance vs frequency plot. |
| `plot_soil_inversion_plotly` | measurement id, inversion options | Plotly figure | Observed vs fitted resistivity plot. |
| `invert_soil_resistivity_layers` | measurement id, layers | dict | Fitted layered model and misfit. |
| `soil_resistivity_curve` | measurement id, method | list | Spacing vs apparent resistivity points. |

## General workflow

### Scenario A: compare impedance across sites
1. Launch the dashboard.
2. Filter by asset type in the sidebar.
3. Select multiple measurements on the map.
4. Open the Impedance vs Frequency tab and generate the plot.

### Scenario B: soil inversion and model inspection
1. Select a soil survey measurement.
2. Open the Soil Simulation tab to test a layered model.
3. Open the Soil Inversion tab and run the inversion.
4. Review the fitted curve and layer table.

## Map and location grouping

The map draws **one marker per location**, not per measurement. Sites
that were visited several times (repeat campaigns, different
frequencies, different operators) therefore no longer stack invisibly
on top of each other — the marker tooltip reports how many measurements
are stored at that site, and the popup lists their IDs.

Selecting measurements works in two steps:

1. **Click a marker on the map.** Every measurement recorded at that
   location is loaded into the *Selected Measurements for Analysis*
   dropdown. In the default mode the click replaces the previous
   selection. Tick *Multi-select mode (append to selection)* to add
   sites incrementally without losing earlier picks.
2. **Refine per site.** When a focused location carries more than one
   measurement, an extra multiselect *Pick measurements from this
   location* appears. Any measurement you remove there is dropped from
   the global selection, while measurements from other sites remain
   untouched. This lets you, for example, compare tower 17 against
   tower 42 while only using two out of five campaigns at tower 17.

Marker colours encode the asset type at a site: red for substations,
green for overhead-line towers, blue for other single types, and gray
for sites that mix several asset types.

Internally the view relies on the pure helper
`groundmeas.ui.dashboard.group_measurements_by_location`, which groups
the measurement dicts returned by `read_measurements_by()` by
`Location.id` (or by `(name, rounded lat, rounded lon)` when the id is
missing) and returns the measurement IDs, asset types and the
underlying location object for each site. The helper is covered by
unit tests in `tests/test_dashboard.py` and is safe to reuse outside
Streamlit — for example in notebooks when you need to know how many
measurements a site carries.

## Python API examples

### Scenario A: compare impedance across sites
```python
from groundmeas.db import connect_db
from groundmeas.visualization.vis_plotly import plot_imp_over_f_plotly

connect_db("groundmeas.db")

fig = plot_imp_over_f_plotly([1, 2, 3])
fig.show()
```

### Scenario B: soil inversion and model inspection
```python
from groundmeas.db import connect_db
from groundmeas.visualization.vis_plotly import plot_soil_inversion_plotly

connect_db("groundmeas.db")

fig = plot_soil_inversion_plotly(
    measurement_id=2,
    method="wenner",
    layers=2,
    initial_rho=[120.0, 35.0],
    initial_thicknesses=[2.5],
)
fig.show()
```

## CLI examples

### Scenario A: compare impedance across sites
```bash
gm-cli plot-impedance 1 2 3 --out plots/imp_over_f.png
```

### Scenario B: soil inversion and model inspection
```bash
gm-cli soil-inversion 2 --layers 2 --method wenner \
  --initial-rho 120 --initial-rho 35 \
  --initial-thickness 2.5

gm-cli plot-soil-inversion 2 --layers 2 --out plots/soil_inv.png
```

## Additional notes
- Large datasets can slow down the dashboard; use filters to reduce selection.
- If the dashboard shows missing data warnings, verify item types and frequencies.
- If soil inversion fails, check spacing values and units for soil resistivity items.
