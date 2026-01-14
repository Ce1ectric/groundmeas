# Groundmeas

Groundmeas is a toolkit for managing, analyzing, and visualizing grounding (earthing) measurements. It combines a SQLite data layer, a Python API, a CLI, a Streamlit dashboard, and physics-aware analytics for field work and reporting.

## What this guide covers
- Quickstart for CLI and Python workflows
- Data model for locations, measurements, and measurement items
- Step-by-step tutorials for creating, reading, editing, and importing data
- Analytics for impedance, touch voltages, split factor, and soil modeling
- Dashboard usage and plotting
- API and CLI reference

## Quick mental model
- You create a measurement with a method and optional location.
- You add measurement items (impedance, current, voltage, soil resistivity) with metadata.
- Analytics functions read items from the database and compute results.
- Plot helpers and the dashboard visualize those results.

## Physical background

Earthing impedance relates Earth Potential Rise to injected current.

$$
Z_E(f) = \frac{V_{EPR}(f)}{I_E(f)}
$$

Earth Potential Rise is computed from impedance and current.

$$
EPR = Z_E \cdot I_E
$$

The rho-f model links impedance to soil resistivity and frequency.

$$
Z(\rho, f) = k_1 \cdot \rho + (k_2 + j k_3) \cdot f + (k_4 + j k_5) \cdot \rho \cdot f
$$

Soil resistivity surveys use Wenner or Schlumberger arrays and feed the multilayer soil model used later in analytics.

## Navigation
- Quickstart: `02_quickstart.md`
- Tutorials: `10_tutorial_intro.md` and the tutorial series
- Reference: `20_ref_intro.md`, `21_ref_api.md`, `22_ref_cli.md`
