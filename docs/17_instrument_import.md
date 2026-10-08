# Import from OMICRON instruments

groundmeas reads the export files of the **OMICRON COMPANO 100** (XML) and the
**OMICRON HGT1** (*StepTouch* text report) directly – no OCR and no typing of
values. Each test becomes one measurement with all its items.

To try it without own files, create the synthetic demo campaign of the tower
workflow; it contains COMPANO and HGT1 files of four towers:

```console
$ gm-cli towers demo demo
```

## Command line

```console
$ gm-cli --db tower8.db import-omicron \
      --location "LX-01 tower 8" --asset-type overhead_line_tower \
      --ze demo/measurements/ZE_LX-01_8.xml \
      --ut demo/measurements/UT_LX-01_8.txt \
      --transferred demo/measurements/UT_LX-01_8-9.txt \
      --soil "demo/measurements/ZE_LX-01_8_spez.Erdw..xml" \
      -D 100 --timezone Europe/Berlin
Connected to tower8.db
Imported fall of potential: measurement id=1
Imported touch voltages: measurement id=2
Imported transferred potential (UT_LX-01_8-9.txt): measurement id=3
Imported soil resistivity: measurement id=4
```

| Option | Meaning |
| --- | --- |
| `--location`, `-l` | location name; an existing location with this name is reused |
| `--asset-type`, `-a` | asset type of the measurements, e.g. `overhead_line_tower` or `substation` |
| `--fall-of-potential`, `--ze` | COMPANO export with the fall-of-potential test |
| `--step-touch`, `--ut` | HGT1 report with touch voltages (needs `--ze` for the reference current) |
| `--transferred` | HGT1 report measured elsewhere, e.g. at a neighbouring tower (repeatable) |
| `--soil` | COMPANO export with a soil-resistivity measurement |
| `--current-electrode-distance`, `-D` | distance of the current electrode in m – needed for the 62 % method |
| `--per-frequency/--no-per-frequency` | also store the values at both test frequencies (default on) |
| `--voltage-level-kv`, `--operator` | measurement metadata |
| `--timezone` | IANA time zone of the instrument clock; the time stamps are converted to UTC |

For a whole campaign of overhead-line towers (one location per tower,
metadata from the measurement description) use
[`gm-cli towers import-db`](towers/database.md).

## What is stored

| Measurement (`method`) | Items |
| --- | --- |
| fall of potential (`injection_earth_electrode`) | `earthing_impedance` per probe distance (`measurement_distance_m`, `distance_to_current_injection_m` = `-D`) at the power frequency – the instrument result, the mean of both test frequencies – and at both test frequencies; `earthing_resistance` (footing resistance: probe voltage / current into the footing) if the reduction factor was applied; `earthing_current` (injected current); `earth_fault_current` and `shield_current` from the clamp readings of the reduction factor |
| touch voltages (`injection_earth_electrode`) | `touch_voltage` per reading with `input_impedance_ohm` = 1000 Ω and `additional_resistance_ohm` = 0 (`1k`) or 1000 Ω (`2x1k`), the measuring point in the description; high-impedance readings (`HIGH Z`) as `prospective_touch_voltage`, other terminations without input impedance (with a warning); values at the power frequency (interpolated) and at both test frequencies; `earthing_current` = output current of the step/touch test from the COMPANO export |
| transferred potential (`injection_earth_electrode`) | `transferred_potential` per reading, reference current as above |
| soil resistivity (`wenner` or `schlumberger`) | `soil_resistivity` per reading; Wenner (`c = a`): spacing `a` in `measurement_distance_m`; Schlumberger: `AB/2 = c + a/2` in `measurement_distance_m` and `MN/2 = a/2` in `distance_to_current_injection_m` (COMPANO: `a` = MN spacing, `b` = electrode depth, `c` = distance current – potential electrode) |

Units are converted to SI (`mA`, `mV`, `kV`, `cm`, `km`, `ft`, `kΩm`, …). An
export that contains only the instrument results (no values at the test
frequencies) is stored at the power frequency. A file that lacks required
elements raises `MeasurementFileError` with the file name. Each test is
stored in one transaction: if an item cannot be stored, no empty
measurement is left behind.

## Python API

```python
import groundmeas as gm

gm.connect_db("tower8.db")
fop = gm.import_fall_of_potential(
    "demo/measurements/ZE_LX-01_8.xml",
    location="LX-01 tower 8",
    asset_type="overhead_line_tower",
    current_electrode_distance_m=100,
    timezone="Europe/Berlin",
)
touch = gm.import_step_touch(
    "demo/measurements/UT_LX-01_8.txt",
    location="LX-01 tower 8",
    asset_type="overhead_line_tower",
    compano_xml_path="demo/measurements/ZE_LX-01_8.xml",
)
soil = gm.import_soil_resistivity(
    "demo/measurements/ZE_LX-01_8_spez.Erdw..xml",
    location="LX-01 tower 8",
    asset_type="overhead_line_tower",
)
```

`location` can also be a dict with `name`, `latitude`, `longitude` and
`altitude`. The readers alone (no database) are in `groundmeas.instruments`:

```python
from groundmeas.instruments import CompanoXMLReader, Hgt1TXTReader

reader = CompanoXMLReader("demo/measurements/ZE_LX-01_8.xml")
data = reader.read_fall_of_potential()      # distances, complex U and I per test frequency
data.impedance()                            # complex Z at the power frequency (instrument result)
data.impedance(30.0)                        # complex Z at one test frequency
reader.read_reduction_factor()              # clamp readings or None
reader.get_step_touch_currents()            # (frequencies, output currents) of the step/touch test
reader.read_soil_resistivity()              # readings with a, b, c, AB/2, MN/2 or None
Hgt1TXTReader("demo/measurements/UT_LX-01_8.txt", nominal_frequency=50).get_touchvoltage_dataframe()
```

## Evaluating the imported data

```python
# earthing impedance of the profile (62 % method, see Analytics)
gm.distance_profile_value(fop, algorithm="62_percent", frequency_hz=50.0)["result_value"]
# 0.1208...

# the procedure of the tower evaluation (extrapolation + conservative corrections)
gm.distance_profile_value(
    fop, algorithm="62_percent", conservative=True, frequency_hz=50.0
)["result_value"]

# one value per frequency (power frequency and both test frequencies)
gm.impedance_over_frequency(fop)
# {50.0: 0.1208..., 30.0: 0.1208..., 70.0: 0.1208...}
```

- `distance_profile_value(..., frequency_hz=...)` evaluates one frequency of a
  profile stored at several frequencies; without it, a warning reminds you
  that the profile mixes frequencies.
- `impedance_over_frequency` reduces the profile at every frequency with the
  chosen `profile_algorithm` (62 % by default) – input for the
  [ρ–f model](15_analytics.md).
- `calculate_split_factor(earth_fault_current_id, shield_current_ids)` with
  the `earth_fault_current` and `shield_current` items of the
  fall-of-potential measurement returns the share of the current that flows
  into the tower footing (the COMPANO reduction factor).
- The soil-resistivity measurement can be inverted into a layered soil model,
  e.g. `invert_soil_resistivity_layers(soil, method="wenner", layers=2)`
  (pass the method of the measurement).
- Touch voltages per ampere follow from the `touch_voltage` items and the
  `earthing_current` item of the *touch-voltage* measurement (the output
  current of the step/touch test, not the injected current of the
  fall-of-potential test). Multiplied by the earth-fault current $I_E$ they
  give the touch voltages of the tower evaluation, see
  [Campaigns in the database](towers/database.md#evaluating-the-imported-data).
