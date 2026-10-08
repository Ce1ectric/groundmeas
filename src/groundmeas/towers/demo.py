"""Generate a complete synthetic demo campaign.

`write_demo_campaign` creates measurement files in the formats of the
OMICRON COMPANO 100 (XML) and HGT1 (text report), the three Excel workbooks
and a ready-to-use configuration:

    demo/
    ├── config.json
    ├── grid_data.xlsx
    ├── measurement_description.xlsx
    ├── short_circuit_data.xlsx
    └── measurements/
        ├── ZE_LX-01_3.xml, UT_LX-01_3.txt, Map_LX-01_3.png, ...
        ├── ZE_LX-01_8_spez.Erdw..xml      (soil resistivity)
        └── UT_LX-01_8-9.txt               (voltage at the neighbouring tower)

Run it with ``gm-cli towers run --config demo/config.json``.

All values are produced by simple physical models (hemispherical earth
electrode in homogeneous soil, two-sided short-circuit infeed); they do not
describe a real installation. The same generator provides the fixtures of the
test suite.
"""

from __future__ import annotations

import json
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from .i18n import normalize_language

__all__ = [
    "DEMO_LINE",
    "DEMO_TOWERS",
    "DemoTower",
    "fall_of_potential_profile",
    "short_circuit_current_kA",
    "write_compano_xml",
    "write_demo_campaign",
    "write_hgt1_report",
]

DEMO_LINE = "LX-01"
FIRST_TOWER, LAST_TOWER = 1, 40
LINE_LENGTH_KM = 11.7
CURRENT_ELECTRODE_DISTANCE_M = 100.0
PROBE_DISTANCES_M: tuple[float, ...] = (1, 2, 5, 10, 20, 30, 40, 50, 60, 65, 70)
FREQUENCIES_HZ = (30.0, 70.0)
NOMINAL_FREQUENCY_HZ = 50.0
REDUCTION_FACTOR = 0.66
SC_MODEL = {"a": 63.5, "b": 1.0, "c": 6.0, "d": 9.0}
"""Parameters of the two-sided short-circuit model (kV, Ohm/km, Ohm, Ohm)."""


@dataclass(frozen=True)
class DemoTower:
    r"""Parameters of one synthetic tower.

    Attributes
    ----------
    tower : str
        Tower number.
    earthing_impedance_ohm : float
        True earthing impedance $Z_E$ of the model in Ohm.
    electrode_radius_m : float
        Radius of the equivalent hemispherical electrode in m.
    footing_share : float
        Share of the injected current that flows through the tower footing
        (the rest returns through the earth wires); the footing resistance is
        $R_A = Z_E / \text{share}$.
    touch_voltages_v : tuple of (str, float)
        Measuring point and touch voltage in V at the earth-fault current
        (reading with additional resistor; without resistor it is 40 % higher).
    hf_footing_resistance_ohm : float or None
        Optional high-frequency single value of the footing resistance.
    finding : str
        Visual inspection (English; translated for German demos).
    """

    tower: str
    earthing_impedance_ohm: float
    electrode_radius_m: float
    footing_share: float
    touch_voltages_v: tuple[tuple[str, float], ...]
    hf_footing_resistance_ohm: float | None = None
    finding: str = "none"
    soil_resistivity: bool = False
    neighbour: str | None = None
    extra: dict[str, float] = field(default_factory=dict)


DEMO_TOWERS: tuple[DemoTower, ...] = (
    DemoTower(
        "3", 0.55, 2.0, 0.30, (("tower", 420.0), ("tower", 380.0), ("fence", 150.0))
    ),
    DemoTower(
        "8",
        0.12,
        2.5,
        0.35,
        (("tower", 95.0), ("tower", 90.0), ("streetlight", 30.0)),
        soil_resistivity=True,
        neighbour="9",
    ),
    DemoTower(
        "21",
        0.60,
        1.5,
        0.25,
        (("tower", 310.0), ("tower", 280.0), ("gate", 120.0)),
        hf_footing_resistance_ohm=3.6,
        finding="corrosion",
    ),
    DemoTower("37", 0.35, 2.0, 0.30, (("tower", 240.0), ("tower", 260.0))),
)

_TEXT = {
    "en": {
        "tower": "Tower",
        "fence": "Fence",
        "streetlight": "Streetlight",
        "gate": "Gate",
        "none": "No findings",
        "corrosion": "Corrosion at the earthing connection of leg B",
        "weather": "dry",
        "network": "low-impedance earthed",
        "protection": "distance protection",
        "map_title": "Measurement layout",
        "map_current": "current electrode",
        "map_probe": "potential probe",
        "map_line": "line",
        "map_tower": "tower",
    },
    "de": {
        "tower": "Mast",
        "fence": "Zaun",
        "streetlight": "Laterne",
        "gate": "Tor",
        "none": "Keine Auffälligkeiten",
        "corrosion": "Korrosion an der Erdungsanbindung Eckstiel B",
        "weather": "trocken",
        "network": "niederohmig",
        "protection": "Distanzschutz",
        "map_title": "Messaufbau",
        "map_current": "Hilfserder",
        "map_probe": "Sonde",
        "map_line": "Leitung",
        "map_tower": "Mast",
    },
}


# --------------------------------------------------------------------------- models
def fall_of_potential_profile(
    distances_m: Sequence[float],
    earthing_impedance_ohm: float,
    electrode_radius_m: float,
    current_electrode_m: float = CURRENT_ELECTRODE_DISTANCE_M,
) -> np.ndarray:
    r"""Fall-of-potential curve of a hemispherical electrode in homogeneous soil.

    With the current $I$ injected at the electrode (radius $a$)
    and returned at the current electrode at distance $D$ (measured from
    the centre of the electrode), the potential probe at distance
    $a + x$ from the centre measures

    $$
    Z(x) = R \, a \left(\frac{1}{a} - \frac{1}{D} - \frac{1}{a + x}
           + \frac{1}{D - a - x}\right)
    $$

    where $R = \rho / (2 \pi a)$ is the true earthing resistance.
    $Z$ equals $R$ where $a + x = 0.618\,D$.

    Parameters
    ----------
    distances_m : sequence of float
        Probe distances $x$ from the electrode surface in m.
    earthing_impedance_ohm : float
        True earthing resistance $R$ in Ohm.
    electrode_radius_m : float
        Electrode radius $a$ in m.
    current_electrode_m : float, optional
        Distance $D$ of the current electrode in m.

    Returns
    -------
    numpy.ndarray
        $Z(x)$ in Ohm.
    """
    x = np.asarray(distances_m, dtype=float)
    a, d = electrode_radius_m, current_electrode_m
    return earthing_impedance_ohm * a * (1 / a - 1 / d - 1 / (a + x) + 1 / (d - a - x))


def short_circuit_current_kA(
    tower_index: float | np.ndarray, n_towers: int, span_km: float
) -> np.ndarray:
    """Short-circuit current of the demo line (two-sided infeed model).

    Parameters
    ----------
    tower_index : float or numpy.ndarray
        Position as number of spans from the line start.
    n_towers : int
        Number of towers $N$ of the line.
    span_km : float
        Mean span length in km.

    Returns
    -------
    numpy.ndarray
        Current in kA.
    """
    p = SC_MODEL
    x = np.asarray(tower_index, dtype=float)
    return p["a"] / (p["b"] * span_km * x + p["c"]) + p["a"] / (
        p["b"] * (n_towers - x) * span_km + p["d"]
    )


# --------------------------------------------------------------------------- writers
def _value_unit(parent: ET.Element, tag: str, value: float, unit: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    ET.SubElement(element, "Value").text = f"{value:.15f}"
    ET.SubElement(element, "Unit").text = unit
    return element


def _complex_measurement(
    parent: ET.Element, values: Sequence[complex], unit: str
) -> None:
    measurement = ET.SubElement(parent, "Measurement")
    raw = ET.SubElement(measurement, "Measurements")
    for value in values:
        cpx = ET.SubElement(raw, "Complex")
        ET.SubElement(cpx, "Real").text = f"{value.real:.15f}"
        ET.SubElement(cpx, "Imag").text = f"{value.imag:.15f}"
    result = ET.SubElement(measurement, "Result")
    mean = complex(np.mean(values))
    _value_unit(result, "Magnitude", abs(mean), unit)
    _value_unit(result, "Phase", math.degrees(math.atan2(mean.imag, mean.real)), "°")


def write_compano_xml(
    path: str | Path,
    distances_m: Sequence[float],
    impedance_ohm: Sequence[float] | np.ndarray,
    footing_share: float,
    step_touch_current_a: tuple[float, float] = (0.098, 0.102),
    injected_current_a: float = 0.055,
    soil_resistivity: dict[str, Sequence[float]] | None = None,
) -> Path:
    """Write a COMPANO 100 style XML export (fall-of-potential + step/touch).

    Parameters
    ----------
    path : str or pathlib.Path
        Output file.
    distances_m : sequence of float
        Potential-probe distances in m.
    impedance_ohm : sequence of float or numpy.ndarray
        Earthing impedance at every distance in Ohm.
    footing_share : float
        Share of the current flowing into the footing (corrected currents).
    step_touch_current_a : tuple of float, optional
        Output currents of the step/touch test at the two test frequencies.
    injected_current_a : float, optional
        Current of the fall-of-potential test in A.
    soil_resistivity : dict or None, optional
        If given, only a soil-resistivity report is written with the keys
        ``rho``, ``a``, ``b``, ``c`` (lists of equal length).

    Returns
    -------
    pathlib.Path
        The written file.
    """
    root = ET.Element("Compano100Report")
    ET.SubElement(root, "Comment").text = (
        "Synthetic demo file generated by groundmeas - not a real measurement."
    )
    report = ET.SubElement(root, "ReportData")
    ET.SubElement(report, "Version").text = "126"
    ET.SubElement(report, "TimeStamp").text = "2026-05-12 09:00:00.000"
    device = ET.SubElement(report, "DeviceInfo")
    ET.SubElement(device, "Product").text = "COMPANO 100"
    ET.SubElement(device, "SerialNumber").text = "DEMO000"
    regional = ET.SubElement(
        ET.SubElement(report, "SystemConfiguration"), "RegionalConfiguration"
    )
    _value_unit(regional, "NominalFrequency", NOMINAL_FREQUENCY_HZ, "Hz")

    if soil_resistivity is not None:
        screen = ET.SubElement(
            ET.SubElement(
                ET.SubElement(report, "SoilResistanceReport"),
                "SoilResistanceWidgetData",
            ),
            "SoilResistanceMeasurementScreenData",
        )
        for tag, key, unit in (
            ("SpecificResistances", "rho", "Ωm"),
            ("DistancesA", "a", "m"),
            ("DistancesB", "b", "m"),
            ("DistancesC", "c", "m"),
        ):
            container = ET.SubElement(screen, tag)
            for value in soil_resistivity[key]:
                _value_unit(container, "Item", float(value), unit)
    else:
        screen = ET.SubElement(
            ET.SubElement(
                ET.SubElement(report, "FallOfPotentialReport"),
                "FallOfPotentialWidgetData",
            ),
            "FallOfPotentialMeasurementScreenData",
        )
        _value_unit(screen, "Distance", float(max(distances_m)), "m")
        distances = ET.SubElement(screen, "Distances")
        for d in distances_m:
            _value_unit(distances, "Distance", float(d), "m")
        raw = ET.SubElement(screen, "RawOutputCurrents")
        volts = ET.SubElement(screen, "InputVoltages")
        corrected = ET.SubElement(screen, "CorrectedOutputCurrents")
        for i, z in enumerate(impedance_ohm):
            # slightly different currents at the two test frequencies, small phase shift
            currents = [
                injected_current_a * (1 - 0.002 * (1 + i % 3)),
                injected_current_a * (1 + 0.002),
            ]
            mean_current = float(np.mean(currents))
            voltage_phase = math.radians(-160.0)
            voltages = [
                complex(
                    z * c * math.cos(voltage_phase), z * c * math.sin(voltage_phase)
                )
                for c in currents
            ]
            _complex_measurement(raw, [complex(c, 0.0) for c in currents], "A")
            _complex_measurement(volts, voltages, "V")
            out = ET.SubElement(corrected, "OutputCurrent")
            _value_unit(out, "Magnitude", mean_current * footing_share, "A")
            _value_unit(out, "Phase", 0.0, "°")

        setup = ET.SubElement(
            ET.SubElement(
                ET.SubElement(report, "StepAndTouchReport"), "StepTouchWidgetData"
            ),
            "OutputSetupScreenData",
        )
        setup_data = ET.SubElement(setup, "OutputSetupData")
        _value_unit(setup_data, "NominalFrequency", NOMINAL_FREQUENCY_HZ, "Hz")
        frequencies = ET.SubElement(setup_data, "Frequencies")
        for f in FREQUENCIES_HZ:
            _value_unit(frequencies, "TargetFrequency", f, "Hz")
        measurements = ET.SubElement(setup, "Measurements")
        for current in step_touch_current_a:
            _value_unit(measurements, "OutputCurrent", current, "A")

    ET.indent(root, space=" ")
    path = Path(path)
    body = ET.tostring(root, encoding="unicode")
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE Compano100Report>\n'
        + body
        + "\n",
        encoding="utf-8",
    )
    return path


def _device_number(value: float) -> str:
    """Format like the HGT1 (``3.567e-3``)."""
    return re.sub(r"e([+-])0(\d)", r"e\1\2", f"{value:.3e}")


def write_hgt1_report(
    path: str | Path,
    readings: Sequence[tuple[str, str, float]],
    date: str = "2026-05-12",
    start_time: str = "09:30:00",
) -> Path:
    """Write an HGT1 *StepTouch* report (tab-separated, CRLF line endings).

    Parameters
    ----------
    path : str or pathlib.Path
        Output file.
    readings : sequence of (str, str, float)
        ``(location, termination, level_at_nominal_frequency_V)`` per reading;
        the levels at 30 Hz and 70 Hz are generated around this value so that
        the linear interpolation returns it.
    date, start_time : str, optional
        Date (``YYYY-MM-DD``) and start time (``hh:mm:ss``) of the readings.

    Returns
    -------
    pathlib.Path
        The written file.
    """
    hours, minutes, seconds = (int(part) for part in start_time.split(":"))
    lines = [
        "StepTouch Reporting:\t\tStepTouch\\DEMO_ST_000_Report.txt",
        "--------------------",
        "",
        "# Hardware Configuration",
        "\tDevice Info:    \tOmicron HGT1, SNo. DEMO0000, FW1.40",
        "",
        "# StepTouch Results",
        "\tLocation   \tMeas. ID\tDate        \tTime      \tf1      \tLevel1  \tf2      "
        "\tLevel2  \tTermination  ",
        "\t           \t        \t[YYYY-MM-DD]\t[hh:mm:ss]\t[Hz]    \t[V]     \t[Hz]    "
        "\t[V]     \t[Ohm]        ",
    ]
    for number, (location, termination, level) in enumerate(readings, start=1):
        total = hours * 3600 + minutes * 60 + seconds + 30 * number
        clock = f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"
        level_1, level_2 = (
            level * 0.8,
            level * 1.2,
        )  # interpolation to 50 Hz gives `level`
        lines.append(
            f"\t{location.upper():<11}\t{number:<8}\t{date:<12}\t{clock:<10}\t{FREQUENCIES_HZ[0]:<8.2f}"
            f"\t{_device_number(level_1):<8}\t{FREQUENCIES_HZ[1]:<8.2f}\t{_device_number(level_2):<8}"
            f"\t{termination:<13}"
        )
    path = Path(path)
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("ascii"))
    return path


def _write_map(path: Path, tower: str, text: dict[str, str]) -> None:
    """Draw a schematic sketch of the measurement layout (stand-in for a map)."""
    with mpl.rc_context({"font.size": 10}):
        fig = Figure(figsize=(6, 3.6), dpi=100)
        ax = fig.subplots()
        angle = math.radians(60)
        ax.plot(
            [-60, 110], [0, 0], color="#888888", linewidth=2, label=text["map_line"]
        )
        ax.plot(
            [0, 100 * math.cos(angle)], [0, 100 * math.sin(angle)], ":", color="#1f4e79"
        )
        probes = np.array(PROBE_DISTANCES_M)
        ax.scatter(
            probes * math.cos(angle),
            probes * math.sin(angle),
            s=14,
            color="#1f4e79",
            label=text["map_probe"],
        )
        ax.scatter(
            [100 * math.cos(angle)],
            [100 * math.sin(angle)],
            s=60,
            marker="v",
            color="#c0392b",
            label=text["map_current"],
        )
        ax.scatter(
            [0],
            [0],
            s=90,
            marker="s",
            color="#222222",
            label=f"{text['map_tower']} {tower}",
        )
        ax.set_aspect("equal")
        ax.set_title(text["map_title"])
        ax.set_xlabel("m")
        ax.legend(loc="lower right", fontsize=8)
        fig.tight_layout()
        fig.savefig(path)


def _readings(
    tower: DemoTower, level_scale: float, text: dict[str, str]
) -> list[tuple[str, str, float]]:
    readings = []
    for location, voltage in tower.touch_voltages_v:
        name = text[location]
        readings.append((name, "1k", voltage * 1.4 * level_scale))
        readings.append((name, "2x1k", voltage * level_scale))
    return readings


def write_demo_campaign(
    target_dir: str | Path,
    *,
    language: str = "en",
    towers: Sequence[DemoTower] = DEMO_TOWERS,
    overwrite: bool = False,
) -> Path:
    """Create the demo campaign.

    Parameters
    ----------
    target_dir : str or pathlib.Path
        Folder to create (must be empty or not exist unless ``overwrite``).
    language : str, optional
        Language of the configuration, the location names and the texts.
    towers : sequence of DemoTower, optional
        Towers to generate.
    overwrite : bool, optional
        Allow writing into a non-empty folder.

    Returns
    -------
    pathlib.Path
        Path of the generated ``config.json``.

    Raises
    ------
    FileExistsError
        If ``target_dir`` exists, is not empty and ``overwrite`` is false.
    """
    lang = normalize_language(language)
    text = _TEXT[lang]
    target = Path(target_dir)
    if target.exists() and any(target.iterdir()) and not overwrite:
        raise FileExistsError(
            f"{target} is not empty; choose another folder or use overwrite=True"
        )
    measurements = target / "measurements"
    measurements.mkdir(parents=True, exist_ok=True)

    n_towers = LAST_TOWER - FIRST_TOWER + 1
    span_km = LINE_LENGTH_KM / (n_towers - 1)
    step_touch_current = (0.098, 0.102)
    i_meas = float(np.mean(step_touch_current))

    description_rows = []
    for tower in towers:
        index = int(tower.tower) - FIRST_TOWER
        ik_kA = float(short_circuit_current_kA(index, n_towers, span_km))
        earth_current = ik_kA * 1e3 * REDUCTION_FACTOR
        level_scale = i_meas / earth_current
        profile = fall_of_potential_profile(
            PROBE_DISTANCES_M, tower.earthing_impedance_ohm, tower.electrode_radius_m
        )
        stem = f"{DEMO_LINE}_{tower.tower}"
        write_compano_xml(
            measurements / f"ZE_{stem}.xml",
            PROBE_DISTANCES_M,
            profile,
            tower.footing_share,
            step_touch_current_a=step_touch_current,
        )
        write_hgt1_report(
            measurements / f"UT_{stem}.txt", _readings(tower, level_scale, text)
        )
        _write_map(measurements / f"Map_{stem}.png", tower.tower, text)
        if tower.soil_resistivity:
            spacing = [1.0, 2.0, 5.0, 10.0, 20.0]
            write_compano_xml(
                measurements / f"ZE_{stem}_spez.Erdw..xml",
                (),
                (),
                1.0,
                soil_resistivity={
                    "rho": [85.0, 92.0, 110.0, 135.0, 150.0],
                    "a": spacing,
                    "b": [0.2] * len(spacing),  # electrode depth
                    "c": spacing,
                },
            )
        if tower.neighbour:
            write_hgt1_report(
                measurements / f"UT_{stem}-{tower.neighbour}.txt",
                [
                    (text["tower"], "1k", 40.0 * level_scale),
                    (text["tower"], "2x1k", 28.0 * level_scale),
                ],
            )
        locations = [text[location] for location, _ in tower.touch_voltages_v]
        description_rows.append(
            {
                "Name": "Doe",
                "Vorname": "Jane",
                "Firma": "Example Earthing Services",
                "Datum": pd.Timestamp("2026-05-12"),
                "Leitung": DEMO_LINE,
                "Mast": int(tower.tower),
                "Entfernung_Hilfserder_m": CURRENT_ELECTRODE_DISTANCE_M,
                "Winkel_Sonde_Hilfserder_grad": 0,
                "Winkel_Leitung_Hilfserder_grad": 60,
                "Witterung": text["weather"],
                "Messtechnik_Name": "COMPANO 100 / HGT1",
                "Messfehler_Z_pu": 0.05,
                "Messfehler_U_pu": 0.02,
                "Messpunkte_UT": ", ".join(locations),
                "Messung_RA_Profil_bool": 1,
                "Messung_RA_Einzelwert_Ohm": tower.hf_footing_resistance_ohm,
                "Sichtbefund": text[tower.finding],
            }
        )

    pd.DataFrame(description_rows).to_excel(
        target / "measurement_description.xlsx", index=False
    )
    pd.DataFrame(
        {
            "Leitung": [DEMO_LINE] * len(towers),
            "Mast": [int(t.tower) for t in towers],
            "Reduktionsfaktor": [REDUCTION_FACTOR] * len(towers),
            "Abschaltzeit": [np.nan] * len(towers),
            "Fehlerstrom": [np.nan] * len(towers),
        }
    ).to_excel(target / "grid_data.xlsx", index=False)

    percent = np.arange(0, 101, 10)
    l_km = percent / 100 * LINE_LENGTH_KM
    training = pd.DataFrame(
        {
            "Fehlerort_Prozent": percent,
            "Ik": np.round(
                short_circuit_current_kA(l_km / span_km, n_towers, span_km), 3
            ),
            "l": np.round(l_km, 4),
            "Mast": [FIRST_TOWER] + [np.nan] * (len(percent) - 2) + [LAST_TOWER],
        }
    )
    protection = pd.DataFrame(
        [
            {
                "Leitung": DEMO_LINE,
                "Netzform": text["network"],
                "Schutzkonzept": text["protection"],
                "Mast_Anfang": FIRST_TOWER,
                "Mast_Ende": LAST_TOWER,
                "Schnellzeit_von_Prozent": 16,
                "Schnellzeit_bis_Prozent": 84,
                "t_Schnellzeit_s": 0.1,
                "t_Endbereich_s": 0.4,
                "Fehlerstrom_pauschal_kA": np.nan,
                "Reduktionsfaktor_pauschal": np.nan,
                "Bemerkung": "",
            }
        ]
    )
    with pd.ExcelWriter(
        target / "short_circuit_data.xlsx", engine="openpyxl"
    ) as writer:
        training.to_excel(writer, sheet_name=DEMO_LINE, index=False)
        protection.to_excel(writer, sheet_name="Leitungsschutz", index=False)

    config = {
        "_comment": "Demo campaign of gm-cli towers demo (synthetic data).",
        "language": lang,
        "logo": "",
        "nominal_frequency_Hz": NOMINAL_FREQUENCY_HZ,
        "touch_voltages": {
            "t_s": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 10.0],
            "U_TP_V": [633, 528, 410, 300, 204, 170, 140, 130, 120, 107, 80],
            "U_TP_ext_V": [1878, 1561, 1270, 831, 538, 397, 327, 287, 260, 244, 80],
        },
        "directory": {
            "path_measurements": "measurements",
            "path_grid_data": "grid_data.xlsx",
            "sc_current_data_path": "short_circuit_data.xlsx",
            "measurement_description_path": "measurement_description.xlsx",
            "json_export_path": "results",
            "path_summary": "results/summary.xlsx",
            "export_path_pdf": "results/protocols.zip",
            "grounding_impedance_structure": "PREFIX_LINENUMBER_TOWER",
        },
        "contacts": {
            "evaluation_first_name": "Alex",
            "evaluation_last_name": "Example",
            "evaluation_company": "Example Grid Operator",
        },
        "default_grid_data": {
            "r": REDUCTION_FACTOR,
            "tripping_time": 0.4,
            "fault_current_kA": 12,
        },
        "touch_voltage_evaluation": "with_resistor",
        "line_protection": {"enabled": True, "sheet_name": "Leitungsschutz"},
    }
    config_path = target / "config.json"
    config_path.write_text(
        json.dumps(config, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return config_path
