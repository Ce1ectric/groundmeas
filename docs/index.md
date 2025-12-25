# Groundmeas

Groundmeas is a toolkit for managing, analyzing, and visualizing grounding (earthing) measurements. It combines a SQLite/SQLModel data layer, a Python API, a Typer-based CLI, a Streamlit dashboard, and physics-aware analytics.

---

## What this guide covers
- Quickstart for CLI and Python
- Data model: locations, measurements, measurement items
- Creating, reading, editing measurements
- Import/export (JSON, CSV, XML, OCR from images)
- Analytics with physical context
- Dashboard usage
- API and CLI reference

---

## Physical background

### Earthing impedance
Ratio of Earth Potential Rise (EPR) to injected earthing current.

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

### Earth Potential Rise (EPR)
Voltage rise of the grounding system during a fault.

$$
EPR = Z_E \cdot I_E
$$

Touch voltages (prospective and actual) stem from the same quantities and must be checked against safety limits.

### Soil resistivity
Soil resistivity (rho) varies with depth and frequency and strongly influences grounding behavior. Wenner or Schlumberger arrays are typical; readings are stored as `soil_resistivity` items.

### Rho–f model
Empirical model for impedance as a function of soil resistivity and frequency.

$$
Z(\rho, f) = k_1 \cdot \rho + (k_2 + j k_3) \cdot f + (k_4 + j k_5) \cdot \rho \cdot f
$$

Coefficients k1..k5 are fitted from measured impedance and resistivity.

### Fall-of-Potential reduction
To extract a characteristic value from a distance–impedance (or voltage) profile, groundmeas offers:
- Maximum
- 62% interpolation
- Minimum gradient
- Minimum standard deviation (sliding window)
- Inverse extrapolation

See `15_analytics.md` for guidance on when to use each method.

---

## Navigation
- Quickstart: `02_quickstart.md`
- Tutorials: `10_tutorial_intro.md` and subsequent files
- Reference: `20_ref_intro.md`, `21_ref_api.md`, `22_ref_cli.md`
