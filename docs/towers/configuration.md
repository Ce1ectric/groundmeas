# Configuration

A campaign is described by one JSON file, usually `config.json` next to the
data. Start from the demo (`gm-cli towers demo DIR`) or write an annotated
example with

```console
$ gm-cli towers example-config campaign-2026/config.json
```

## Which file is used

1. the path given with `--config PATH`,
2. otherwise the file named in the environment variable
   `GROUNDMEAS_TOWER_CONFIG` (the former name `TOWER_GROUNDING_CONFIG` is
   still read),
3. otherwise `config.json` in the current working directory.

## Paths

Every path may be

- **relative to the folder of the configuration file** (recommended – the
  campaign folder can then be moved, synchronised or opened on another
  operating system without changes),
- absolute (`/home/me/data`, `C:/Data` or `C:\\Data` in JSON),
- written with `~` for the home folder or with environment variables
  (`$HOME`, `${DATA}`, `%USERPROFILE%`).

Files are read as UTF-8; a byte-order mark written by Windows editors is
accepted.

## Complete example

```json
{
    "language": "en",
    "logo": "logo.png",
    "nominal_frequency_Hz": 50,
    "touch_voltages": {
        "t_s":        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 10.0],
        "U_TP_V":     [633, 528, 410, 300, 204, 170, 140, 130, 120, 107, 80],
        "U_TP_ext_V": [1878, 1561, 1270, 831, 538, 397, 327, 287, 260, 244, 80]
    },
    "directory": {
        "path_measurements": "measurements",
        "path_grid_data": "grid_data.xlsx",
        "sc_current_data_path": "short_circuit_data.xlsx",
        "measurement_description_path": "measurement_description.xlsx",
        "json_export_path": "results",
        "path_summary": "results/summary.xlsx",
        "export_path_pdf": "results/protocols.zip",
        "grounding_impedance_structure": "PREFIX_LINENUMBER_TOWER"
    },
    "contacts": {
        "evaluation_first_name": "Alex",
        "evaluation_last_name": "Example",
        "evaluation_company": "Example Grid Operator"
    },
    "default_grid_data": {
        "r": 0.66,
        "tripping_time": 0.4,
        "fault_current_kA": 12
    },
    "touch_voltage_evaluation": "with_resistor",
    "line_protection": {
        "enabled": true,
        "sheet_name": "Leitungsschutz"
    }
}
```

Keys starting with `_` (for example `_comment`) are ignored and can hold notes.
The unit of a value is given by the suffix of its key: `_V` volt, `_s`
seconds, `_kA` kiloampere, `_Hz` hertz, `_m` metre.

## Reference

### General

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `language` | `"en"` \| `"de"` | `"en"` | language of protocols, diagrams, verdicts and hints |
| `logo` | path | `""` | image shown in the protocol header (PNG, JPG or SVG); empty for none |
| `nominal_frequency_Hz` | number | `50` | power frequency the HGT1 readings are interpolated to (50 or 60 Hz) |
| `touch_voltage_evaluation` | string | `"with_resistor"` | which HGT1 readings are assessed, see below |

`touch_voltage_evaluation`

| Value | Readings used for the assessment |
| --- | --- |
| `with_resistor` | termination `2x1k` (body resistance + 1 kΩ for footwear/standing surface) |
| `without_resistor` | termination `1k` (body resistance only) – the stricter choice |
| `all` | all readings |

If the selected subset is empty (or the report has no termination column),
all readings are used.

### `touch_voltages` – permissible touch voltage

| Key | Type | Meaning |
| --- | --- | --- |
| `t_s` | list of numbers | fault durations in s |
| `U_TP_V` | list of numbers | permissible touch voltage $U_{TP}$ in V for each duration (curve *UD1*, without additional resistances) |
| `U_TP_ext_V` | list of numbers | curve with additional resistances (*UD2*); validated and stored, **not used for the assessment** |

The three lists must have the same length. Between two entries the value is
interpolated linearly; a clearing time outside the table uses the nearest end
value and logs a warning.

!!! warning "Check the curve"

    The example values are the ones used by the original project (curve
    names *UD1*/*UD2* follow EN 50341); the last point (10 s → 80 V) covers
    long clearing times in compensated networks. They are **not** a normative
    reference: take the values from the edition of EN 50522 / EN 50341 and
    the national annex you apply – the assessment depends directly on this
    table.

### `directory` – data and results

| Key | Required | Meaning |
| --- | --- | --- |
| `path_measurements` | yes | flat folder with all instrument files |
| `path_grid_data` | yes | grid-data workbook (**rewritten by `--calc`**) |
| `measurement_description_path` | yes | measurement-description workbook |
| `sc_current_data_path` | no | short-circuit workbook (one sheet per line, sheet `Leitungsschutz`) |
| `json_export_path` | yes | output folder for JSON files, protocols (`html_files/`) and statistics (`Statistik/`); created if missing |
| `path_summary` | no | Excel summary; default `<json_export_path>/summary.xlsx` |
| `export_path_pdf` | no | ZIP archive of the PDF protocols; default `<json_export_path>/protocols.zip` |
| `grounding_impedance_structure` | no | layout of the COMPANO file names: `PREFIX_LINENUMBER_TOWER` (default), `LINENUMBER_TOWER` or `TOWER_LINENUMBER` |

The input paths must exist; otherwise the run stops with exit code 2 and
names the missing path.

### `contacts` – who evaluated the measurement

| Key | Meaning |
| --- | --- |
| `evaluation_first_name`, `evaluation_last_name`, `evaluation_company` | shown in the signature block of the protocol and in the JSON (`Auswertung_*`) |

The measuring engineer is taken from the measurement description (`Name`,
`Vorname`, `Firma`).

### `default_grid_data` – fallback values

Used for towers without values in the grid-data workbook and without
short-circuit data.

| Key | Unit | Default | Meaning |
| --- | --- | --- | --- |
| `r` | – | `1.0` | reduction factor of the earth wire |
| `tripping_time` | s | `0.4` | fault clearing time |
| `fault_current_kA` | kA | `12` | single-phase short-circuit current |

!!! note

    The defaults are deliberately conservative but generic. Set them to the
    values of your network; a reduction factor of `1.0` assumes that the whole
    fault current flows into the earth at the tower.

### `line_protection` – position-dependent clearing time

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `false` | read the protection sheet of the short-circuit workbook |
| `sheet_name` | `"Leitungsschutz"` | name of that sheet |

See [Preparing a campaign](campaign.md#sheet-leitungsschutz) for the sheet
layout and [Assessment procedure](assessment.md#fault-clearing-time) for the
background.

## Validation

The configuration is validated before anything is evaluated. Typical
messages:

| Message | Cause |
| --- | --- |
| `Configuration file not found: …` | wrong `--config` path or no `config.json` in the working directory |
| `… is not valid JSON: …` | syntax error, e.g. a trailing comma or a single backslash in a Windows path |
| `directory.path_measurements: directory does not exist: …` | path wrong or relative to the wrong folder |
| `touch_voltages: the length of t_s (11) does not match …` | the lists of the curve differ in length |
| `Unsupported language 'fr'; supported: en, de` | only `en` and `de` are available |
| `logo: file does not exist: …` | the logo path is wrong |
