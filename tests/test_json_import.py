"""Tests for groundmeas.services.json_import (JSON import and export round trip)."""

from __future__ import annotations

import datetime as dt
import json

import pytest

import groundmeas as gm
from groundmeas.core import db
from groundmeas.services.json_import import (
    collect_json_measurements,
    parse_timestamp,
    prepare_measurement_for_import,
)


def _sample_measurement(name: str = "Tower 8") -> dict:
    return {
        "timestamp": dt.datetime(2026, 5, 12, 9, 30),
        "method": "injection_earth_electrode",
        "asset_type": "overhead_line_tower",
        "voltage_level_kv": 110.0,
        "operator": "Jane Doe",
        "location": {"name": name, "latitude": 52.1, "longitude": 10.2},
    }


def _sample_items() -> list[dict]:
    return [
        {
            "measurement_type": "earthing_impedance",
            "value": 0.12,
            "value_angle_deg": 5.0,
            "unit": "Ω",
            "frequency_hz": 50.0,
            "measurement_distance_m": float(d),
            "distance_to_current_injection_m": 100.0,
        }
        for d in (10, 20, 62)
    ] + [{"measurement_type": "earthing_current", "value": 0.1, "unit": "A"}]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-05-12T09:00:00", dt.datetime(2026, 5, 12, 9, 0)),
        ("2026-05-12 09:00", dt.datetime(2026, 5, 12, 9, 0)),
        ("2026-05-12", dt.datetime(2026, 5, 12)),
        ("2026-05-12T11:00:00+02:00", dt.datetime(2026, 5, 12, 9, 0)),
        ("2026-05-12T09:00:00Z", dt.datetime(2026, 5, 12, 9, 0)),
        ("2026-05-12T09:00:00.250000", dt.datetime(2026, 5, 12, 9, 0, 0, 250000)),
    ],
)
def test_parse_timestamp_iso_variants(text, expected):
    assert parse_timestamp(text) == expected


def test_parse_timestamp_datetime_and_empty():
    aware = dt.datetime(2026, 5, 12, 11, tzinfo=dt.timezone(dt.timedelta(hours=2)))
    assert parse_timestamp(aware) == dt.datetime(2026, 5, 12, 9)
    assert parse_timestamp(None) is None
    assert parse_timestamp("  ") is None


@pytest.mark.parametrize("value", ["12.05.2026", "yesterday", 1715500000])
def test_parse_timestamp_rejects_invalid(value):
    with pytest.raises(ValueError, match="Invalid timestamp"):
        parse_timestamp(value)


def test_prepare_measurement_drops_database_keys():
    measurement, items = prepare_measurement_for_import(
        {
            "id": 4,
            "location_id": 2,
            "timestamp": "2026-05-12T09:00:00",
            "method": "wenner",
            "asset_type": "substation",
            "location": {"id": 2, "name": "A"},
            "items": [{"id": 1, "measurement_id": 4, "value": 3.0, "unit": "Ωm"}],
        }
    )
    assert measurement == {
        "timestamp": dt.datetime(2026, 5, 12, 9),
        "method": "wenner",
        "asset_type": "substation",
        "location": {"name": "A"},
    }
    assert items == [{"value": 3.0, "unit": "Ωm"}]


def test_prepare_measurement_null_timestamp_and_location():
    measurement, items = prepare_measurement_for_import(
        {"timestamp": None, "location": None, "method": "wenner", "asset_type": "house"}
    )
    assert measurement == {"method": "wenner", "asset_type": "house"}
    assert items == []


@pytest.mark.parametrize(
    "bad",
    [
        "string",
        {"method": "wenner", "items": {"value": 1}},
        {"method": "wenner", "items": [1, 2]},
    ],
)
def test_prepare_measurement_rejects_malformed(bad):
    with pytest.raises(ValueError):
        prepare_measurement_for_import(bad)


def test_export_import_round_trip(tmp_path):
    """export_measurements_to_json -> import_measurements_from_json keeps all data."""
    gm.connect_db(str(tmp_path / "source.db"))
    mid = gm.create_measurement(_sample_measurement())
    gm.create_items(_sample_items(), measurement_id=mid)
    export = tmp_path / "export.json"
    gm.export_measurements_to_json(str(export))
    source, _ = gm.read_measurements_by()
    gm.disconnect_db()

    gm.connect_db(str(tmp_path / "target.db"))
    created = gm.import_measurements_from_json(export)
    target, _ = gm.read_measurements_by()

    assert created == [(target[0]["id"], 4)]
    assert target[0]["timestamp"] == source[0]["timestamp"]
    for key in ("method", "asset_type", "voltage_level_kv", "operator"):
        assert target[0][key] == source[0][key]
    assert target[0]["location"]["name"] == "Tower 8"
    assert target[0]["location"]["latitude"] == pytest.approx(52.1)

    def _strip(item):
        return {k: v for k, v in item.items() if k not in ("id", "measurement_id")}

    assert [_strip(i) for i in target[0]["items"]] == [
        _strip(i) for i in source[0]["items"]
    ]


def test_import_into_database_with_existing_rows(tmp_path):
    """Exported ids must not collide with rows that already exist."""
    gm.connect_db(str(tmp_path / "ground.db"))
    mid = gm.create_measurement(_sample_measurement())
    gm.create_items(_sample_items(), measurement_id=mid)
    export = tmp_path / "export.json"
    gm.export_measurements_to_json(str(export))

    created = gm.import_measurements_from_json(export)

    measurements, ids = gm.read_measurements_by()
    assert len(measurements) == 2
    assert created[0][0] not in (mid,)
    # same name and coordinates -> the location is reused
    assert len({m["location"]["id"] for m in measurements}) == 1
    items, _ = gm.read_items_by(measurement_id=created[0][0])
    assert len(items) == 4


def test_import_validates_everything_before_inserting(tmp_path):
    gm.connect_db(str(tmp_path / "ground.db"))
    good = {**_sample_measurement(), "timestamp": "2026-05-12T09:00:00"}
    bad = {**_sample_measurement("Other"), "timestamp": "not a date"}
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps([good, bad]), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid timestamp"):
        gm.import_measurements_from_json(path)
    assert gm.read_measurements_by()[0] == []


def test_collect_json_merges_paired_items_file(tmp_path):
    (tmp_path / "x_measurement.json").write_text(
        json.dumps(
            {"method": "wenner", "asset_type": "house", "items": [{"value": 1}]}
        ),
        encoding="utf-8",
    )
    (tmp_path / "x_items.json").write_text(
        json.dumps({"items": [{"value": 2}, {"value": 3}]}), encoding="utf-8"
    )
    (tmp_path / "y.json").write_text(
        json.dumps([{"method": "wenner", "asset_type": "house"}]), encoding="utf-8"
    )

    collected = collect_json_measurements(tmp_path)

    names = [path.name for path, _ in collected]
    assert names == ["x_measurement.json", "y.json"]
    assert [i["value"] for i in collected[0][1][0]["items"]] == [1, 2, 3]


def test_collect_json_rejects_unsupported_structure(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps("string"), encoding="utf-8")
    with pytest.raises(ValueError, match="unsupported JSON structure"):
        collect_json_measurements(path)


def test_create_items_inserts_all_in_one_transaction():
    gm.connect_db(":memory:")
    mid = gm.create_measurement(_sample_measurement())
    ids = gm.create_items(_sample_items(), measurement_id=mid)
    items, item_ids = gm.read_items_by(measurement_id=mid)
    assert ids == sorted(item_ids)
    assert len(items) == 4
    imp = [i for i in items if i["measurement_type"] == "earthing_impedance"]
    # the insert listener fills in the rectangular components
    assert imp[0]["value_real"] == pytest.approx(0.12 * 0.9961946980917455)


def test_create_items_is_atomic():
    gm.connect_db(":memory:")
    mid = gm.create_measurement(_sample_measurement())
    payloads = _sample_items() + [{"measurement_type": "earthing_current", "unit": "A"}]
    with pytest.raises(ValueError):
        gm.create_items(payloads, measurement_id=mid)
    assert gm.read_items_by(measurement_id=mid)[0] == []


def test_create_items_empty_list():
    gm.connect_db(":memory:")
    mid = gm.create_measurement(_sample_measurement())
    assert gm.create_items([], measurement_id=mid) == []


def test_create_items_requires_connection():
    db.disconnect_db()
    with pytest.raises(RuntimeError):
        gm.create_items([{"value": 1, "unit": "Ω"}], measurement_id=1)
