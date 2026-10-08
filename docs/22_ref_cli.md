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
| `import-omicron` | `--location`, `--asset-type`, `--ze`, `--ut`, `--transferred`, `--soil`, `-D`, options | console summary | Import OMICRON COMPANO 100 / HGT1 exports ([details](17_instrument_import.md)). |

## Analytics
| function | input | output | description |
| --- | --- | --- | --- |
| `distance-profile` | `MEAS_ID`, `--type`, `--algorithm`, `--window`, `--frequency/-f`, `--conservative` | console or JSON | Reduce a distance profile. |
| `impedance-over-frequency` | `MEAS_ID...`, `--profile-algorithm` | console or JSON | Frequency to impedance map. |
| `real-imag-over-frequency` | `MEAS_ID...` | console or JSON | Frequency to real and imag map. |
| `rho-f-model` | `MEAS_ID...` | console or JSON | Fit rho-f coefficients. |
| `voltage-vt-epr` | `MEAS_ID...`, `--frequency`, `--profile-algorithm`, `--additional-resistance` | console or JSON | EPR and touch voltage summary. |
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

## Tower campaigns (`gm-cli towers`)
| function | input | output | description |
| --- | --- | --- | --- |
| `towers run` | `--config`, `--calc`, `--print`, `--zip`, `--stats`, `--worker`, `--no-pdf`, `-v/-q` | files | Evaluate a campaign (JSON, Excel, HTML/PDF protocols, ZIP, statistics). |
| `towers demo` | `DIR`, `--language`, `--overwrite` | folder | Synthetic demo campaign. |
| `towers example-config` | `PATH`, `--overwrite` | JSON file | Example configuration. |
| `towers flatten` | `SRC`, `DEST`, `--apply`, `--report`, `--only`, patterns | files | Copy a nested delivery into the flat layout (dry run by default). |
| `towers import-db` | `--config`, `--dry-run`, `--reimport`, `--timezone`, `--voltage-level-kv`, `--per-frequency` | database | Copy the instrument data of a campaign into the database. |
| `towers install-browser` | none | browser | Download Playwright's Chromium (needs `groundmeas[pdf]`). |

The `towers` commands do not open the database, except `towers import-db`.
See [Tower campaigns – Command line](towers/cli.md).

## Maps and dashboard
| function | input | output | description |
| --- | --- | --- | --- |
| `map` | `--measurement-id/-m`, `--out`, `--open-browser` | HTML file | Generate a Folium map. |
| `dashboard` | none | Streamlit app | Launch the dashboard. |

## Configuration
| function | input | output | description |
| --- | --- | --- | --- |
| `set-default-db` | `PATH` | console confirmation | Store default DB path. |

### `set-default-db` end-to-end (1.5.2+)

`gm-cli set-default-db PATH` writes the absolute form of `PATH` into the JSON
file at `~/.config/groundmeas/config.json` under the `"db_path"` key. The
config directory is created automatically if it does not yet exist.

**Resolution order** for the active database path (highest priority first):

1. The `GROUNDMEAS_DB` environment variable, if set and non-empty.
2. The `"db_path"` entry in `~/.config/groundmeas/config.json`.
3. The fallback `groundmeas.db` in the current working directory.

The dashboard, the CLI and the Streamlit UI all share this resolution chain
via :func:`groundmeas.ui.dashboard.resolve_db_path` (or its CLI equivalent),
so a default written via `set-default-db` is honoured anywhere.

```bash
# Persist the default database path for this user.
gm-cli set-default-db ~/projects/groundmeas/data/site-A.db

# Verify which path the CLI will pick (env-var overrides config).
GROUNDMEAS_DB=~/projects/groundmeas/data/site-B.db gm-cli read-measurements
```

To inspect the active configuration interactively:

```bash
cat ~/.config/groundmeas/config.json
```

This section documents the resolution chain and env-var precedence in one
place.

## Database lifecycle

The CLI uses :func:`groundmeas.connect_db` under the hood. Two notes on
its behaviour:

1. **Re-connect / force override.** ``connect_db(path)`` refuses to run
   when an engine is already initialised in the same Python process and
   raises :class:`RuntimeError`. Pass ``force=True`` to dispose the
   existing engine and rebind to a new path:

   ```python
   import groundmeas as gm

   gm.connect_db("first.db")
   # ... work ...
   gm.connect_db("second.db", force=True)   # replaces the engine
   ```

   The ``gm-cli`` commands invoke ``connect_db`` once per process and
   therefore do not normally need ``force=True``; the override is for
   long-lived Python sessions (Jupyter, Streamlit, FastAPI workers).

2. **Read-only filesystems.** ``connect_db`` performs a best-effort
   writability probe on the parent directory of ``path`` and raises
   :class:`RuntimeError` (``"... not writable"``) before SQLAlchemy is
   touched. NextCloud-/Dropbox-synced folders that are temporarily
   marked read-only and Streamlit-Cloud containers are the typical
   triggers. Move the database to a writable directory, point
   ``GROUNDMEAS_DB`` at it, and re-run the CLI command.

   When invoking the dashboard via ``gm-cli dashboard`` the same error
   surfaces as an ``st.error`` panel and the dashboard halts before any
   downstream query runs.

3. **Explicit teardown.** Use :func:`groundmeas.disconnect_db` to
   release the engine deterministically (e.g. between unit tests or in
   notebooks that switch between databases). The function is idempotent
   and safe to call even if no engine is currently bound.
