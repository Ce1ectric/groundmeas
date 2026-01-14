from pathlib import Path

import numpy as np
import pytest

from groundmeas.services import vision_import as vi

from groundmeas.services.vision_import import (
    ParsedRow,
    build_items_from_rows,
    import_items_from_images,
    ocr_image,
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


def test_parse_measurement_rows_compact_angles():
    text = "1.0m 114.0 mA 0.00° 13.46 mV -136.56° 118.1 mΩ -130.00°"
    rows = parse_measurement_rows(text)
    assert rows
    assert rows[0].impedance_angle_deg == pytest.approx(-130.0)


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


def test_normalize_ocr_text():
    out = vi._normalize_ocr_text(".5 0. 1.23 rn")
    assert "0.5" in out
    assert "0.0" in out
    assert "1.23" in out
    assert "m" in out


def test_parse_value_angle_unit():
    value, angle, unit = vi._parse_value_angle_unit("118.1 mΩ -136.56°")
    assert value == pytest.approx(0.1181)
    assert angle == pytest.approx(-136.56)
    assert unit == "mΩ"


def test_read_api_key_missing(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    with pytest.raises(RuntimeError):
        vi._read_api_key("MISSING_KEY")


def test_ocr_image_tesseract(monkeypatch):
    monkeypatch.setattr(vi, "preprocess_image", lambda path: np.zeros((2, 2)))
    monkeypatch.setattr(vi.pytesseract, "image_to_string", lambda img, lang, config: "TEXT")
    out = ocr_image(Path("dummy.png"), provider_model="tesseract")
    assert out == "TEXT"


def test_ocr_image_openai(monkeypatch):
    monkeypatch.setattr(vi, "_read_api_key", lambda env: "key")
    monkeypatch.setattr(vi, "_image_to_base64", lambda path, max_dim=None: "b64")

    class DummyResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "OCR"}}]}

    monkeypatch.setattr(vi.requests, "post", lambda *args, **kwargs: DummyResp())
    out = ocr_image(Path("dummy.png"), provider_model="openai:gpt-test")
    assert out == "OCR"


def test_ocr_image_invalid_provider():
    with pytest.raises(ValueError):
        ocr_image(Path("dummy.png"), provider_model="bogus")


def test_import_items_from_images_dir_mode(monkeypatch, tmp_path):
    img_dir = tmp_path / "images"
    subdir = img_dir / "50"
    subdir.mkdir(parents=True)
    (subdir / "sample.png").write_bytes(b"fake")

    monkeypatch.setattr(vi, "ocr_image", lambda *args, **kwargs: "text")
    monkeypatch.setattr(vi, "parse_measurement_rows", lambda text: [ParsedRow(distance_m=1.0, current_a=0.1)])
    monkeypatch.setattr(
        vi,
        "build_items_from_rows",
        lambda **kwargs: {"impedance_items": [{"value": 1}], "earthing_current_items": [], "prospective_items": []},
    )
    monkeypatch.setattr(vi, "create_item", lambda payload, measurement_id: 123)

    out = import_items_from_images(
        images_dir=img_dir,
        measurement_id=1,
        frequency_hz="dir",
    )
    assert out["created_item_ids"] == [123]
