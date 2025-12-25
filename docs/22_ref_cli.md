# CLI Reference (gm-cli)

All commands accept `--db PATH` (or `GROUNDMEAS_DB` or `~/.config/groundmeas/config.json`). Default DB is `./groundmeas.db`.

## Data management
| Command | Description | Key arguments |
| --- | --- | --- |
| `add-measurement` | Interactive wizard to create a measurement and items. | none |
| `list-measurements` | Summary list `[id] location \| method \| asset \| items`. | none |
| `edit-measurement MEAS_ID` | Interactive edit with current values prefilled. | `MEAS_ID` |
| `delete-measurement MEAS_ID` | Delete measurement and items. | `--yes/-y` to skip prompt |
| `add-item MEAS_ID` | Add one item (magnitude/angle or real/imag; distance optional). | `MEAS_ID` |
| `list-items MEAS_ID` | Tabular items for a measurement. | `--type TYPE` optional |
| `edit-item ITEM_ID` | Edit one item; auto-detects representation. | `ITEM_ID` |
| `delete-item ITEM_ID` | Delete one item. | `--yes/-y` |

## Import / Export
| Command | Description | Key arguments |
| --- | --- | --- |
| `import-json PATH` | Import from file/folder or split pairs `_measurement.json` + `_items.json`. | `PATH` |
| `export-json OUT.json` | Export measurements with items. | `--measurement-id ID` (repeatable) |
| `import-from-images MEAS_ID IMAGES_DIR` | OCR import of distance–current–voltage–impedance tables from images. | `--type earthing_impedance|earthing_resistance`; `--frequency 50|dir`; `--ocr tesseract|openai:<model>|ollama:<model>`; `--injection-distance M`; `--json-out FILE` |

## Analytics
| Command | Description | Key arguments |
| --- | --- | --- |
| `distance-profile MEAS_ID` | Reduce distance–value profile to one value. | `--type TYPE`; `--algorithm maximum|62_percent|minimum_gradient|minimum_stddev|inverse`; `--window N`; `--json-out FILE` |
| `impedance-over-frequency MEAS_ID...` | Map of freq → |Z|. | `--json-out FILE` |
| `real-imag-over-frequency MEAS_ID...` | Map of freq → {real, imag}. | `--json-out FILE` |
| `rho-f-model MEAS_ID...` | Fit rho–f coefficients. | `--json-out FILE` |
| `voltage-vt-epr MEAS_ID...` | EPR and touch voltages per ampere. | `--frequency F`; `--json-out FILE` |
| `shield-currents LOCATION_ID` | List shield currents at a location. | `--frequency F`; `--json-out FILE` |
| `calculate-split-factor` | Compute split factor and local earthing current. | `--earth-fault-id ITEM_ID`; `--shield-id ITEM_ID` (repeatable); `--json-out FILE` |

## Plotting
| Command | Description | Key arguments |
| --- | --- | --- |
| `plot-impedance MEAS_ID...` | Matplotlib |Z| vs frequency. | `--normalize FREQ`; `--out FILE` |
| `plot-rho-f-model MEAS_ID...` | Overlay measured vs rho–f model. | `--rho-f k1 k2 k3 k4 k5`; `--rho RHO` (repeatable); `--out FILE` |
| `plot-voltage-vt-epr MEAS_ID...` | Bars for EPR/Vtp/Vt. | `--frequency F`; `--out FILE` |

## Maps and dashboard
| Command | Description | Key arguments |
| --- | --- | --- |
| `map` | Generate Folium map. | `--measurement-id ID` (repeatable); `--out FILE`; `--open-browser/--no-open-browser` |
| `dashboard` | Launch Streamlit dashboard. | none |

## Configuration
| Command | Description | Key arguments |
| --- | --- | --- |
| `set-default-db PATH` | Store default DB path in `~/.config/groundmeas/config.json`. | `PATH` |

Use `--help` with any command for full option details. `--json-out FILE` writes structured output where available.
