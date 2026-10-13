"""Audit 2026-10-13: unit conversion (mΩ, µΩ, mA, mV, kA, kΩm, ...).

Every path that turns a value with a unit into a number is checked against
two references: the same data written in the SI base unit, and the value
converted by hand. The paths are

* the OMICRON readers (COMPANO 100 XML, HGT1 report),
* the OCR import (``vision_import``),
* the analytics that read items from the database (profiles, impedance over
  frequency, per-ampere voltages, split factor, rho-f model, soil profile),
* the unit suggested by the interactive CLI.

Both spellings of the micro prefix occur in practice: U+00B5 MICRO SIGN
(``µ``, what most keyboards produce) and U+03BC GREEK SMALL LETTER MU
(``μ``, what many fonts and instruments produce); the ohm symbol likewise
as U+03A9 GREEK CAPITAL LETTER OMEGA and U+2126 OHM SIGN.
"""

from __future__ import annotations

import cmath
import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest

import groundmeas as gm
from groundmeas.core.units import UnitWarning
from groundmeas.instruments import CompanoXMLReader, Hgt1TXTReader
from groundmeas.services.vision_import import (
    _parse_value_angle_unit,
    parse_measurement_rows,
)
from groundmeas.ui import cli

MICRO = "µ"  # MICRO SIGN
MU = "μ"  # GREEK SMALL LETTER MU
OMEGA = "Ω"  # GREEK CAPITAL LETTER OMEGA
OHM_SIGN = "Ω"  # OHM SIGN

FOP = "FallOfPotentialReport/FallOfPotentialWidgetData/FallOfPotentialMeasurementScreenData"
STEP_TOUCH = "StepAndTouchReport/StepTouchWidgetData/OutputSetupScreenData"


# =========================================================================== helpers
def _edit_xml(source: Path, target: Path, edit: Callable[[ET.Element], None]) -> Path:
    """Copy a COMPANO export and apply ``edit`` to its ``ReportData``."""
    tree = ET.parse(source)
    edit(tree.getroot().find("ReportData"))
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target


def _rescale_series(
    screen: ET.Element, tag: str, unit: str, factor: float, scale_complex: bool
) -> None:
    """Write the results of ``<tag><Measurement>...`` in ``unit`` (= factor x SI)."""
    for measurement in screen.findall(f"{tag}/Measurement"):
        magnitude = measurement.find("Result/Magnitude")
        magnitude.find("Value").text = repr(
            float(magnitude.find("Value").text) / factor
        )
        magnitude.find("Unit").text = unit
        if scale_complex:
            for c in measurement.findall("Measurements/Complex"):
                for part in ("Real", "Imag"):
                    c.find(part).text = repr(float(c.find(part).text) / factor)


def _rescale_plain(container: ET.Element, unit: str, factor: float) -> None:
    """Rewrite ``<X><Value/><Unit/></X>`` and ``<X><Magnitude>...`` children."""
    for child in container:
        node = child.find("Magnitude") if child.find("Value") is None else child
        node.find("Value").text = repr(float(node.find("Value").text) / factor)
        node.find("Unit").text = unit


@pytest.fixture
def db() -> None:
    """In-memory database (disposed by the autouse fixture of conftest)."""
    gm.connect_db(":memory:")


def _store(items: list[dict[str, Any]], method: str = "staged_fault_test") -> int:
    """Store one measurement with ``items`` and return its id."""
    measurement_id, _ids = gm.create_measurement_with_items(
        {
            "method": method,
            "asset_type": "substation",
            "location": {"name": "Unit audit"},
        },
        items,
    )
    return measurement_id


# ================================================================ COMPANO 100 reader
VOLTAGE_UNITS = [
    ("mV", 1e-3),
    (f"{MICRO}V", 1e-6),
    (f"{MU}V", 1e-6),
    ("uV", 1e-6),
    ("kV", 1e3),
]
CURRENT_UNITS = [
    ("mA", 1e-3),
    (f"{MICRO}A", 1e-6),
    (f"{MU}A", 1e-6),
    ("uA", 1e-6),
]


@pytest.mark.parametrize("scale_complex", [False, True])
@pytest.mark.parametrize(("current_unit", "current_factor"), CURRENT_UNITS)
@pytest.mark.parametrize(("voltage_unit", "voltage_factor"), VOLTAGE_UNITS)
def test_compano_prefixed_voltages_and_currents(
    compano_xml: Path,
    tmp_path: Path,
    voltage_unit: str,
    voltage_factor: float,
    current_unit: str,
    current_factor: float,
    scale_complex: bool,
) -> None:
    reference = CompanoXMLReader(compano_xml).read_fall_of_potential()
    ref_profile, ref_residual = CompanoXMLReader(
        compano_xml
    ).get_impedance_to_ground_dataframe()

    def rescale(report: ET.Element) -> None:
        screen = report.find(FOP)
        _rescale_series(
            screen, "InputVoltages", voltage_unit, voltage_factor, scale_complex
        )
        _rescale_series(
            screen, "RawOutputCurrents", current_unit, current_factor, scale_complex
        )
        _rescale_plain(
            screen.find("CorrectedOutputCurrents"), current_unit, current_factor
        )
        _rescale_plain(
            report.find(f"{STEP_TOUCH}/Measurements"), current_unit, current_factor
        )

    path = _edit_xml(compano_xml, tmp_path / "prefixed.xml", rescale)
    data = CompanoXMLReader(path).read_fall_of_potential()
    profile, residual = CompanoXMLReader(path).get_impedance_to_ground_dataframe()

    # method 1: same export written in SI base units
    np.testing.assert_allclose(data.impedance(), reference.impedance(), rtol=1e-9)
    for f in reference.test_frequencies_hz:
        np.testing.assert_allclose(data.impedance(f), reference.impedance(f), rtol=1e-9)
    np.testing.assert_allclose(data.result_currents, reference.result_currents)
    np.testing.assert_allclose(profile["Impedance"], ref_profile["Impedance"])
    np.testing.assert_allclose(residual["Impedance"], ref_residual["Impedance"])
    np.testing.assert_allclose(
        np.abs(profile["StepTouchCurrent"]), np.abs(ref_profile["StepTouchCurrent"])
    )
    # method 2: hand-converted SI values of the fixture (README of tests/data)
    assert abs(data.result_currents[0]) == pytest.approx(0.0545)
    assert abs(profile["StepTouchCurrent"].iloc[0]) == pytest.approx(0.0535)


def test_compano_step_touch_currents_in_micro_ampere(
    compano_xml: Path, tmp_path: Path
) -> None:
    path = _edit_xml(
        compano_xml,
        tmp_path / "st.xml",
        lambda r: _rescale_plain(r.find(f"{STEP_TOUCH}/Measurements"), f"{MU}A", 1e-6),
    )
    _freq, currents = CompanoXMLReader(path).get_step_touch_currents()
    np.testing.assert_allclose(currents, [0.053, 0.054])


# ------------------------------------------------------------- COMPANO soil export
def _soil_export(
    path: Path, rho_unit: str, rho_factor: float, r_unit: str, r_factor: float
) -> tuple[Path, list[float], list[float]]:
    """Wenner soil export, resistivities and resistances in the given units."""
    spacing = [1.0, 2.0, 5.0]
    resistance = [10.0, 5.0, 2.0]
    rho = [2 * math.pi * a * r for a, r in zip(spacing, resistance)]
    root = ET.Element("Compano100Report")
    report = ET.SubElement(root, "ReportData")
    screen = ET.SubElement(
        ET.SubElement(
            ET.SubElement(report, "SoilResistanceReport"), "SoilResistanceWidgetData"
        ),
        "SoilResistanceMeasurementScreenData",
    )
    for tag in ("DistancesA", "DistancesB", "DistancesC"):
        container = ET.SubElement(screen, tag)
        for a in spacing:
            item = ET.SubElement(container, "Distance")
            ET.SubElement(item, "Value").text = repr(a if tag != "DistancesB" else 0.1)
            ET.SubElement(item, "Unit").text = "m"
    rho_node = ET.SubElement(screen, "SpecificResistances")
    impedances = ET.SubElement(screen, "Impedances")
    for value_rho, value_r in zip(rho, resistance):
        item = ET.SubElement(rho_node, "Rho")
        ET.SubElement(item, "Value").text = repr(value_rho / rho_factor)
        ET.SubElement(item, "Unit").text = rho_unit
        magnitude = ET.SubElement(impedances, "Magnitude")
        ET.SubElement(magnitude, "Value").text = repr(value_r / r_factor)
        ET.SubElement(magnitude, "Unit").text = r_unit
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path, rho, resistance


RESISTANCE_UNITS = [
    (OMEGA, 1.0),
    (OHM_SIGN, 1.0),
    ("Ohm", 1.0),
    ("ohm", 1.0),
    ("Ohms", 1.0),
    (f"m{OMEGA}", 1e-3),
    (f"m{OHM_SIGN}", 1e-3),
    ("mOhm", 1e-3),
    ("mohm", 1e-3),
    (f"{MICRO}{OMEGA}", 1e-6),
    (f"{MU}{OMEGA}", 1e-6),
    (f"{MU}{OHM_SIGN}", 1e-6),
    (f"u{OMEGA}", 1e-6),
    ("uOhm", 1e-6),
    (f"k{OMEGA}", 1e3),
    ("kOhm", 1e3),
    (f"M{OMEGA}", 1e6),
    ("MOhm", 1e6),
]


@pytest.mark.parametrize(("unit", "factor"), RESISTANCE_UNITS)
def test_compano_soil_resistance_units(
    tmp_path: Path, unit: str, factor: float
) -> None:
    path, rho, resistance = _soil_export(
        tmp_path / "soil.xml", f"{OMEGA}m", 1.0, unit, factor
    )
    data = CompanoXMLReader(path).read_soil_resistivity()
    assert data is not None and data.resistance_ohm is not None
    # method 1: hand-converted values; method 2: Wenner formula rho = 2 pi a R
    np.testing.assert_allclose(data.resistance_ohm, resistance, rtol=1e-12)
    np.testing.assert_allclose(
        data.rho_ohm_m, 2 * math.pi * data.spacing_a_m * data.resistance_ohm
    )


RESISTIVITY_UNITS = [
    (f"{OMEGA}m", 1.0),
    (f"{OHM_SIGN}m", 1.0),
    (f"{OMEGA} m", 1.0),
    (f"{OMEGA}·m", 1.0),
    (f"{OMEGA}*m", 1.0),
    ("Ohm m", 1.0),
    ("Ohm·m", 1.0),
    ("Ohm-m", 1.0),
    ("ohm-m", 1.0),
    ("ohm*m", 1.0),
    ("Ohmm", 1.0),
    (f"k{OMEGA}m", 1e3),
    (f"k{OMEGA}·m", 1e3),
    ("kOhm m", 1e3),
    ("kOhm-m", 1e3),
    (f"m{OMEGA}m", 1e-3),
    (f"M{OMEGA}m", 1e6),
    (f"{OMEGA}cm", 1e-2),
    (f"{OMEGA}·cm", 1e-2),
    ("Ohm-cm", 1e-2),
]


@pytest.mark.parametrize(("unit", "factor"), RESISTIVITY_UNITS)
def test_compano_soil_resistivity_units(
    tmp_path: Path, unit: str, factor: float
) -> None:
    path, rho, _resistance = _soil_export(
        tmp_path / "soil.xml", unit, factor, OMEGA, 1.0
    )
    data = CompanoXMLReader(path).read_soil_resistivity()
    assert data is not None
    np.testing.assert_allclose(data.rho_ohm_m, rho, rtol=1e-12)
    np.testing.assert_allclose(
        data.rho_ohm_m, 2 * math.pi * data.spacing_a_m * data.resistance_ohm
    )


# ======================================================================= HGT1 report
def _hgt1_variant(source: Path, target: Path, unit: str, factor: float) -> Path:
    """HGT1 report with both levels written in ``unit`` (= factor x V)."""
    lines = source.read_bytes().decode("ascii").split("\r\n")
    header_index = next(i for i, line in enumerate(lines) if "Level1" in line)
    header = [cell.strip() for cell in lines[header_index].split("\t")]
    columns = [header.index("Level1"), header.index("Level2")]
    units = lines[header_index + 1].split("\t")
    for col in columns:
        units[col] = unit
    lines[header_index + 1] = "\t".join(units)
    for i in range(header_index + 2, len(lines)):
        cells = lines[i].split("\t")
        if len(cells) != len(header):
            continue
        for col in columns:
            cells[col] = repr(float(cells[col]) / factor)
        lines[i] = "\t".join(cells)
    target.write_bytes("\r\n".join(lines).encode("utf-8"))
    return target


@pytest.mark.parametrize(
    ("unit", "factor"),
    [
        ("[V]", 1.0),
        ("[mV]", 1e-3),
        (f"[{MICRO}V]", 1e-6),
        (f"[{MU}V]", 1e-6),
        ("[uV]", 1e-6),
        ("[kV]", 1e3),
    ],
)
def test_hgt1_level_units(
    hgt1_txt: Path, tmp_path: Path, unit: str, factor: float
) -> None:
    reference = Hgt1TXTReader(hgt1_txt).get_touchvoltage_dataframe()
    path = _hgt1_variant(hgt1_txt, tmp_path / "UT_X_1.txt", unit, factor)
    df = Hgt1TXTReader(path).get_touchvoltage_dataframe()
    # method 1: report in V; method 2: first reading interpolated by hand
    np.testing.assert_allclose(df["Level50"], reference["Level50"], rtol=1e-12)
    assert df["Level50"].iloc[0] == pytest.approx(3.5e-3 + 20 * (5.5e-3 - 3.5e-3) / 40)


# ======================================================================== OCR import
@pytest.mark.parametrize(
    ("chunk", "expected"),
    [
        ("114.0 mA 0.00°", 0.114),
        ("13.46mV -136.56°", 0.01346),
        (f"118.1 m{OMEGA} -136.56°", 0.1181),
        ("118.1 mOhm", 0.1181),
        (f"2.5 k{OMEGA}", 2500.0),
        (f"1.2 M{OMEGA}", 1.2e6),
        (f"250 {MICRO}V 10°", 250e-6),
        (f"250 {MU}V", 250e-6),
        ("250 uV", 250e-6),
        (f"35 {MU}{OMEGA}", 35e-6),
        ("3 kA", 3000.0),
        (f"0.5 {OMEGA}", 0.5),
    ],
)
def test_ocr_value_with_unit_is_returned_in_si(chunk: str, expected: float) -> None:
    value, _angle, _unit = _parse_value_angle_unit(chunk)
    assert value == pytest.approx(expected, rel=1e-12)


def test_ocr_milliampere_is_not_read_as_milliohm() -> None:
    # current in mA, voltage in V, impedance in Ω: Z must not be taken from "mA"
    rows = parse_measurement_rows(f"10 m 114.0 mA 1.35 V 11.8 {OMEGA}")
    assert len(rows) == 1
    # method 1: the value on the display; method 2: U / I
    assert rows[0].impedance_ohm == pytest.approx(11.8, rel=1e-9)
    assert rows[0].impedance_ohm == pytest.approx(1.35 / 0.114, rel=0.01)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (f"Distance 10 m Z = 118.1 m{OMEGA}", 0.1181),
        (f"Distance 10 m Z = 2.5 k{OMEGA}", 2500.0),
        (f"Distance 10 m Z = 350 {MU}{OMEGA}", 350e-6),
        (f"Distance 10 m R = 350 {MICRO}{OMEGA}", 350e-6),
        ("Distance 10 m Z = 0.85 Ohm", 0.85),
    ],
)
def test_ocr_labelled_impedance_honours_the_unit(line: str, expected: float) -> None:
    rows = parse_measurement_rows(line)
    assert len(rows) == 1
    assert rows[0].distance_m == pytest.approx(10.0)
    assert rows[0].impedance_ohm == pytest.approx(expected, rel=1e-12)


# ========================================================================= analytics
@pytest.mark.parametrize(
    ("unit", "factor"),
    [
        (f"m{OMEGA}", 1e-3),
        ("mOhm", 1e-3),
        (f"{MICRO}{OMEGA}", 1e-6),
        (f"{MU}{OMEGA}", 1e-6),
        (f"k{OMEGA}", 1e3),
        ("kOhm", 1e3),
        (f"M{OMEGA}", 1e6),
    ],
)
def test_soil_profile_auto_detects_prefixed_resistance(
    db: None, unit: str, factor: float
) -> None:
    spacing = [1.0, 2.0, 5.0]
    resistance = [10.0, 5.0, 2.0]
    scaled = _store(
        [
            {
                "measurement_type": "soil_resistivity",
                "value": r / factor,
                "unit": unit,
                "measurement_distance_m": a,
            }
            for a, r in zip(spacing, resistance)
        ],
        method="wenner",
    )
    base = _store(
        [
            {
                "measurement_type": "soil_resistivity",
                "value": r,
                "unit": OMEGA,
                "measurement_distance_m": a,
            }
            for a, r in zip(spacing, resistance)
        ],
        method="wenner",
    )
    got = gm.soil_resistivity_profile(scaled, method="wenner")
    reference = gm.soil_resistivity_profile(base, method="wenner")
    by_hand = {0.5 * a: 2 * math.pi * a * r for a, r in zip(spacing, resistance)}
    assert sorted(got) == pytest.approx(sorted(by_hand))
    assert [got[k] for k in sorted(got)] == pytest.approx(
        [by_hand[k] for k in sorted(by_hand)]
    )
    assert [reference[k] for k in sorted(reference)] == pytest.approx(
        [by_hand[k] for k in sorted(by_hand)]
    )


@pytest.mark.parametrize(
    ("unit", "factor"),
    [
        (f"{OMEGA}m", 1.0),
        ("ohm-m", 1.0),
        (f"k{OMEGA}m", 1e3),
        ("kOhm m", 1e3),
        (f"{OMEGA}cm", 1e-2),
    ],
)
def test_soil_profile_auto_scales_prefixed_resistivity(
    db: None, unit: str, factor: float
) -> None:
    rho = {1.0: 120.0, 2.0: 95.0, 5.0: 60.0}
    mid = _store(
        [
            {
                "measurement_type": "soil_resistivity",
                "value": value / factor,
                "unit": unit,
                "measurement_distance_m": a,
            }
            for a, value in rho.items()
        ],
        method="wenner",
    )
    got = gm.soil_resistivity_profile(mid, method="wenner")
    assert [got[0.5 * a] for a in rho] == pytest.approx(list(rho.values()))


def _profile_items(units: list[str], factors: list[float]) -> list[dict[str, Any]]:
    """Fall-of-potential profile 0.30/0.38/0.35 Ω at 10/20/30 m in mixed units."""
    values = [0.30, 0.38, 0.35]
    return [
        {
            "measurement_type": "earthing_impedance",
            "frequency_hz": 50.0,
            "value": value / factor,
            "value_angle_deg": 5.0,
            "unit": unit,
            "measurement_distance_m": d,
            "distance_to_current_injection_m": 100.0,
        }
        for d, value, unit, factor in zip((10.0, 20.0, 30.0), values, units, factors)
    ]


def test_distance_profile_with_mixed_units(db: None) -> None:
    mixed = _store(_profile_items([OMEGA, f"m{OMEGA}", "Ohm"], [1.0, 1e-3, 1.0]))
    base = _store(_profile_items([OMEGA] * 3, [1.0] * 3))
    got = gm.distance_profile_value(mixed, algorithm="maximum")
    reference = gm.distance_profile_value(base, algorithm="maximum")
    assert got["result_value"] == pytest.approx(0.38)
    assert got["result_value"] == pytest.approx(reference["result_value"])
    assert got["result_distance_m"] == pytest.approx(20.0)
    assert got["unit"] in (OMEGA, OHM_SIGN, "Ohm", "ohm")
    assert [p["value"] for p in got["data_points"]] == pytest.approx([0.30, 0.38, 0.35])


def test_value_over_distance_with_mixed_units(db: None) -> None:
    mixed = _store(
        _profile_items([OMEGA, f"m{OMEGA}", f"{MU}{OMEGA}"], [1.0, 1e-3, 1e-6])
    )
    got = gm.value_over_distance(mixed)
    assert [got[d] for d in (10.0, 20.0, 30.0)] == pytest.approx([0.30, 0.38, 0.35])
    detailed = gm.value_over_distance_detailed(mixed)
    assert [p["value"] for p in detailed] == pytest.approx([0.30, 0.38, 0.35])


def test_impedance_and_real_imag_over_frequency_in_milliohm(db: None) -> None:
    z = 0.1181 * cmath.exp(1j * math.radians(-36.5))
    items = [
        {
            "measurement_type": "earthing_impedance",
            "frequency_hz": 50.0,
            "value_real": z.real * 1e3,
            "value_imag": z.imag * 1e3,
            "unit": f"m{OMEGA}",
        }
    ]
    mid = _store(items)
    assert gm.impedance_over_frequency(mid)[50.0] == pytest.approx(abs(z))
    ri = gm.real_imag_over_frequency(mid)[50.0]
    assert ri["real"] == pytest.approx(z.real)
    assert ri["imag"] == pytest.approx(z.imag)


def _vt_epr_items(
    z: tuple[float, str],
    i: tuple[float, str],
    vtp: tuple[float, str],
    vt: tuple[float, str],
) -> list[dict[str, Any]]:
    return [
        {
            "measurement_type": "earthing_impedance",
            "frequency_hz": 50.0,
            "value": z[0],
            "unit": z[1],
        },
        {
            "measurement_type": "earthing_current",
            "frequency_hz": 50.0,
            "value": i[0],
            "unit": i[1],
        },
        {
            "measurement_type": "prospective_touch_voltage",
            "frequency_hz": 50.0,
            "value": vtp[0],
            "unit": vtp[1],
        },
        {
            "measurement_type": "touch_voltage",
            "frequency_hz": 50.0,
            "value": vt[0],
            "unit": vt[1],
        },
    ]


def test_voltage_vt_epr_with_prefixed_units(db: None) -> None:
    base = _store(
        _vt_epr_items((0.5, OMEGA), (0.054, "A"), (0.027, "V"), (0.0135, "V"))
    )
    scaled = _store(
        _vt_epr_items((500.0, f"m{OMEGA}"), (54.0, "mA"), (0.027, "V"), (13.5, "mV"))
    )
    reference = gm.voltage_vt_epr(base)
    got = gm.voltage_vt_epr(scaled)
    by_hand = {"z_per_amp": 0.5, "vtp_max": 0.027 / 0.054, "vt_max": 0.0135 / 0.054}
    for key, value in by_hand.items():
        assert reference[key] == pytest.approx(value)
        assert got[key] == pytest.approx(value)


def test_split_factor_with_kiloampere_fault_current(db: None) -> None:
    fault = 2500.0
    shields = [
        800 * cmath.exp(1j * math.radians(-10)),
        450 * cmath.exp(1j * math.radians(5)),
    ]

    def store(fault_value: float, fault_unit: str) -> tuple[int, list[int]]:
        items = [
            {
                "measurement_type": "earth_fault_current",
                "value": fault_value,
                "value_angle_deg": 0.0,
                "unit": fault_unit,
                "frequency_hz": 50.0,
            },
        ] + [
            {
                "measurement_type": "shield_current",
                "value_real": s.real,
                "value_imag": s.imag,
                "unit": "A",
                "frequency_hz": 50.0,
            }
            for s in shields
        ]
        mid = _store(items)
        _items, ids = gm.read_items_by(measurement_id=mid)
        return ids[0], ids[1:]

    base_fault, base_shields = store(fault, "A")
    ka_fault, ka_shields = store(fault / 1e3, "kA")
    by_hand = abs(fault - sum(shields)) / fault
    assert gm.calculate_split_factor(base_fault, base_shields)[
        "split_factor"
    ] == pytest.approx(by_hand)
    got = gm.calculate_split_factor(ka_fault, ka_shields)
    assert got["split_factor"] == pytest.approx(by_hand)
    assert got["earth_fault_current"]["value"] == pytest.approx(fault)


def test_rho_f_model_with_milliohm_impedances(db: None) -> None:
    k = (0.004, 1e-4, 2e-4, 3e-6, 1e-6)

    def model(rho: float, f: float) -> complex:
        return k[0] * rho + (k[1] + 1j * k[2]) * f + (k[3] + 1j * k[4]) * rho * f

    def store(rho: float, factor: float, unit: str) -> int:
        items: list[dict[str, Any]] = [
            {
                "measurement_type": "soil_resistivity",
                "value": rho,
                "unit": f"{OMEGA}m",
                "measurement_distance_m": 1.0,
            },
        ]
        for f in (30.0, 50.0, 70.0, 120.0):
            z = model(rho, f)
            items.append(
                {
                    "measurement_type": "earthing_impedance",
                    "frequency_hz": f,
                    "value_real": z.real / factor,
                    "value_imag": z.imag / factor,
                    "unit": unit,
                }
            )
        return _store(items)

    base = [store(rho, 1.0, OMEGA) for rho in (50.0, 200.0, 800.0)]
    scaled = [store(rho, 1e-3, f"m{OMEGA}") for rho in (50.0, 200.0, 800.0)]
    # method 1: coefficients of the generating model; method 2: SI data
    assert gm.rho_f_model(base) == pytest.approx(k, rel=1e-6)
    assert gm.rho_f_model(scaled) == pytest.approx(k, rel=1e-6)


# ============================================================================== CLI
@pytest.mark.parametrize(
    ("measurement_type", "expected"),
    [
        ("earthing_impedance", (OMEGA,)),
        ("earthing_resistance", (OMEGA,)),
        ("earthing_current", ("A",)),
        ("earth_fault_current", ("A",)),
        ("shield_current", ("A",)),
        ("touch_voltage", ("V",)),
        ("prospective_touch_voltage", ("V",)),
        ("earth_potential_rise", ("V",)),
        ("step_voltage", ("V",)),
        ("transferred_potential", ("V",)),
        ("soil_resistivity", (f"{OMEGA}m", f"{OMEGA}·m")),
    ],
)
def test_cli_suggests_the_unit_of_the_measurement_type(
    monkeypatch: pytest.MonkeyPatch, measurement_type: str, expected: tuple[str, ...]
) -> None:
    defaults: dict[str, Any] = {}

    def prompt_text(label: str, default: Any = None, **_kwargs: Any) -> Any:
        defaults[label] = default
        return default

    choices = iter([measurement_type, "magnitude_angle"])
    monkeypatch.setattr(cli, "_prompt_text", prompt_text)
    monkeypatch.setattr(cli, "_prompt_choice", lambda *a, **k: next(choices))
    monkeypatch.setattr(cli, "_prompt_float", lambda *a, **k: k.get("default") or 1.0)
    monkeypatch.setattr(
        cli, "_existing_item_values", lambda field, measurement_type=None: []
    )
    monkeypatch.setattr(cli, "_existing_item_units", lambda measurement_type: [])
    stored: dict[str, Any] = {}
    monkeypatch.setattr(
        cli, "create_item", lambda item, measurement_id: stored.update(item) or 1
    )
    cli.add_item(1)
    assert defaults["Unit"] in expected
    assert stored["unit"] in expected


# ==================================================== stored data and robustness
def test_voltage_stored_with_the_former_cli_default_unit_a(db: None) -> None:
    """groundmeas <= 1.6.0 suggested "A" for voltages: keep the values, warn."""
    labelled_v = _store(
        _vt_epr_items((0.5, OMEGA), (0.054, "A"), (0.027, "V"), (0.0135, "V"))
    )
    labelled_a = _store(
        _vt_epr_items((0.5, OMEGA), (0.054, "A"), (0.027, "A"), (0.0135, "A"))
    )
    reference = gm.voltage_vt_epr(labelled_v)
    with pytest.warns(UnitWarning, match="'A' is a current unit, expected voltage"):
        got = gm.voltage_vt_epr(labelled_a)
    assert got == pytest.approx(reference)


def test_soil_value_kind_overrides_a_contradicting_unit(db: None) -> None:
    mid = _store(
        [
            {
                "measurement_type": "soil_resistivity",
                "value": 2.0,
                "unit": f"{OMEGA}m",
                "measurement_distance_m": 4.0,
            }
        ],
        method="wenner",
    )
    with pytest.warns(UnitWarning, match="is a resistivity unit but value_kind"):
        got = gm.soil_resistivity_profile(mid, method="wenner", value_kind="resistance")
    # value used as stored, as before: rho = 2 pi a R
    assert got[2.0] == pytest.approx(2 * math.pi * 4.0 * 2.0)


def test_soil_profile_with_unknown_unit_uses_the_former_rule(db: None) -> None:
    mid = _store(
        [
            {
                "measurement_type": "soil_resistivity",
                "value": 80.0,
                "unit": "Ohm-meter2",
                "measurement_distance_m": 4.0,
            }
        ],
        method="wenner",
    )
    with pytest.warns(UnitWarning, match="unknown unit"):
        got = gm.soil_resistivity_profile(mid, method="wenner")
    assert got[2.0] == pytest.approx(80.0)


def test_distance_profile_of_soil_resistivity_in_ohm_metre(db: None) -> None:
    mid = _store(
        [
            {
                "measurement_type": "soil_resistivity",
                "value": value,
                "unit": unit,
                "measurement_distance_m": a,
            }
            for a, value, unit in (
                (1.0, 0.12, f"k{OMEGA}m"),
                (2.0, 95.0, "ohm-m"),
                (5.0, 6000.0, f"{OMEGA}cm"),
            )
        ],
        method="wenner",
    )
    out = gm.distance_profile_value(
        mid, measurement_type="soil_resistivity", algorithm="maximum"
    )
    assert out["unit"] == f"{OMEGA}m"
    assert out["result_value"] == pytest.approx(120.0)
    assert [p["value"] for p in out["data_points"]] == pytest.approx([120, 95, 60])


def test_rho_f_model_converts_and_reports_soil_units(db: None) -> None:
    def store(rho_value: float, rho_unit: str) -> int:
        items: list[dict[str, Any]] = [
            {
                "measurement_type": "soil_resistivity",
                "value": rho_value,
                "unit": rho_unit,
                "measurement_distance_m": 1.0,
            },
        ]
        for f in (30.0, 50.0, 70.0):
            items.append(
                {
                    "measurement_type": "earthing_impedance",
                    "frequency_hz": f,
                    "value_real": 0.5 + 0.001 * f,
                    "value_imag": 0.0002 * f,
                    "unit": OMEGA,
                }
            )
        return _store(items)

    base = [store(100.0, f"{OMEGA}m"), store(300.0, f"{OMEGA}m")]
    scaled = [store(0.1, f"k{OMEGA}m"), store(30000.0, f"{OMEGA}cm")]
    assert gm.rho_f_model(scaled) == pytest.approx(gm.rho_f_model(base))
    resistance = [store(100.0, OMEGA), store(300.0, OMEGA)]
    with pytest.warns(UnitWarning, match="is a resistance unit, expected resistivity"):
        gm.rho_f_model(resistance)


def test_shield_currents_for_location_in_ampere(db: None) -> None:
    mid = _store(
        [
            {
                "measurement_type": "shield_current",
                "value": 0.8,
                "unit": "kA",
                "frequency_hz": 50.0,
            },
            {
                "measurement_type": "shield_current",
                "value": 450.0,
                "unit": "A",
                "frequency_hz": 50.0,
            },
        ]
    )
    measurement = gm.read_measurements_by(id=mid)[0][0]
    got = gm.shield_currents_for_location(measurement["location_id"])
    assert sorted(c["value"] for c in got) == pytest.approx([450.0, 800.0])
    assert {c["unit"] for c in got} == {"A"}


def test_reader_rejects_values_without_unit(compano_xml: Path, tmp_path: Path) -> None:
    from groundmeas.instruments import MeasurementFileError

    def drop_one_unit(report: ET.Element) -> None:
        distance = report.find(f"{FOP}/Distances/Distance")
        distance.remove(distance.find("Unit"))

    path = _edit_xml(compano_xml, tmp_path / "no_unit.xml", drop_one_unit)
    with pytest.raises(MeasurementFileError, match="distance values but"):
        CompanoXMLReader(path).read_fall_of_potential()


def test_unit_factors_constant_keeps_its_former_entries() -> None:
    from groundmeas.instruments.omicron import UNIT_FACTORS

    former = {
        "current": {"A": 1.0, "mA": 1e-3, "kA": 1e3, "µA": 1e-6, "uA": 1e-6},
        "voltage": {"V": 1.0, "mV": 1e-3, "kV": 1e3, "µV": 1e-6, "uV": 1e-6},
        "distance": {"m": 1.0, "cm": 1e-2, "km": 1e3, "ft": 0.3048},
        "resistance": {
            OMEGA: 1.0,
            "Ohm": 1.0,
            f"m{OMEGA}": 1e-3,
            f"k{OMEGA}": 1e3,
            f"M{OMEGA}": 1e6,
        },
        "resistivity": {
            f"{OMEGA}m": 1.0,
            f"{OMEGA} m": 1.0,
            f"{OMEGA}·m": 1.0,
            "Ohm m": 1.0,
            "Ohmm": 1.0,
            f"m{OMEGA}m": 1e-3,
            f"k{OMEGA}m": 1e3,
            f"k{OMEGA} m": 1e3,
            f"k{OMEGA}·m": 1e3,
            f"M{OMEGA}m": 1e6,
        },
    }
    for quantity, entries in former.items():
        for unit, factor in entries.items():
            assert UNIT_FACTORS[quantity][unit] == factor
    assert UNIT_FACTORS["current"][f"{MU}A"] == 1e-6


@pytest.mark.parametrize(
    ("chunk", "expected"),
    [
        ("5 MA", 5e-3),  # OCR confuses the case of m; no mega-amperes on displays
        ("13.5 MV", 0.0135),
        ("118.1 m", 0.1181),  # unit symbol lost: the prefix still applies
        ("2.5 KΩ", 2500.0),
        (f"118.1 m{OHM_SIGN}", 0.1181),
        ("118.1 m0", 0.1181),  # Ω read as zero
    ],
)
def test_ocr_unit_leniency(chunk: str, expected: float) -> None:
    value, _angle, _unit = _parse_value_angle_unit(chunk)
    assert value == pytest.approx(expected, rel=1e-12)


def test_ocr_rows_with_micro_kilo_and_mega_prefixes() -> None:
    rows = parse_measurement_rows(
        f"1.0m | 114.0 mA 0.00° | 250 {MU}V 10.00° | 2.193 m{OMEGA} 10.00°"
    )
    assert len(rows) == 1
    assert rows[0].current_a == pytest.approx(0.114)
    assert rows[0].voltage_v == pytest.approx(250e-6)
    # two methods: the impedance read and U / I
    assert rows[0].impedance_ohm == pytest.approx(2.193e-3)
    assert rows[0].impedance_ohm == pytest.approx(250e-6 / 0.114, rel=1e-3)

    rows = parse_measurement_rows(f"5.0m | 0.5 {MICRO}A | 1.1 V | 2.2 M{OMEGA}")
    assert rows[0].current_a == pytest.approx(0.5e-6)
    assert rows[0].impedance_ohm == pytest.approx(2.2e6)

    rows = parse_measurement_rows(f"20 m 2.5 kA 1.25 kV 0.5 {OMEGA}")
    assert rows[0].voltage_v == pytest.approx(1250.0)
    assert rows[0].impedance_ohm == pytest.approx(0.5)
    assert rows[0].impedance_ohm == pytest.approx(1250.0 / 2500.0)


def test_cli_warns_about_a_unit_that_cannot_be_converted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "_existing_item_units", lambda measurement_type: [])
    monkeypatch.setattr(cli, "_prompt_text", lambda *a, **k: "A")
    assert cli._prompt_unit("touch_voltage") == "A"  # stored as entered
    out = capsys.readouterr().out
    assert "'A' is a current unit, expected voltage" in out
    monkeypatch.setattr(cli, "_prompt_text", lambda *a, **k: "mV")
    assert cli._prompt_unit("touch_voltage") == "mV"
    assert capsys.readouterr().out == ""


def test_cli_offers_only_convertible_existing_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli, "_existing_item_units", lambda measurement_type: ["A", "mV", "furlong"]
    )
    assert cli._unit_choices("touch_voltage") == ["mV", "V", "kV"]
    defaults: dict[str, Any] = {}

    def prompt_text(label: str, default: Any = None, **_kwargs: Any) -> Any:
        defaults[label] = default
        return default

    monkeypatch.setattr(cli, "_prompt_text", prompt_text)
    assert cli._prompt_unit("touch_voltage") == "mV"
    assert cli._prompt_unit("touch_voltage", current="kV") == "kV"


def test_ocr_prefixes_do_not_match_words() -> None:
    rows = parse_measurement_rows(f"10 m 4 Kabel 118.1 m{OMEGA}")
    assert rows[0].current_a is None  # "4 Ka..." is no current in kA
    assert rows[0].impedance_ohm == pytest.approx(0.1181)
    # "2 na..." is no current in nA, "kΩm" (a resistivity) no impedance in kΩ
    rows = parse_measurement_rows(f"10 m 2 nach 3.2 k{OMEGA}m")
    assert all(r.current_a is None and r.impedance_ohm is None for r in rows)
    # a lost unit symbol after "n" (n/a) does not scale the value
    value, _angle, unit = _parse_value_angle_unit("114.0 n/a")
    assert value == pytest.approx(114.0) and unit is None


@pytest.mark.parametrize(
    ("prefix", "symbol", "factor", "unit"),
    [
        ("m", "A", 1e-3, "mA"),
        ("M", "A", 1e-3, "mA"),
        ("M", OMEGA, 1e6, f"M{OMEGA}"),
        ("K", "ohm", 1e3, f"k{OMEGA}"),
        ("u", "V", 1e-6, f"{MU}V"),
        ("n", "V", 1e-9, "nV"),  # prefix not used for voltages: applied anyway
        ("", "0", 1.0, OMEGA),
        (MICRO, None, 1e-6, None),
        ("n", None, 1.0, None),
        ("u", None, 1.0, None),
        ("k", "x", 1e3, None),  # unknown symbol read: treated like a lost one
    ],
)
def test_ocr_unit_factor(prefix: str, symbol: Any, factor: float, unit: Any) -> None:
    from groundmeas.services.vision_import import _ocr_unit_factor

    assert _ocr_unit_factor(prefix, symbol) == (pytest.approx(factor), unit)
