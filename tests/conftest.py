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

from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"
"""Synthetic instrument exports (see ``tests/data/README.md``)."""


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
