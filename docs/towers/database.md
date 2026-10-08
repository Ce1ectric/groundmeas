# Campaigns in the database

The tower evaluation works on files: the JSON results and protocols are its
output. The *measured data* of a campaign can additionally be copied into the
groundmeas database, where the dashboard, the map, the profile algorithms,
the ρ–f model, the split factor and the soil inversion of groundmeas are
available:

```console
$ gm-cli --db towers.db towers import-db --config campaign-2026/config.json --dry-run
$ gm-cli --db towers.db towers import-db --config campaign-2026/config.json \
      --voltage-level-kv 110 --timezone Europe/Berlin
LX-01 tower 3                  fall_of_potential      ZE_LX-01_3.xml: measurement 1
LX-01 tower 3                  touch_voltage          UT_LX-01_3.txt: measurement 2
LX-01 tower 8                  fall_of_potential      ZE_LX-01_8.xml: measurement 3
...
10 measurements imported, 0 skipped, 0 failed (4 towers)
```

The database is chosen like for every `gm-cli` command (`--db`,
`GROUNDMEAS_DB`, the stored default, `./groundmeas.db`). `--dry-run` lists the
files without opening the database.

## What is stored

Every tower becomes a **location** named `"<line> tower <tower>"` (tower
number without leading zeros, letters upper-case: `LX-01 tower 8N`). If the
measurement description has the columns `latitude`/`longitude`/`altitude`
(or `Breitengrad`/`Längengrad`), the location gets coordinates and appears on
the map.

Each test becomes a **measurement** with `asset_type = "overhead_line_tower"`:

| File | Measurement (`method`) | Items |
| --- | --- | --- |
| `ZE_<line>_<tower>.xml` | fall-of-potential test (`injection_earth_electrode`) | `earthing_impedance` per probe distance at the power frequency and at both test frequencies, with `distance_to_current_injection_m` = `Entfernung_Hilfserder_m` of the measurement description; `earthing_resistance` (footing resistance) if the reduction factor was applied; `earthing_current` (injected current); `earth_fault_current` and `shield_current` from the clamp readings of the reduction factor |
| `UT_<line>_<tower>.txt` | touch voltages (`injection_earth_electrode`) | `touch_voltage` per HGT1 reading (`input_impedance_ohm` 1000 Ω, `additional_resistance_ohm` 0 for `1k` and 1000 Ω for `2x1k`, measuring point in the description) at the power frequency and both test frequencies; `earthing_current` = output current of the step/touch test from the COMPANO export |
| `UT_<line>_<tower>-<neighbour>.txt` | transferred potential (`injection_earth_electrode`) | `transferred_potential` per reading, reference current as above |
| `ZE_<line>_<tower>_spez….xml` | soil resistivity (`wenner` or `schlumberger`) | `soil_resistivity` per reading; Wenner: spacing `a`; Schlumberger: `AB/2 = c + a/2` and `MN/2 = a/2` |

The measurement description provides the **operator** (`Vorname Name, Firma`)
and notes in the measurement description (file name, weather, instruments,
current-electrode distance and angle). The **time stamps** come from the
instruments; `--timezone Europe/Berlin` converts the instrument clock to UTC
as stored by groundmeas (without the option the local time is kept).
`--no-per-frequency` stores the values at the power frequency only.

The **evaluation results** (grid values, permissible touch voltage, category,
protocols) are not stored in the database; they stay in the JSON and Excel
output of [`gm-cli towers run`](cli.md).

## Repeated imports

Files that are already in the database – same location, file name in the
measurement description – are skipped, so the command can be run again after
further deliveries:

```text
0 measurements imported, 10 skipped, 0 failed (4 towers)
```

`--reimport` imports them again (as additional measurements). A file that
cannot be read is reported with `FAILED` and the reason; the other files are
imported and the command exits with code 1.

## Evaluating the imported data

The imported data reproduce the tower evaluation. For the demo campaign:

```python
import numpy as np
import groundmeas as gm

gm.connect_db("towers.db")
measurements, _ = gm.read_measurements_by(asset_type="overhead_line_tower")
tower8 = [m for m in measurements if m["location"]["name"] == "LX-01 tower 8"]
fop = next(m for m in tower8 if m["description"].startswith("Fall-of-potential"))
touch = next(m for m in tower8 if m["description"].startswith("Touch voltages"))

# earthing impedance with the 62 % method of the tower evaluation
z62 = gm.distance_profile_value(
    fop["id"], algorithm="62_percent", conservative=True, frequency_hz=50.0
)
print(round(z62["result_value"], 3))            # 0.121 = ZE_62_Ohm of the JSON result

# touch voltages scaled to the earth-fault current I_E = r * I_k
earth_current = 0.66 * 11_200                    # from grid_data.xlsx
items = [i for i in touch["items"] if i["frequency_hz"] == 50.0]
reference = next(i["value"] for i in items if i["measurement_type"] == "earthing_current")
print([int(np.ceil(i["value"] * earth_current / reference))
       for i in items if i["measurement_type"] == "touch_voltage"])
# [133, 95, 127, 91, 43, 31] = UT_V of the JSON result
```

`conservative=True` applies the corrections of the tower evaluation (see
[The 62 % method](physics.md#the-62-method)); without it the plain 62 %
interpolation of groundmeas is used. Other profile algorithms
(`maximum`, `minimum_gradient`, `minimum_stddev`, `inverse`) are useful for a
comparison, see [Analytics](../15_analytics.md).

## Python API

```python
import groundmeas as gm
from groundmeas.towers import import_campaign

gm.connect_db("towers.db")
records = import_campaign(
    "campaign-2026/config.json",
    voltage_level_kv=110,
    timezone="Europe/Berlin",
)
# one dict per file: line, tower, location, test, file, status, measurement_id, message
```

`import_campaign(..., dry_run=True)` needs no database connection.
`find_tower_files(folder)` lists the files that belong to each tower.
