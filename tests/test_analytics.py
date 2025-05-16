# tests/test_analytics.py

import pytest
import warnings
import numpy as np

from groundmeas import analytics


# ─── impedance_over_frequency ───────────────────────────────────────────────────

def test_impedance_over_frequency_single_success(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [{"id": 1, "frequency_hz": 50, "value": 100}], None
        ),
    )
    out = analytics.impedance_over_frequency(1)
    assert out == {50.0: 100.0}


def test_impedance_over_frequency_multiple_success(monkeypatch):
    def fake_read(measurement_id, measurement_type):
        return ([{"id": measurement_id, "frequency_hz": 1, "value": measurement_id}], None)
    monkeypatch.setattr(analytics, "read_items_by", fake_read)

    out = analytics.impedance_over_frequency([1, 2])
    assert out == {
        1: {1.0: 1.0},
        2: {1.0: 2.0},
    }


def test_impedance_over_frequency_read_error(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (_ for _ in ()).throw(Exception("db fail")),
    )
    with pytest.raises(RuntimeError) as exc:
        analytics.impedance_over_frequency(1)
    assert "Failed to load impedance data for measurement 1" in str(exc.value)


def test_impedance_over_frequency_no_items_warn(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([], None),
    )
    with pytest.warns(UserWarning) as w:
        out = analytics.impedance_over_frequency(3)
    assert "No earthing_impedance measurements found for measurement_id=3" in str(w.list[0].message)
    assert out == {}


def test_impedance_over_frequency_skip_missing_freq(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([{"id": 7, "frequency_hz": None, "value": 5}], None),
    )
    with pytest.warns(UserWarning) as w:
        out = analytics.impedance_over_frequency(7)
    assert "missing frequency_hz; skipping" in str(w.list[0].message)
    assert out == {}


def test_impedance_over_frequency_skip_conversion_error(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([{"id": 8, "frequency_hz": "bad", "value": "bad"}], None),
    )
    with pytest.warns(UserWarning) as w:
        out = analytics.impedance_over_frequency(8)
    assert "Could not convert item 8 to floats; skipping" in str(w.list[0].message)
    assert out == {}


# ─── real_imag_over_frequency ──────────────────────────────────────────────────

def test_real_imag_over_frequency_single_success(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [{"id": 1, "frequency_hz": 20, "value_real": 1.5, "value_imag": -2.5}], None
        ),
    )
    out = analytics.real_imag_over_frequency(1)
    assert out == {20.0: {"real": 1.5, "imag": -2.5}}


def test_real_imag_over_frequency_multiple_success(monkeypatch):
    def fake_read(measurement_id, measurement_type):
        return ([{"id": measurement_id, "frequency_hz": 2, "value_real": measurement_id * 1.0, "value_imag": measurement_id * -1.0}], None)
    monkeypatch.setattr(analytics, "read_items_by", fake_read)

    out = analytics.real_imag_over_frequency([5, 6])
    assert out == {
        5: {2.0: {"real": 5.0, "imag": -5.0}},
        6: {2.0: {"real": 6.0, "imag": -6.0}},
    }


def test_real_imag_over_frequency_missing_freq(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([{"id": 2, "frequency_hz": None, "value_real": 0, "value_imag": 0}], None),
    )
    with pytest.warns(UserWarning) as w:
        out = analytics.real_imag_over_frequency(2)
    assert "missing frequency_hz; skipping" in str(w.list[0].message)
    assert out == {}


def test_real_imag_over_frequency_missing_r_or_i(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([{"id": 3, "frequency_hz": 3, "value_real": None, "value_imag": 7}], None),
    )
    out = analytics.real_imag_over_frequency(3)
    assert out == {3.0: {"real": None, "imag": 7.0}}


def test_real_imag_over_frequency_conversion_error(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([{"id": 4, "frequency_hz": 4, "value_real": "bad", "value_imag": "0"}], None),
    )
    with pytest.warns(UserWarning) as w:
        out = analytics.real_imag_over_frequency(4)
    assert "Could not convert real/imag for item 4; skipping" in str(w.list[0].message)
    assert out == {}


def test_real_imag_over_frequency_no_items_warn(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([], None),
    )
    with pytest.warns(UserWarning) as w:
        out = analytics.real_imag_over_frequency(9)
    assert "No earthing_impedance measurements found for measurement_id=9" in str(w.list[0].message)
    assert out == {}


def test_real_imag_over_frequency_read_error(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (_ for _ in ()).throw(Exception("oops")),
    )
    with pytest.raises(RuntimeError) as exc:
        analytics.real_imag_over_frequency(1)
    assert "Failed to load impedance data for measurement 1" in str(exc.value)


# ─── rho_f_model ────────────────────────────────────────────────────────────────

def test_rho_f_model_no_soil_data(monkeypatch):
    monkeypatch.setattr(analytics, "real_imag_over_frequency", lambda ids: {1: {}})
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: ([], None),
    )
    with pytest.raises(ValueError) as exc:
        analytics.rho_f_model([1])
    assert "No soil_resistivity data for measurement 1" in str(exc.value)


def test_rho_f_model_no_overlap(monkeypatch):
    monkeypatch.setattr(analytics, "real_imag_over_frequency", lambda ids: {1: {}})
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [{"id": 1, "measurement_distance_m": 1.0, "value": 10.0}], None
        ),
    )
    with pytest.raises(ValueError) as exc:
        analytics.rho_f_model([1])
    assert "No overlapping impedance data available for fitting" in str(exc.value)


def test_rho_f_model_least_squares_error(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "real_imag_over_frequency",
        lambda ids: {1: {1.0: {"real": 5.0, "imag": -5.0}}},
    )
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [{"id": 1, "measurement_distance_m": 2.0, "value": 3.0}], None
        ),
    )
    monkeypatch.setattr(
        np.linalg,
        "lstsq",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("bad solve")),
    )
    with pytest.raises(RuntimeError) as exc:
        analytics.rho_f_model([1])
    assert "Failed to solve rho-f least-squares problem" in str(exc.value)


