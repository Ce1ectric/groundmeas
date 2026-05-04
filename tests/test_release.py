# tests/test_release.py
"""
Tests for the changelog handling helpers used by the release script.

The helpers live in ``scripts/_changelog.py`` (stdlib-only); the
interactive Typer command in ``scripts/release.py`` is not exercised
here. No git or filesystem side effects outside of the temporary test
directory occur.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
_CHANGELOG_HELPER_PATH = _REPO_ROOT / "scripts" / "_changelog.py"


def _load_helpers():
    """Import ``scripts/_changelog.py`` as a standalone module."""
    spec = importlib.util.spec_from_file_location(
        "groundmeas_changelog_under_test", _CHANGELOG_HELPER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


changelog = _load_helpers()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_BASE_CHANGELOG = """\
# Changelog

All notable changes to `groundmeas` are documented in this file.

---

## [Unreleased]

### Added

- Some unreleased feature bullet.

### Internal

- Some internal note.

---

## [1.4.3] — 2026-04-22

### Fixed

- A previous bugfix.

---

[Unreleased]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.1...v1.4.3
"""


_EMPTY_CHANGELOG = """\
# Changelog

---

## [Unreleased]

### Added

### Internal

---

## [1.4.3] — 2026-04-22

### Fixed

- A previous bugfix.

---

[Unreleased]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.1...v1.4.3
"""


@pytest.fixture
def changelog_path(tmp_path: Path) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_BASE_CHANGELOG, encoding="utf-8")
    return path


@pytest.fixture
def empty_changelog_path(tmp_path: Path) -> Path:
    path = tmp_path / "CHANGELOG.md"
    path.write_text(_EMPTY_CHANGELOG, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# _split_unreleased / _is_empty_unreleased
# ---------------------------------------------------------------------------


def test_split_unreleased_extracts_body() -> None:
    _, _, body = changelog._split_unreleased(_BASE_CHANGELOG)
    assert "Some unreleased feature bullet." in body
    assert "Some internal note." in body
    # Neither the previous version's content nor its header may leak in.
    assert "A previous bugfix." not in body
    assert "## [1.4.3]" not in body


def test_split_unreleased_raises_when_section_missing() -> None:
    with pytest.raises(RuntimeError, match=r"no \[Unreleased\]"):
        changelog._split_unreleased("# Changelog\n\n## [1.0.0] — 2025-01-01\n")


def test_split_unreleased_raises_when_no_following_version() -> None:
    bad = "# Changelog\n\n## [Unreleased]\n\n- foo\n"
    with pytest.raises(RuntimeError, match=r"no '## \[X.Y.Z\]'"):
        changelog._split_unreleased(bad)


def test_is_empty_unreleased_detects_bullets() -> None:
    assert changelog._is_empty_unreleased("\n### Added\n\n### Internal\n\n---\n")
    assert changelog._is_empty_unreleased("")
    assert not changelog._is_empty_unreleased("\n### Added\n\n- a bullet\n")
    # Indented bullets still count as content.
    assert not changelog._is_empty_unreleased("  - nested bullet\n")


# ---------------------------------------------------------------------------
# bump_changelog — happy path
# ---------------------------------------------------------------------------


def test_bump_changelog_moves_unreleased_block(changelog_path: Path) -> None:
    new_text = changelog.bump_changelog(
        changelog_path,
        new_version="1.5.0",
        today=_dt.date(2026, 4, 30),
    )

    # The new version section now carries the previous Unreleased content.
    assert "## [1.5.0] — 2026-04-30" in new_text
    idx_new = new_text.index("## [1.5.0]")
    idx_old = new_text.index("## [1.4.3]")
    assert idx_new < idx_old, "new version must appear before the previous one"

    section_1_5_0 = new_text[idx_new:idx_old]
    assert "Some unreleased feature bullet." in section_1_5_0
    assert "Some internal note." in section_1_5_0

    # A fresh, empty [Unreleased] header sits above the new version.
    idx_unreleased = new_text.index("## [Unreleased]")
    assert idx_unreleased < idx_new
    fresh_block = new_text[idx_unreleased:idx_new]
    assert "- " not in fresh_block, "fresh [Unreleased] must not carry bullets"

    # The persisted file matches the returned content.
    assert changelog_path.read_text(encoding="utf-8") == new_text


def test_bump_changelog_updates_compare_links(changelog_path: Path) -> None:
    new_text = changelog.bump_changelog(
        changelog_path,
        new_version="1.5.0",
        today=_dt.date(2026, 4, 30),
    )

    assert (
        "[Unreleased]: https://github.com/Ce1ectric/groundmeas/" "compare/v1.5.0...HEAD"
    ) in new_text
    assert (
        "[1.5.0]: https://github.com/Ce1ectric/groundmeas/" "compare/v1.4.3...v1.5.0"
    ) in new_text
    # The old Unreleased link must be gone.
    assert "compare/v1.4.3...HEAD" not in new_text
    # The previous compare link is preserved.
    assert "[1.4.3]: https://github.com/Ce1ectric/groundmeas/" in new_text


def test_bump_changelog_explicit_previous_version(changelog_path: Path) -> None:
    new_text = changelog.bump_changelog(
        changelog_path,
        new_version="2.0.0",
        previous_version="1.4.3",
        today=_dt.date(2026, 5, 1),
    )
    assert (
        "[2.0.0]: https://github.com/Ce1ectric/groundmeas/" "compare/v1.4.3...v2.0.0"
    ) in new_text


# ---------------------------------------------------------------------------
# bump_changelog — empty handling
# ---------------------------------------------------------------------------


def test_bump_changelog_rejects_empty_unreleased(
    empty_changelog_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match=r"empty \[Unreleased\]"):
        changelog.bump_changelog(
            empty_changelog_path,
            new_version="1.5.0",
            today=_dt.date(2026, 4, 30),
        )
    # The file must be unchanged on failure.
    assert empty_changelog_path.read_text(encoding="utf-8") == _EMPTY_CHANGELOG


def test_bump_changelog_allow_empty_creates_dated_section(
    empty_changelog_path: Path,
) -> None:
    new_text = changelog.bump_changelog(
        empty_changelog_path,
        new_version="1.5.0",
        today=_dt.date(2026, 4, 30),
        allow_empty=True,
    )
    assert "## [1.5.0] — 2026-04-30" in new_text
    # No bullets carried over (the original Unreleased had none).
    idx_new = new_text.index("## [1.5.0]")
    idx_old = new_text.index("## [1.4.3]")
    section_1_5_0 = new_text[idx_new:idx_old]
    assert "- " not in section_1_5_0


# ---------------------------------------------------------------------------
# bump_changelog — idempotency / structural invariants
# ---------------------------------------------------------------------------


def test_bump_changelog_second_call_raises_on_empty_block(
    changelog_path: Path,
) -> None:
    """
    After a first bump, [Unreleased] is empty. A second call without
    --allow-empty must therefore raise instead of silently re-bumping.
    """
    changelog.bump_changelog(
        changelog_path,
        new_version="1.5.0",
        today=_dt.date(2026, 4, 30),
    )
    with pytest.raises(RuntimeError, match=r"empty \[Unreleased\]"):
        changelog.bump_changelog(
            changelog_path,
            new_version="1.6.0",
            today=_dt.date(2026, 5, 1),
        )


def test_bump_changelog_preserves_blank_line_after_new_header(
    changelog_path: Path,
) -> None:
    """
    Regression: a previous version of the regex used ``\\s*$`` which
    greedily consumed the newline after ``## [Unreleased]``, dropping
    the blank line between the new version header and its first
    ``###`` sub-section. Use ``[ \\t]*$`` instead.
    """
    new_text = changelog.bump_changelog(
        changelog_path,
        new_version="1.5.0",
        today=_dt.date(2026, 4, 30),
    )
    assert "## [1.5.0] — 2026-04-30\n\n### Added" in new_text


def test_bump_changelog_preserves_trailing_text(changelog_path: Path) -> None:
    """
    Lines below the compare-link footer (roadmap / ideas-inbox content)
    must not be touched by the bump.
    """
    extra = "\n## Roadmap\n\nSome trailing roadmap text that must survive.\n"
    changelog_path.write_text(
        changelog_path.read_text(encoding="utf-8") + extra, encoding="utf-8"
    )
    new_text = changelog.bump_changelog(
        changelog_path,
        new_version="1.5.0",
        today=_dt.date(2026, 4, 30),
    )
    assert "Some trailing roadmap text that must survive." in new_text
    assert "## Roadmap" in new_text
