# Dashboard

The Streamlit dashboard provides interactive exploration, plotting, and map-based selection of measurements.

## Launch
```bash
gm-cli dashboard
```
The command resolves the database path in this order: `GROUNDMEAS_DB`, `~/.config/groundmeas/config.json`, then `./groundmeas.db`.

## Layout
- **Sidebar filters**: multi-select asset types; shows how many measurements match.
- **Map**: Folium map with color-coded markers (e.g., red for substations, green for towers). Click a marker to select a measurement. Enable “Multi-select mode” to add multiple sites without replacing the previous selection.
- **Selection list**: multiselect widget listing current selection by measurement ID.
- **Tabs**:
  - *Measurement Items*: JSON view of the selected measurement(s) and a table of items (ID, type, value, unit, frequency, distance).
  - *Impedance vs Frequency*: Plotly chart of |Z| over frequency for the selection; click “Generate Impedance Plot”.
  - *Rho-f Model*: Fits coefficients for the selection, displays them, and overlays model curves on measured data.
  - *Voltage / EPR*: Bar chart for EPR, prospective touch voltage (min/max), and touch voltage (min/max) at a chosen frequency.
  - *Value vs Distance*: Distance plots for impedance/resistance/soil resistivity. Optionally show all frequencies or choose one frequency to filter.

## Tips
- Keep a consistent `frequency_hz` across related impedance/current/voltage items so plots and analytics align.
- Ensure items include `measurement_distance_m` when you want Fall-of-Potential or soil profile plots.
- Use the CLI to add or adjust data while the dashboard is open; refresh the browser to reload.

## Troubleshooting
- If the dashboard cannot connect to the DB, check `GROUNDMEAS_DB` or the config file and rerun.
- For missing data warnings in plots, confirm that items of the requested type and frequency exist.
