"""
Regression tests for the 2026-05-13 audit-driven fix bundle.

The fixes implemented here cover the highest-priority findings from the
four audit passes (2026-05-09 .. 2026-05-12 pass 4) on ``groundmeas``:

1. ``calculate_split_factor``      — vector formula instead of magnitude.
2. ``voltage_vt_epr``              — ``z_per_amp`` key + ``epr`` alias,
                                     narrower exception handling.
3. ``rho_f_model`` helper          — sliding-window minimum-spread.
4. ``LayeredEarthModel.__post_init__`` — nan/inf rejection.
5. ``_normalize_ocr_text``         — context-aware ``rn`` → ``m`` mapping.
6. ``connect_db`` / ``disconnect_db`` — threading-safe + writability probe.
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# 1) calculate_split_factor — vector formula
# ---------------------------------------------------------------------------


def test_split_factor_in_phase_currents_matches_magnitude_formula(monkeypatch):
    """When shield currents are in phase with the fault current the new
    vector formula and the old magnitude formula must agree."""
    from groundmeas.services import analytics as A

    earth_item = {"id": 1, "value": 1000.0, "value_angle_deg": 0.0}
    shield_items = [
        {"id": 10, "value": 300.0, "value_angle_deg": 0.0},
        {"id": 11, "value": 200.0, "value_angle_deg": 0.0},
    ]

    def fake_read_items_by(**kwargs):
        if "id" in kwargs and kwargs["id"] == 1:
            return [earth_item], [1]
        if "id__in" in kwargs:
            return shield_items, [it["id"] for it in shield_items]
        return [], []

    monkeypatch.setattr(A, "read_items_by", fake_read_items_by)

    result = A.calculate_split_factor(1, [10, 11])
    # In-phase: local current = 500 A, fault current = 1000 A → split = 0.5
    assert result["split_factor"] == pytest.approx(0.5, rel=1e-9)
    assert result["local_earthing_current"]["value"] == pytest.approx(500.0)


def test_split_factor_out_of_phase_stays_in_unit_interval(monkeypatch):
    """The pre-1.5.2 magnitude formula went negative when the shield sum
    exceeded the fault magnitude despite being phase-shifted; the vector
    formula returns the proper local-current ratio (always ≥ 0)."""
    from groundmeas.services import analytics as A

    earth_item = {"id": 1, "value": 1000.0, "value_angle_deg": 0.0}
    # Shields out of phase by 180° with magnitudes that sum > 1000 A
    shield_items = [
        {"id": 10, "value": 800.0, "value_angle_deg": 180.0},
        {"id": 11, "value": 400.0, "value_angle_deg": 180.0},
    ]

    def fake_read_items_by(**kwargs):
        if "id" in kwargs and kwargs["id"] == 1:
            return [earth_item], [1]
        if "id__in" in kwargs:
            return shield_items, [it["id"] for it in shield_items]
        return [], []

    monkeypatch.setattr(A, "read_items_by", fake_read_items_by)

    result = A.calculate_split_factor(1, [10, 11])
    # I_local = 1000 - (-1200) = 2200 ; |I_local| / |I_E| = 2.2
    assert result["split_factor"] == pytest.approx(2.2, rel=1e-9)
    assert result["split_factor"] >= 0.0


# ---------------------------------------------------------------------------
# 2) voltage_vt_epr — key rename + narrower exceptions
# ---------------------------------------------------------------------------


def test_voltage_vt_epr_emits_z_per_amp_and_legacy_epr(monkeypatch):
    from groundmeas.services import analytics as A

    impedance = {"value": 0.42}
    current = {"value": 100.0}

    def fake_read_items_by(**kwargs):
        kind = kwargs.get("measurement_type")
        if kind == "earthing_impedance":
            return [impedance], [1]
        if kind == "earthing_current":
            return [current], [2]
        return [], []

    monkeypatch.setattr(A, "read_items_by", fake_read_items_by)

    out = A.voltage_vt_epr(7, frequency=50.0)
    assert "z_per_amp" in out
    assert out["z_per_amp"] == pytest.approx(0.42)
    # legacy alias
    assert out["epr"] == out["z_per_amp"]


def test_voltage_vt_epr_ambiguous_impedance_warns_and_averages(monkeypatch):
    from groundmeas.services import analytics as A

    imps = [{"value": 0.4}, {"value": 0.6}]
    current = {"value": 10.0}

    def fake_read_items_by(**kwargs):
        if kwargs.get("measurement_type") == "earthing_impedance":
            return imps, [1, 2]
        if kwargs.get("measurement_type") == "earthing_current":
            return [current], [3]
        return [], []

    monkeypatch.setattr(A, "read_items_by", fake_read_items_by)

    with pytest.warns(UserWarning, match="earthing_impedance rows matched"):
        out = A.voltage_vt_epr(7)
    # mean of 0.4 and 0.6 = 0.5
    assert out["z_per_amp"] == pytest.approx(0.5)


def test_voltage_vt_epr_does_not_swallow_unexpected_errors(monkeypatch):
    """Pre-1.5.2 voltage_vt_epr wrapped a bare ``except Exception`` around
    ``read_items_by``; programmer errors got silently turned into a
    ``UserWarning``.  The narrower handling must propagate them."""
    from groundmeas.services import analytics as A

    def boom(**kwargs):
        raise RuntimeError("DB schema mismatch — should not be swallowed")

    monkeypatch.setattr(A, "read_items_by", boom)
    with pytest.raises(RuntimeError, match="schema mismatch"):
        A.voltage_vt_epr(1)


# ---------------------------------------------------------------------------
# 3) rho_f_model helper — sliding-window minimum-spread selector
# ---------------------------------------------------------------------------


def test_select_minimum_spread_depths_two_measurements_same_depth():
    from groundmeas.services.analytics import _select_minimum_spread_depths

    rho_map = {
        1: {0.1: 50.0, 0.5: 80.0, 1.0: 120.0},
        2: {0.1: 60.0, 0.6: 90.0, 1.2: 130.0},
    }
    combo, spread = _select_minimum_spread_depths([1, 2], rho_map)
    assert spread == pytest.approx(0.0, abs=1e-12)
    assert set(combo) == {0.1}


def test_select_minimum_spread_depths_no_common_depth():
    from groundmeas.services.analytics import _select_minimum_spread_depths

    rho_map = {
        1: {0.2: 50.0},
        2: {0.8: 70.0},
        3: {0.5: 60.0},
    }
    combo, spread = _select_minimum_spread_depths([1, 2, 3], rho_map)
    # smallest window that covers all three: [0.2, 0.5, 0.8] → spread = 0.6
    assert spread == pytest.approx(0.6, abs=1e-12)
    assert combo == (0.2, 0.8, 0.5)


def test_select_minimum_spread_depths_scales_to_many_measurements():
    """The pre-1.5.2 implementation used itertools.product over per-measurement
    depth lists; with 12 measurements × 5 depths that is 5^12 ≈ 2·10^8
    iterations.  The sliding-window replacement must finish instantly."""
    from groundmeas.services.analytics import _select_minimum_spread_depths

    depths = [0.1, 0.5, 1.0, 1.5, 2.0]
    rho_map = {mid: {d: 50.0 + d for d in depths} for mid in range(20)}
    combo, spread = _select_minimum_spread_depths(list(range(20)), rho_map)
    # every measurement has 0.1 available
    assert spread == pytest.approx(0.0, abs=1e-12)
    assert all(d == 0.1 for d in combo)


# ---------------------------------------------------------------------------
# 4) LayeredEarthModel — nan/inf rejection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_layered_earth_rejects_non_finite_rho(bad):
    from groundmeas.services.analytics import LayeredEarthModel

    with pytest.raises(ValueError, match="finite"):
        LayeredEarthModel(rho_layers=(bad,))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_layered_earth_rejects_non_finite_thickness(bad):
    from groundmeas.services.analytics import LayeredEarthModel

    with pytest.raises(ValueError, match="finite"):
        LayeredEarthModel(rho_layers=(50.0, 200.0), thicknesses_m=(bad,))


def test_layered_earth_accepts_well_formed_two_layer():
    from groundmeas.services.analytics import LayeredEarthModel

    m = LayeredEarthModel(rho_layers=(50.0, 200.0), thicknesses_m=(1.0,))
    assert m.n_layers == 2


# ---------------------------------------------------------------------------
# 5) _normalize_ocr_text — context-aware ``rn`` → ``m``
# ---------------------------------------------------------------------------


def test_normalize_ocr_text_preserves_operator_names():
    from groundmeas.services.vision_import import _normalize_ocr_text

    cleaned = _normalize_ocr_text("Operator: Bernhard Schwerin")
    # ``rn`` inside names must NOT be touched
    assert "Bernhard" in cleaned
    assert "Schwerin" in cleaned


def test_normalize_ocr_text_fixes_unit_context():
    from groundmeas.services.vision_import import _normalize_ocr_text

    cleaned = _normalize_ocr_text("118.1 rnΩ -136.56°")
    assert "mΩ" in cleaned
    assert "rnΩ" not in cleaned


def test_normalize_ocr_text_leading_zero_preserved():
    from groundmeas.services.vision_import import _normalize_ocr_text

    cleaned = _normalize_ocr_text(".5 mA")
    assert cleaned.startswith("0.5")


# ---------------------------------------------------------------------------
# 6) connect_db / disconnect_db — threading + writability + idempotency
# ---------------------------------------------------------------------------


def test_connect_db_then_disconnect_idempotent(tmp_path: Path):
    from groundmeas.core import db as gdb

    target = tmp_path / "smoke.db"
    # Clean slate
    if gdb._engine is not None:
        gdb.disconnect_db()

    gdb.connect_db(str(target))
    assert gdb._engine is not None
    gdb.disconnect_db()
    assert gdb._engine is None
    # Idempotent — second disconnect must be a no-op
    gdb.disconnect_db()


def test_connect_db_rejects_double_connect(tmp_path: Path):
    from groundmeas.core import db as gdb

    if gdb._engine is not None:
        gdb.disconnect_db()
    gdb.connect_db(str(tmp_path / "a.db"))
    try:
        with pytest.raises(RuntimeError, match="already initialised"):
            gdb.connect_db(str(tmp_path / "b.db"))
    finally:
        gdb.disconnect_db()


def test_connect_db_force_replaces_engine(tmp_path: Path):
    from groundmeas.core import db as gdb

    if gdb._engine is not None:
        gdb.disconnect_db()
    gdb.connect_db(str(tmp_path / "first.db"))
    first_engine = gdb._engine
    gdb.connect_db(str(tmp_path / "second.db"), force=True)
    assert gdb._engine is not None
    assert gdb._engine is not first_engine
    gdb.disconnect_db()


def test_connect_db_writability_probe_rejects_missing_dir(tmp_path: Path):
    from groundmeas.core import db as gdb

    if gdb._engine is not None:
        gdb.disconnect_db()
    bogus = tmp_path / "nope" / "child" / "db.sqlite"
    with pytest.raises(RuntimeError, match="parent directory"):
        gdb.connect_db(str(bogus))


def test_connect_db_thread_safety(tmp_path: Path):
    """Two concurrent ``connect_db`` calls must not both succeed silently."""
    from groundmeas.core import db as gdb

    if gdb._engine is not None:
        gdb.disconnect_db()

    barrier = threading.Barrier(2)
    errors: List[Exception] = []
    successes: List[int] = []

    def worker(idx: int) -> None:
        barrier.wait()
        try:
            gdb.connect_db(str(tmp_path / f"db{idx}.db"))
            successes.append(idx)
        except RuntimeError as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        # Exactly one thread must win the race; the other must raise.
        assert len(successes) == 1
        assert len(errors) == 1
    finally:
        gdb.disconnect_db()


# ---------------------------------------------------------------------------
# 7) groundmeas top-level re-exports disconnect_db
# ---------------------------------------------------------------------------


def test_top_level_exposes_disconnect_db():
    import groundmeas as gm

    assert hasattr(gm, "disconnect_db")
    assert "disconnect_db" in gm.__all__
