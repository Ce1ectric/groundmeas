# scripts/_changelog.py
"""
Changelog manipulation helpers used by ``scripts/release.py``.

The functions in this module operate purely on text and dates; they have
no dependency on ``typer``, ``rich``, ``poetry``, the working tree or
git, which keeps them straightforward to unit-test.
"""

from __future__ import annotations

import datetime as _dt
import re
from pathlib import Path
from typing import Optional, Tuple


_UNRELEASED_HEADER_RE = re.compile(r"^## \[Unreleased\][ \t]*$", re.MULTILINE)
_VERSION_HEADER_RE = re.compile(r"^## \[\d+\.\d+\.\d+\]", re.MULTILINE)
_COMPARE_LINK_UNRELEASED_RE = re.compile(
    r"^\[Unreleased\]:[ \t]*(?P<repo>https://\S+?)/compare/"
    r"v(?P<prev>\d+\.\d+\.\d+)\.\.\.HEAD[ \t]*$",
    re.MULTILINE,
)


def _split_unreleased(content: str) -> Tuple[int, int, str]:
    """
    Locate the body of the ``[Unreleased]`` block in a Keep-a-Changelog file.

    The body is everything between the ``## [Unreleased]`` header line and
    the next ``## [X.Y.Z]`` version header. Both header lines themselves
    are excluded.

    Parameters
    ----------
    content : str
        Full text of ``CHANGELOG.md``.

    Returns
    -------
    Tuple[int, int, str]
        ``(body_start, body_end, body)`` where ``body_start`` and
        ``body_end`` are character offsets into ``content``.

    Raises
    ------
    RuntimeError
        If no ``[Unreleased]`` section or no following version section
        is found.
    """
    m_unrel = _UNRELEASED_HEADER_RE.search(content)
    if m_unrel is None:
        raise RuntimeError("CHANGELOG.md has no [Unreleased] section.")

    body_start = m_unrel.end()
    m_next = _VERSION_HEADER_RE.search(content, body_start)
    if m_next is None:
        raise RuntimeError(
            "CHANGELOG.md has no '## [X.Y.Z]' section after [Unreleased]."
        )
    body_end = m_next.start()
    return body_start, body_end, content[body_start:body_end]


def _is_empty_unreleased(body: str) -> bool:
    """
    Return ``True`` when the ``[Unreleased]`` body has no bullet entries.

    Empty sub-section headers (``### Added`` etc.) and trailing horizontal
    rules (``---``) do not count as content.
    """
    for line in body.splitlines():
        if line.lstrip().startswith("- "):
            return False
    return True


def _update_compare_links(
    content: str,
    new_version: str,
    previous_version: str,
) -> str:
    """
    Update the compare-link footer for a new release.

    Rewrites the ``[Unreleased]`` link to point at the new tag and inserts
    a fresh ``[new_version]`` line directly below it.

    Parameters
    ----------
    content : str
        Full text of ``CHANGELOG.md``.
    new_version : str
        The version being released.
    previous_version : str
        The previous tag the new version is compared against.

    Returns
    -------
    str
        The updated changelog text.

    Raises
    ------
    RuntimeError
        If no ``[Unreleased]`` compare link is found.
    """
    m = _COMPARE_LINK_UNRELEASED_RE.search(content)
    if m is None:
        raise RuntimeError(
            "CHANGELOG.md has no '[Unreleased]: .../compare/vX.Y.Z...HEAD' link."
        )
    repo = m.group("repo")
    new_unreleased = f"[Unreleased]: {repo}/compare/v{new_version}...HEAD"
    new_version_link = (
        f"[{new_version}]: {repo}/compare/v{previous_version}...v{new_version}"
    )
    return _COMPARE_LINK_UNRELEASED_RE.sub(
        f"{new_unreleased}\n{new_version_link}",
        content,
        count=1,
    )


def bump_changelog(
    changelog_path: Path,
    new_version: str,
    previous_version: Optional[str] = None,
    today: Optional[_dt.date] = None,
    allow_empty: bool = False,
) -> str:
    """
    Move ``[Unreleased]`` into a dated version section in ``CHANGELOG.md``.

    Concretely the function

    1. validates that the ``[Unreleased]`` block has at least one bullet
       entry (override with ``allow_empty=True``);
    2. inserts a fresh empty ``[Unreleased]`` block above the existing
       content and converts the old header into ``## [X.Y.Z] — YYYY-MM-DD``;
    3. rewrites the ``[Unreleased]`` compare link in the footer and adds
       a new ``[X.Y.Z]`` compare link directly below it.

    The function writes the updated content back to ``changelog_path`` and
    also returns it for convenience.

    Parameters
    ----------
    changelog_path : Path
        Path to ``CHANGELOG.md``.
    new_version : str
        The version being released, e.g. ``"1.5.0"``.
    previous_version : Optional[str], default None
        The previous tag. When ``None``, it is read from the existing
        ``[Unreleased]`` compare link.
    today : Optional[datetime.date], default None
        Release date, used in the version header. Defaults to
        ``datetime.date.today()``.
    allow_empty : bool, default False
        When ``True``, an empty ``[Unreleased]`` block is accepted and a
        version section without entries is produced.

    Returns
    -------
    str
        The new full content of ``CHANGELOG.md``.

    Raises
    ------
    RuntimeError
        If the changelog structure is invalid, the ``[Unreleased]`` block
        is empty without ``allow_empty``, or the previous version cannot
        be determined.
    """
    content = changelog_path.read_text(encoding="utf-8")
    release_date = today or _dt.date.today()

    _, _, body = _split_unreleased(content)
    if _is_empty_unreleased(body) and not allow_empty:
        raise RuntimeError(
            "CHANGELOG.md has an empty [Unreleased] block. "
            "Add an entry under [Unreleased], or pass --allow-empty."
        )

    if previous_version is None:
        m = _COMPARE_LINK_UNRELEASED_RE.search(content)
        if m is None:
            raise RuntimeError(
                "Cannot determine previous version: no [Unreleased] compare "
                "link found in CHANGELOG.md."
            )
        previous_version = m.group("prev")

    insertion = (
        "## [Unreleased]\n"
        "\n"
        "---\n"
        "\n"
        f"## [{new_version}] — {release_date.isoformat()}"
    )
    new_content, count = _UNRELEASED_HEADER_RE.subn(insertion, content, count=1)
    if count != 1:
        raise RuntimeError("Failed to rewrite the [Unreleased] header.")

    new_content = _update_compare_links(
        new_content,
        new_version=new_version,
        previous_version=previous_version,
    )

    changelog_path.write_text(new_content, encoding="utf-8")
    return new_content
