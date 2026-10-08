# Preparing a campaign

A *campaign* is a set of towers measured with the same procedure, usually one
or more overhead lines. Everything the tool needs is described by one
[configuration file](configuration.md); the data live in a folder of your
choice, for example:

```text
campaign-2026/
├── config.json
├── grid_data.xlsx                    grid data per tower (updated by --calc)
├── measurement_description.xlsx      one row per measured tower
├── short_circuit_data.xlsx           short-circuit currents + line protection (optional)
├── measurements/                     all instrument files in ONE flat folder
│   ├── ZE_<line>_<tower>.xml
│   ├── UT_<line>_<tower>.txt
│   └── Map_<line>_<tower>.png
└── results/                          created by the tool
```

The quickest way to get a valid starting point is the demo campaign
(`gm-cli towers demo DIR`): replace its files with yours and adjust
`config.json`. `gm-cli towers example-config config.json` writes only the
configuration.

!!! tip "Keep campaign data out of source repositories"

    Configuration and data contain names, locations and grid data. Keep them
    next to the measurements, not in a clone of a code repository (the
    groundmeas `.gitignore` excludes `*.json`, `*.xml` and `*.csv` for this
    reason).

## Measurement files

All instrument files of a campaign are stored in **one flat folder**
(`directory.path_measurements`). The file name tells the tool which line and
tower a file belongs to.

| File | Instrument | Required | Content |
| --- | --- | --- | --- |
| `ZE_<line>_<tower>.xml` | OMICRON COMPANO 100 | yes | fall-of-potential measurement and the measuring currents of the step/touch test |
| `UT_<line>_<tower>.txt` | OMICRON HGT1 | yes[^ut] | touch-voltage readings (*StepTouch* report) |
| `ZE_<line>_<tower>_spez….xml` | COMPANO 100 | no | soil-resistivity measurement (any name that contains `spez`) |
| `UT_<line>_<tower>-<neighbour>.txt` | HGT1 | no | voltage measured at the neighbouring tower during the injection at `<tower>` |
| `Map_<line>_<tower>.<png\|jpg\|jpeg\|gif\|svg\|webp>` | – | no | map or sketch of the measurement layout for the protocol |

[^ut]: A tower without HGT1 report is listed with a warning and skipped by
    the assessment, because the touch voltages are part of every protocol.

### Naming rules

- **Line identifiers must not contain `_`** – the underscore separates the
  parts of the file name. Hyphens, dots and digits are fine (`L-110.07`).
- **Tower identifiers** may contain letters (`28N`, `2M`). Leading zeros and
  letter case are ignored when files are matched: `UT_L1_008n.txt` belongs to
  `ZE_L1_8N.xml`.
- **Extensions** are case-insensitive (`.XML`, `.Txt`).
- Unicode spellings are normalised (macOS stores `ü` decomposed), so names
  with umlauts match on every operating system.
- The layout of the COMPANO file names is configurable with
  `directory.grounding_impedance_structure`:

| Value | File name | Example |
| --- | --- | --- |
| `PREFIX_LINENUMBER_TOWER` (default) | `<prefix>_<line>_<tower>.xml` | `ZE_LX-01_8.xml` |
| `LINENUMBER_TOWER` | `<line>_<tower>.xml` | `LX-01_8.xml` |
| `TOWER_LINENUMBER` | `<tower>_<line>.xml` | `8_LX-01.xml` |

HGT1 reports are always named `UT_<line>_<tower>.txt`.

### Delivery with one folder per tower

Contractors often deliver one folder per line and tower
(`<line>/Mast <tower>/…`). `gm-cli towers flatten` copies such a delivery into
the flat layout. Line and tower are taken from the **folder names**, so typos
in delivered file names are corrected (`UT_LH_01-0815_5.txt`, a touch-voltage
report saved as `ZE_….txt`); photos, PDFs and spreadsheets are not copied and
the originals stay untouched.

```console
$ gm-cli towers flatten delivery/ campaign-2026/measurements/
$ gm-cli towers flatten delivery/ campaign-2026/measurements/ --apply --report mapping.csv
```

Without `--apply` the command only prints the plan (`N files, M renamed,
K conflicts`). If two files would get the same name it stops with exit code 1
and copies nothing. Folder names are matched with regular expressions
(`--line-pattern`, default `(LH[-_]\d+[-_][0-9A-Z]+)`, and `--tower-pattern`,
default `^Mast\s+(\S+)`); `--only FOLDER` (repeatable) restricts the run to
some tower folders and `--map-strip` sets the prefix removed from the line in
map file names (default `LH-`).

### COMPANO 100 export (XML)

Export the measurement on the COMPANO 100 (or with its PC software) as XML.
The tool reads

- the potential-probe **distances**, the **input voltages**, the **raw output
  currents** and the **corrected output currents** of the fall-of-potential
  measurement (`FallOfPotentialReport`),
- the **output currents of the step/touch test** (the current that was
  injected while the HGT1 readings were taken),
- the **nominal frequency** configured on the instrument (available through
  the Python API; the evaluation uses `nominal_frequency_Hz` of the
  configuration),
- for soil-resistivity exports the apparent **specific resistances** and the
  electrode distances a, b, c (`SoilResistanceReport`).

Units are converted to A, V and m (`mA`, `kV`, `cm`, `km` and `ft` are
accepted). A file that lacks one of the required elements is reported with
its name and skipped. The readers are available as
`groundmeas.instruments.CompanoXMLReader` and `Hgt1TXTReader`, see
[Import from OMICRON instruments](../17_instrument_import.md).

### HGT1 report (text)

The HGT1 *StepTouch* report is a tab-separated text file with a header row
`Location  Meas. ID  Date  Time  f1  Level1  f2  Level2  Termination` followed
by a unit row and one row per reading. Each reading contains the voltage at two
frequencies next to the power frequency (for example 30 Hz and 70 Hz); the
value at the nominal frequency is interpolated linearly (see
[Physical background](physics.md#touch-voltage)).

The `Termination` column tells how the voltage was measured:

| Termination | Meaning | Used for the assessment with `touch_voltage_evaluation` |
| --- | --- | --- |
| `1k` | 1 kΩ measuring resistance (body impedance) only | `without_resistor` |
| `2x1k` | additional 1 kΩ in series (footwear/standing surface) | `with_resistor` (default) |

UTF-8 and Windows-1252 encoded files are both accepted.

## Measurement description (`measurement_description.xlsx`)

One row per measured tower, describing *how* it was measured. The first
worksheet is read.

| Column | Required | Meaning |
| --- | --- | --- |
| `Leitung` | yes | line identifier (as in the file names) |
| `Mast` | yes | tower identifier |
| `Messung_RA_Profil_bool` | yes | `1` if the footing-resistance profile of the COMPANO export is valid, `0` to ignore it[^bool] |
| `Messung_RA_Einzelwert_Ohm` | yes (may be empty) | footing resistance measured with a high-frequency earth tester in Ω |
| `Entfernung_Hilfserder_m` | yes | distance between tower and current electrode in m (needed for the 62 % method) |
| `Messpunkte_UT` | yes | measuring points of the touch voltage, comma-separated, e.g. `Tower, Tower, Fence` |
| `Name`, `Vorname`, `Firma` | no | measuring engineer and company (shown in the protocol) |
| `Datum` | no | date of the measurement |
| `Winkel_Sonde_Hilfserder_grad` | no | angle between potential probe and current electrode in degrees |
| `Winkel_Leitung_Hilfserder_grad` | no | angle between line and current electrode in degrees |
| `Witterung` | no | weather |
| `Messtechnik_Name` | no | instruments used |
| `Messfehler_Z_pu`, `Messfehler_U_pu` | no | measurement uncertainty of impedance and voltage (per unit) |
| `Sichtbefund` | no | visual inspection findings |
| `latitude`, `longitude`, `altitude` (or `Breitengrad`, `Längengrad`) | no | tower coordinates; used only by [`import-db`](database.md) for the location |

[^bool]: An **empty** cell counts as `1` (profile valid).

Every column whose name equals a key of the [JSON result](results.md#json-result-per-tower)
is copied into the JSON file. Do not add columns named like computed results
(for example `UT_V`), they would overwrite them.

**Measuring points.** `Messpunkte_UT` lists one entry per HGT1 reading, or one
entry per measuring point if every point was measured twice (`1k` and `2x1k`).
If the HGT1 itself recorded real location names, those are used and a
warning is logged when they differ from the description. If the number of
entries fits neither, the list is repeated cyclically and a warning asks you
to check the labels.

## Grid data (`grid_data.xlsx`)

The grid values per tower. Only `Leitung` and `Mast` are needed initially; the
`--calc` step fills in the rest and **writes the workbook back** (rows sorted,
duplicates merged, further columns kept).

| Column | Unit | Meaning |
| --- | --- | --- |
| `Mast`, `Leitung` | – | tower and line identifier |
| `Reduktionsfaktor` | – | reduction factor $r$ of the earth wire |
| `Abschaltzeit` | s | fault clearing time |
| `Fehlerstrom` | A | single-phase short-circuit current $I_k$ at the tower |
| `Lage_Prozent` | % | position of the tower on the line (written by `--calc`) |
| `Hinweis_Abschaltzeit` | – | how the clearing time was determined (written by `--calc`) |

The values are chosen per tower in this order (highest priority first):

| Value | 1. | 2. | 3. | 4. |
| --- | --- | --- | --- | --- |
| fault current | flat value of the `Leitungsschutz` sheet | short-circuit line model | value in the workbook | `default_grid_data.fault_current_kA` |
| reduction factor | flat value of the `Leitungsschutz` sheet | value in the workbook | `default_grid_data.r` | |
| clearing time | `Leitungsschutz` sheet (position on the line) | value in the workbook | `default_grid_data.tripping_time` | |

!!! warning "Close the workbook and keep a backup"

    Excel locks open files; `--calc` then stops with a message. Because the
    workbook is rewritten, keep a copy of the original.

## Short-circuit data (`short_circuit_data.xlsx`, optional)

### One sheet per line

A worksheet **named exactly like the line** provides calculated single-phase
short-circuit currents along the line, for example from a network
calculation for faults at 0 %, 10 %, …, 100 % of the line length. Columns
`B` to `D` are read; column `A` is free (e.g. the fault location in percent).

| Column | Header | Meaning |
| --- | --- | --- |
| B | `Ik` | short-circuit current in kA |
| C | `l` | distance of the fault location from the line start in km |
| D | `Mast` | tower number; only the **first and the last row** are needed (first and last tower of the line) |

The tool fits the [two-sided infeed model](physics.md#short-circuit-current-along-the-line)
to these points and evaluates it at every measured tower. If the fit fails, a
straight line is used and a warning is logged.

### Sheet `Leitungsschutz`

Enables the **position-dependent fault clearing time** (and optional flat
values per line). It is read only if `line_protection.enabled` is `true` in the
configuration.

| Column | Required | Meaning |
| --- | --- | --- |
| `Leitung` | yes | line identifier |
| `t_Schnellzeit_s` | yes | clearing time in the middle section (both relays in zone 1), e.g. 0.1 |
| `t_Endbereich_s` | yes | clearing time near the line ends (remote relay in zone 2), e.g. 0.4 |
| `Mast_Anfang`, `Mast_Ende` | for positions | first and last tower number (0 % and 100 %) |
| `Schnellzeit_von_Prozent`, `Schnellzeit_bis_Prozent` | no | limits of the middle section, default 16 and 84 |
| `Fehlerstrom_pauschal_kA` | no | flat fault current for the whole line |
| `Reduktionsfaktor_pauschal` | no | flat reduction factor for the whole line |
| `Netzform`, `Schutzkonzept`, `Bemerkung` | no | free text (network earthing, protection concept, remark) |

Equal times in both columns give one flat clearing time for the line, e.g. a
compensated network with `t_Schnellzeit_s = t_Endbereich_s = 10`. The
background is explained in
[Assessment procedure](assessment.md#fault-clearing-time).

## Map images and logo

`Map_<line>_<tower>.<ext>` is searched next to the JSON results first and then
in the measurement folder; it appears on the first page of the protocol. A
company logo for the protocol header is configured with the key `logo`.

## Checklist

- [ ] All files in one flat measurement folder, names follow the rules above
- [ ] One row per tower in the measurement description, required columns present
- [ ] Current-electrode distance filled in for every tower
- [ ] Grid-data workbook closed in Excel, backup made
- [ ] Short-circuit sheets named like the lines (if used)
- [ ] Permissible touch-voltage curve checked against the applicable standard
- [ ] `gm-cli towers run --config … --calc` runs without warnings
