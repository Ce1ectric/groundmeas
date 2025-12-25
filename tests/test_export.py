# tests/test_export.py
import json
import csv
import datetime
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import groundmeas.services.export as export_module


def test_export_json_success(tmp_path, monkeypatch):
    # prepare fake data including a datetime
    data = [
        {"id": 1, "ts": datetime.datetime(2020, 1, 1, 12, 0), "value": 3},
        {"id": 2, "ts": datetime.datetime(2021, 6, 15, 8, 30), "value": None},
    ]
    # stub read_measurements_by
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **filters: (data, None),
    )

    out_file = tmp_path / "out.json"
    # run
    export_module.export_measurements_to_json(str(out_file), some_filter=5)

    # verify file exists and content is valid JSON
    assert out_file.exists()
    text = out_file.read_text(encoding="utf-8")
    loaded = json.loads(text)
    # datetime fields should be isoformat strings
    assert loaded[0]["ts"] == "2020-01-01T12:00:00"
    assert loaded[1]["value"] is None


def test_export_json_read_error(monkeypatch):
    # stub to raise
    def fake_read(**filters):
        raise RuntimeError("DB down")
    monkeypatch.setattr(export_module, "read_measurements_by", fake_read)

    with pytest.raises(RuntimeError) as exc:
        export_module.export_measurements_to_json("dummy.json", foo=1)
    assert "Could not read measurements: DB down" in str(exc.value)


def test_export_json_write_error(tmp_path, monkeypatch):
    data = [{"id": 1}]
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (data, None),
    )
    # force Path.open to error
    def fake_open(self, *args, **kwargs):
        raise OSError("disk full")
    monkeypatch.setattr(Path, "open", fake_open)

    with pytest.raises(IOError) as exc:
        export_module.export_measurements_to_json(str(tmp_path / "x.json"))
    assert "Could not write JSON file" in str(exc.value)


def test_export_csv_success(tmp_path, monkeypatch):
    data = [
        {"id": 1, "name": "A", "items": [{"id": 10}, {"id": 11}]},
        {"id": 2, "name": "B", "items": []},
    ]
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (data, None),
    )

    out_file = tmp_path / "out.csv"
    export_module.export_measurements_to_csv(str(out_file), foo="bar")

    assert out_file.exists()
    with out_file.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    # header should have id, name, items
    assert set(reader.fieldnames) == {"id", "name", "items"}
    # two rows
    assert len(rows) == 2
    # items column should be JSON-encoded list
    assert json.loads(rows[0]["items"]) == [{"id": 10}, {"id": 11}]
    assert json.loads(rows[1]["items"]) == []


def test_export_csv_empty_data(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: ([], None),
    )
    caplog.set_level("WARNING")
    out_file = tmp_path / "empty.csv"
    # should not raise, just warn
    export_module.export_measurements_to_csv(str(out_file), x=1)
    assert "No data to export to CSV" in caplog.text
    assert not out_file.exists()


def test_export_csv_read_error(monkeypatch):
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (_ for _ in ()).throw(Exception("fail read")),
    )
    with pytest.raises(RuntimeError) as exc:
        export_module.export_measurements_to_csv("dummy.csv")
    assert "Could not read measurements: fail read" in str(exc.value)


def test_export_csv_write_error(tmp_path, monkeypatch):
    data = [{"id": 1, "foo": "bar", "items": []}]
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (data, None),
    )
    def fake_open(self, *args, **kwargs):
        raise OSError("no space")
    monkeypatch.setattr(Path, "open", fake_open)

    with pytest.raises(IOError) as exc:
        export_module.export_measurements_to_csv(str(tmp_path / "c.csv"))
    assert "Could not write CSV file" in str(exc.value)


def test_export_xml_success(tmp_path, monkeypatch):
    data = [
        {
            "id": 1,
            "foo": None,
            "bar": "baz",
            "items": [
                {"id": 10, "val": None},
                {"id": 11, "val": 5},
            ],
        }
    ]
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (data, None),
    )

    out_file = tmp_path / "out.xml"
    export_module.export_measurements_to_xml(str(out_file), x=2)

    # parse and verify structure
    tree = ET.parse(out_file)
    root = tree.getroot()
    meas = root.find("measurement")
    assert meas is not None and meas.attrib["id"] == "1"
    # foo child should exist with empty text
    foo = meas.find("foo")
    assert foo is not None
    assert foo.text is None or foo.text == ""
    bar = meas.find("bar")
    assert bar.text == "baz"
    items = meas.find("items")
    its = items.findall("item")
    assert len(its) == 2
    # first item val is empty
    first_val = its[0].find("val")
    assert first_val.text is None or first_val.text == ""
    second_val = its[1].find("val")
    assert second_val.text == "5"


def test_export_xml_read_error(monkeypatch):
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (_ for _ in ()).throw(Exception("no db")),
    )
    with pytest.raises(RuntimeError) as exc:
        export_module.export_measurements_to_xml("dummy.xml")
    assert "Could not read measurements: no db" in str(exc.value)


def test_export_xml_write_error(tmp_path, monkeypatch):
    data = [{"id": 1, "items": []}]
    monkeypatch.setattr(
        export_module,
        "read_measurements_by",
        lambda **f: (data, None),
    )
    # stub ElementTree.write to raise
    monkeypatch.setattr(
        ET.ElementTree,
        "write",
        lambda self, path, encoding, xml_declaration: (_ for _ in ()).throw(IOError("full")),
    )

    with pytest.raises(IOError) as exc:
        export_module.export_measurements_to_xml(str(tmp_path / "x.xml"))
    assert "Could not write XML file" in str(exc.value)
