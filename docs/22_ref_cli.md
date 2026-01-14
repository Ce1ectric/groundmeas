# CLI Reference (gm-cli)

All commands accept `--db PATH` or `GROUNDMEAS_DB`. Default order is `GROUNDMEAS_DB`, `~/.config/groundmeas/config.json`, then `./groundmeas.db`.

## Data management
| function | input | output | description |
| --- | --- | --- | --- |
| `add-measurement` | prompts for location, method, asset, metadata | console summary | Interactive measurement creation. |
| `list-measurements` | none | console table | List measurements with basic metadata. |
| `list-items` | `MEAS_ID`, `--type` | console table | List items for a measurement. |
| `add-item` | `MEAS_ID`, prompts | console summary | Interactive item creation. |
| `edit-measurement` | `MEAS_ID`, prompts | console summary | Interactive measurement edit. |
| `edit-item` | `ITEM_ID`, prompts | console summary | Interactive item edit. |
| `delete-measurement` | `MEAS_ID`, `--yes/-y` | console confirmation | Delete measurement and items. |
| `delete-item` | `ITEM_ID`, `--yes/-y` | console confirmation | Delete one item. |

## Import and export
| function | input | output | description |
| --- | --- | --- | --- |
| `import-json` | `PATH` | console summary | Import measurements from JSON file or folder. |
| `export-json` | `OUT.json`, `--measurement-id/-m` | JSON file | Export measurements to JSON. |
| `import-from-images` | `MEAS_ID`, `IMAGES_DIR`, options | console or JSON | OCR import from images. |

## Analytics
| function | input | output | description |
| --- | --- | --- | --- |
| `distance-profile` | `MEAS_ID`, `--type`, `--algorithm`, `--window` | console or JSON | Reduce a distance profile. |
| `impedance-over-frequency` | `MEAS_ID...` | console or JSON | Frequency to impedance map. |
| `real-imag-over-frequency` | `MEAS_ID...` | console or JSON | Frequency to real and imag map. |
| `rho-f-model` | `MEAS_ID...` | console or JSON | Fit rho-f coefficients. |
| `voltage-vt-epr` | `MEAS_ID...`, `--frequency` | console or JSON | EPR and touch voltage summary. |
| `shield-currents` | `LOCATION_ID`, `--frequency` | console or JSON | List shield currents. |
| `calculate-split-factor` | `--earth-fault-id`, `--shield-id` | console or JSON | Split factor and currents. |
| `soil-profile` | `MEAS_ID`, options | console or JSON | Depth-resistivity profile. |
| `soil-model` | `--rho`, `--thickness`, options | console or JSON | Layered model and optional simulation. |
| `soil-inversion` | `MEAS_ID`, options | console or JSON | Invert layered model. |

## Plotting
| function | input | output | description |
| --- | --- | --- | --- |
| `plot-impedance` | `MEAS_ID...`, `--normalize`, `--out` | image file | Impedance vs frequency plot. |
| `plot-rho-f-model` | `MEAS_ID...`, `--rho-f`, `--rho`, `--out` | image file | Rho-f model plot. |
| `plot-voltage-vt-epr` | `MEAS_ID...`, `--frequency`, `--out` | image file | EPR and touch voltage plot. |
| `plot-soil-model` | `--rho`, `--thickness`, `--max-depth`, `--out` | image file | Layered soil model plot. |
| `plot-soil-inversion` | `MEAS_ID`, options, `--out` | image file | Observed vs fitted resistivity plot. |

## Maps and dashboard
| function | input | output | description |
| --- | --- | --- | --- |
| `map` | `--measurement-id/-m`, `--out`, `--open-browser` | HTML file | Generate a Folium map. |
| `dashboard` | none | Streamlit app | Launch the dashboard. |

## Configuration
| function | input | output | description |
| --- | --- | --- | --- |
| `set-default-db` | `PATH` | console confirmation | Store default DB path. |
