# scripts/check_changelog.py
"""
CI guard that fails when ``src/`` is changed without an entry in
``CHANGELOG.md``'s ``[Unreleased]`` block.

The script is intentionally stdlib-only so it can run in the CI image
before ``poetry install`` is finished and so its decision logic is easy
to unit-test without a real git tree.

Usage
-----

::

    python scripts/check_changelog.py --base origin/main

Returns exit code ``0`` when no ``src/`` change is present, when
``CHANGELOG.md``'s ``[Unreleased]`` block was touched, or when the
``--allow-empty`` flag is supplied. Returns exit code ``1`` otherwise.

The behaviour is split between a glue ``main`` that talks to ``git`` and
a handful of pure helper functions (``changes_touch_src``,
``parse_diff_hunks``, ``find_unreleased_line_range``,
``diff_touches_unreleased``) that operate on already-produced strings
and lists. The helpers are what ``tests/test_check_changelog.py``
exercises.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


_VERSION_HEADER_RE = re.compile(r"^## \[\d+\.\d+\.\d+\]")
_HUNK_HEADER_RE = re.compile(
    r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@"
)


# ---------------------------------------------------------------------------
# Pure helpers — exercised directly by the unit tests
# ---------------------------------------------------------------------------


def changes_touch_src(
    changed_files: Iterable[str],
    src_prefix: str = "src/groundmeas/",
) -> bool:
    """
    Return ``True`` iff any of the given paths is below ``src_prefix``.

    Parameters
    ----------
    changed_files : Iterable[str]
        Paths reported by ``git diff --name-only``, relative to the
        repository root.
    src_prefix : str, default ``"src/groundmeas/"``
        Prefix under which production code lives.
    """
    return any(p.startswith(src_prefix) for p in changed_files)


def find_unreleased_line_range(content: str) -> Tuple[int, int]:
    """
    Return the 1-based line range covered by the ``[Unreleased]`` block.

    Parameters
    ----------
    content : str
        Full text of ``CHANGELOG.md``.

    Returns
    -------
    Tuple[int, int]
        ``(start, end)`` where ``start`` is the first line *after* the
        ``## [Unreleased]`` header and ``end`` is the exclusive boundary
        — the line of the next ``## [X.Y.Z]`` header, or
        ``len(lines) + 1`` if no version header follows.

    Raises
    ------
    RuntimeError
        If no ``## [Unreleased]`` header is present.
    """
    lines = content.splitlines()
    start: Optional[int] = None
    end: Optional[int] = None
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if start is None:
            if stripped == "## [Unreleased]":
                start = i + 1
        else:
            if _VERSION_HEADER_RE.match(stripped):
                end = i
                break
    if start is None:
        raise RuntimeError("CHANGELOG.md has no [Unreleased] header.")
    if end is None:
        end = len(lines) + 1
    return start, end


def parse_diff_hunks(
    diff_text: str,
    target_path: str,
) -> List[Tuple[int, int]]:
    """
    Extract the ``(start, count)`` pairs of hunks that touch ``target_path``.

    The returned tuples describe the *post-image* line numbers (the
    ``+`` side of the diff), so they can be compared directly against
    the line range of the new file.

    Parameters
    ----------
    diff_text : str
        Output of ``git diff <base>... -- <path>``.
    target_path : str
        Path of the file whose hunks should be extracted, relative to
        the repository root.

    Returns
    -------
    List[Tuple[int, int]]
        For each hunk ``(start_line, line_count)`` in the post-image.
    """
    hunks: List[Tuple[int, int]] = []
    in_target = False
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            # ``+++ b/<path>`` or ``+++ <path>`` or ``+++ /dev/null``.
            payload = line[4:].strip()
            in_target = payload.endswith(target_path) or payload.endswith(
                "b/" + target_path
            )
            continue
        if line.startswith("--- "):
            continue
        if not in_target:
            continue
        m = _HUNK_HEADER_RE.match(line)
        if m is not None:
            start = int(m.group("start"))
            count = int(m.group("count")) if m.group("count") else 1
            hunks.append((start, count))
    return hunks


def diff_touches_unreleased(
    diff_text: str,
    new_changelog_content: str,
    changelog_path: str = "CHANGELOG.md",
) -> bool:
    """
    Return ``True`` iff any hunk for ``changelog_path`` in ``diff_text``
    overlaps the ``[Unreleased]`` block of ``new_changelog_content``.

    The new file content is needed to know where the block lives in the
    post-image; the diff alone may not contain enough context.
    """
    block_start, block_end = find_unreleased_line_range(new_changelog_content)
    for start, count in parse_diff_hunks(diff_text, changelog_path):
        hunk_end = start + count  # exclusive
        # ``count == 0`` (pure deletion) hunks anchor at start; treat the
        # single line ``start`` as the touched range.
        if count == 0:
            hunk_end = start + 1
        if hunk_end > block_start and start < block_end:
            return True
    return False


# ---------------------------------------------------------------------------
# Git glue — only used when running as a script
# ---------------------------------------------------------------------------


def _run_git(args: List[str], repo: Path) -> str:
    """Run ``git`` with the given args in ``repo`` and return stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def _git_changed_files(base: str, repo: Path) -> List[str]:
    out = _run_git(["diff", "--name-only", f"{base}...HEAD"], repo)
    return [line for line in out.splitlines() if line]


def _git_diff(base: str, repo: Path, paths: List[str]) -> str:
    return _run_git(["diff", f"{base}...HEAD", "--", *paths], repo)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """
    Argparse-based entry point.

    Returns the process exit code instead of calling ``sys.exit`` so it
    can be exercised from tests.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Fail when src/ changes are not accompanied by an "
            "[Unreleased] entry in CHANGELOG.md."
        )
    )
    parser.add_argument(
        "--base",
        default="origin/main",
        help="Base ref to diff against (default: origin/main).",
    )
    parser.add_argument(
        "--repo",
        default=".",
        help="Path to the repository root (default: current directory).",
    )
    parser.add_argument(
        "--src-prefix",
        default="src/groundmeas/",
        help="Path prefix that identifies production code.",
    )
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to the changelog, relative to the repository root.",
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()

    try:
        changed = _git_changed_files(args.base, repo)
    except subprocess.CalledProcessError as exc:
        print(f"[error] git diff --name-only failed: {exc.stderr}", file=sys.stderr)
        return 2

    if not changes_touch_src(changed, src_prefix=args.src_prefix):
        print(
            f"[ok] No changes under {args.src_prefix!r} — " "skipping changelog check."
        )
        return 0

    if args.changelog not in changed:
        print(
            f"[error] {args.src_prefix!r} was changed but {args.changelog!r} "
            "was not. Add an entry under [Unreleased], or apply the "
            "'skip-changelog' label to the PR.",
            file=sys.stderr,
        )
        return 1

    try:
        diff = _git_diff(args.base, repo, paths=[args.changelog])
    except subprocess.CalledProcessError as exc:
        print(f"[error] git diff failed: {exc.stderr}", file=sys.stderr)
        return 2

    new_content = (repo / args.changelog).read_text(encoding="utf-8")
    if not diff_touches_unreleased(diff, new_content, changelog_path=args.changelog):
        print(
            f"[error] {args.changelog!r} was changed but the [Unreleased] "
            "block was not touched. Add your entry there, or apply the "
            "'skip-changelog' label to the PR.",
            file=sys.stderr,
        )
        return 1

    print(f"[ok] {args.changelog!r} [Unreleased] was updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
