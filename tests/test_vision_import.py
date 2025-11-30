import math
from pathlib import Path

import pytest

from groundmeas.vision_import import (
    ParsedRow,
    build_items_from_rows,
    parse_measurement_rows,
)


def test_parse_measurement_rows_basic():
    text = """
    Distance: 1 m  Current: 10 A  Voltage: 100 V  Impedance: 0.5 ohm
    Distance: 20 m Current: 12 A  Voltage: 120 V  Impedance: 0.8 ohm
    """
    rows = parse_measurement_rows(text)
    assert len(rows) == 2
    assert rows[0].distance_m == 1.0
    assert rows[0].current_a == 10.0
    assert rows[0].voltage_v == 100.0
    assert rows[0].impedance_ohm == 0.5
    assert rows[1].distance_m == 20.0
    assert rows[1].impedance_ohm == 0.8


def test_parse_measurement_rows_table_and_dedup():
    text = """
    Entf. | V OUT (Korr.) | IN 1 | Z (Korr)
    1.0m | 114.0 mA 0.00° | 13.46mV -136.56°| 118.1 mΩ -136.56°
    1.0m | 114.0 mA 0.00° | 13.46mV -136.56°| 118.1 mΩ -136.56°
    20.0m | 120.0 mA 0.00° | 16.00mV -130.00°| 133.3 mΩ -130.00°
    """
    rows = parse_measurement_rows(text)
    assert len(rows) == 2
    assert rows[0].distance_m == 1.0
    assert rows[0].current_a == pytest.approx(0.114)  # mA -> A
    assert rows[0].voltage_v == pytest.approx(0.01346)  # mV -> V
    assert rows[0].impedance_ohm == pytest.approx(0.1181)  # mΩ -> Ω


def test_build_items_median_current_and_ptv():
    rows = [
        ParsedRow(distance_m=0.5, current_a=10.0, voltage_v=50.0, impedance_ohm=0.4),
        ParsedRow(distance_m=1.0, current_a=11.0, voltage_v=60.0, impedance_ohm=0.5),
        ParsedRow(distance_m=2.0, current_a=9.5, voltage_v=80.0, impedance_ohm=0.7),
    ]
    items = build_items_from_rows(
        measurement_id=1,
        rows=rows,
        measurement_type="earthing_impedance",
        frequency_hz=50.0,
        distance_to_current_injection_m=100.0,
    )
    assert len(items["impedance_items"]) == 3
    current_items = items["earthing_current_items"]
    assert len(current_items) == 1
    assert current_items[0]["value"] == pytest.approx(10.0)
    ptv = items["prospective_items"][0]
    assert ptv["measurement_distance_m"] == 1.0
    assert ptv["value"] == 60.0


def test_build_items_split_current_when_spread_large():
    rows = [
        ParsedRow(distance_m=1.0, current_a=10.0),
        ParsedRow(distance_m=2.0, current_a=16.0),
    ]
    items = build_items_from_rows(
        measurement_id=1,
        rows=rows,
        measurement_type="earthing_impedance",
        frequency_hz=50.0,
    )
    current_items = items["earthing_current_items"]
    assert len(current_items) == 2
    vals = sorted(c["value"] for c in current_items)
    assert vals == [10.0, 16.0]
    assert items["prospective_items"] == []


def test_prospective_only_from_rows():
    rows = [
        ParsedRow(distance_m=1.0, voltage_v=10.0),
        ParsedRow(distance_m=1.0, voltage_v=10.0),
    ]
    items = build_items_from_rows(
        measurement_id=1,
        rows=rows,
        measurement_type="earthing_impedance",
        frequency_hz=50.0,
    )
    assert len(items["prospective_items"]) == 1
    assert items["prospective_items"][0]["value"] == pytest.approx(10.0)
