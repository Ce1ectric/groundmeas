# API Reference

Docstrings follow the pandas/PEP 257 convention. Call `groundmeas.db.connect_db(path)` once per process before using database-backed functions.

## Database (`groundmeas.db`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `connect_db(path, echo=False)` | Initialize/open SQLite; create tables. | `path` file path; `echo` log SQL |
| `create_measurement(data)` | Insert measurement (optional nested `location`). Returns ID. | |
| `create_item(data, measurement_id)` | Insert item linked to a measurement. Returns ID. | |
| `read_measurements(where=None)` | Raw WHERE string; returns records + IDs (with items, location). | |
| `read_measurements_by(**filters)` | Filtered read; supports `__lt/__lte/__gt/__gte/__in/__ne`. | |
| `read_items_by(**filters)` | Filtered read for items; same suffix rules. | |
| `update_measurement(measurement_id, updates)` | Update measurement (nested `location` allowed). | Returns bool |
| `update_item(item_id, updates)` | Update one item. | Returns bool |
| `delete_measurement(measurement_id)` | Delete measurement and items. | Returns bool |
| `delete_item(item_id)` | Delete one item. | Returns bool |

## Models (`groundmeas.models`)
| Object | Key fields | Notes |
| --- | --- | --- |
| `Location` | `id`, `name`, `latitude`, `longitude`, `altitude`, `measurements` | Site metadata |
| `Measurement` | `id`, `timestamp`, `location`, `method`, `asset_type`, `voltage_level_kv`, `fault_resistance_ohm`, `operator`, `description`, `items` | Event tied to a location |
| `MeasurementItem` | `id`, `measurement_id`, `measurement_type`, `value`, `value_angle_deg`, `value_real`, `value_imag`, `unit`, `frequency_hz`, `measurement_distance_m`, `distance_to_current_injection_m`, `additional_resistance_ohm`, `input_impedance_ohm`, `description` | Data point with polar/rectangular support |
| `_compute_magnitude` | Auto-computes missing polar/rectangular parts; raises `ValueError` if neither is present. | SQLAlchemy event |

## Analytics (`groundmeas.analytics`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `impedance_over_frequency(measurement_ids)` | Map freq → \|Z\| (or per measurement). | Accepts single ID or list |
| `real_imag_over_frequency(measurement_ids)` | Map freq → `{real, imag}` (or per measurement). | |
| `distance_profile_value(measurement_id, measurement_type="earthing_impedance", algorithm="maximum", window=3)` | Reduce distance–value profile via algorithm (`maximum`, `62_percent`, `minimum_gradient`, `minimum_stddev`, `inverse`). | Inverse fits `1/Z = a*(1/d) + b` |
| `rho_f_model(measurement_ids)` | Fit rho–f coefficients `(k1..k5)` using impedance (real/imag) + soil resistivity. | Requires overlap in freq |
| `voltage_vt_epr(measurement_ids, frequency=50)` | EPR and touch/prospective voltages per ampere. | Needs impedance + current at `frequency` |
| `shield_currents_for_location(location_id, frequency_hz=None)` | List shield-current items for a location. | Optional frequency filter |
| `calculate_split_factor(earth_fault_current_id, shield_current_ids)` | Compute split factor and vector sums (mag/angle/real/imag). | Provide shield IDs with consistent reference |
| `value_over_distance(measurement_ids, measurement_type="earthing_impedance")` | Map distance → value (or per measurement). | |
| `value_over_distance_detailed(...)` | List of `{distance, value, frequency}` (or dict per measurement). | |
| `_current_item_to_complex(item)` | Convert an item to a complex current (A). | Prefers real/imag, else magnitude/angle |

## Export (`groundmeas.export`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `export_measurements_to_json(path, **filters)` | JSON export (filters match `read_measurements_by`). | |
| `export_measurements_to_csv(path, **filters)` | One row per measurement; items as JSON string column. | |
| `export_measurements_to_xml(path, **filters)` | XML with nested `<items>`. | |

## Matplotlib Plots (`groundmeas.plots`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `plot_imp_over_f(measurement_ids, normalize_freq_hz=None)` | \|Z\| vs frequency (optional normalization). | |
| `plot_rho_f_model(measurement_ids, rho_f, rho=100)` | Measured vs rho–f model curves. | `rho`: single or list |
| `plot_voltage_vt_epr(measurement_ids, frequency=50)` | Bars for EPR/Vtp/Vt. | |
| `plot_value_over_distance(measurement_ids, measurement_type="earthing_impedance")` | Value vs distance. | |

## Plotly (`groundmeas.vis_plotly`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `plot_imp_over_f_plotly(...)` | Interactive \|Z\| vs frequency. | |
| `plot_rho_f_model_plotly(...)` | Measured + rho–f model curves. | |
| `plot_voltage_vt_epr_plotly(...)` | Bars for EPR/Vtp/Vt. | |
| `plot_value_over_distance_plotly(..., show_all_frequencies=False, target_frequency=None)` | Distance plots; optionally split by frequency. | |

## Maps (`groundmeas.map_vis`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `generate_map(measurements, output_file="measurements_map.html", open_browser=True)` | Folium map for measurements with valid GPS. | |

## OCR Import (`groundmeas.vision_import`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `_normalize_number`, `_parse_value_angle_unit`, `_read_api_key`, `_image_to_base64`, `preprocess_image` | Internal helpers. | |
| `ocr_image(path, lang="eng", provider_model="tesseract"| "openai:<model>"| "ollama:<model>", api_key_env="OPENAI_API_KEY", timeout=120, max_dim=1400)` | Run OCR. | |
| `parse_measurement_rows(text)` | Extract distance–current–voltage–impedance rows; normalize units; infer impedance if possible. | |
| `_relative_spread(values)`, `_interpolate_at_distance(rows, target)` | Helper calculations. | |
| `build_items_from_rows(measurement_id, rows, measurement_type, frequency_hz, distance_to_current_injection_m=None)` | Assemble payloads for impedance, earthing currents, prospective touch voltage near 1 m. | |
| `import_items_from_images(images_dir, measurement_id, measurement_type="earthing_impedance", frequency_hz=50, distance_to_current_injection_m=None, ocr_provider="tesseract", api_key_env="OPENAI_API_KEY", ocr_timeout=120, ocr_max_dim=1400)` | Batch OCR import; returns summary (`created_item_ids`, `skipped`, `parsed_row_count`). | |

## CLI helpers (`groundmeas.cli`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `_resolve_db`, `_save_default_db` | DB path resolution and persistence. | |
| `_prompt_text`, `_prompt_float`, `_prompt_choice` | Prompt helpers (prompt_toolkit). | |
| `_measurement_types`, `_existing_locations`, `_existing_measurement_values`, `_existing_item_units`, `_existing_item_values` | Suggestion helpers from DB. | |
| `_load_measurement`, `_load_item`, `_dump_or_print`, `_print_measurement_summary` | ID loading, JSON output, console summary. | |
| `_main` | Entry point for `python -m groundmeas.cli`. | |

## Dashboard (`groundmeas.dashboard`)
| Function | Description | Key args/notes |
| --- | --- | --- |
| `resolve_db_path()` | Resolve DB path from env/config/default. | |
| `init_db()` | Connect DB; show errors in UI. | |
| `main()` | Streamlit app layout (map, selection, tabs). | |

## Extension
No additional extension modules; all analytics are in `groundmeas.services.analytics`.
