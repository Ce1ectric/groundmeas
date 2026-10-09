"""
Regression tests for the Audit pass 6 / 7 fix bundle (2026-05-18).

This test module pins the implementation of the seventh-pass
audit-report (``Claude Audits/audit-report-changelogs-2026-05-18-pass7.md``)
items that have repeatedly been flagged across passes 6 and 7:

1. ``groundmeas._shim.make_shim`` — single source of truth for the
   compatibility-shim ``__getattr__``/``__all__``/``__dir__`` pattern.
2. Five-shim cross-rollout: ``groundmeas.models``, ``groundmeas.plots``,
   ``groundmeas.export``, ``groundmeas.vision_import`` and
   ``groundmeas.cli`` emit a single ``DeprecationWarning`` per attribute
   access *and* honour the underscore-prefix short-circuit demanded by
   the pass-6 finding on ``groundmeas.db``.
3. ``groundmeas.db`` shim does *not* warn on private attributes
   (``_get_session``) — closes the pass-6 finding.
4. ``__version__`` parity between ``pyproject.toml`` and
   ``groundmeas.__version__`` (no fixed version, so the check survives
   ``poetry run release``).
5. ``ui.dashboard.init_db()`` is rerun-aware and reconnects when the
   resolved DB path changes (pass-6/7 footgun).
6. ``invert_layered_earth`` emits a ``UserWarning`` when the damped
   Gauss-Newton scheme hits ``max_iter`` without satisfying the
   tolerance — closes the pass-6 swallowed-``OptimizeResult.success``
   finding.
7. ``core.db.current_db_path`` mirrors the active engine binding and
   is reset to ``None`` after ``disconnect_db``.
"""

from __future__ import annotations

import importlib
import warnings
from pathlib import Path
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# 1) _shim.make_shim helper
# ---------------------------------------------------------------------------


def _make_canonical(extras=None):
    """Tiny synthetic canonical module used by the helper-level tests."""
    import types

    canon = types.ModuleType("_test_canonical")
    canon.__all__ = ["foo", "bar"]
    canon.foo = lambda: "foo-result"
    canon.bar = 42
    canon._private = "should-not-leak"
    if extras:
        for name, value in extras.items():
            setattr(canon, name, value)
    return canon


def test_make_shim_public_symbol_emits_warning():
    """A public symbol access must emit exactly one DeprecationWarning."""
    from groundmeas._shim import make_shim

    canon = _make_canonical()
    _, getattr_, _ = make_shim(
        canonical=canon,
        shim_name="groundmeas.fake",
        canonical_name="groundmeas.real",
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        val = getattr_("foo")
    assert val() == "foo-result"
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "groundmeas.fake" in str(w[0].message)
    assert "groundmeas.real" in str(w[0].message)


def test_make_shim_private_symbol_does_not_warn():
    """Underscore-prefixed names must raise AttributeError without warning.

    This pins the pass-6 finding on ``groundmeas.db``: ``_get_session``
    used to slip through the ``if name in _CANONICAL_ATTRS`` filter and
    produce a spurious DeprecationWarning at the canonical-import call
    site.
    """
    from groundmeas._shim import make_shim

    canon = _make_canonical()
    _, getattr_, _ = make_shim(
        canonical=canon,
        shim_name="groundmeas.fake",
        canonical_name="groundmeas.real",
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with pytest.raises(AttributeError):
            getattr_("_private")
    assert len(w) == 0, "private-attr access must not warn"


def test_make_shim_extra_attrs_resolve_with_warning():
    """``extra_attrs`` opt-in for *one* private symbol must still warn."""
    from groundmeas._shim import make_shim

    canon = _make_canonical(extras={"_compute_magnitude": lambda x: abs(x)})
    all_names, getattr_, dir_ = make_shim(
        canonical=canon,
        shim_name="groundmeas.fake",
        canonical_name="groundmeas.real",
        extra_attrs=("_compute_magnitude",),
    )
    assert "_compute_magnitude" in all_names
    assert "_compute_magnitude" in dir_()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        fn = getattr_("_compute_magnitude")
    assert fn(-7) == 7
    assert len(w) == 1


def test_make_shim_unknown_attribute_raises():
    from groundmeas._shim import make_shim

    canon = _make_canonical()
    _, getattr_, _ = make_shim(
        canonical=canon, shim_name="groundmeas.fake", canonical_name="real"
    )
    with pytest.raises(AttributeError, match="no attribute"):
        getattr_("definitely_not_here")


# ---------------------------------------------------------------------------
# 2) Five-shim cross-rollout
# ---------------------------------------------------------------------------


FIVE_SHIMS = [
    "groundmeas.models",
    "groundmeas.plots",
    "groundmeas.export",
    "groundmeas.vision_import",
    "groundmeas.cli",
]


def _import_shim_or_skip(shim_name):
    """Import the deprecated shim, skipping the test if an optional
    dependency of the canonical module is missing in the current
    environment. The shim module itself has no dependencies beyond
    :mod:`groundmeas._shim`; canonical-side imports (typer, plotly,
    streamlit, …) are what may fail in stripped-down CI matrices.
    """
    try:
        return importlib.import_module(shim_name)
    except ModuleNotFoundError as e:  # pragma: no cover - environment-only
        pytest.skip(f"optional dep missing for {shim_name}: {e.name}")


@pytest.mark.parametrize("shim_name", FIVE_SHIMS)
def test_five_shim_rollout_emits_deprecation_warning(shim_name):
    """Each retrofitted shim must emit a ``DeprecationWarning`` on
    first attribute access.

    The probe walks ``dir(shim)`` to find a public symbol to access — we
    do not hardcode an attribute per module so the test stays valid if
    the canonical modules grow new public names.
    """
    shim = _import_shim_or_skip(shim_name)
    # Find any public attribute on the shim.
    public = [a for a in dir(shim) if not a.startswith("_")]
    assert public, f"shim {shim_name} exposes no public attributes"
    target = public[0]
    with pytest.warns(DeprecationWarning, match="compatibility shim"):
        _ = getattr(shim, target)


@pytest.mark.parametrize("shim_name", FIVE_SHIMS)
def test_five_shim_rollout_underscore_short_circuit(shim_name):
    """Private symbols on the five new shims must raise AttributeError
    *without* emitting a DeprecationWarning. Mirrors the pass-6
    ``_get_session`` finding for the wider shim family."""
    shim = _import_shim_or_skip(shim_name)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with pytest.raises(AttributeError):
            _ = getattr(shim, "_definitely_private_xyz")
    assert len(w) == 0


def test_db_shim_does_not_warn_on_private_attribute():
    """``from groundmeas.db import _get_session`` used to trigger a
    DeprecationWarning on the private symbol. After the pass-6 fix the
    private name must raise ``AttributeError`` and produce no warnings.
    """
    shim = importlib.import_module("groundmeas.db")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        with pytest.raises(AttributeError):
            _ = shim._get_session
    assert len(w) == 0, "private symbol must not warn"


# ---------------------------------------------------------------------------
# 3) __version__ parity
# ---------------------------------------------------------------------------


def test_pyproject_version_matches_package_version():
    """``pyproject.toml`` carries the same version as ``groundmeas.__version__``."""
    import groundmeas

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    # The first ``version = "..."`` in the file is the project version.
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("version") and "=" in line:
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            assert value == groundmeas.__version__, (value, groundmeas.__version__)
            break
    else:  # pragma: no cover - defensive
        raise AssertionError("no version line found in pyproject.toml")


# ---------------------------------------------------------------------------
# 4) Dashboard rerun-aware init_db
# ---------------------------------------------------------------------------


def _import_dashboard():
    """Import :mod:`groundmeas.ui.dashboard` with tolerance for missing
    optional dependencies and Streamlit's singleton enforcement.

    ``dashboard`` calls ``st.set_page_config`` at module-load time which
    is fine in a fresh Streamlit process but fails with
    ``RuntimeError("DeltaGeneratorSingleton instance already exists!")``
    in some CI environments. The function also pulls in plotly, folium,
    streamlit-folium and matplotlib transitively — any of which may be
    absent in a stripped-down test environment. Skip the test in either
    case; the production code path is unaffected.
    """
    try:
        from groundmeas.ui import dashboard
    except RuntimeError as e:  # pragma: no cover - environment-only
        pytest.skip(f"streamlit singleton collision in CI: {e}")
    except ModuleNotFoundError as e:  # pragma: no cover - environment-only
        pytest.skip(f"optional dashboard dep missing: {e.name}")
    return dashboard


def test_init_db_reconnects_on_path_change(monkeypatch, tmp_path):
    """``init_db`` must call ``disconnect_db`` and reconnect when the
    resolved DB path changes between Streamlit reruns.

    The previous behaviour ignored the new path because ``connect_db``
    short-circuited on ``_engine is not None``. After the pass-6/7 fix
    the dashboard explicitly tears down the stale engine.
    """
    dashboard = _import_dashboard()
    from groundmeas.core import db as core_db

    calls = {"connect": [], "disconnect": 0}

    def fake_connect_db(path, *args, **kwargs):
        calls["connect"].append(path)
        # Pretend ``connect_db`` populated the module-level state.
        core_db._engine = object()
        core_db._engine_path = path

    def fake_disconnect_db():
        calls["disconnect"] += 1
        core_db._engine = None
        core_db._engine_path = None

    # Stub Streamlit primitives that ``init_db`` would otherwise touch.
    class _Stub:
        def error(self, *a, **kw):
            pass

        def info(self, *a, **kw):
            pass

    monkeypatch.setattr(dashboard, "st", _Stub())
    monkeypatch.setattr(dashboard, "connect_db", fake_connect_db)
    monkeypatch.setattr(dashboard, "disconnect_db", fake_disconnect_db)
    # Path A first; path B on the rerun.
    paths = iter([str(tmp_path / "a.db"), str(tmp_path / "b.db")])
    monkeypatch.setattr(dashboard, "resolve_db_path", lambda: next(paths))

    # Reset module-state so the test starts clean.
    core_db._engine = None
    core_db._engine_path = None

    try:
        assert dashboard.init_db() is True
        assert dashboard.init_db() is True
    finally:
        core_db._engine = None
        core_db._engine_path = None

    assert len(calls["connect"]) == 2, calls
    assert calls["connect"][0] != calls["connect"][1]
    assert calls["disconnect"] == 1, calls


def test_init_db_short_circuits_on_same_path(monkeypatch, tmp_path):
    """If the resolved path matches the active engine path, ``init_db``
    must reuse the existing engine without calling ``connect_db`` again
    (and without calling ``disconnect_db``)."""
    dashboard = _import_dashboard()
    from groundmeas.core import db as core_db

    db_path = str(tmp_path / "same.db")
    calls = {"connect": 0, "disconnect": 0}

    def fake_connect_db(path, *a, **kw):
        calls["connect"] += 1
        core_db._engine = object()
        core_db._engine_path = path

    def fake_disconnect_db():
        calls["disconnect"] += 1
        core_db._engine = None
        core_db._engine_path = None

    class _Stub:
        def error(self, *a, **kw):
            pass

        def info(self, *a, **kw):
            pass

    monkeypatch.setattr(dashboard, "st", _Stub())
    monkeypatch.setattr(dashboard, "connect_db", fake_connect_db)
    monkeypatch.setattr(dashboard, "disconnect_db", fake_disconnect_db)
    monkeypatch.setattr(dashboard, "resolve_db_path", lambda: db_path)

    core_db._engine = None
    core_db._engine_path = None
    try:
        assert dashboard.init_db() is True
        # Second call must short-circuit.
        assert dashboard.init_db() is True
    finally:
        core_db._engine = None
        core_db._engine_path = None

    assert calls["connect"] == 1, calls
    assert calls["disconnect"] == 0, calls


# ---------------------------------------------------------------------------
# 5) Non-converging inversion warns
# ---------------------------------------------------------------------------


def test_invert_layered_earth_emits_warning_on_non_convergence():
    """Force ``invert_layered_earth`` to bail out at ``max_iter=1`` and
    assert the new ``UserWarning`` is raised. The result payload must
    still contain ``"converged": False`` and ``misfit["converged"]`` so
    downstream callers can inspect the outcome programmatically."""
    import numpy as np

    from groundmeas.services.analytics import invert_layered_earth

    # Two-layer synthetic data — exact closed form does not matter for
    # the convergence flag, only that the loop hits max_iter.
    spacings = [1.0, 2.0, 4.0, 8.0, 16.0, 32.0]
    rho_obs = [100.0, 110.0, 130.0, 170.0, 220.0, 260.0]

    with pytest.warns(UserWarning, match="did not converge"):
        result = invert_layered_earth(
            spacings_m=spacings,
            rho_obs=rho_obs,
            layers=2,
            max_iter=1,
            tol=1e-12,
        )

    assert result["converged"] is False
    assert result["misfit"]["converged"] is False
    assert result["misfit"]["iterations"] == 1


# ---------------------------------------------------------------------------
# 6) current_db_path mirrors engine state
# ---------------------------------------------------------------------------


def test_current_db_path_tracks_connect_and_disconnect(tmp_path):
    """``current_db_path`` returns ``None`` initially, the bound path
    after ``connect_db`` and ``None`` again after ``disconnect_db``."""
    from groundmeas.core import db as core_db

    # Defensive cleanup if a previous test left an engine behind.
    core_db._engine = None
    core_db._engine_path = None

    target = str(tmp_path / "track.db")
    assert core_db.current_db_path() is None
    core_db.connect_db(target)
    try:
        assert core_db.current_db_path() == target
    finally:
        core_db.disconnect_db()
    assert core_db.current_db_path() is None


# ---------------------------------------------------------------------------
# 7) Repo hygiene
# ---------------------------------------------------------------------------


REPO_HYGIENE_PATHS = (
    "feature.txt",
    "dummy.xml",
    "tmp_test.db",
    "test_write_check.tmp",
    "groundmeas.db",
    "groundmeas.db-journal",
    "Users",
    "Python=3.14",
    "src/test_marker.tmp",
)


def _git_tracked_artefacts():
    """Return the subset of REPO_HYGIENE_PATHS that ``git ls-files`` reports
    as tracked, or ``None`` if git is not available."""
    import subprocess

    repo_root = Path(__file__).resolve().parents[1]
    if not (repo_root / ".git").exists():
        return None
    try:
        tracked = subprocess.check_output(["git", "ls-files"], cwd=repo_root, text=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    tracked_set = set(tracked.splitlines())
    return [p for p in REPO_HYGIENE_PATHS if p in tracked_set]


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / ".git").exists(),
    reason="only meaningful in a git checkout",
)
def test_gitignore_lists_runtime_artefact_patterns():
    """``.gitignore`` must enumerate all known runtime-artefact patterns
    so that *future* clones cannot pick them up. This is the half of the
    repo-hygiene contract that is fully under the maintainer's control —
    the complementary ``git rm --cached`` step is covered (xfail-tagged)
    in :func:`test_no_runtime_artefacts_tracked`.
    """
    gi_path = Path(__file__).resolve().parents[1] / ".gitignore"
    gi = gi_path.read_text(encoding="utf-8")
    missing = [p for p in REPO_HYGIENE_PATHS if p not in gi]
    assert not missing, f".gitignore is missing patterns: {missing}"


@pytest.mark.xfail(
    _git_tracked_artefacts() not in (None, []),
    reason=(
        "Pass-7 audit forcing-function: runtime artefacts are still tracked "
        "by git. Run `git rm --cached -r` on the entries reported by "
        "`_git_tracked_artefacts()` to clear them; this test will turn green "
        "automatically once the cleanup commit lands."
    ),
    strict=False,
)
@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / ".git").exists(),
    reason="only meaningful in a git checkout",
)
def test_no_runtime_artefacts_tracked():
    """Audit pass 6/7 keeps flagging the same scratch files at the repo
    root. The ``.gitignore`` was extended in 1.5.2; this test asserts the
    files are no longer *tracked* by git.

    The test is tagged ``xfail(strict=False)`` because the in-tree
    cleanup requires a ``git rm --cached`` step that the audit-run
    sandbox cannot perform — see ``test_gitignore_lists_runtime_artefact_patterns``
    for the half of the contract that is sandbox-friendly. Once the
    maintainer commits the cleanup, the test starts passing on its own.
    """
    bad = _git_tracked_artefacts()
    if bad is None:
        pytest.skip("git not available")
    assert not bad, f"runtime artefacts tracked by git: {bad}"
