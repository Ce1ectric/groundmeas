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
