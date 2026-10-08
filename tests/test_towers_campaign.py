"""Evaluation of a complete campaign (``--calc``)."""

from __future__ import annotations

import json
import logging
import math

import numpy as np
import pandas as pd
import pytest

from groundmeas.towers import campaign as summary_storage
from groundmeas.towers.campaign import (
    CATEGORY_MEASURES,
    CATEGORY_UT,
    CATEGORY_ZE,
    assessment_text,
    build_touch_voltage_labels,
    calculate_summary,
    find_unique_line_tower,
    select_footing_resistance,
    split_locations,
)
from groundmeas.towers.demo import (
    FIRST_TOWER,
    LAST_TOWER,
    LINE_LENGTH_KM,
    short_circuit_current_kA,
)


def load(config, tower):
    path = config.parent / "results" / f"LX-01_{tower}.json"
    # strict JSON: NaN/Infinity are not allowed
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=lambda c: pytest.fail(f"{c} in JSON"),
    )


# ------------------------------------------------------------- touch-voltage labels
def readings(locations, terminations):
    return pd.DataFrame(
        {"Location": locations, "Termination": terminations, "Level50": 0.001}
    )


def test_labels_from_the_hgt1_report_use_the_description_spelling():
    df = readings(
        ["MAST", "MAST", "E-SAEULE", "E-SAEULE"], ["1k", "2x1k", "1k", "2x1k"]
    )
    labels, terminations = build_touch_voltage_labels(df, ["Mast", "E-Säule"], "de")
    assert labels == [
        "Mast (kein Zusatzwiderstand)",
        "Mast (mit Zusatzwiderstand 1kOhm)",
        "E-Säule (kein Zusatzwiderstand)",
        "E-Säule (mit Zusatzwiderstand 1kOhm)",
    ]
    assert terminations == ["1k", "2x1k", "1k", "2x1k"]


def test_pairs_are_not_assigned_cyclically():
    """Regression test: the pre-0.2 code assigned the list cyclically (i % n)."""
    df = readings(["MAST"] * 4 + ["ZAUN"] * 2, ["1k", "2x1k"] * 3)
    labels, _ = build_touch_voltage_labels(df, ["Mast", "Mast", "Zaun"], "en")
    assert [label.split(" (")[0] for label in labels] == ["Mast"] * 4 + ["Zaun"] * 2


def test_hgt1_locations_win_over_a_wrong_description(caplog):
    df = readings(["ZAUN", "ZAUN", "MAST", "MAST"], ["1k", "2x1k", "1k", "2x1k"])
    with caplog.at_level(logging.WARNING, logger="groundmeas"):
        labels, _ = build_touch_voltage_labels(
            df, ["Mast", "Zaun"], "en", context="LX-01 tower 9"
        )
    assert [label.split(" (")[0] for label in labels] == [
        "Zaun",
        "Zaun",
        "Mast",
        "Mast",
    ]
    assert (
        "LX-01 tower 9" in caplog.text and "differ from the HGT1 report" in caplog.text
    )


def test_description_used_when_the_instrument_has_no_names():
    one_per_reading = readings(["1", "1", "1"], ["1k", "2x1k", "1k"])
    labels, _ = build_touch_voltage_labels(
        one_per_reading, ["Mast 1", "Mast 2", "Fence"], "en"
    )
    assert [label.split(" (")[0] for label in labels] == ["Mast 1", "Mast 2", "Fence"]
    pairs = readings(["MyLocation"] * 4, ["1k", "2x1k"] * 2)
    labels, _ = build_touch_voltage_labels(pairs, ["Tower", "Gate"], "en")
    assert [label.split(" (")[0] for label in labels] == [
        "Tower",
        "Tower",
        "Gate",
        "Gate",
    ]


def test_unmatched_description_is_repeated_with_a_warning(caplog):
    df = readings(["1"] * 3, ["1k", "2x1k", "1k"])
    with caplog.at_level(logging.WARNING, logger="groundmeas"):
        labels, _ = build_touch_voltage_labels(df, ["A", "B"], "en")
    assert [label.split(" (")[0] for label in labels] == ["A", "B", "A"]
    assert "repeated cyclically" in caplog.text


def test_unknown_location_and_termination():
    df = pd.DataFrame({"Location": ["MyLocation"], "Termination": ["200k (High Z)"]})
    labels, terminations = build_touch_voltage_labels(df, [], "de")
    assert labels == ["Unbekannter Messort (200k (High Z))"]
    assert terminations == ["200k (High Z)"]
    without_columns = pd.DataFrame({"Level50": [0.1]})
    assert build_touch_voltage_labels(without_columns, [], "en")[0] == [
        "unknown measuring point"
    ]


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("Mast, Mast, Zaun", ["Mast", "Mast", "Zaun"]),
        ("Mast; Hochstand", ["Mast", "Hochstand"]),
        ("Mast, Box,", ["Mast", "Box", ""]),
        ("", []),
        (None, []),
        (float("nan"), []),
    ],
)
def test_split_locations(cell, expected):
    assert split_locations(cell) == expected


# --------------------------------------------------------------------- assessment
@pytest.mark.parametrize(
    ("compano", "hf", "expected"),
    [
        (2.0, 2.2, (2.0, "")),  # deviation 9 % -> COMPANO value
        (2.0, 3.0, (3.0, "measured with the high-frequency method")),  # 33 %
        (None, 3.0, (3.0, "measured with the high-frequency method")),
        (2.0, None, (2.0, "")),
        (None, None, (None, "")),
    ],
)
def test_select_footing_resistance(compano, hf, expected):
    assert select_footing_resistance(compano, hf, "en") == expected


def test_assessment_texts():
    assert assessment_text(CATEGORY_MEASURES, "en").startswith(
        "The touch voltages exceed"
    )
    assert assessment_text(CATEGORY_UT, "de").startswith(
        "Die Messung der Berührungsspannung"
    )
    assert assessment_text(CATEGORY_ZE, "de").startswith(
        "Die Messung der Erdungsimpedanz"
    )
    assert assessment_text("?", "en") == "No assessment possible."


def test_find_unique_line_tower():
    data = [
        {"Leitung": "A", "Mast": 1},
        {"Leitung": "A", "Mast": "2"},
        {"Leitung": "B", "Mast": 1},
    ]
    assert dict(find_unique_line_tower(data)) == {"A": {"1", "2"}, "B": {"1"}}


# ------------------------------------------------------------------ demo campaign
def test_demo_campaign_results(evaluated_demo):
    results = {tower: load(evaluated_demo, tower) for tower in ("3", "8", "21", "37")}
    categories = {tower: data["Bewertung_Kategorie"] for tower, data in results.items()}
    assert categories == {"3": "MASS", "8": "ZE", "21": "UT", "37": "UT"}
    t3 = results["3"]
    assert (
        t3["UT_max_Messung_V"] == 420
        and t3["UD_V"] == 300.0
        and t3["Abschaltzeit_s"] == 0.4
    )
    assert t3["Messpunkte_UT"][:2] == [
        "Tower (no additional resistor)",
        "Tower (with additional resistor 1kOhm)",
    ]
    assert t3["Messpunkte_UT_Termination"][:2] == ["1k", "2x1k"]
    assert t3["Auslegung_korrekt"].startswith("The touch voltages exceed")
    assert (
        results["8"]["Abschaltzeit_s"] == 0.1
        and results["8"]["Lage_Leitung_Prozent"] == 17.9
    )
    assert (
        results["21"]["RA_Quelle_Hinweis"] == "measured with the high-frequency method"
    )
    assert results["21"]["RA_62_Ohm"] == 3.6
    assert results["8"]["Bodenwiderstand_Schlumberger"]["vorhanden"] is True
    neighbour = results["8"]["Erdungsspannung_Nachbarmast"]
    assert neighbour["Nachbarmast"] == "9"
    # 40 V / 28 V at the neighbour (with/without resistor) by construction of the demo
    assert neighbour["UT_gemessen_V"] == pytest.approx([40.0, 28.0], rel=2e-3)
    assert results["37"]["Netzform"] == "low-impedance earthed"


def test_fault_current_from_the_short_circuit_model(evaluated_demo):
    """The fitted line model must reproduce the generating model (two methods)."""
    grid = pd.read_excel(evaluated_demo.parent / "grid_data.xlsx")
    n = LAST_TOWER - FIRST_TOWER + 1
    span = LINE_LENGTH_KM / (n - 1)
    for _, row in grid.iterrows():
        expected = (
            float(short_circuit_current_kA(int(row["Mast"]) - FIRST_TOWER, n, span))
            * 1e3
        )
        assert row["Fehlerstrom"] == pytest.approx(expected, rel=5e-3)
    assert set(grid["Abschaltzeit"]) == {0.1, 0.4}
    assert grid["Hinweis_Abschaltzeit"].str.startswith("Position").all()


def test_summary_workbook(evaluated_demo):
    summary = pd.read_excel(evaluated_demo.parent / "results" / "summary.xlsx")
    assert summary["Mast"].tolist() == [3, 8, 21, 37]
    assert (
        summary.loc[summary["Mast"] == 3, "UT_zu_hoch"].item() is True
        or summary.loc[summary["Mast"] == 3, "UT_zu_hoch"].item() == 1
    )
    row = summary.loc[summary["Mast"] == 8].iloc[0]
    assert row["UT_zulaessig_V"] == 633 and not row["ZE_zu_hoch"]


def test_step_voltages_are_rounded(evaluated_demo):
    data = load(evaluated_demo, "3")
    assert all(round(v, 3) == v for v in data["US_V"])
    assert len(data["US_V"]) == len(data["Distanz_m"]) + 1


def test_german_campaign(evaluated_demo_de):
    data = load(evaluated_demo_de, "21")
    assert data["Auslegung_korrekt"].startswith(
        "Die Messung der Berührungsspannung an ausgewählten Punkten zeigt"
    )
    assert data["Messpunkte_UT"][0] == "Mast (kein Zusatzwiderstand)"
    assert data["RA_Quelle_Hinweis"] == "Messung über Hochfrequenz-Verfahren"
    assert data["Abschaltzeit_Hinweis"].startswith("Lage 51,3 % der Leitungslänge")


def test_empty_description_cells_are_exported_as_empty_strings(demo_campaign):
    path = demo_campaign.parent / "measurement_description.xlsx"
    description = pd.read_excel(path)
    description["Winkel_Sonde_Hilfserder_grad"] = np.nan
    description["Witterung"] = np.nan
    description.to_excel(path, index=False)
    calculate_summary(config_path=demo_campaign)
    data = load(demo_campaign, "3")  # fails on NaN
    assert data["Winkel_Sonde_Hilfserder_grad"] == "" and data["Witterung"] == ""


def test_towers_without_description_or_hgt1_are_skipped(demo_campaign, caplog):
    path = demo_campaign.parent / "measurement_description.xlsx"
    description = pd.read_excel(path)
    description[description["Mast"] != 37].to_excel(path, index=False)
    (demo_campaign.parent / "measurements" / "UT_LX-01_21.txt").unlink()
    with caplog.at_level(logging.WARNING, logger="groundmeas"):
        summary = calculate_summary(config_path=demo_campaign)
    assert sorted(summary["Mast"].astype(int)) == [3, 8]
    assert "LX-01 tower 37: no row in the measurement description" in caplog.text
    assert "LX-01 tower 21: no touch-voltage (HGT1) data" in caplog.text


def test_missing_description_columns(demo_campaign):
    path = demo_campaign.parent / "measurement_description.xlsx"
    pd.read_excel(path).drop(columns=["Messpunkte_UT"]).to_excel(path, index=False)
    with pytest.raises(ValueError, match="lacks the columns"):
        calculate_summary(config_path=demo_campaign)


def test_duplicate_grid_rows_are_merged(demo_campaign, caplog):
    path = demo_campaign.parent / "grid_data.xlsx"
    grid = pd.read_excel(path)
    pd.concat([grid, grid.iloc[[0, 0]]]).to_excel(path, index=False)
    with caplog.at_level(logging.INFO, logger="groundmeas"):
        calculate_summary(config_path=demo_campaign)
    assert len(pd.read_excel(path)) == len(grid)
    assert "merged 2 duplicate rows" in caplog.text


def test_default_values_without_short_circuit_data(demo_campaign, edit_config, DELETE):
    edit_config(
        demo_campaign,
        directory__sc_current_data_path=DELETE,
        line_protection__enabled=False,
    )
    calculate_summary(config_path=demo_campaign)
    data = load(demo_campaign, "8")
    assert data["Ik_kA"] == 12.0 and data["Abschaltzeit_s"] == 0.4
    assert data["Abschaltzeit_Hinweis"] == "default value from the configuration"


def test_locked_workbook_gives_a_clear_message(demo_campaign, monkeypatch):
    def locked(*args, **kwargs):
        raise PermissionError("[Errno 13] Permission denied")

    monkeypatch.setattr(pd.DataFrame, "to_excel", locked)
    with pytest.raises(PermissionError, match="probably open in Excel"):
        calculate_summary(config_path=demo_campaign)


def test_json_default_conversion():
    convert = summary_storage._json_default
    assert convert(np.int64(3)) == 3 and isinstance(convert(np.float64(1.5)), float)
    assert convert(np.bool_(True)) is True
    assert convert(pd.Timestamp("2026-01-02")).startswith("2026-01-02")
    assert summary_storage._cell(float("nan")) == ""
    assert summary_storage._cell(np.int64(4)) == 4
    assert summary_storage._cell(pd.Timestamp("2026-05-12")) == "2026-05-12"
    assert math.isclose(summary_storage._cell(np.float64(0.5)), 0.5)
