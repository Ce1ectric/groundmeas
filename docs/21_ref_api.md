# API Reference

All database-backed functions require `groundmeas.connect_db(path)` once per
process.

!!! note "Canonical vs. shim import paths"
    The canonical public surface lives at the top of the package
    (`groundmeas`) and inside `groundmeas.core` / `groundmeas.services`
    / `groundmeas.visualization` / `groundmeas.ui`. The bare module
    paths listed in the table below are **compatibility shims** that
    re-export everything from their canonical home. Each shim emits a
    single `DeprecationWarning` on first attribute access; the warning
    machinery lives in `groundmeas._shim.make_shim`, which is the
    single source of truth for all seven shims.

    New code should write either:

    ```python
    import groundmeas as gm
    gm.connect_db("...")
    ```

    or the canonical sub-module path:

    ```python
    from groundmeas.core.db import connect_db
    from groundmeas.services.analytics import distance_profile_value
    ```

    The shim paths will be removed in a future major release.

### Compatibility shims — full list

| Shim module | Canonical replacement | Deprecated since |
| --- | --- | --- |
| `groundmeas.db` | `groundmeas.core.db` | 1.5.2 |
| `groundmeas.analytics` | `groundmeas.services.analytics` | 1.5.2 |
| `groundmeas.models` | `groundmeas.core.models` | 1.5.2 |
| `groundmeas.plots` | `groundmeas.visualization.plots` | 1.5.2 |
| `groundmeas.export` | `groundmeas.services.export` | 1.5.2 |
| `groundmeas.vision_import` | `groundmeas.services.vision_import` | 1.5.2 |
| `groundmeas.cli` | `groundmeas.ui.cli` | 1.5.2 |

All seven shims share the implementation in
`groundmeas._shim.make_shim`. Private symbols (names starting with
`_`) raise `AttributeError` *without* emitting a deprecation warning,
mirroring how `import _name` would behave on the canonical module —
for example, `from groundmeas.db import _get_session` no longer
emits a spurious deprecation warning.

## Database (`groundmeas` / `groundmeas.core.db`)
| function | input | output | description |
| --- | --- | --- | --- |
| `connect_db` | `path`, `echo`, `force` | none | Initialize or open the SQLite database. Pass `force=True` to swap the engine after a previous `connect_db` call. |
| `disconnect_db` | none | none | Dispose the active engine. Idempotent. |
| `create_measurement` | measurement dict | measurement id | Create a measurement, optionally with nested location. |
| `create_item` | item dict, `measurement_id` | item id | Create a measurement item. |
| `read_measurements` | `where` clause | list of measurements, list of ids | Read measurements with nested items and location. |
| `read_measurements_by` | filters | list of measurements, list of ids | Read measurements with suffix operators (`__lt`, `__in`, etc). |
| `read_items_by` | filters | list of items, list of ids | Read items with suffix operators. |
| `update_measurement` | measurement id, updates | bool | Update measurement and optional location. |
| `update_item` | item id, updates | bool | Update a measurement item. |
| `delete_measurement` | measurement id | bool | Delete a measurement and its items. |
| `delete_item` | item id | bool | Delete a single item. |

## Analytics (`groundmeas` / `groundmeas.services.analytics`)
| function | input | output | description |
| --- | --- | --- | --- |
| `impedance_over_frequency` | measurement id or list | dict | Frequency to impedance map. |
| `real_imag_over_frequency` | measurement id or list | dict | Frequency to real and imag map. |
| `distance_profile_value` | measurement id, algorithm, window | dict | Reduce distance profile to one value. |
| `value_over_distance` | measurement id or list, type | dict | Distance to value map. |
| `value_over_distance_detailed` | measurement id or list, type | list or dict | Distance, value, frequency points. |
| `rho_f_model` | measurement ids | tuple | Rho-f coefficients k1 to k5. |
| `voltage_vt_epr` | measurement id or list, frequency | dict | EPR and touch voltage summary. |
| `shield_currents_for_location` | location id, frequency | list | Shield current items. |
| `calculate_split_factor` | earth fault item id, shield item ids | dict | Split factor and current components. |
| `soil_resistivity_profile` | measurement id, method, value_kind | dict | Depth to apparent resistivity map. |
| `soil_resistivity_profile_detailed` | measurement id, method, value_kind | list | Detailed depth and spacing points. |
| `soil_resistivity_curve` | measurement id, method, value_kind | list | Spacing to apparent resistivity points. |
| `multilayer_soil_model` | `rho_layers`, `thicknesses_m` | dict | Layer table from resistivities and thicknesses. |
| `layered_earth_forward` | spacings, model params | list | Simulated apparent resistivity. |
| `invert_layered_earth` | spacings, observed rho, model params | dict | Fitted layers and misfit stats. |
| `invert_soil_resistivity_layers` | measurement id, model params | dict | Invert from stored soil items. |

## Export (`groundmeas` / `groundmeas.services.export`)
| function | input | output | description |
| --- | --- | --- | --- |
| `export_measurements_to_json` | `path`, filters | none | Write measurements and items to JSON. |
| `export_measurements_to_csv` | `path`, filters | none | Write measurements to CSV with items as JSON. |
| `export_measurements_to_xml` | `path`, filters | none | Write measurements and items to XML. |

## OCR Import (`groundmeas` / `groundmeas.services.vision_import`)
| function | input | output | description |
| --- | --- | --- | --- |
| `import_items_from_images` | images dir, measurement id, options | dict | OCR import of items from images. |

## Matplotlib plots (`groundmeas` / `groundmeas.visualization.plots`)
| function | input | output | description |
| --- | --- | --- | --- |
| `plot_imp_over_f` | measurement id or list, normalize | figure | Impedance vs frequency plot. |
| `plot_rho_f_model` | measurement ids, rho_f, rho | figure | Rho-f model plot. |
| `plot_voltage_vt_epr` | measurement ids, frequency | figure | EPR and touch voltage plot. |
| `plot_value_over_distance` | measurement id or list, type | figure | Value vs distance plot. |
| `plot_soil_model` | `rho_layers`, `thicknesses_m`, max depth | figure | Layered soil model plot. |
| `plot_soil_inversion` | measurement id, inversion options | figure | Observed vs fitted resistivity plot. |

## Plotly plots (`groundmeas` / `groundmeas.visualization.vis_plotly`)
| function | input | output | description |
| --- | --- | --- | --- |
| `plot_imp_over_f_plotly` | measurement id or list, normalize | figure | Interactive impedance plot. |
| `plot_rho_f_model_plotly` | measurement ids, rho_f, rho | figure | Interactive rho-f plot. |
| `plot_voltage_vt_epr_plotly` | measurement ids, frequency | figure | Interactive EPR plot. |
| `plot_value_over_distance_plotly` | measurement id or list, options | figure | Interactive distance plot. |
| `plot_soil_model_plotly` | `rho_layers`, `thicknesses_m`, max depth | figure | Interactive soil model plot. |
| `plot_soil_inversion_plotly` | measurement id, inversion options | figure | Interactive inversion plot. |

## Maps (`groundmeas` / `groundmeas.visualization.map_vis`)
| function | input | output | description |
| --- | --- | --- | --- |
| `generate_map` | measurements, output file, open_browser | none | Generate a Folium map. |
