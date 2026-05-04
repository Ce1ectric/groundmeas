# tests/test_check_changelog.py
"""
Tests for the pure helpers of ``scripts/check_changelog.py``.

The script's git-glue (``_git_changed_files``, ``_git_diff``) is not
exercised; the helpers operate on already-produced strings and lists,
which is what we cover here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts" / "check_changelog.py"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "groundmeas_check_changelog_under_test", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check = _load_script()


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------


_CHANGELOG_AFTER = """\
# Changelog

## [Unreleased]

### Added

- New shiny feature.

---

## [1.4.3] — 2026-04-22

### Fixed

- A previous bugfix.

---

[Unreleased]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.3...HEAD
[1.4.3]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.1...v1.4.3
"""


_DIFF_TOUCHES_UNRELEASED = """\
diff --git a/CHANGELOG.md b/CHANGELOG.md
index abc..def 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -3,6 +3,10 @@
 ## [Unreleased]

 ### Added
+
+- New shiny feature.

 ---

"""


_DIFF_TOUCHES_OTHER_VERSION = """\
diff --git a/CHANGELOG.md b/CHANGELOG.md
index abc..def 100644
--- a/CHANGELOG.md
+++ b/CHANGELOG.md
@@ -13,3 +13,3 @@
-## [1.4.3] — 2026-04-21
+## [1.4.3] — 2026-04-22
"""


_DIFF_OTHER_FILE = """\
diff --git a/src/groundmeas/foo.py b/src/groundmeas/foo.py
index 1..2 100644
--- a/src/groundmeas/foo.py
+++ b/src/groundmeas/foo.py
@@ -1,1 +1,1 @@
-x = 1
+x = 2
"""


# ---------------------------------------------------------------------------
# changes_touch_src
# ---------------------------------------------------------------------------


def test_changes_touch_src_detects_prefix() -> None:
    assert check.changes_touch_src(["src/groundmeas/db.py", "README.md"])
    assert check.changes_touch_src(["src/groundmeas/services/foo.py"])


def test_changes_touch_src_negative() -> None:
    assert not check.changes_touch_src(["docs/foo.md", "tests/test_x.py"])
    assert not check.changes_touch_src([])


def test_changes_touch_src_custom_prefix() -> None:
    assert check.changes_touch_src(["src/other/foo.py"], src_prefix="src/other/")
    assert not check.changes_touch_src(
        ["src/groundmeas/foo.py"], src_prefix="src/other/"
    )


# ---------------------------------------------------------------------------
# find_unreleased_line_range
# ---------------------------------------------------------------------------


def test_find_unreleased_line_range_matches_block() -> None:
    start, end = check.find_unreleased_line_range(_CHANGELOG_AFTER)
    lines = _CHANGELOG_AFTER.splitlines()
    # Lines are 1-based; the header itself is excluded from the range,
    # the next version header is the exclusive end.
    assert lines[start - 1].strip() == "" or lines[start - 1].startswith(("###", "-"))
    assert lines[end - 1].strip().startswith("## [1.4.3]")


def test_find_unreleased_line_range_raises_when_missing() -> None:
    with pytest.raises(RuntimeError, match=r"no \[Unreleased\]"):
        check.find_unreleased_line_range("# Changelog\n\n## [1.0.0]\n")


def test_find_unreleased_line_range_no_following_version() -> None:
    text = "## [Unreleased]\n\n- foo\n"
    start, end = check.find_unreleased_line_range(text)
    # Without a following version section, end is len(lines)+1.
    assert end == len(text.splitlines()) + 1
    assert start == 2


# ---------------------------------------------------------------------------
# parse_diff_hunks
# ---------------------------------------------------------------------------


def test_parse_diff_hunks_extracts_post_image_ranges() -> None:
    hunks = check.parse_diff_hunks(_DIFF_TOUCHES_UNRELEASED, "CHANGELOG.md")
    assert hunks == [(3, 10)]


def test_parse_diff_hunks_short_form() -> None:
    diff = "+++ b/CHANGELOG.md\n" "@@ -1 +1 @@\n" "-old\n" "+new\n"
    assert check.parse_diff_hunks(diff, "CHANGELOG.md") == [(1, 1)]


def test_parse_diff_hunks_skips_other_files() -> None:
    assert check.parse_diff_hunks(_DIFF_OTHER_FILE, "CHANGELOG.md") == []


def test_parse_diff_hunks_handles_combined_diff() -> None:
    combined = _DIFF_OTHER_FILE + _DIFF_TOUCHES_UNRELEASED
    assert check.parse_diff_hunks(combined, "CHANGELOG.md") == [(3, 10)]


# ---------------------------------------------------------------------------
# diff_touches_unreleased
# ---------------------------------------------------------------------------


def test_diff_touches_unreleased_positive() -> None:
    assert check.diff_touches_unreleased(_DIFF_TOUCHES_UNRELEASED, _CHANGELOG_AFTER)


def test_diff_touches_unreleased_negative_other_version() -> None:
    assert not check.diff_touches_unreleased(
        _DIFF_TOUCHES_OTHER_VERSION, _CHANGELOG_AFTER
    )


def test_diff_touches_unreleased_negative_other_file() -> None:
    assert not check.diff_touches_unreleased(_DIFF_OTHER_FILE, _CHANGELOG_AFTER)


def test_diff_touches_unreleased_empty_diff() -> None:
    assert not check.diff_touches_unreleased("", _CHANGELOG_AFTER)
