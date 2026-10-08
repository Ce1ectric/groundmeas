# Python API

Everything `gm-cli towers` does is available as functions and classes, for
example to evaluate single towers in a notebook, to run parameter studies or
to integrate the evaluation into another tool. The most important names can
be imported from `groundmeas.towers` (imported lazily, so the import is
fast) and the instrument readers from `groundmeas.instruments`:

```python
from groundmeas.instruments import (
    CompanoXMLReader,         # COMPANO 100 XML export
    Hgt1TXTReader,            # HGT1 StepTouch report
)
from groundmeas.towers import (
    GroundingSystemAnalysis,  # assessment of one tower
    LineModel,                # short-circuit current along a line
    LineProtectionTable,      # position-dependent clearing time
    calculate_summary,        # run --calc
    print_protocol,           # run --print
    zip_protocols,            # run --zip
    generate_asset_report,    # run --stats
    import_campaign,          # import-db
    write_demo_campaign,      # demo
    read_config,
)
```

## Run the pipeline from Python

```python
from groundmeas.towers import calculate_summary, print_protocol, zip_protocols

config = "demo/config.json"
summary = calculate_summary(config_path=config)                      # returns a DataFrame
print(summary[["Leitung", "Mast", "ZE_62", "UT", "UT_zulaessig_V", "UT_zu_hoch"]])
print_protocol(config_path=config, worker_count=2, print_pdf=False)  # HTML only
zip_protocols(config_path=config)
```

```text
  Leitung Mast     ZE_62          UT  UT_zulaessig_V  UT_zu_hoch
0   LX-01    3  0.552489  419.879955           300.0        True
1   LX-01    8  0.120835   94.987200           633.0       False
2   LX-01   21  0.601578  309.824592           633.0       False
3   LX-01   37  0.351584  260.134875           300.0       False
```

With `worker_count > 1` the protocols are printed in separate processes; in a
script, put the calls under `if __name__ == "__main__":` (required by Python's
`spawn`/`forkserver` start methods, the default on Windows, macOS and – since
Python 3.14 – Linux).

Log messages go to the logger `groundmeas` (its sub-logger
`groundmeas.towers`); enable them with `logging.basicConfig(level=logging.INFO)`.

## Evaluate a single tower

`GroundingSystemAnalysis` needs no configuration file when the
touch-voltage curve and the evaluation mode are passed explicitly:

```python
from groundmeas.instruments import CompanoXMLReader, Hgt1TXTReader
from groundmeas.towers import GroundingSystemAnalysis

impedance, footing = CompanoXMLReader(
    "demo/measurements/ZE_LX-01_8.xml"
).get_impedance_to_ground_dataframe()
touch = Hgt1TXTReader(
    "demo/measurements/UT_LX-01_8.txt", nominal_frequency=50
).get_touchvoltage_dataframe()

tower = GroundingSystemAnalysis(
    impedance_to_ground=impedance,
    touch_voltage=touch,
    fault_current=11_200,          # I_k in A
    fault_duration=0.1,            # t_F in s
    reduction_factor=0.66,         # r
    extended_resistance=False,
    residual_resistance=footing,
    current_probe_dist=100,        # D in m
    touch_voltage_curve={0.1: 633, 0.2: 528, 0.3: 410, 0.4: 300, 0.5: 204, 1.0: 107, 10.0: 80},
    touch_voltage_evaluation="with_resistor",
)
print(f"I_E     = {tower.earth_current:.0f} A")
print(f"U_TP    = {tower.permitted_touch_voltage:.0f} V")
print(f"Z_E,62  = {tower.grounding_impedance_62:.3f} Ohm (limit {tower.permitted_ground_impedance:.3f} Ohm)")
print(f"U_E     = {tower.earth_current * tower.grounding_impedance_62:.0f} V")
print(f"U_T,max = {tower.touch_voltage_max:.0f} V")
```

```text
I_E     = 7392 A
U_TP    = 633 V
Z_E,62  = 0.121 Ohm (limit 0.171 Ohm)
U_E     = 893 V
U_T,max = 95 V
```

Useful attributes after the evaluation:

| Attribute | Meaning |
| --- | --- |
| `earth_current` | $I_E = r \cdot I_k$ in A |
| `permitted_touch_voltage` | $U_{TP}(t_F)$ in V |
| `permitted_ground_impedance` | $2\,U_{TP} / I_E$ in Ω |
| `grounding_impedance_62`, `dist_62` | assessed impedance and the 62 % distance |
| `residual_resistance_62` | footing resistance scaled to the 62 % point |
| `touch_voltage` | data frame of the readings with `CalculatedTouchVoltage` (V at $I_E$) |
| `touch_voltage_max` | highest assessed touch voltage |
| `impedance_to_high`, `touch_voltage_to_high` | results of the limit checks |
| `step_voltage` | step voltage per metre along the profile |

The category of the [assessment](assessment.md) follows from the two flags:

```python
from groundmeas.towers.campaign import assessment_category

assessment_category(tower)  # 'ZE'
```

The 62 % value itself is computed by `groundmeas.value_at_62_percent(...,
conservative=True)`, the same function that `distance_profile_value(...,
algorithm="62_percent", conservative=True)` uses for profiles stored in the
database.

## Short-circuit current along a line

```python
import pandas as pd

from groundmeas.towers import LineModel

training = pd.DataFrame(
    {
        "Ik": [12.9, 11.0, 9.9, 9.6, 10.4],      # kA, from a network calculation
        "l": [0.0, 2.9, 5.85, 8.8, 11.7],       # km from the line start
        "Mast": [1, None, None, None, 40],      # first and last tower number
    }
)
model = LineModel()
model.training_data["LX-01"] = training         # or model.read_training_parameter(path, "LX-01")
model.train_curve_model("LX-01")
model.get_sc_current("LX-01", 21)               # 9.9 (kA)
model.curve_data["LX-01"]["type"]               # 'two_sided'
```

## Position-dependent clearing time

```python
import pandas as pd

from groundmeas.towers import LineProtectionTable

table = LineProtectionTable(
    pd.DataFrame(
        [{"Leitung": "LX-01", "Mast_Anfang": 1, "Mast_Ende": 40,
          "t_Schnellzeit_s": 0.1, "t_Endbereich_s": 0.4}]
    )
)
result = table.lookup("LX-01", "37")
result.tripping_time_s, round(result.position_percent, 1), result.zone   # (0.4, 92.3, 'Endbereich')
table.lookup("LX-01", "8").hint("en")
# 'Position 17.9 % of the line length: instantaneous tripping from both line ends (distance protection)'
```

## Synthetic test data

`groundmeas.towers.demo` creates instrument files from physical models. They
are useful for tests of your own tooling:

```python
import numpy as np

from groundmeas.towers.demo import fall_of_potential_profile, write_compano_xml

distances = np.array([1, 2, 5, 10, 20, 30, 40, 50, 60, 65, 70], dtype=float)
profile = fall_of_potential_profile(distances, earthing_impedance_ohm=0.4, electrode_radius_m=3.0)
write_compano_xml("ZE_TEST_1.xml", distances, profile, footing_share=0.5)
```

## Modules

| Module | Content |
| --- | --- |
| `groundmeas.towers.analysis` | `GroundingSystemAnalysis`, `LineModel`, `permitted_voltage_for_time` |
| `groundmeas.towers.line_protection` | `LineProtectionTable` |
| `groundmeas.towers.campaign` | `calculate_summary`, assessment categories, grid-data handling |
| `groundmeas.towers.config` | `read_config`, `ConfigError`, `write_example_config`, `EXPORT_TEMPLATE` |
| `groundmeas.towers.files` | file discovery in the flat measurement folder (`read_from_device`) |
| `groundmeas.towers.flatten` | `plan_flatten`, `apply_flatten` |
| `groundmeas.towers.database` | `import_campaign`, `find_tower_files`, `location_name` |
| `groundmeas.towers.protocol`, `.plots`, `.results`, `.pdf` | diagrams, HTML/PDF protocols, ZIP |
| `groundmeas.towers.stats` | statistics report |
| `groundmeas.towers.i18n`, `.naming`, `.paths` | texts (en/de), identifiers, paths |
| `groundmeas.towers.demo` | synthetic demo campaign |
| `groundmeas.instruments` | COMPANO 100 / HGT1 readers |
