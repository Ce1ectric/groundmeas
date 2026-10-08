"""Tests for groundmeas.instruments.omicron (COMPANO 100 XML and HGT1 readers)."""

from __future__ import annotations

import cmath
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from groundmeas.instruments import (
    CompanoXMLReader,
    FallOfPotentialData,
    Hgt1TXTReader,
    MeasurementFileError,
    SoilResistivityData,
    informative_locations,
)

# --------------------------------------------------------------------------- COMPANO
DISTANCES = [1.0, 5.0, 10.0, 20.0, 30.0, 40.0, 60.0]
FOP = "FallOfPotentialReport/FallOfPotentialWidgetData/FallOfPotentialMeasurementScreenData"
RF = "FallOfPotentialReport/FallOfPotentialWidgetData/ReductionFactorScreenData"


def model_impedance(x):
    """Hemispherical electrode used to create the fixture (see tests/data/README.md)."""
    r, a, d = 0.40, 3.0, 100.0
    x = np.asarray(x, dtype=float)
    return r * a * (1 / a - 1 / d - 1 / (a + x) + 1 / (d - a - x))


def _edit_xml(source: Path, target: Path, edit) -> Path:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    tree = ET.parse(source, parser=parser)
    edit(tree.getroot().find("ReportData"))
    tree.write(target, encoding="utf-8", xml_declaration=True)
    return target


def test_fall_of_potential_profile(compano_xml):
    impedance, residual = CompanoXMLReader(
        compano_xml
    ).get_impedance_to_ground_dataframe()
    assert list(impedance.columns) == [
        "Distance",
        "Impedance",
        "Unit",
        "StepTouchCurrent",
    ]
    np.testing.assert_allclose(impedance["Distance"], DISTANCES)
    # two methods: values read from the export vs. the generating model
    np.testing.assert_allclose(
        impedance["Impedance"], model_impedance(DISTANCES), rtol=1e-9
    )
    np.testing.assert_allclose(
        residual["Impedance"], 2 * model_impedance(DISTANCES), rtol=1e-9
    )
    assert abs(impedance["StepTouchCurrent"].iloc[0]) == pytest.approx(0.0535)
    assert abs(residual["ResidualCurrent"].iloc[0]) == pytest.approx(0.02725)
    assert (impedance["Unit"] == "Ohm").all()


def test_values_in_other_units_give_the_same_result(compano_xml, tmp_path):
    def to_millivolt_and_feet(report):
        screen = report.find(FOP)
        for magnitude in screen.findall("InputVoltages/Measurement/Result/Magnitude"):
            magnitude.find("Value").text = repr(
                float(magnitude.find("Value").text) * 1000
            )
            magnitude.find("Unit").text = "mV"
        for distance in screen.findall("Distances/Distance"):
            distance.find("Value").text = repr(
                float(distance.find("Value").text) / 0.3048
            )
            distance.find("Unit").text = "ft"

    changed = _edit_xml(compano_xml, tmp_path / "units.xml", to_millivolt_and_feet)
    reference, _ = CompanoXMLReader(compano_xml).get_impedance_to_ground_dataframe()
    converted, _ = CompanoXMLReader(changed).get_impedance_to_ground_dataframe()
    np.testing.assert_allclose(
        converted["Impedance"], reference["Impedance"], rtol=1e-12
    )
    np.testing.assert_allclose(converted["Distance"], reference["Distance"], rtol=1e-12)


def test_unknown_unit_is_rejected(compano_xml, tmp_path):
    def bad_unit(report):
        report.find(f"{FOP}/Distances/Distance/Unit").text = "furlong"

    with pytest.raises(MeasurementFileError, match="unexpected distance unit"):
        CompanoXMLReader(
            _edit_xml(compano_xml, tmp_path / "x.xml", bad_unit)
        ).get_impedance_to_ground_dataframe()


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (
            lambda r: r.find(FOP).remove(r.find(f"{FOP}/Distances")),
            "Distances' is missing",
        ),
        (lambda r: r.remove(r.find("StepAndTouchReport")), "is missing"),
        (
            lambda r: [
                r.find(f"{FOP}/Distances").remove(d)
                for d in list(r.find(f"{FOP}/Distances"))
            ],
            "no valid distance",
        ),
        (
            lambda r: r.find(f"{FOP}/Distances").remove(
                r.find(f"{FOP}/Distances/Distance")
            ),
            "distances but",
        ),
        (
            lambda r: setattr(r.find(f"{FOP}/Distances/Distance/Value"), "text", "abc"),
            "not numeric",
        ),
        (
            lambda r: setattr(r.find(f"{FOP}/Distances/Distance/Value"), "text", ""),
            "empty value",
        ),
    ],
)
def test_incomplete_exports(compano_xml, tmp_path, edit, message):
    broken = _edit_xml(compano_xml, tmp_path / "broken.xml", edit)
    with pytest.raises(MeasurementFileError, match=message):
        CompanoXMLReader(broken).get_impedance_to_ground_dataframe()


def test_not_an_xml_file(tmp_path):
    path = tmp_path / "ZE_X_1.xml"
    path.write_text("this is not xml", encoding="utf-8")
    with pytest.raises(MeasurementFileError, match="not a valid XML"):
        CompanoXMLReader(path).get_impedance_to_ground_dataframe()


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        CompanoXMLReader(tmp_path / "missing.xml")


def test_nominal_frequency_and_timestamp(compano_xml):
    reader = CompanoXMLReader(compano_xml)
    assert reader.get_nominal_frequency() == 50.0
    assert reader.get_report_timestamp() == "2024-01-01 10:00:00.000"


def test_complex_conversion():
    value = CompanoXMLReader.convert_to_complex(2.0, 90.0)
    assert value.real == pytest.approx(0.0, abs=1e-12)
    assert value.imag == pytest.approx(2.0)


# ------------------------------------------------------------- per-frequency data
def test_read_fall_of_potential_per_frequency(compano_xml):
    data = CompanoXMLReader(compano_xml).read_fall_of_potential()
    assert isinstance(data, FallOfPotentialData)
    assert data.test_frequencies_hz == (30.0, 70.0)
    assert data.voltages.shape == data.currents.shape == (7, 2)
    np.testing.assert_allclose(data.distances_m, DISTANCES)
    assert len(data.timestamps) == 7
    assert data.nominal_frequency_hz == 50.0
    # injected current 54 / 55 mA at 30 / 70 Hz (README of the fixture)
    np.testing.assert_allclose(abs(data.currents[0]), [0.054, 0.055], rtol=1e-3)
    # the instrument result is the complex mean of both test frequencies
    np.testing.assert_allclose(data.voltages.mean(axis=1), data.result_voltages)
    np.testing.assert_allclose(data.currents.mean(axis=1), data.result_currents)


def test_impedance_three_ways(compano_xml):
    """Result impedance = per-frequency impedance = model = TGM-style frame."""
    reader = CompanoXMLReader(compano_xml)
    data = reader.read_fall_of_potential()
    frame, residual = reader.get_impedance_to_ground_dataframe()
    np.testing.assert_allclose(abs(data.impedance()), frame["Impedance"], rtol=1e-12)
    np.testing.assert_allclose(abs(data.impedance()), model_impedance(DISTANCES))
    for f in (30.0, 70.0):
        np.testing.assert_allclose(
            abs(data.impedance(f)), model_impedance(DISTANCES), rtol=1e-6
        )
    np.testing.assert_allclose(
        abs(data.footing_resistance()), residual["Impedance"], rtol=1e-12
    )
    with pytest.raises(ValueError, match="not a test frequency"):
        data.impedance(50.0)


def _scale_complex(report, factor):
    for c in report.find(FOP).iter("Complex"):
        for tag in ("Real", "Imag"):
            c.find(tag).text = repr(float(c.find(tag).text) * factor)


def test_per_frequency_values_with_scaled_result_unit(compano_xml, tmp_path):
    reference = CompanoXMLReader(compano_xml).read_fall_of_potential()

    def to_millivolt(report, scale_complex):
        screen = report.find(FOP)
        for magnitude in screen.findall("InputVoltages/Measurement/Result/Magnitude"):
            magnitude.find("Value").text = repr(
                float(magnitude.find("Value").text) * 1000
            )
            magnitude.find("Unit").text = "mV"
        if scale_complex:
            for c in screen.findall("InputVoltages/Measurement/Measurements/Complex"):
                for tag in ("Real", "Imag"):
                    c.find(tag).text = repr(float(c.find(tag).text) * 1000)

    # per-frequency values left in V (base unit) or written in mV like the result
    for scale_complex in (False, True):
        path = _edit_xml(
            compano_xml,
            tmp_path / f"mv_{scale_complex}.xml",
            lambda r, s=scale_complex: to_millivolt(r, s),
        )
        data = CompanoXMLReader(path).read_fall_of_potential()
        np.testing.assert_allclose(data.voltages, reference.voltages, rtol=1e-12)
        np.testing.assert_allclose(
            data.result_voltages, reference.result_voltages, rtol=1e-12
        )


def test_inconsistent_per_frequency_values_are_rejected(compano_xml, tmp_path):
    def break_values(report):
        screen = report.find(FOP)
        magnitude = screen.find("InputVoltages/Measurement/Result/Magnitude")
        magnitude.find("Value").text = repr(float(magnitude.find("Value").text) * 1000)
        magnitude.find("Unit").text = "mV"
        for c in screen.findall("InputVoltages/Measurement/Measurements/Complex")[:2]:
            for tag in ("Real", "Imag"):
                c.find(tag).text = repr(float(c.find(tag).text) * 10)

    path = _edit_xml(compano_xml, tmp_path / "broken.xml", break_values)
    with pytest.raises(MeasurementFileError, match="do not match"):
        CompanoXMLReader(path).read_fall_of_potential()


def test_varying_number_of_frequencies_is_rejected(compano_xml, tmp_path):
    def drop_one(report):
        first = report.find(f"{FOP}/InputVoltages/Measurement/Measurements")
        first.remove(first.find("Complex"))

    path = _edit_xml(compano_xml, tmp_path / "broken.xml", drop_one)
    with pytest.raises(MeasurementFileError, match="varying number"):
        CompanoXMLReader(path).read_fall_of_potential()


def _add_measurement(container: ET.Element, values: list[complex], unit: str) -> None:
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


def test_reduction_factor_with_clamp_readings(compano_xml, tmp_path):
    legs = [0.012 * cmath.exp(1j * math.radians(35)) for _ in range(4)]

    def add_clamp_readings(report):
        screen = report.find(RF)
        for tag, values in (
            ("OutputCurrents", [complex(0.19, 0)] * 4),
            ("InputCurrents", legs),
        ):
            container = screen.find(tag)
            for child in list(container):
                container.remove(child)
            for value in values:
                _add_measurement(container, [value * 0.99, value * 1.01], "A")
        factor = sum(legs) / 0.19
        node = screen.find("ReductionFactorData")
        node.find("Magnitude/Value").text = repr(abs(factor))
        node.find("Phase/Value").text = repr(math.degrees(cmath.phase(factor)))

    path = _edit_xml(compano_xml, tmp_path / "rf.xml", add_clamp_readings)
    data = CompanoXMLReader(path).read_reduction_factor()
    assert data is not None
    assert len(data.input_currents) == len(data.output_currents) == 4
    # two methods: instrument factor vs. sum of clamp currents / injected current
    expected = data.input_currents.sum() / data.output_currents.mean()
    assert data.reduction_factor == pytest.approx(expected)
    assert abs(data.reduction_factor) == pytest.approx(4 * 0.012 / 0.19)
    assert data.clamp_ratio_v_per_a is not None


def test_reduction_factor_without_report(compano_xml, tmp_path):
    def drop(report):
        widget = report.find("FallOfPotentialReport/FallOfPotentialWidgetData")
        widget.remove(widget.find("ReductionFactorScreenData"))

    path = _edit_xml(compano_xml, tmp_path / "no_rf.xml", drop)
    assert CompanoXMLReader(path).read_reduction_factor() is None


def test_step_touch_currents(compano_xml, tmp_path):
    frequencies, currents = CompanoXMLReader(compano_xml).get_step_touch_currents()
    assert frequencies == (30.0, 70.0)
    np.testing.assert_allclose(currents, [0.053, 0.054])

    def drop(report):
        report.remove(report.find("StepAndTouchReport"))

    path = _edit_xml(compano_xml, tmp_path / "no_st.xml", drop)
    frequencies, currents = CompanoXMLReader(path).get_step_touch_currents()
    assert frequencies == () and len(currents) == 0


# ----------------------------------------------------------------------- soil
def _soil_export(
    path: Path,
    a: list[float],
    b: list[float],
    c: list[float],
    resistance: list[float],
) -> Path:
    """COMPANO soil export in the layout of firmware 2.40."""
    root = ET.Element("Compano100Report")
    report = ET.SubElement(root, "ReportData")
    ET.SubElement(report, "TimeStamp").text = "2024-01-01 11:00:00.000"
    screen = ET.SubElement(
        ET.SubElement(
            ET.SubElement(report, "SoilResistanceReport"), "SoilResistanceWidgetData"
        ),
        "SoilResistanceMeasurementScreenData",
    )
    stamps = ET.SubElement(screen, "TimeStamps")
    for tag, values in (("DistancesA", a), ("DistancesB", b), ("DistancesC", c)):
        container = ET.SubElement(screen, tag)
        for value in values:
            item = ET.SubElement(container, "Distance")
            ET.SubElement(item, "Value").text = repr(value)
            ET.SubElement(item, "Unit").text = "m"
    rho = ET.SubElement(screen, "SpecificResistances")
    impedances = ET.SubElement(screen, "Impedances")
    for ai, ci, r in zip(a, c, resistance):
        ET.SubElement(stamps, "TimeStamp").text = "2024-01-01 11:00:00.000"
        item = ET.SubElement(rho, "Rho")
        ET.SubElement(item, "Value").text = repr(math.pi * ci * (ci + ai) / ai * r)
        ET.SubElement(item, "Unit").text = "Ωm"
        magnitude = ET.SubElement(impedances, "Magnitude")
        ET.SubElement(magnitude, "Value").text = repr(r)
        ET.SubElement(magnitude, "Unit").text = "Ω"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_soil_resistivity_schlumberger(tmp_path):
    a, c = [4.0, 4.0, 4.0], [2.0, 6.0, 26.0]
    path = _soil_export(tmp_path / "soil.xml", a, [0.2] * 3, c, [3.5, 0.6, 0.02])
    data = CompanoXMLReader(path).read_soil_resistivity()
    assert isinstance(data, SoilResistivityData)
    np.testing.assert_allclose(data.ab_half_m, [4.0, 8.0, 28.0])
    np.testing.assert_allclose(data.mn_half_m, [2.0, 2.0, 2.0])
    assert not data.is_wenner
    # two methods: exported resistivity vs. Schlumberger formula with AB/2, MN/2
    ab, mn = data.ab_half_m, data.mn_half_m
    np.testing.assert_allclose(
        data.rho_ohm_m, math.pi * (ab**2 - mn**2) / (2 * mn) * data.resistance_ohm
    )
    assert len(data.timestamps) == 3
    legacy = CompanoXMLReader(path).get_soil_resistivity()
    assert legacy["DistanzC_m"] == c


def test_soil_resistivity_wenner(tmp_path):
    spacing = [1.0, 2.0, 5.0]
    path = _soil_export(tmp_path / "w.xml", spacing, [0.1] * 3, spacing, [10, 5, 2])
    data = CompanoXMLReader(path).read_soil_resistivity()
    assert data.is_wenner
    # Wenner: rho = 2 pi a R
    np.testing.assert_allclose(
        data.rho_ohm_m, 2 * math.pi * np.array(spacing) * np.array([10, 5, 2])
    )


def test_soil_resistivity_units(tmp_path):
    a, c = [4.0, 4.0], [2.0, 6.0]
    path = _soil_export(tmp_path / "soil.xml", a, [0.2] * 2, c, [3.5, 0.6])
    base = CompanoXMLReader(path).read_soil_resistivity()
    text = path.read_text(encoding="utf-8")
    scaled = tmp_path / "soil_k.xml"
    rho_k = [repr(float(v) / 1000) for v in base.rho_ohm_m]
    for old_value, new_value in zip((repr(float(v)) for v in base.rho_ohm_m), rho_k):
        text = text.replace(
            f"<Value>{old_value}</Value>", f"<Value>{new_value}</Value>"
        )
    text = text.replace("<Unit>Ωm</Unit>", "<Unit>kΩm</Unit>")
    text = text.replace("<Value>3.5</Value>", "<Value>3500.0</Value>")
    text = text.replace("<Value>0.6</Value>", "<Value>600.0</Value>")
    text = text.replace("<Unit>Ω</Unit>", "<Unit>mΩ</Unit>")
    scaled.write_text(text, encoding="utf-8")
    data = CompanoXMLReader(scaled).read_soil_resistivity()
    assert data.rho_ohm_m == pytest.approx(base.rho_ohm_m)
    assert data.resistance_ohm == pytest.approx([3.5, 0.6])
    legacy = CompanoXMLReader(scaled).get_soil_resistivity()
    assert legacy["rho_OhmMeter"] == pytest.approx(list(base.rho_ohm_m))
    scaled.write_text(text.replace("<Unit>kΩm</Unit>", "<Unit>Ωft</Unit>"), "utf-8")
    with pytest.raises(MeasurementFileError, match="unexpected resistivity unit"):
        CompanoXMLReader(scaled).read_soil_resistivity()


def test_soil_resistivity_absent_or_inconsistent(compano_xml, tmp_path):
    assert CompanoXMLReader(compano_xml).read_soil_resistivity() is None
    assert CompanoXMLReader(compano_xml).get_soil_resistivity() is None
    path = _soil_export(tmp_path / "bad.xml", [4.0, 4.0], [0.2], [2.0, 4.0], [1, 2])
    with pytest.raises(MeasurementFileError, match="distances a/b/c"):
        CompanoXMLReader(path).read_soil_resistivity()


# --------------------------------------------------------------------------- HGT1
EXPECTED_LEVEL50 = [4.5e-3, 3.1e-3, 4.2e-3, 2.8e-3, 1.2e-3, 0.8e-3]


def test_hgt1_report(hgt1_txt):
    df = Hgt1TXTReader(hgt1_txt).get_touchvoltage_dataframe()
    assert list(df.columns[:9]) == list(Hgt1TXTReader.COLUMNS)
    assert df["Location"].tolist() == ["MAST"] * 4 + ["ZAUN"] * 2
    assert df["Termination"].tolist() == ["1k", "2x1k"] * 3
    assert df["Meas. ID"].tolist() == ["1", "2", "3", "4", "5", "6"]
    assert df["Date"].unique().tolist() == ["2024-01-01"]
    np.testing.assert_allclose(df["Level50"], EXPECTED_LEVEL50, rtol=1e-12)
    assert df["TerminationLabel"].tolist()[:2] == [
        "no additional resistor",
        "with additional resistor 1kOhm",
    ]


def test_interpolation_matches_numpy_interp(hgt1_txt):
    """Two methods for the value at the nominal frequency."""
    for frequency in (50.0, 60.0):
        df = Hgt1TXTReader(
            hgt1_txt, nominal_frequency=frequency
        ).get_touchvoltage_dataframe()
        reference = [
            np.interp(frequency, [f1, f2], [u1, u2])
            for f1, f2, u1, u2 in zip(
                df["f1"], df["f2"], df["Level1"], df["Level2"], strict=True
            )
        ]
        np.testing.assert_allclose(df["Level50"], reference, rtol=1e-12)
        assert (df["f50"] == frequency).all()


def test_german_termination_labels(hgt1_txt):
    df = Hgt1TXTReader(hgt1_txt, language="de").get_touchvoltage_dataframe()
    assert df["TerminationLabel"].iloc[0] == "kein Zusatzwiderstand"


def _variant(
    hgt1_txt: Path,
    tmp_path: Path,
    replace: tuple[str, str] | None = None,
    *,
    newline=None,
    encoding="ascii",
) -> Path:
    text = hgt1_txt.read_bytes().decode("ascii")
    if replace:
        assert replace[0] in text
        text = text.replace(*replace)
    if newline:
        text = text.replace("\r\n", newline)
    path = tmp_path / "UT_X_1.txt"
    path.write_bytes(text.encode(encoding))
    return path


def test_unix_line_endings(hgt1_txt, tmp_path):
    df = Hgt1TXTReader(
        _variant(hgt1_txt, tmp_path, newline="\n")
    ).get_touchvoltage_dataframe()
    np.testing.assert_allclose(df["Level50"], EXPECTED_LEVEL50)


def test_windows_1252_and_utf8_bom(hgt1_txt, tmp_path):
    cp1252 = _variant(
        hgt1_txt, tmp_path, ("ZAUN       ", "TÜR        "), encoding="cp1252"
    )
    assert (
        Hgt1TXTReader(cp1252).get_touchvoltage_dataframe()["Location"].iloc[-1] == "TÜR"
    )
    bom = tmp_path / "UT_X_2.txt"
    bom.write_bytes(b"\xef\xbb\xbf" + hgt1_txt.read_bytes())
    assert len(Hgt1TXTReader(bom).get_touchvoltage_dataframe()) == 6


def test_millivolt_units(hgt1_txt, tmp_path):
    text = hgt1_txt.read_bytes().decode("ascii")
    text = text.replace("[V]     \t[Hz]    \t[V]     ", "[mV]    \t[Hz]    \t[mV]    ")
    text = text.replace("3.500e-3", "3.500e+0").replace("5.500e-3", "5.500e+0")
    path = tmp_path / "UT_mV.txt"
    path.write_bytes(text.encode("ascii"))
    df = Hgt1TXTReader(path).get_touchvoltage_dataframe()
    assert df["Level50"].iloc[0] == pytest.approx(4.5e-3)


@pytest.mark.parametrize(
    ("replace", "message"),
    [
        (("[V]     \t[Hz]", "[1V]    \t[Hz]"), "unexpected unit"),
        (("\t3.500e-3\t", "\t\t\t3.500e-3\t"), "fields, expected"),
        (("3.500e-3", "n/a"), "not numeric"),
        (("Termination", "Terminal"), "header line"),
    ],
)
def test_malformed_reports(hgt1_txt, tmp_path, replace, message):
    with pytest.raises(MeasurementFileError, match=message):
        Hgt1TXTReader(
            _variant(hgt1_txt, tmp_path, replace)
        ).get_touchvoltage_dataframe()


def test_report_without_readings(hgt1_txt, tmp_path):
    lines = hgt1_txt.read_bytes().decode("ascii").split("\r\n")
    path = tmp_path / "UT_empty.txt"
    path.write_bytes("\r\n".join(lines[:9]).encode("ascii"))
    with pytest.raises(MeasurementFileError, match="no readings"):
        Hgt1TXTReader(path).get_touchvoltage_dataframe()


def test_equal_frequencies_cannot_be_interpolated(hgt1_txt, tmp_path):
    path = _variant(hgt1_txt, tmp_path, ("70.00   \t5.500e-3", "30.00   \t5.500e-3"))
    with pytest.raises(MeasurementFileError, match="must differ"):
        Hgt1TXTReader(path).get_touchvoltage_dataframe()


def test_calc_before_parse_is_an_error(hgt1_txt):
    with pytest.raises(MeasurementFileError, match="parse_report"):
        Hgt1TXTReader(hgt1_txt).calc_50_Hz_voltage()


def test_missing_report(tmp_path):
    with pytest.raises(FileNotFoundError):
        Hgt1TXTReader(tmp_path / "missing.txt")


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["MAST", "MAST"], True),
        (["MyLocation", "MyLocation"], False),
        (["1", "1"], False),
        (["", "nan"], False),
        (pd.Series(["1", "ZAUN"]), True),
    ],
)
def test_informative_locations(values, expected):
    assert informative_locations(values) is expected
