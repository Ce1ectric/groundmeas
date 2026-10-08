# Results

All results are written below `directory.json_export_path`:

```text
results/
├── <line>_<tower>.json          one result per tower (--calc)
├── summary.xlsx                 one row per tower (--calc, path_summary)
├── protocols.zip                PDF protocols (--zip, export_path_pdf)
├── html_files/                  protocols and diagrams (--print)
└── Statistik/                   statistics report (--stats)
```

In addition, `--calc` updates the [grid-data workbook](campaign.md#grid-data-grid_dataxlsx)
with fault current, reduction factor, clearing time and position of every
measured tower.

## JSON result per tower

The JSON file is the central result: protocols and statistics are created
from it, and it is the interface for your own analyses. The keys are German
for compatibility with existing data sets; the table translates them. Values copied from the
measurement description keep the type of the Excel cell.

### Identification and measurement set-up

| Key | Unit | Meaning | Source |
| --- | --- | --- | --- |
| `Leitung` | – | line identifier | measurement description |
| `Mast` | – | tower identifier | measurement description |
| `Datum` | – | date of the measurement (`YYYY-MM-DD`) | measurement description |
| `Name`, `Vorname`, `Firma` | – | measuring engineer (last name, first name, company) | measurement description |
| `Messtechnik_Name` | – | instruments | measurement description |
| `Witterung` | – | weather | measurement description |
| `Entfernung_Hilfserder_m` | m | distance tower – current electrode $D$ | measurement description |
| `Winkel_Sonde_Hilfserder_grad` | ° | angle potential probe – current electrode | measurement description |
| `Winkel_Leitung_Hilfserder_grad` | ° | angle line – current electrode | measurement description |
| `Messfehler_Z_pu`, `Messfehler_U_pu` | p.u. | measurement uncertainty of impedance and voltage | measurement description (template default 0.05 / 0.02) |
| `Sichtbefund` | – | visual inspection findings | measurement description |
| `Auswertung_Vorname`, `Auswertung_Name`, `Auswertung_Firma` | – | who evaluated the measurement | configuration (`contacts`) |

### Grid values

| Key | Unit | Meaning |
| --- | --- | --- |
| `Ik_kA` | kA | single-phase short-circuit current $I_k$ at the tower |
| `r_pu` | – | reduction factor $r$ of the earth wire |
| `Abschaltzeit_s` | s | fault clearing time $t_F$ |
| `Abschaltzeit_Hinweis` | – | how the clearing time was determined (position on the line, flat value, default) |
| `Lage_Leitung_Prozent` | % | position of the tower on the line; `""` if unknown |
| `Netzform` | – | network earthing from the `Leitungsschutz` sheet; `""` if not listed |

### Fall-of-potential measurement

| Key | Unit | Meaning |
| --- | --- | --- |
| `Distanz_m` | m | potential-probe distances $x_i$ |
| `ZE_Ohm` | Ω | earthing impedance $Z_E(x_i)$ at every distance |
| `Distanz_62_m` | m | $0.62\,D$ (integer part) |
| `ZE_62_Ohm` | Ω | assessed earthing impedance $Z_{E,62}$ ([62 % method](physics.md#the-62-method)) |
| `IE_A` | A | measuring current of the step/touch test $I_{meas}$ (shown in mA in the protocol) |
| `RA_Ohm` | Ω | footing-resistance profile $R_A(x_i)$; `""` if not measured or not usable |
| `IA_A` | A | current into the tower footing during the fall-of-potential test; `""` without profile |
| `RA_62_Ohm` | Ω | footing resistance shown in the protocol (62 % value of the profile or the high-frequency single value) |
| `RA_Quelle_Hinweis` | – | non-empty if the high-frequency single value was used |
| `US_V` | V | step voltage per metre at $x_0 = 0$ and every probe distance, at the earth-fault current |

### Touch voltages and assessment

| Key | Unit | Meaning |
| --- | --- | --- |
| `Messpunkte_UT` | – | label of every HGT1 reading, e.g. `Tower (with additional resistor 1kOhm)` |
| `Messpunkte_UT_Termination` | – | HGT1 termination of every reading (`1k`, `2x1k`) – language independent |
| `UT_V` | V | touch voltage of every reading at the earth-fault current, rounded up |
| `UT_max_Messung_V` | V | highest assessed touch voltage (subset chosen by `touch_voltage_evaluation`), rounded up |
| `UD_Kurve_50341` | – | curve of the permissible touch voltage used (`UD1`) |
| `UD_V` | V | permissible touch voltage $U_{TP}(t_F)$ |
| `Bewertung_Kategorie` | – | result code: `ZE`, `UT` or `MASS` ([assessment](assessment.md#categories)) – language independent |
| `Auslegung_korrekt` | – | verdict sentence in the configured language |

### Optional sections

```json
"Bodenwiderstand_Schlumberger": {
    "vorhanden": true,
    "rho_OhmMeter": [85.0, 92.0, 110.0, 135.0, 150.0],
    "DistanzA_m": [1.0, 2.0, 5.0, 10.0, 20.0],
    "DistanzB_m": [3.0, 6.0, 15.0, 30.0, 60.0],
    "DistanzC_m": [1.0, 2.0, 5.0, 10.0, 20.0]
},
"Erdungsspannung_Nachbarmast": {
    "vorhanden": true,
    "Nachbarmast": "9",
    "UT_gemessen_V": [40.002, 28.001]
}
```

| Key | Meaning |
| --- | --- |
| `Bodenwiderstand_Schlumberger` | apparent soil resistivity $\rho$ in Ωm and electrode distances a, b, c in m from the `…spez….xml` export |
| `Erdungsspannung_Nachbarmast` | voltages measured at the neighbouring tower (`UT_<line>_<tower>-<neighbour>.txt`), scaled to the earth-fault current like the own touch voltages |
| `rhoE_Distanz_m`, `rhoE_OhmMeter` | legacy single values; filled only if the measurement description has such columns |

The section `Bodenwiderstand_Schlumberger` keeps its name for compatibility
although the export may also be a Wenner measurement (`DistanzC_m` equal to
`DistanzA_m`). [`import-db`](database.md) stores such readings with the
correct method and geometry.

!!! tip "Use the codes, not the texts"

    For your own analyses use `Bewertung_Kategorie` and
    `Messpunkte_UT_Termination`. The texts (`Auslegung_korrekt`,
    `Messpunkte_UT`) depend on the configured language.

### Reading the results in Python

```python
import json
from pathlib import Path

import pandas as pd

rows = []
for path in Path("demo/results").glob("*.json"):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows.append(
        {
            "line": data["Leitung"],
            "tower": data["Mast"],
            "Z_E_62": data["ZE_62_Ohm"],
            "U_E_kV": data["Ik_kA"] * data["r_pu"] * data["ZE_62_Ohm"],
            "U_T_max": data["UT_max_Messung_V"],
            "U_TP": data["UD_V"],
            "category": data["Bewertung_Kategorie"],
        }
    )
print(pd.DataFrame(rows).sort_values(["line", "tower"]))
```

To work with the *measured data* instead (profiles, touch voltages, soil
resistivity), import the campaign into the database with
[`gm-cli towers import-db`](database.md) and use the groundmeas analytics.

## Excel summary (`summary.xlsx`)

One row per evaluated tower:

| Column | Unit | Meaning |
| --- | --- | --- |
| `Leitung`, `Mast` | – | identifiers |
| `Fehlerstrom` | A | short-circuit current $I_k$ |
| `Abschaltzeit` | s | clearing time |
| `Reduktionsfaktor` | – | reduction factor $r$ |
| `Erweiterte_UTP` | – | always `False` (curve UD2 not used) |
| `ZE` | Ω | highest earthing impedance of the profile |
| `ZE_62` | Ω | assessed earthing impedance $Z_{E,62}$ |
| `ZE_zu_hoch` | – | `True` if $Z_{E,62} > 2\,U_{TP} / I_E$ |
| `UT` | V | highest assessed touch voltage (not rounded) |
| `UT_zu_hoch` | – | `True` if `UT` > $U_{TP}$ |
| `UT_zulaessig_V` | V | permissible touch voltage $U_{TP}$ |
| `Lage_Prozent` | % | position on the line |
| `Hinweis_Abschaltzeit` | – | how the clearing time was determined |

## Protocol (`html_files/<line>_<tower>.html` / `.pdf`)

One A4 protocol per tower in the configured language:

1. **Header** – logo (optional) and title.
2. **Installation** – line, tower, instruments, date.
3. **Measurement set-up** – weather, distance and angles of the current
   electrode, measuring current.
4. **Map** – `Map_<line>_<tower>.<ext>` if available.
5. **Measured values** – table of $Z_E$ and $R_A$ over the distance, table of
   the touch voltages per measuring point.
6. **Diagrams** – earthing impedance with the 62 % value and the earth
   potential in kV, footing resistance, step voltage, touch voltages with and
   without additional resistor compared with the permissible value.
7. **Assessment** – visual findings, clearing time (with explanation), curve
   and value of $U_{TP}$, fault current, reduction factor, earth current
   $I_E$, $Z_{E,62}$, $R_A$, highest touch voltage and the verdict.
8. **Contacts** – measuring engineer, evaluator and a signature field.

The diagrams and the stylesheet (`protocol.css`) are stored next to the HTML
file and referenced by file name, so the folder can be moved or archived as a
whole.

## Statistics report (`Statistik/Asset_Auswertung.html` / `.pdf`)

A four-page report over all JSON files of the campaign for asset management:
distributions of earth potential rise $U_E$ and touch voltage $U_T$,
exceedances per line, correlations between the quantities and a list of all
towers above the permissible touch voltage. Towers evaluated with the default
fault current of 12 kA are marked. The report texts are German.
