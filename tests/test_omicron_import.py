"""Tests for groundmeas.services.omicron_import (COMPANO/HGT1 -> database)."""

from __future__ import annotations

import cmath
import datetime as dt
import math
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

import groundmeas as gm
from groundmeas.instruments import CompanoXMLReader, Hgt1TXTReader
from groundmeas.services.omicron_import import (
    fall_of_potential_items,
    parse_instrument_timestamp,
    soil_resistivity_items,
    step_touch_items,
)
from groundmeas.ui import cli

DISTANCES = [1.0, 5.0, 10.0, 20.0, 30.0, 40.0, 60.0]
RF = "FallOfPotentialReport/FallOfPotentialWidgetData/ReductionFactorScreenData"


def model_impedance(x):
    """Hemispherical electrode of the synthetic COMPANO fixture."""
    r, a, d = 0.40, 3.0, 100.0
    x = np.asarray(x, dtype=float)
    return r * a * (1 / a - 1 / d - 1 / (a + x) + 1 / (d - a - x))


@pytest.fixture
def db():
    gm.connect_db(":memory:")
    yield
    gm.disconnect_db()


def _items(measurement_id, **filters):
    items, _ = gm.read_items_by(measurement_id=measurement_id, **filters)
    return items


# ----------------------------------------------------------------------- time stamps
@pytest.mark.parametrize(
    ("text", "zone", "expected"),
    [
        ("2025-09-10 12:19:39.914", None, dt.datetime(2025, 9, 10, 12, 19, 39, 914000)),
        ("2025-09-10 12:19:39", None, dt.datetime(2025, 9, 10, 12, 19, 39)),
        ("2025-09-10", None, dt.datetime(2025, 9, 10)),
        ("2025-09-10 12:00:00.000", "Europe/Berlin", dt.datetime(2025, 9, 10, 10, 0)),
        ("2025-01-10 12:00:00.000", "Europe/Berlin", dt.datetime(2025, 1, 10, 11, 0)),
        ("", None, None),
        (None, None, None),
        ("10.09.2025", None, None),
    ],
)
def test_parse_instrument_timestamp(text, zone, expected):
    assert parse_instrument_timestamp(text, zone) == expected


# ----------------------------------------------------------------- fall of potential
def test_import_fall_of_potential(db, compano_xml):
    mid = gm.import_fall_of_potential(
        compano_xml,
        location={"name": "LX-01 tower 8", "latitude": 52.1, "longitude": 10.2},
        asset_type="overhead_line_tower",
        current_electrode_distance_m=100.0,
        operator="Jane Doe",
        voltage_level_kv=110.0,
    )
    measurement = gm.read_measurements_by(id=mid)[0][0]
    assert measurement["method"] == "injection_earth_electrode"
    assert measurement["asset_type"] == "overhead_line_tower"
    assert measurement["location"]["name"] == "LX-01 tower 8"
    assert measurement["voltage_level_kv"] == 110.0
    assert measurement["timestamp"] == dt.datetime(2024, 1, 1, 9, 10)
    assert "compano_fall_of_potential.xml" in measurement["description"]

    counts = Counter(
        (i["measurement_type"], i["frequency_hz"]) for i in measurement["items"]
    )
    assert counts == {
        ("earthing_impedance", 50.0): 7,
        ("earthing_impedance", 30.0): 7,
        ("earthing_impedance", 70.0): 7,
        ("earthing_resistance", 50.0): 7,
        ("earthing_current", 50.0): 1,
    }
    # two methods: database profile vs. the generating model
    profile = sorted(
        (i["measurement_distance_m"], i["value"])
        for i in _items(mid, measurement_type="earthing_impedance", frequency_hz=50.0)
    )
    np.testing.assert_allclose([z for _, z in profile], model_impedance(DISTANCES))
    footing = sorted(
        (i["measurement_distance_m"], i["value"])
        for i in _items(mid, measurement_type="earthing_resistance")
    )
    np.testing.assert_allclose([r for _, r in footing], 2 * model_impedance(DISTANCES))
    assert all(
        i["distance_to_current_injection_m"] == 100.0
        for i in _items(mid, measurement_type="earthing_impedance")
    )
    current = _items(mid, measurement_type="earthing_current")[0]
    assert current["value"] == pytest.approx(0.0545, rel=1e-3)


def test_fall_of_potential_profile_evaluation(db, compano_xml):
    mid = gm.import_fall_of_potential(
        compano_xml,
        location="T",
        asset_type="overhead_line_tower",
        current_electrode_distance_m=100.0,
    )
    for f in (30.0, 50.0, 70.0):
        out = gm.distance_profile_value(
            mid, algorithm="62_percent", frequency_hz=f, conservative=True
        )
        # d62 = 62 m lies beyond the last probe (60 m): extrapolated value
        x, z = np.array(DISTANCES[-3:]), model_impedance(DISTANCES[-3:])
        slope = (z[-1] - z[-2]) / (x[-1] - x[-2])
        assert out["result_value"] == pytest.approx(z[-1] + 2 * slope, rel=1e-6)
    by_frequency = gm.impedance_over_frequency(mid)
    assert set(by_frequency) == {30.0, 50.0, 70.0}


def test_fall_of_potential_without_per_frequency_and_distance(db, compano_xml, caplog):
    mid = gm.import_fall_of_potential(
        compano_xml, location="T", asset_type="substation", per_frequency=False
    )
    items = _items(mid)
    assert len(items) == 15
    assert "no current-electrode distance" in caplog.text
    with pytest.raises(ValueError, match="distance_to_current_injection_m"):
        gm.distance_profile_value(mid, algorithm="62_percent")


def test_fall_of_potential_timezone(db, compano_xml):
    mid = gm.import_fall_of_potential(
        compano_xml, location="T", asset_type="substation", timezone="Europe/Berlin"
    )
    assert gm.read_measurements_by(id=mid)[0][0]["timestamp"] == dt.datetime(
        2024, 1, 1, 8, 10
    )


def _add_measurement(container, values, unit):
    measurement = ET.SubElement(container, "Measurement")
    raw = ET.SubElement(measurement, "Measurements")
    for value in values:
        cpx = ET.SubElement(raw, "Complex")
        ET.SubElement(cpx, "Real").text = repr(value.real)
        ET.SubElement(cpx, "Imag").text = repr(value.imag)
    mean = complex(np.mean(values))
    result = ET.SubElement(measurement, "Result")
    magnitude = ET.SubElement(result, "Magnitude")
    ET.SubElement(magnitude, "Value").text = repr(abs(mean))
    ET.SubElement(magnitude, "Unit").text = unit
    phase = ET.SubElement(result, "Phase")
    ET.SubElement(phase, "Value").text = repr(math.degrees(cmath.phase(mean)))
    ET.SubElement(phase, "Unit").text = "°"


def _with_clamp_readings(source: Path, target: Path) -> tuple[Path, complex]:
    tree = ET.parse(source)
    screen = tree.getroot().find("ReportData").find(RF)
    legs = [0.012 * cmath.exp(1j * math.radians(35))] * 4
    for tag, values in (
        ("OutputCurrents", [complex(0.19, 0)] * 4),
        ("InputCurrents", legs),
    ):
        container = screen.find(tag)
        for child in list(container):
            container.remove(child)
        for value in values:
            _add_measurement(container, [value, value], "A")
    factor = sum(legs) / 0.19
    node = screen.find("ReductionFactorData")
    node.find("Magnitude/Value").text = repr(abs(factor))
    node.find("Phase/Value").text = repr(math.degrees(cmath.phase(factor)))
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target, factor


def test_reduction_factor_gives_split_factor(db, compano_xml, tmp_path):
    path, factor = _with_clamp_readings(compano_xml, tmp_path / "rf.xml")
    mid = gm.import_fall_of_potential(
        path, location="T", asset_type="overhead_line_tower"
    )
    fault = _items(mid, measurement_type="earth_fault_current")
    shield = _items(mid, measurement_type="shield_current")
    assert len(fault) == len(shield) == 1
    result = gm.calculate_split_factor(fault[0]["id"], [shield[0]["id"]])
    # two methods: instrument factor vs. split factor of the stored currents
    assert result["split_factor"] == pytest.approx(abs(factor))
    assert result["local_earthing_current"]["value_angle_deg"] == pytest.approx(
        math.degrees(cmath.phase(factor))
    )


def test_fall_of_potential_items_without_reduction(compano_xml):
    data = CompanoXMLReader(compano_xml).read_fall_of_potential()
    plain = fall_of_potential_items(data, per_frequency=False)
    kinds = Counter(i["measurement_type"] for i in plain)
    assert kinds == {
        "earthing_impedance": 7,
        "earthing_resistance": 7,
        "earthing_current": 1,
    }
    assert all("distance_to_current_injection_m" not in i for i in plain)


# ----------------------------------------------------------------- touch voltages
def test_import_step_touch(db, compano_xml, hgt1_txt):
    mid = gm.import_step_touch(
        hgt1_txt,
        location="LX-01 tower 8",
        asset_type="overhead_line_tower",
        compano_xml_path=compano_xml,
    )
    measurement = gm.read_measurements_by(id=mid)[0][0]
    assert measurement["timestamp"] == dt.datetime(2024, 1, 1, 10, 1)
    touch = _items(mid, measurement_type="touch_voltage", frequency_hz=50.0)
    assert len(touch) == 6
    assert {i["input_impedance_ohm"] for i in touch} == {1000.0}
    assert (
        sorted(i["additional_resistance_ohm"] for i in touch)
        == [0.0] * 3 + [1000.0] * 3
    )
    assert touch[0]["description"].startswith("MAST (1k")
    current = _items(mid, measurement_type="earthing_current", frequency_hz=50.0)
    assert current[0]["value"] == pytest.approx(0.0535)
    assert len(_items(mid, measurement_type="earthing_current")) == 3

    # per-ampere touch voltages with additional resistor (two methods)
    readings = Hgt1TXTReader(hgt1_txt).get_touchvoltage_dataframe()
    expected = readings.loc[readings["Termination"] == "2x1k", "Level50"] / 0.0535
    gm.create_items(
        [
            {
                "measurement_type": "earthing_impedance",
                "value": 0.4,
                "unit": "Ω",
                "frequency_hz": 50.0,
            }
        ],
        measurement_id=mid,
    )
    with pytest.warns(UserWarning):  # no prospective touch voltages
        out = gm.voltage_vt_epr(mid, additional_resistance_ohm=1000.0)
    assert out["vt_max"] == pytest.approx(expected.max())
    assert out["vt_min"] == pytest.approx(expected.min())


def test_import_transferred_potential_without_compano(db, hgt1_txt):
    mid = gm.import_step_touch(
        hgt1_txt,
        location="LX-01 tower 9",
        asset_type="overhead_line_tower",
        transferred=True,
        per_frequency=False,
        nominal_frequency_hz=60.0,
    )
    items = _items(mid)
    assert {i["measurement_type"] for i in items} == {"transferred_potential"}
    assert {i["frequency_hz"] for i in items} == {60.0}
    assert len(items) == 6
    assert (
        "Transferred potential" in gm.read_measurements_by(id=mid)[0][0]["description"]
    )


def test_step_touch_items_unknown_termination(hgt1_txt, caplog):
    readings = Hgt1TXTReader(hgt1_txt).get_touchvoltage_dataframe()
    readings.loc[0, "Termination"] = "open"
    with caplog.at_level("WARNING", logger="groundmeas"):
        items = step_touch_items(readings, per_frequency=False)
    assert "additional_resistance_ohm" not in items[0]
    assert "input_impedance_ohm" not in items[0]  # not a 1 kΩ reading
    assert items[0]["measurement_type"] == "touch_voltage"
    assert items[1]["additional_resistance_ohm"] == 1000.0
    assert "Unknown HGT1 termination 'open'" in caplog.text


@pytest.mark.parametrize("termination", ["HIGHZ", "High Z", "hi-z", "200k"])
def test_step_touch_items_high_impedance(hgt1_txt, termination):
    readings = Hgt1TXTReader(hgt1_txt).get_touchvoltage_dataframe()
    readings.loc[0, "Termination"] = termination
    items = step_touch_items(readings, per_frequency=False)
    assert items[0]["measurement_type"] == "prospective_touch_voltage"
    assert "input_impedance_ohm" not in items[0]
    assert items[1]["measurement_type"] == "touch_voltage"
    transferred = step_touch_items(
        readings, per_frequency=False, measurement_type="transferred_potential"
    )
    assert transferred[0]["measurement_type"] == "transferred_potential"


def _results_only(source: Path, target: Path) -> Path:
    """Remove the values at the test frequencies (keep the instrument results)."""
    tree = ET.parse(source)
    for parent in tree.getroot().iter():
        for child in list(parent):
            if child.tag == "Measurements" and child.find("Complex") is not None:
                parent.remove(child)
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target


def test_import_fall_of_potential_results_only(db, compano_xml, tmp_path):
    path = _results_only(compano_xml, tmp_path / "ZE_results_only.xml")
    assert not CompanoXMLReader(path).read_fall_of_potential().has_test_frequency_values
    mid = gm.import_fall_of_potential(
        path,
        location="LX-01 tower 8",
        asset_type="overhead_line_tower",
        current_electrode_distance_m=100,
    )
    profile = _items(mid, measurement_type="earthing_impedance")
    assert {i["frequency_hz"] for i in profile} == {50.0}
    reference = _items(
        gm.import_fall_of_potential(
            compano_xml,
            location="LX-01 tower 8",
            asset_type="overhead_line_tower",
            current_electrode_distance_m=100,
        ),
        measurement_type="earthing_impedance",
        frequency_hz=50.0,
    )
    assert [i["value"] for i in profile] == pytest.approx(
        [i["value"] for i in reference]
    )


def test_import_is_atomic(db, compano_xml, monkeypatch):
    import groundmeas.services.omicron_import as omicron_import

    monkeypatch.setattr(
        omicron_import,
        "fall_of_potential_items",
        lambda *args, **kwargs: [{"measurement_type": "earthing_current"}],
    )
    with pytest.raises(ValueError):
        gm.import_fall_of_potential(
            compano_xml, location="LX-01 tower 8", asset_type="overhead_line_tower"
        )
    assert gm.read_measurements_by()[0] == []  # no empty measurement left behind


# --------------------------------------------------------------------------- soil
def _soil_export(path, a, c, rho):
    root = ET.Element("Compano100Report")
    report = ET.SubElement(root, "ReportData")
    ET.SubElement(report, "TimeStamp").text = "2024-01-01 11:00:00.000"
    screen = ET.SubElement(
        ET.SubElement(
            ET.SubElement(report, "SoilResistanceReport"), "SoilResistanceWidgetData"
        ),
        "SoilResistanceMeasurementScreenData",
    )
    for tag, values in (
        ("DistancesA", a),
        ("DistancesB", [0.2] * len(a)),
        ("DistancesC", c),
    ):
        container = ET.SubElement(screen, tag)
        for value in values:
            item = ET.SubElement(container, "Distance")
            ET.SubElement(item, "Value").text = repr(float(value))
            ET.SubElement(item, "Unit").text = "m"
    container = ET.SubElement(screen, "SpecificResistances")
    for value in rho:
        item = ET.SubElement(container, "Rho")
        ET.SubElement(item, "Value").text = repr(float(value))
        ET.SubElement(item, "Unit").text = "Ωm"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_import_soil_schlumberger_and_inversion(db, tmp_path):
    """Homogeneous soil: the inversion must return the true resistivity."""
    c = [2.0, 4.0, 6.0, 10.0, 16.0, 26.0]
    path = _soil_export(tmp_path / "soil.xml", [4.0] * 6, c, [120.0] * 6)
    mid = gm.import_soil_resistivity(
        path, location="LX-01 tower 8", asset_type="overhead_line_tower"
    )
    measurement = gm.read_measurements_by(id=mid)[0][0]
    assert measurement["method"] == "schlumberger"
    assert measurement["timestamp"] == dt.datetime(2024, 1, 1, 11, 0)
    items = sorted(_items(mid), key=lambda i: i["measurement_distance_m"])
    np.testing.assert_allclose(
        [i["measurement_distance_m"] for i in items], [ci + 2.0 for ci in c]
    )
    assert {i["distance_to_current_injection_m"] for i in items} == {2.0}
    result = gm.invert_soil_resistivity_layers(
        mid, method="schlumberger", layers=1, value_kind="resistivity"
    )
    assert result["rho_layers"][0] == pytest.approx(120.0, rel=1e-3)


def test_import_soil_wenner(db, tmp_path):
    spacing = [1.0, 2.0, 5.0]
    path = _soil_export(tmp_path / "w.xml", spacing, spacing, [80.0, 85.0, 90.0])
    mid = gm.import_soil_resistivity(path, location="S", asset_type="substation")
    assert gm.read_measurements_by(id=mid)[0][0]["method"] == "wenner"
    items = sorted(_items(mid), key=lambda i: i["measurement_distance_m"])
    assert [i["measurement_distance_m"] for i in items] == spacing
    assert all(
        "distance_to_current_injection_m" not in i
        or i["distance_to_current_injection_m"] is None
        for i in items
    )
    method, payloads = soil_resistivity_items(
        CompanoXMLReader(path).read_soil_resistivity()
    )
    assert method == "wenner" and len(payloads) == 3


def test_import_soil_from_export_without_soil(db, compano_xml):
    with pytest.raises(ValueError, match="no soil-resistivity readings"):
        gm.import_soil_resistivity(compano_xml, location="T", asset_type="substation")


@pytest.mark.parametrize("location", ["", "  ", {}, {"latitude": 1.0}, 7])
def test_invalid_location(db, compano_xml, location):
    with pytest.raises(ValueError, match="location"):
        gm.import_fall_of_potential(
            compano_xml, location=location, asset_type="substation"
        )


# ---------------------------------------------------------------------------- CLI
def test_cli_import_omicron(tmp_path, compano_xml, hgt1_txt):
    db_path = tmp_path / "ground.db"
    result = CliRunner().invoke(
        cli.app,
        [
            "--db",
            str(db_path),
            "import-omicron",
            "--location",
            "LX-01 tower 8",
            "--asset-type",
            "overhead_line_tower",
            "--ze",
            str(compano_xml),
            "--ut",
            str(hgt1_txt),
            "--transferred",
            str(hgt1_txt),
            "-D",
            "100",
            "--no-per-frequency",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Imported fall of potential: measurement id=1" in result.output
    assert "Imported touch voltages: measurement id=2" in result.output
    assert "transferred potential" in result.output
    gm.disconnect_db()
    gm.connect_db(str(db_path))
    measurements, _ = gm.read_measurements_by()
    assert len(measurements) == 3
    assert len({m["location"]["id"] for m in measurements}) == 1
    assert len(measurements[0]["items"]) == 15


def test_cli_import_omicron_requires_a_file(tmp_path):
    result = CliRunner().invoke(
        cli.app,
        [
            "--db",
            str(tmp_path / "g.db"),
            "import-omicron",
            "--location",
            "X",
            "--asset-type",
            "substation",
        ],
    )
    assert result.exit_code == 1
    assert "Nothing to import" in result.output


def test_cli_import_omicron_reports_errors(tmp_path, compano_xml):
    result = CliRunner().invoke(
        cli.app,
        [
            "--db",
            str(tmp_path / "g.db"),
            "import-omicron",
            "--location",
            "X",
            "--asset-type",
            "substation",
            "--ze",
            str(compano_xml),
            "--soil",
            str(compano_xml),
        ],
    )
    assert result.exit_code == 1
    assert "Imported fall of potential" in result.output
    assert "no soil-resistivity readings" in result.output
