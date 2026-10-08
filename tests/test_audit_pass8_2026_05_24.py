"""
Regression tests for the Audit pass 8 fix bundle (2026-05-24).

This pass closes three remaining findings from the pass 6 / 7 backlog
that the previous implementation run explicitly deferred:

1. Tutorial pages (``02_quickstart.md``, ``10_tutorial_intro.md``,
   ``11_create_measurements.md``, ``14_import_export.md``) must use the
   canonical top-level package (``import groundmeas as gm``) instead of
   the legacy shim paths (``from groundmeas.db import ...``).
2. An ADR directory is opened in ``docs/adr/`` with ADR-0001 —
   Compatibility-shim deprecation strategy — as the first record.
3. ``tests/test_repo_hygiene.py`` (this file's repo-hygiene helpers) is
   the forcing function for the recurring repo-root-junk findings;
   the dedicated module covers the file-set in detail.

The intent is the same as for previous audit-passes: small, deterministic
regression tests that fail loudly if the corresponding finding regresses.
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    """Return the repository root (directory containing ``pyproject.toml``)."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate repository root (no pyproject.toml found).")


# ---------------------------------------------------------------------------
# 1) Tutorial pages use canonical imports
# ---------------------------------------------------------------------------


CANONICAL_TUTORIALS = (
    "docs/02_quickstart.md",
    "docs/10_tutorial_intro.md",
    "docs/11_create_measurements.md",
    "docs/14_import_export.md",
)

SHIM_IMPORT_PREFIXES = (
    "from groundmeas.db ",
    "from groundmeas.analytics ",
    "from groundmeas.models ",
    "from groundmeas.plots ",
    "from groundmeas.export ",
    "from groundmeas.vision_import ",
    "from groundmeas.cli ",
)


@pytest.mark.parametrize("rel_path", CANONICAL_TUTORIALS)
def test_tutorial_uses_canonical_imports(rel_path: str) -> None:
    """The named tutorial page must not import via any shim submodule.

    The pass-6/7 reports flagged four tutorial pages that still taught
    the deprecated ``from groundmeas.db import ...`` style. Pass 8
    migrated them to ``import groundmeas as gm``. This test guards the
    invariant.
    """
    doc = _repo_root() / rel_path
    assert doc.is_file(), f"Tutorial page missing: {rel_path}"
    text = doc.read_text(encoding="utf-8")
    # Strip fenced code blocks so we can scan import lines specifically.
    offenders: list[str] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        for prefix in SHIM_IMPORT_PREFIXES:
            if stripped.startswith(prefix):
                offenders.append(f"{rel_path}:{lineno}: {stripped}")
    assert not offenders, (
        "Tutorial pages must use canonical imports "
        "(`import groundmeas as gm`); shim imports found:\n  "
        + "\n  ".join(offenders)
    )


def test_tutorial_mentions_canonical_import_idiom() -> None:
    """At least one tutorial page must show the recommended canonical idiom."""
    quickstart = _repo_root() / "docs/02_quickstart.md"
    text = quickstart.read_text(encoding="utf-8")
    assert "import groundmeas as gm" in text, (
        "docs/02_quickstart.md must showcase `import groundmeas as gm` "
        "as the recommended Python import style."
    )


# ---------------------------------------------------------------------------
# 2) ADR directory and ADR-0001 are present
# ---------------------------------------------------------------------------


def test_adr_directory_exists() -> None:
    """The ADR directory must exist and contain a README index."""
    adr_dir = _repo_root() / "docs" / "adr"
    assert adr_dir.is_dir(), "docs/adr/ directory is missing"
    assert (adr_dir / "README.md").is_file(), "docs/adr/README.md is missing"


def test_adr_0001_present_and_substantive() -> None:
    """ADR-0001 must exist and contain the canonical decision sections."""
    adr = _repo_root() / "docs/adr/0001-compatibility-shim-deprecation-strategy.md"
    assert adr.is_file(), "ADR-0001 file is missing"
    text = adr.read_text(encoding="utf-8")
    for required_heading in ("## Context", "## Decision", "## Consequences"):
        assert required_heading in text, (
            f"ADR-0001 must contain a '{required_heading}' section; "
            "the short-form ADR template is mandatory."
        )
    # All seven shim names should be enumerated.
    for shim in (
        "groundmeas.db",
        "groundmeas.analytics",
        "groundmeas.models",
        "groundmeas.plots",
        "groundmeas.export",
        "groundmeas.vision_import",
        "groundmeas.cli",
    ):
        assert shim in text, f"ADR-0001 must enumerate the shim '{shim}'."


def test_mkdocs_nav_lists_adr_section() -> None:
    """The mkdocs nav must surface the ADR section so it renders in docs."""
    yml = _repo_root() / "mkdocs.yml"
    text = yml.read_text(encoding="utf-8")
    assert "ADRs:" in text, "mkdocs.yml nav must contain an 'ADRs:' section"
    assert "0001" in text, (
        "mkdocs.yml nav must list ADR-0001 explicitly so the rendered docs "
        "do not silently hide it."
    )


# ---------------------------------------------------------------------------
# 3) Pass-7 docstring polish: the CHANGELOG must record this pass
# ---------------------------------------------------------------------------


def test_changelog_has_pass8_block() -> None:
    """The CHANGELOG must carry a 'Audit pass 8' implementation block."""
    changelog = _repo_root() / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    # Tolerate the exact heading variant a maintainer might choose.
    assert "Audit pass 8" in text or "audit pass 8" in text, (
        "CHANGELOG.md must record the 2026-05-24 pass-8 implementation."
    )
    assert "2026-05-24" in text, (
        "CHANGELOG.md pass-8 block must be dated 2026-05-24."
    )
