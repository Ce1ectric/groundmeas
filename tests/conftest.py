"""
Pytest configuration for the groundmeas test suite.

Adds an auto-use fixture that disposes of any database engine left behind
by the previous test.  Pre-1.5.2 the module-level ``_engine`` in
``groundmeas.core.db`` was silently replaced on a second ``connect_db``
call, which masked test-ordering bugs.  The post-1.5.2 guard
(`audit-report-changelogs-2026-05-12-pass4`) now refuses a double connect,
so tests that share a process need an explicit reset between cases.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

DATA = Path(__file__).parent / "data"
"""Synthetic instrument exports (see ``tests/data/README.md``)."""


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers of the tower tests."""
    config.addinivalue_line(
        "markers",
        "pdf: renders a PDF with Playwright/Chromium (skipped if no browser is installed)",
    )


@pytest.fixture(scope="session")
def data_dir() -> Path:
    """Folder with the synthetic instrument exports."""
    return DATA


@pytest.fixture(scope="session")
def compano_xml() -> Path:
    """Synthetic OMICRON COMPANO 100 export with a fall-of-potential test."""
    return DATA / "compano_fall_of_potential.xml"


@pytest.fixture(scope="session")
def hgt1_txt() -> Path:
    """Synthetic OMICRON HGT1 StepTouch report (CRLF line endings)."""
    return DATA / "hgt1_step_touch_report.txt"


@pytest.fixture(autouse=True)
def _reset_groundmeas_db_engine():
    """Dispose of the global SQLAlchemy engine between tests."""
    from groundmeas.core import db as _gdb

    # Pre-test: clear any leftover engine without raising.
    if _gdb._engine is not None:
        try:
            _gdb.disconnect_db()
        except Exception:  # pragma: no cover - defensive
            _gdb._engine = None

    yield

    # Post-test: clean up whatever the test connected.
    if _gdb._engine is not None:
        try:
            _gdb.disconnect_db()
        except Exception:  # pragma: no cover - defensive
            _gdb._engine = None


# --------------------------------------------------------------------------- towers
@pytest.fixture(autouse=True)
def _isolate_tower_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never pick up a tower-campaign configuration from the environment."""
    from groundmeas.towers.config import CONFIG_ENV_VAR, LEGACY_CONFIG_ENV_VAR

    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
    monkeypatch.delenv(LEGACY_CONFIG_ENV_VAR, raising=False)


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    """Undo the console logging set up by CLI tests (keeps ``caplog`` working)."""
    package_logger = logging.getLogger("groundmeas")
    state = (package_logger.handlers[:], package_logger.level, package_logger.propagate)
    yield
    package_logger.handlers[:], package_logger.level, package_logger.propagate = state


@pytest.fixture(scope="session")
def demo_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Tower demo campaign generated once per session (do not modify)."""
    from groundmeas.towers.demo import write_demo_campaign

    root = tmp_path_factory.mktemp("demo_template") / "campaign"
    write_demo_campaign(root, language="en")
    return root


@pytest.fixture
def demo_campaign(demo_template: Path, tmp_path: Path) -> Path:
    """Writable copy of the tower demo campaign; returns the path of its config."""
    target = tmp_path / "campaign"
    shutil.copytree(demo_template, target)
    return target / "config.json"


@pytest.fixture(scope="session")
def evaluated_demo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """English tower demo campaign after the calc step (session scoped, read only)."""
    from groundmeas.towers.campaign import calculate_summary
    from groundmeas.towers.demo import write_demo_campaign

    root = tmp_path_factory.mktemp("evaluated") / "campaign"
    config = write_demo_campaign(root, language="en")
    calculate_summary(config_path=config)
    return config


@pytest.fixture(scope="session")
def evaluated_demo_de(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """German tower demo campaign after the calc step (session scoped, read only)."""
    from groundmeas.towers.campaign import calculate_summary
    from groundmeas.towers.demo import write_demo_campaign

    root = tmp_path_factory.mktemp("evaluated_de") / "campaign"
    config = write_demo_campaign(root, language="de")
    calculate_summary(config_path=config)
    return config


@pytest.fixture
def use_config(monkeypatch: pytest.MonkeyPatch) -> Callable[[Path], Path]:
    """Activate a tower configuration like the CLI option ``--config`` does."""
    from groundmeas.towers.config import CONFIG_ENV_VAR

    def _use(path: Path) -> Path:
        monkeypatch.setenv(CONFIG_ENV_VAR, str(path))
        return path

    return _use


class _Delete:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "DELETE"


_DELETE = _Delete()


@pytest.fixture(scope="session")
def DELETE() -> _Delete:
    """Sentinel for `edit_config` to remove a key."""
    return _DELETE


@pytest.fixture
def edit_config() -> Callable[..., Path]:
    """Modify keys of a configuration file in place (``__`` separates sections)."""

    def _edit(path: Path, **changes: Any) -> Path:
        data = json.loads(path.read_text(encoding="utf-8"))
        for key, value in changes.items():
            target = data
            *parents, last = key.split("__")
            for parent in parents:
                target = target.setdefault(parent, {})
            if value is _DELETE:
                target.pop(last, None)
            else:
                target[last] = value
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return path

    return _edit


@pytest.fixture(scope="session")
def chromium_available(tmp_path_factory: pytest.TempPathFactory) -> bool:
    """Whether a Chromium-based browser can print PDFs on this machine."""
    from groundmeas.towers.pdf import generate_pdf

    folder = tmp_path_factory.mktemp("pdf_probe")
    html = folder / "probe.html"
    html.write_text("<html><body>probe</body></html>", encoding="utf-8")
    try:
        generate_pdf(html, folder / "probe.pdf")
    except Exception:
        return False
    return (folder / "probe.pdf").exists()
