"""
Regression tests for the Audit pass 5 fix bundle (2026-05-13).

The fifth audit pass on ``groundmeas`` produced a focused list of
follow-up findings on top of the pass-4 implementation. These tests
pin the corresponding fixes:

1. ``groundmeas.db`` shim exposes ``disconnect_db`` and emits a
   ``DeprecationWarning`` on attribute access.
2. ``groundmeas.analytics`` shim emits a ``DeprecationWarning`` on
   attribute access.
3. ``services.vision_import.ocr_image`` (OpenAI branch) raises a
   single ``RuntimeError`` for malformed envelopes (empty choices,
   ``content=None``, list-shaped content).
4. ``_normalize_ocr_text`` rewrites ``rn`` → ``m`` even when a
   whitespace separates the bigram from the unit letter
   (``118.1 rn Ω`` → ``118.1 m Ω``).
5. ``distance_profile_value`` emits a ``UserWarning`` when duplicate
   measurement distances are collapsed by the interpolation dedup.
6. ``ui.dashboard.init_db`` returns ``False`` (and renders a friendly
   ``st.error`` message) when ``connect_db`` raises ``RuntimeError``
   because the database path is on a read-only mount.
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# 1) groundmeas.db shim — disconnect_db + DeprecationWarning
# ---------------------------------------------------------------------------


def test_groundmeas_db_shim_exposes_disconnect_db():
    """The pass-4 implementation re-exported ``disconnect_db`` only via
    the top-level package. Pass 5 demands the same on the
    legacy ``groundmeas.db`` shim."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        from groundmeas.db import disconnect_db as shim_disconnect
        from groundmeas.core.db import disconnect_db as canonical_disconnect

    assert shim_disconnect is canonical_disconnect


def test_groundmeas_db_shim_emits_deprecationwarning():
    """Accessing a symbol via ``groundmeas.db`` should emit a
    ``DeprecationWarning`` that points at the canonical path."""
    import importlib

    shim = importlib.import_module("groundmeas.db")
    with pytest.warns(DeprecationWarning, match="groundmeas.db is a compatibility shim"):
        _ = shim.connect_db


def test_groundmeas_db_shim_dir_lists_disconnect_db():
    """``dir(groundmeas.db)`` must include ``disconnect_db`` for
    discoverability."""
    import importlib

    shim = importlib.import_module("groundmeas.db")
    assert "disconnect_db" in dir(shim)


def test_groundmeas_db_shim_attributeerror_for_missing_name():
    """Accessing a non-existent attribute on the shim must raise
    ``AttributeError`` (not return ``None``)."""
    import importlib

    shim = importlib.import_module("groundmeas.db")
    with pytest.raises(AttributeError):
        _ = shim.no_such_attribute


# ---------------------------------------------------------------------------
# 2) groundmeas.analytics shim — DeprecationWarning
# ---------------------------------------------------------------------------


def test_groundmeas_analytics_shim_emits_deprecationwarning():
    """Attribute access on the legacy ``groundmeas.analytics`` shim
    must emit a ``DeprecationWarning``."""
    import importlib

    shim = importlib.import_module("groundmeas.analytics")
    with pytest.warns(DeprecationWarning, match="groundmeas.analytics is a compatibility shim"):
        _ = shim.distance_profile_value


def test_groundmeas_analytics_shim_star_import_still_works():
    """``from groundmeas.analytics import *`` must still resolve every
    canonical name (via ``__all__`` + ``__getattr__``)."""
    import importlib

    shim = importlib.import_module("groundmeas.analytics")
    # The shim exposes a non-empty __all__ that mirrors the canonical
    # module surface.
    assert shim.__all__, "groundmeas.analytics.__all__ should not be empty"
    assert "distance_profile_value" in shim.__all__
    # Resolving the symbol via the shim must succeed (the
    # DeprecationWarning is silenced here).
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        dpv = getattr(shim, "distance_profile_value")
    from groundmeas.services.analytics import distance_profile_value as canonical
    assert dpv is canonical


# ---------------------------------------------------------------------------
# 3) ocr_image — defensive OpenAI envelope parsing
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):  # noqa: D401
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


@pytest.fixture
def _ocr_env(monkeypatch, tmp_path):
    """Provide an OPENAI_API_KEY and a stub image so ocr_image runs."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used")

    img = tmp_path / "fake.jpg"
    # Write a tiny non-empty file. _image_to_base64 is patched below so
    # we do not need a valid JPEG byte-stream.
    img.write_bytes(b"\x00\x01\x02")
    return img


def _patch_openai_call(monkeypatch, payload: Dict[str, Any]):
    """Patch the requests.post + _image_to_base64 helpers in vision_import."""
    from groundmeas.services import vision_import as vi

    monkeypatch.setattr(vi, "_image_to_base64", lambda *a, **kw: "AAA")
    monkeypatch.setattr(
        vi.requests,
        "post",
        lambda *args, **kwargs: _FakeResponse(payload),
    )
    return vi


def test_ocr_image_openai_empty_choices_raises_runtimeerror(monkeypatch, _ocr_env):
    """Empty ``choices`` list must raise RuntimeError, not IndexError."""
    vi = _patch_openai_call(monkeypatch, {"choices": [], "error": {"message": "5xx"}})
    with pytest.raises(RuntimeError, match="no choices"):
        vi.ocr_image(_ocr_env, provider_model="openai:gpt-4o-mini")


def test_ocr_image_openai_content_none_raises_runtimeerror(monkeypatch, _ocr_env):
    """``content=None`` (content filter / tool-call) must raise RuntimeError."""
    vi = _patch_openai_call(
        monkeypatch,
        {
            "choices": [
                {
                    "finish_reason": "content_filter",
                    "message": {"role": "assistant", "content": None},
                }
            ]
        },
    )
    with pytest.raises(RuntimeError, match="no content"):
        vi.ocr_image(_ocr_env, provider_model="openai:gpt-4o-mini")


def test_ocr_image_openai_list_content_is_joined(monkeypatch, _ocr_env):
    """List-shaped content (new envelope) must be joined into one string."""
    vi = _patch_openai_call(
        monkeypatch,
        {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"type": "text", "text": "118.1 mΩ "},
                            {"type": "text", "text": "0.0°"},
                        ]
                    }
                }
            ]
        },
    )
    out = vi.ocr_image(_ocr_env, provider_model="openai:gpt-4o-mini")
    assert out == "118.1 mΩ 0.0°"


def test_ocr_image_openai_happy_path_returns_string(monkeypatch, _ocr_env):
    """The classic envelope must still work."""
    vi = _patch_openai_call(
        monkeypatch,
        {"choices": [{"message": {"content": "hello"}}]},
    )
    out = vi.ocr_image(_ocr_env, provider_model="openai:gpt-4o-mini")
    assert out == "hello"


# ---------------------------------------------------------------------------
# 4) _normalize_ocr_text — whitespace-tolerant rn → m
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_contains",
    [
        ("118.1 rnΩ", "118.1 mΩ"),
        ("118.1 rn Ω", "118.1 m Ω"),  # Megger OCR with stray space
        ("5 rnA", "5 mA"),
        ("5 rn A", "5 m A"),
        ("Bernhardt operator notes", "Bernhardt"),  # negative case
    ],
)
def test_normalize_ocr_text_whitespace_rn(raw, expected_contains):
    from groundmeas.services.vision_import import _normalize_ocr_text

    cleaned = _normalize_ocr_text(raw)
    assert expected_contains in cleaned


# ---------------------------------------------------------------------------
# 5) distance_profile_value — duplicate-distance UserWarning
# ---------------------------------------------------------------------------


def test_distance_profile_value_warns_on_duplicate_distances(monkeypatch):
    """When two MeasurementItems share the same distance the dedup must
    fire a single ``UserWarning`` that names the duplicate distances."""
    from groundmeas.services import analytics

    items: List[Dict[str, Any]] = [
        {"id": 1, "measurement_distance_m": 1.0, "value": 0.1, "unit": "Ω"},
        {"id": 2, "measurement_distance_m": 5.0, "value": 0.4, "unit": "Ω"},
        {"id": 3, "measurement_distance_m": 5.0, "value": 0.42, "unit": "Ω"},
        {"id": 4, "measurement_distance_m": 10.0, "value": 0.5, "unit": "Ω"},
    ]
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (items, [it["id"] for it in items]),
    )

    with pytest.warns(UserWarning, match="duplicate measurement distances"):
        out = analytics.distance_profile_value(
            1, measurement_type="earthing_impedance", algorithm="maximum"
        )
    # Sanity: dedup kept one point per unique distance.
    distances = sorted({p["distance_m"] for p in out["data_points"]})
    assert distances == [1.0, 5.0, 10.0]


def test_distance_profile_value_no_warn_when_distances_unique(monkeypatch):
    """No duplicates ⇒ no warning."""
    from groundmeas.services import analytics

    items = [
        {"id": 1, "measurement_distance_m": 1.0, "value": 0.1, "unit": "Ω"},
        {"id": 2, "measurement_distance_m": 5.0, "value": 0.4, "unit": "Ω"},
        {"id": 3, "measurement_distance_m": 10.0, "value": 0.5, "unit": "Ω"},
    ]
    monkeypatch.setattr(
        analytics,
        "read_items_by",
        lambda measurement_id, measurement_type: (items, [it["id"] for it in items]),
    )

    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        # If a UserWarning fires the test fails. Filter only the duplicate-
        # distance warning ⇒ promote ALL UserWarnings to errors and rely on
        # the existing implementation not to emit any.
        out = analytics.distance_profile_value(
            1, measurement_type="earthing_impedance", algorithm="maximum"
        )
    assert out["result_value"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 6) dashboard.init_db — read-only filesystem handling
# ---------------------------------------------------------------------------


def test_dashboard_init_db_returns_false_on_runtimeerror(monkeypatch):
    """When ``connect_db`` raises a writability ``RuntimeError`` the
    dashboard's ``init_db`` must catch it, render ``st.error`` and
    return ``False`` so ``main()`` can ``st.stop()``."""
    try:
        from groundmeas.ui import dashboard
    except Exception as exc:  # pragma: no cover - import-time skip
        pytest.skip(f"dashboard module not importable in this env: {exc}")

    # Force the helper to fail with a writability error.
    def _raise(*args, **kwargs):
        raise RuntimeError("Database parent directory not writable: /readonly")

    monkeypatch.setattr(dashboard, "connect_db", _raise)
    monkeypatch.setattr(dashboard, "resolve_db_path", lambda: "/readonly/x.db")

    # Replace the global ``st`` so we can record the error message without
    # actually rendering anything.
    fake_st = SimpleNamespace(
        error=mock.MagicMock(),
        info=mock.MagicMock(),
    )
    monkeypatch.setattr(dashboard, "st", fake_st)

    ok = dashboard.init_db()
    assert ok is False
    fake_st.error.assert_called_once()
    message = fake_st.error.call_args[0][0]
    assert "read-only" in message or "not writable" in message


def test_dashboard_init_db_returns_true_on_already_initialised(monkeypatch):
    """A Streamlit auto-rerun that hits the "already initialised" guard
    must continue to render (return True) instead of halting."""
    try:
        from groundmeas.ui import dashboard
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"dashboard module not importable in this env: {exc}")

    def _raise(*args, **kwargs):
        raise RuntimeError(
            "Database engine is already initialised. Call disconnect_db() first ..."
        )

    monkeypatch.setattr(dashboard, "connect_db", _raise)
    monkeypatch.setattr(dashboard, "resolve_db_path", lambda: "/tmp/x.db")

    fake_st = SimpleNamespace(error=mock.MagicMock(), info=mock.MagicMock())
    monkeypatch.setattr(dashboard, "st", fake_st)

    ok = dashboard.init_db()
    assert ok is True
    fake_st.info.assert_called_once()
    fake_st.error.assert_not_called()
