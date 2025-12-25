# tests/test_analytics.py

import math
import pytest
import warnings
import numpy as np

from groundmeas.services import analytics


# ─── distance_profile_value ─────────────────────────────────────────────────────


def test_distance_profile_maximum(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [
                {"id": 1, "measurement_distance_m": 1.0, "value": 0.1, "unit": "Ω"},
                {"id": 2, "measurement_distance_m": 10.0, "value": 0.5, "unit": "Ω"},
            ],
            None,
        ),
    )
    out = analytics.distance_profile_value(
        1, measurement_type="earthing_impedance", algorithm="maximum"
    )
    assert out["result_value"] == pytest.approx(0.5)
    assert out["algorithm"] == "maximum"
    assert out["result_distance_m"] == pytest.approx(10.0)
    assert len(out["data_points"]) == 2


def test_distance_profile_62_percent(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [
                {
                    "id": 1,
                    "measurement_distance_m": 50.0,
                    "value": 1.0,
                    "distance_to_current_injection_m": 100.0,
                },
                {
                    "id": 2,
                    "measurement_distance_m": 60.0,
                    "value": 2.0,
                    "distance_to_current_injection_m": 100.0,
                },
                {
                    "id": 3,
                    "measurement_distance_m": 70.0,
                    "value": 3.0,
                    "distance_to_current_injection_m": 100.0,
                },
            ],
            None,
        ),
    )
    out = analytics.distance_profile_value(1, algorithm="62_percent")
    assert out["distance_to_current_injection_m"] == pytest.approx(100.0)
    assert out["details"]["target_distance_m"] == pytest.approx(62.0)
    assert out["result_value"] == pytest.approx(2.2)
    assert out["result_distance_m"] == pytest.approx(62.0)


def test_distance_profile_minimum_gradient(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [
                {"measurement_distance_m": 1.0, "value": 0.1},
                {"measurement_distance_m": 5.0, "value": 0.5},
                {"measurement_distance_m": 10.0, "value": 0.55},
                {"measurement_distance_m": 20.0, "value": 1.5},
            ],
            None,
        ),
    )
    out = analytics.distance_profile_value(2, algorithm="minimum_gradient")
    assert out["details"]["distance_m"] == pytest.approx(10.0)
    assert out["details"]["gradient"] == pytest.approx(0.03833, rel=1e-3)
    assert out["result_distance_m"] == pytest.approx(10.0)


def test_distance_profile_minimum_stddev(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [
                {"measurement_distance_m": 1.0, "value": 1.0},
                {"measurement_distance_m": 2.0, "value": 1.1},
                {"measurement_distance_m": 3.0, "value": 1.2},
                {"measurement_distance_m": 4.0, "value": 3.0},
                {"measurement_distance_m": 5.0, "value": 4.0},
            ],
            None,
        ),
    )
    out = analytics.distance_profile_value(
        3, algorithm="minimum_stddev", window=3
    )
    assert out["result_value"] == pytest.approx(1.2)
    assert out["details"]["window_size"] == 3
    assert out["details"]["stddev"] == pytest.approx(0.0816, rel=1e-2)
    assert out["result_distance_m"] == pytest.approx(3.0)


def test_distance_profile_inverse(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [
                {"measurement_distance_m": 1.0, "value": 0.5},
                {"measurement_distance_m": 2.0, "value": 0.6},
                {"measurement_distance_m": 4.0, "value": 0.7},
                {"measurement_distance_m": 8.0, "value": 0.8},
            ],
            None,
        ),
    )
    out = analytics.distance_profile_value(4, algorithm="inverse")
    assert out["details"]["intercept"] != 0
    assert out["result_value"] == pytest.approx(0.8349, rel=1e-3)
    assert math.isinf(out["result_distance_m"])


def test_distance_profile_requires_injection(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (
            [{"measurement_distance_m": 10.0, "value": 1.0}],
            None,
        ),
    )
    with pytest.raises(ValueError):
        analytics.distance_profile_value(5, algorithm="62_percent")


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


# ─── shield_currents_for_location ───────────────────────────────────────────────


def test_shield_currents_for_location_collects(monkeypatch):
    def fake_read_measurements_by(location_id):
        return (
            [
                {
                    "id": 10,
                    "items": [
                        {
                            "id": 1,
                            "measurement_type": "shield_current",
                            "frequency_hz": 50.0,
                            "value": 5.0,
                            "value_angle_deg": 0.0,
                            "unit": "A",
                        },
                        {
                            "id": 2,
                            "measurement_type": "earthing_current",
                            "value": 1.0,
                            "unit": "A",
                        },
                    ],
                },
                {
                    "id": 11,
                    "items": [
                        {
                            "id": 3,
                            "measurement_type": "shield_current",
                            "frequency_hz": 50.0,
                            "value_real": 1.0,
                            "value_imag": 1.0,
                            "unit": "A",
                        }
                    ],
                },
            ],
            [10, 11],
        )

    monkeypatch.setattr(analytics, "read_measurements_by", fake_read_measurements_by)

    out = analytics.shield_currents_for_location(5, frequency_hz=50.0)
    assert [c["id"] for c in out] == [1, 3]
    assert {c["measurement_id"] for c in out} == {10, 11}


def test_shield_currents_for_location_warns(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_measurements_by",
        lambda location_id: ([{"id": 1, "items": []}], [1]),
    )
    with pytest.warns(UserWarning):
        out = analytics.shield_currents_for_location(1)
    assert out == []


def test_shield_currents_for_location_error(monkeypatch):
    monkeypatch.setattr(
        analytics,
        "read_measurements_by",
        lambda location_id: (_ for _ in ()).throw(Exception("db down")),
    )
    with pytest.raises(RuntimeError):
        analytics.shield_currents_for_location(1)


# ─── calculate_split_factor ─────────────────────────────────────────────────────


def test_calculate_split_factor_success(monkeypatch):
    def fake_read_items_by(**filters):
        if filters.get("measurement_type") == "earth_fault_current":
            return (
                [
                    {
                        "id": filters.get("id"),
                        "measurement_type": "earth_fault_current",
                        "value": 100.0,
                        "value_angle_deg": 0.0,
                        "unit": "A",
                    }
                ],
                [filters.get("id")],
            )
        if filters.get("measurement_type") == "shield_current":
            ids = filters.get("id__in", [])
            return (
                [
                    {
                        "id": ids[0],
                        "measurement_type": "shield_current",
                        "value": 30.0,
                        "value_angle_deg": 0.0,
                        "unit": "A",
                    },
                    {
                        "id": ids[1],
                        "measurement_type": "shield_current",
                        "value_real": 10.0,
                        "value_imag": 0.0,
                        "unit": "A",
                    },
                ],
                ids,
            )
        raise AssertionError("unexpected filters")

    monkeypatch.setattr(analytics, "read_items_by", fake_read_items_by)

    result = analytics.calculate_split_factor(200, [1, 2])
    assert result["split_factor"] == pytest.approx(0.6)
    assert result["local_earthing_current"]["value"] == pytest.approx(60.0)
    assert result["local_earthing_current"]["value_angle_deg"] == pytest.approx(0.0)


def test_calculate_split_factor_warns_missing(monkeypatch):
    def fake_read_items_by(**filters):
        if filters.get("measurement_type") == "earth_fault_current":
            return (
                [
                    {
                        "id": 50,
                        "measurement_type": "earth_fault_current",
                        "value": 50.0,
                        "value_angle_deg": 0.0,
                        "unit": "A",
                    }
                ],
                [50],
            )
        if filters.get("measurement_type") == "shield_current":
            return (
                [
                    {
                        "id": 2,
                        "measurement_type": "shield_current",
                        "value": 10.0,
                        "value_angle_deg": 0.0,
                        "unit": "A",
                    }
                ],
                [2],
            )
        raise AssertionError("unexpected filters")

    monkeypatch.setattr(analytics, "read_items_by", fake_read_items_by)

    with pytest.warns(UserWarning):
        result = analytics.calculate_split_factor(50, [1, 2])
    assert result["split_factor"] == pytest.approx(0.8)
    assert result["shield_current_sum"]["value"] == pytest.approx(10.0)


def test_calculate_split_factor_zero_earth_current(monkeypatch):
    def fake_read_items_by(**filters):
        if filters.get("measurement_type") == "earth_fault_current":
            return (
                [
                    {
                        "id": 1,
                        "measurement_type": "earth_fault_current",
                        "value": 0.0,
                        "value_angle_deg": 0.0,
                        "unit": "A",
                    }
                ],
                [1],
            )
        if filters.get("measurement_type") == "shield_current":
            return (
                [
                    {
                        "id": 2,
                        "measurement_type": "shield_current",
                        "value": 1.0,
                        "value_angle_deg": 0.0,
                        "unit": "A",
                    }
                ],
                [2],
            )
        raise AssertionError("unexpected filters")

    monkeypatch.setattr(analytics, "read_items_by", fake_read_items_by)

    with pytest.raises(ValueError):
        analytics.calculate_split_factor(1, [2])


def test_calculate_split_factor_requires_ids():
    with pytest.raises(ValueError):
        analytics.calculate_split_factor(1, [])
