"""Position-dependent clearing time (sheet 'Leitungsschutz')."""

from __future__ import annotations

import pandas as pd
import pytest

from groundmeas.towers.analysis import LineModel, permitted_voltage_for_time
from groundmeas.towers.line_protection import LineProtectionTable, tower_number

TOUCH_CURVE = dict(
    zip(
        [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 10.0],
        [633, 528, 410, 300, 204, 170, 140, 130, 120, 107, 80],
        strict=True,
    )
)


def _table():
    return LineProtectionTable(
        pd.DataFrame(
            [
                # main line, towers 0..100 -> tower number == position in %
                {
                    "Leitung": "L100",
                    "Netzform": "low-impedance",
                    "Mast_Anfang": 0,
                    "Mast_Ende": 100,
                    "Schnellzeit_von_Prozent": 16,
                    "Schnellzeit_bis_Prozent": 84,
                    "t_Schnellzeit_s": 0.1,
                    "t_Endbereich_s": 0.4,
                },
                # numbering offset 22..49
                {
                    "Leitung": "L22",
                    "Mast_Anfang": 22,
                    "Mast_Ende": 49,
                    "Schnellzeit_von_Prozent": 16,
                    "Schnellzeit_bis_Prozent": 84,
                    "t_Schnellzeit_s": 0.1,
                    "t_Endbereich_s": 0.4,
                },
                # compensated network, flat values
                {
                    "Leitung": "KOMP",
                    "Netzform": "compensated",
                    "t_Schnellzeit_s": 10,
                    "t_Endbereich_s": 10,
                    "Fehlerstrom_pauschal_kA": 0.2,
                    "Reduktionsfaktor_pauschal": 0.7,
                },
                # tower range unknown, different times -> conservative
                {"Leitung": "UNKNOWN", "t_Schnellzeit_s": 0.1, "t_Endbereich_s": 0.4},
            ]
        )
    )


@pytest.mark.parametrize(
    ("tower", "expected"),
    [
        ("0", 0.4),
        ("15", 0.4),
        ("16", 0.1),
        ("50", 0.1),
        ("84", 0.1),
        ("85", 0.4),
        ("100", 0.4),
    ],
)
def test_bands(tower, expected):
    """0-15 % -> 400 ms, 16-84 % -> 100 ms, 85-100 % -> 400 ms."""
    assert _table().lookup("L100", tower).tripping_time_s == expected


def test_values_between_integer_bands_are_conservative():
    table = LineProtectionTable(
        pd.DataFrame(
            [
                {
                    "Leitung": "L200",
                    "Mast_Anfang": 0,
                    "Mast_Ende": 200,
                    "Schnellzeit_von_Prozent": 16,
                    "Schnellzeit_bis_Prozent": 84,
                    "t_Schnellzeit_s": 0.1,
                    "t_Endbereich_s": 0.4,
                }
            ]
        )
    )
    assert table.lookup("L200", "31").tripping_time_s == 0.4  # 15.5 %
    assert table.lookup("L200", "32").tripping_time_s == 0.1  # 16.0 %
    assert table.lookup("L200", "168").tripping_time_s == 0.1  # 84.0 %
    assert table.lookup("L200", "169").tripping_time_s == 0.4  # 84.5 %


def test_tower_suffix_and_leading_zeros():
    assert (
        tower_number("28N") == 28
        and tower_number("08") == 8
        and tower_number("2M") == 2
    )
    assert _table().lookup("L100", "050N").position_percent == pytest.approx(50.0)


def test_position_matches_the_short_circuit_line_model():
    """Two independent ways to place a tower on the line must agree."""
    l_km = [round(0.6137 * i, 4) for i in range(11)]
    ik = [7.829, 7.877, 7.945, 8.033, 8.143, 8.275, 8.433, 8.618, 8.834, 9.086, 9.377]
    model = LineModel()
    model.training_data["L22"] = pd.DataFrame(
        {"Ik": ik, "l": l_km, "Mast": [22] + [None] * 9 + [49]}
    )
    model.train_curve_model("L22")
    data = model.curve_data["L22"]
    for tower in range(22, 50):
        pos_model = (tower - data["first_tower"]) / (data["N"] - 1) * 100
        assert _table().position_percent("L22", str(tower)) == pytest.approx(pos_model)


def test_compensated_line_flat_values():
    res = _table().lookup("KOMP", "7")
    assert res.tripping_time_s == 10 and res.zone == "pauschal"
    assert res.fault_current_A == pytest.approx(200.0)
    assert res.reduction_factor == pytest.approx(0.7)
    assert permitted_voltage_for_time(TOUCH_CURVE, res.tripping_time_s) == 80


def test_unknown_position_uses_longer_time():
    res = _table().lookup("UNKNOWN", "5")
    assert res.tripping_time_s == 0.4 and res.position_percent is None


def test_tower_outside_the_range(caplog):
    res = _table().lookup("L100", "120")
    assert res.tripping_time_s == 0.4 and res.zone == "Endbereich"
    assert "outside Mast_Anfang..Mast_Ende" in caplog.text


def test_line_not_listed():
    table = _table()
    assert table.lookup("NOT_THERE", "1") is None
    assert "L100" in table and "NOT_THERE" not in table
    assert table.lines() == ["L100", "L22", "KOMP", "UNKNOWN"]


def test_missing_times_raise():
    table = LineProtectionTable(
        pd.DataFrame([{"Leitung": "L", "t_Schnellzeit_s": None, "t_Endbereich_s": 0.4}])
    )
    with pytest.raises(ValueError, match="missing for line L"):
        table.lookup("L", "1")


@pytest.mark.parametrize(
    ("tower", "language", "expected"),
    [
        ("20", "en", "Position 20.0 % of the line length: instantaneous tripping"),
        ("20", "de", "Lage 20,0 % der Leitungslänge: beidseitige Schnellzeit"),
        ("5", "de", "Lage 5,0 % der Leitungslänge: Endbereich"),
    ],
)
def test_hints(tower, language, expected):
    assert _table().lookup("L100", tower).hint(language).startswith(expected)


def test_flat_and_unknown_hints():
    assert (
        _table().lookup("KOMP", "1").hint("de") == "Pauschale Abschaltzeit der Leitung"
    )
    assert "conservative" in _table().lookup("UNKNOWN", "1").hint("en")


def test_read_sheet_from_excel(tmp_path):
    path = tmp_path / "short_circuit.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="L1", index=False)
        pd.DataFrame(
            [
                {
                    "Leitung": "L1",
                    "Mast_Anfang": 1,
                    "Mast_Ende": 11,
                    "t_Schnellzeit_s": 0.1,
                    "t_Endbereich_s": 0.4,
                },
                {"Leitung": None},
            ]
        ).to_excel(writer, sheet_name="Leitungsschutz", index=False)
    table = LineProtectionTable.from_excel(str(path))
    assert table.lines() == ["L1"]
    assert table.lookup("L1", "6").tripping_time_s == 0.1
    assert LineProtectionTable.from_excel(str(path), "Other").lines() == []
    assert LineProtectionTable.from_excel(None).lines() == []
    assert LineProtectionTable.from_excel(str(tmp_path / "missing.xlsx")).lines() == []


def test_sheet_without_required_columns(tmp_path):
    path = tmp_path / "short_circuit.xlsx"
    pd.DataFrame([{"Leitung": "L1"}]).to_excel(
        path, sheet_name="Leitungsschutz", index=False
    )
    with pytest.raises(ValueError, match="misses the columns"):
        LineProtectionTable.from_excel(str(path))
