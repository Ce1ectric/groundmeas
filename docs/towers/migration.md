# Migration from tower-grounding-measurement

The evaluation of tower campaigns was developed as the separate package
`tower-grounding-measurement` (TGM, last version 0.2). Its complete
functionality is part of groundmeas since 2026-10, and TGM is no longer
developed. Campaign folders, configuration files and workbooks can be used
unchanged; the results are the same.

## What stays the same

- **Campaign layout, configuration keys and workbooks** – no change.
- **Results** – JSON files (same German keys and values), Excel summary,
  protocols and statistics report. On the demo campaign and on a measured
  tower the JSON files and workbooks are identical, the PDF protocols are
  pixel-identical when the same matplotlib version is installed. Touch
  voltages in the results are still rounded up (`ceil`).
- **The 62 % evaluation** with its conservative corrections, the touch-voltage
  scaling, the line model and the line-protection table.

## Installation

```console
$ pip uninstall tower-grounding-measurement
$ pip install "groundmeas[pdf]"      # the extra adds Playwright for PDF protocols
$ gm-cli towers install-browser       # if Playwright's Chromium is not installed yet
```

!!! warning "Python 3.14"

    groundmeas needs Python 3.14 or newer (TGM ran on 3.11+) and brings more
    dependencies (database, dashboard, maps, OCR). Without the `pdf` extra
    everything except the PDF export works; `--no-pdf` writes HTML protocols.

## Commands

| tower-grounding-measurement | groundmeas |
| --- | --- |
| `tower-grounding-measurement --config C` | `gm-cli towers run --config C` |
| `… --calc --print --zip --stats --worker N --no-pdf -v -q` | same options on `gm-cli towers run` |
| `tower-grounding-measurement --demo DIR --language de` | `gm-cli towers demo DIR --language de` |
| `tower-grounding-measurement --install-browser` | `gm-cli towers install-browser` |
| `tower-grounding-measurement --version` | `python -c "import groundmeas; print(groundmeas.__version__)"` |
| `python -m tower_grounding_measurement …` | `python -m groundmeas.ui.cli towers …` |
| `config.example.json` in the package | `gm-cli towers example-config PATH` |
| `python scripts/flatten_measurements.py SRC DEST [--apply] [--only A B]` | `gm-cli towers flatten SRC DEST [--apply] [--only A --only B]` |
| – | `gm-cli towers import-db` (new: [campaign → database](database.md)) |

The exit codes (0 success, 1 processing error, 2 invalid usage or
configuration) are unchanged.

## Environment variables

| tower-grounding-measurement | groundmeas |
| --- | --- |
| `TOWER_GROUNDING_CONFIG` | `GROUNDMEAS_TOWER_CONFIG` (the old name is still read) |
| `TOWER_GROUNDING_BROWSER` | `GROUNDMEAS_BROWSER` (the old name is still read) |

## Python imports

| tower-grounding-measurement | groundmeas |
| --- | --- |
| `tower_grounding_measurement` (top-level names) | `groundmeas.towers` (readers: `groundmeas.instruments`) |
| `….device_reader.omicron_reader` | `groundmeas.instruments` (`groundmeas.instruments.omicron`) |
| `….device_reader.device_reader` | `groundmeas.towers.files` |
| `….analyzer.analyzer` | `groundmeas.towers.analysis` |
| `….analyzer.line_protection` | `groundmeas.towers.line_protection` |
| `….analyzer.summary_storage` | `groundmeas.towers.campaign` |
| `….config.config_reader` | `groundmeas.towers.config` |
| `….config.export_format_reader` (`DEFAULT_EXPORT_FORMAT`) | `groundmeas.towers.config` (`EXPORT_TEMPLATE`, `read_export_json`) |
| `….data_import_export.json_data` | `groundmeas.towers.results` |
| `….data_import_export.mat_plotter` | `groundmeas.towers.plots` |
| `….protocol_printer.print_protocol` | `groundmeas.towers.protocol` |
| `….protocol_printer.html_printer`, `….pdf_zipper` | `groundmeas.towers.pdf` |
| `….stats.asset_report` | `groundmeas.towers.stats` |
| `….i18n`, `….naming`, `….paths`, `….demo` | `groundmeas.towers.i18n`, `.naming`, `.paths`, `.demo` |
| `….cli` | `groundmeas.towers.cli` (typer app) |

Function and class names are unchanged. The private pre-0.2 aliases of TGM
(`_find_ut_file`, `_norm_tower`, …) were removed; use the public names
(`find_touch_voltage_file`, `normalize_tower_id`, …). Log messages go to the
logger `groundmeas` instead of `tower_grounding_measurement`.

The readers return more than before: `CompanoXMLReader.read_fall_of_potential()`
gives the complex values at both test frequencies,
`read_reduction_factor()` the clamp readings, `read_soil_resistivity()` the
readings with their electrode geometry and `get_report_timestamp()` the time
stamp (see [Import from OMICRON instruments](../17_instrument_import.md)).
`get_impedance_to_ground_dataframe()` and `get_soil_resistivity()` return the
same data as before.

## Small differences in the output folder

- The protocol stylesheet next to the HTML files is called `protocol.css`
  (formerly `styles_template.css`).
- Diagrams may differ in anti-aliasing between matplotlib versions; groundmeas
  pins its own matplotlib range.
