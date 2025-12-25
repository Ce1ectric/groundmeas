# groundmeas: Grounding System Measurements & Analysis

**groundmeas** is a comprehensive Python package designed for the management, analysis, and visualization of earthing (grounding) system measurements. It provides a robust toolset for engineers and researchers to handle field data, perform complex physical analysis, and generate interactive reports.

See the full documentation here: https://ce1ectric.github.io/groundmeas/

---

## 📚 Physical Background

Understanding the behavior of grounding systems is critical for electrical safety and system performance. `groundmeas` implements several standard and advanced methods for analyzing measurement data.

### Earthing Impedance ($Z_E$)
The earthing impedance is a frequency-dependent parameter defined as the ratio of the Earth Potential Rise (EPR) to the current flowing into the earth ($I_E$).
$$ Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)} $$

### Soil Resistivity ($\rho$)
Soil resistivity is a key factor influencing the grounding resistance. It is typically measured using the Wenner or Schlumberger method and varies with depth and frequency.

### The Rho-f Model
To characterize the frequency dependence of a grounding system, `groundmeas` implements the **Rho-f Model**. This empirical model correlates the earthing impedance with soil resistivity ($\rho$) and frequency ($f$) using a linear regression approach with complex coefficients:

$$ Z(\rho, f) = k_1 \cdot \rho + (k_2 + j \cdot k_3) \cdot f + (k_4 + j \cdot k_5) \cdot \rho \cdot f $$

Where $k_1 \dots k_5$ are coefficients determined by fitting the model to measured data. This allows for the prediction of impedance behavior under varying soil conditions and frequencies.

### Determination of Earthing Impedance (Fall-of-Potential)
When measuring impedance using the Fall-of-Potential method, the challenge is to determine the "true" impedance from a distance vs. impedance profile. `groundmeas` offers multiple algorithms to extract this value:

1.  **Maximum**: Returns the highest measured value (conservative approach).
2.  **62% Rule**: Interpolates the value at 62% of the distance to the current injection point (valid for homogeneous soil).
3.  **Minimum Gradient**: Identifies the flat portion of the curve where the gradient ($\Delta Z / \Delta d$) is minimal.
4.  **Minimum Standard Deviation**: Uses a sliding window to find the region with the lowest variance (flattest part of the curve).
5.  **Inverse Extrapolation**: Fits a function $1/Z = a \cdot (1/d) + b$ to extrapolate the value at infinite distance ($d \to \infty$).

---

## 🚀 Features

*   **Data Management**: robust SQLite database with SQLModel (Pydantic) ORM for `Measurements`, `MeasurementItems`, and `Locations`.
*   **Interactive Dashboard**: A Streamlit-based web interface with:
    *   **Map Visualization**: Geospatial view of measurement locations using Folium.
    *   **Interactive Plots**: Plotly-based charts for Impedance vs. Frequency, Voltage profiles, and more.
    *   **Engineering Notation**: Automatic formatting of axis labels (e.g., $k\Omega$, $mA$).
*   **CLI (Command Line Interface)**: A powerful Typer-based CLI for all operations.
*   **Analytics**: Built-in functions for:
    *   Split factor calculation (shield currents).
    *   Touch voltage ($V_t$) and Prospective Touch Voltage ($V_{tp}$) analysis.
    *   Complex number processing (Real/Imaginary/Magnitude/Angle).
*   **Import/Export**: Support for JSON import/export, including batch processing of folders.

---

## 📦 Installation

**Prerequisites**: Python 3.12+

### Using Poetry (Recommended)
```bash
git clone https://github.com/Ce1ectric/groundmeas.git
cd groundmeas
poetry install
poetry shell
```

### Using Pip
```bash
pip install groundmeas
```

---

## 🖥️ Usage

### 1. The Command Line Interface (CLI)
The `gm-cli` tool is the main entry point for managing your data.

**Setup Database:**
By default, `groundmeas` looks for a database. You can specify one via the `--db` flag or set a default path in `~/.config/groundmeas/config.json`.

**Common Commands:**

*   **Dashboard**: Launch the interactive visualization tool.
    ```bash
    gm-cli dashboard
    ```

*   **Import Data**: Import measurements from a JSON file or a folder of JSON files.
    ```bash
    gm-cli import-json ./data/measurements/
    ```

*   **List Data**: View stored measurements.
    ```bash
    gm-cli list-measurements
    ```

*   **Analytics**: Calculate the characteristic impedance using the minimum gradient method.
    ```bash
    gm-cli distance-profile 1 --algorithm minimum_gradient
    ```

*   **Help**: See all available commands.
    ```bash
    gm-cli --help
    ```

### 2. The Interactive Dashboard
The dashboard provides a user-friendly interface to explore your data.

1.  Run `gm-cli dashboard`.
2.  **Map View**: Select measurement points on the map. Use "Multi-select mode" to compare multiple datasets.
3.  **Analysis Tabs**:
    *   **Impedance vs Frequency**: Compare frequency responses ($Z_E$).
    *   **Rho-f Model**: Fit and visualize the model parameters.
    *   **Voltage / EPR**: Analyze Earth Potential Rise and Touch Voltages ($V_t$, $V_{tp}$).
    *   **Value vs Distance**: Visualize Fall-of-Potential curves with filtering by frequency.

### 3. Python API
You can use `groundmeas` directly in your Python scripts or Jupyter notebooks.

```python
from groundmeas.db import connect_db, read_measurements_by
from groundmeas.analytics import impedance_over_frequency

# Connect to DB
connect_db("groundmeas.db")

# Fetch data
measurements, _ = read_measurements_by(location_id=1)

# Analyze
for meas in measurements:
    z_f = impedance_over_frequency(meas["id"])
    print(f"Measurement {meas['id']}: {z_f}")
```

---

## 📂 Project Structure

```
groundmeas/
├── src/groundmeas/       # Source code
│   ├── analytics.py      # Physical models and algorithms
│   ├── cli.py            # Command Line Interface definition
│   ├── dashboard.py      # Streamlit dashboard entry point
│   ├── db.py             # Database connection and CRUD
│   ├── models.py         # SQLModel data definitions
│   └── vis_plotly.py     # Plotly visualization logic
├── scripts/              # Helper scripts (e.g., release.py)
├── tests/                # Pytest suite
└── pyproject.toml        # Project configuration and dependencies
```

---

## 🤝 Contributing

1.  Fork the repository.
2.  Create a feature branch (`git checkout -b feat/new-feature`).
3.  Commit your changes.
4.  Push to the branch.
5.  Open a Pull Request.

## 📄 License

[MIT License](LICENSE)
