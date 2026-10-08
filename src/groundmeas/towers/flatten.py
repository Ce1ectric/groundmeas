r"""
groundmeas.towers.flatten
=========================

Copy a nested measurement delivery into the flat measurement folder.

Measurement contractors often deliver one folder per line and tower::

    <delivery>/<line>/<tower folder>/ZE_....xml
                                    /UT_....txt
                                    /Map_....png

The tower evaluation reads a *flat* folder in which the file names carry line
and tower (``path_measurements`` in the campaign configuration). The
canonical line and tower are taken from the *folder names*, not from the file
names, because delivered file names contain typos now and then
(``UT_LH_01-0815_5.txt`` instead of ``UT_LH-01-0815_5.txt``, a touch-voltage
report saved as ``ZE_...txt``). Every file is copied as::

    ZE_<line>_<tower>.xml                COMPANO fall-of-potential export
    ZE_<line>_<tower>_spez.Erdw..xml     COMPANO soil-resistivity export
    UT_<line>_<tower>.txt                HGT1 touch-voltage report
    UT_<line>_<tower>-<neighbour>.txt    HGT1 report of a neighbouring tower
    Map_<line*>_<tower>.<ext>            map for the protocol (*see map_strip)

Photos, PDFs and spreadsheets are not copied. The originals stay untouched; a
CSV report (source, target, renamed, note) documents the mapping. Used by
``gm-cli towers flatten`` (dry run unless ``--apply`` is given).
"""

from __future__ import annotations

import csv
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Sequence

__all__ = [
    "DEFAULT_LINE_PATTERN",
    "DEFAULT_TOWER_PATTERN",
    "apply_flatten",
    "plan_flatten",
]

logger = logging.getLogger(__name__)

DEFAULT_LINE_PATTERN = r"(LH[-_]\d+[-_][0-9A-Z]+)"
"""Regular expression with one group matching the line folder (e.g. ``LH-01-0815``)."""

DEFAULT_TOWER_PATTERN = r"^Mast\s+(\S+)"
"""Regular expression with one group matching the tower folder (e.g. ``Mast 015``)."""

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def _normalize_tower(tower: str) -> str:
    """Drop leading zeros and upper-case the suffix (``008n`` -> ``8N``)."""
    match = re.match(r"^0*(\d+)(.*)$", tower)
    return (match.group(1) + match.group(2)).upper() if match else tower.upper()


def _line_from_path(path: Path, line_re: re.Pattern[str]) -> Optional[str]:
    """Return the line identifier of the closest parent folder that matches."""
    for part in reversed(path.parts[:-1]):
        match = line_re.match(part)
        if match:
            return match.group(1).upper().replace("_", "-")
    return None


def _is_hgt1_report(path: Path) -> bool:
    """Tell an HGT1 StepTouch report from other text files."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return "StepTouch" in handle.read(400)
    except OSError:
        return False


def plan_flatten(
    src_root: Path,
    *,
    only: Optional[Sequence[str]] = None,
    line_pattern: str = DEFAULT_LINE_PATTERN,
    tower_pattern: str = DEFAULT_TOWER_PATTERN,
    map_strip: str = "LH-",
) -> List[Dict[str, str]]:
    """Plan the copy operations for a nested delivery (nothing is copied).

    Parameters
    ----------
    src_root : pathlib.Path
        Root folder of the nested delivery.
    only : sequence of str, optional
        Restrict to these tower folders (paths relative to ``src_root``).
    line_pattern, tower_pattern : str
        Regular expressions (case-insensitive) with one group for the line
        and the tower folder.
    map_strip : str, optional
        Prefix removed from the line in map file names (``""`` keeps it).

    Returns
    -------
    list of dict
        One row per relevant file with the keys ``src``, ``dst`` (empty for
        ignored files), ``renamed`` (``"yes"``/``"no"``) and ``reason``
        (contains ``CONFLICT`` if two files map to the same target).
    """
    line_re = re.compile(line_pattern, re.IGNORECASE)
    tower_re = re.compile(tower_pattern, re.IGNORECASE)
    rows: List[Dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(src_root):
        dirnames.sort()
        folder = Path(dirpath)
        tower_match = tower_re.match(folder.name)
        if not tower_match:
            continue
        rel = folder.relative_to(src_root).as_posix()
        if only and not any(rel.endswith(o) or rel == o for o in only):
            continue
        line = _line_from_path(folder / "x", line_re)
        tower = _normalize_tower(tower_match.group(1))
        if line is None:
            logger.warning("No line identifier in path: %s", rel)
            continue
        short = (
            line[len(map_strip) :] if map_strip and line.startswith(map_strip) else line
        )
        for filename in sorted(filenames):
            source = folder / filename
            low = filename.lower()
            stem, ext = os.path.splitext(filename)
            target, reason = None, ""
            if ext.lower() == ".xml" and low.startswith("ze"):
                if "spez" in low or "sepz" in low:
                    target = f"ZE_{line}_{tower}_spez.Erdw..xml"
                else:
                    target = f"ZE_{line}_{tower}.xml"
            elif ext.lower() == ".txt" and low.startswith(("ut", "ze")):
                if not _is_hgt1_report(source):
                    reason = "not an HGT1 report, ignored"
                else:
                    tail = stem.split("_")[-1]
                    if "-" in tail and _normalize_tower(tail.split("-", 1)[0]) == tower:
                        target = f"UT_{line}_{tower}-{tail.split('-', 1)[1]}.txt"
                    else:
                        target = f"UT_{line}_{tower}.txt"
                    if low.startswith("ze"):
                        reason = "HGT1 report was named ZE_*.txt"
            elif ext.lower() in IMAGE_EXTENSIONS and low.startswith("map"):
                target = f"Map_{short}_{tower}{ext}"
            if target is None:
                if reason:
                    rows.append(
                        {"src": str(source), "dst": "", "renamed": "", "reason": reason}
                    )
                continue
            renamed = target != filename
            if renamed and not reason:
                reason = "file name adapted to the folder (line/tower)"
            rows.append(
                {
                    "src": str(source),
                    "dst": target,
                    "renamed": "yes" if renamed else "no",
                    "reason": reason,
                }
            )
    # name conflicts (two sources for one target)
    seen: Dict[str, str] = {}
    for row in rows:
        if row["dst"]:
            key = row["dst"].casefold()  # case-insensitive file systems
            if key in seen:
                other = Path(seen[key]).relative_to(src_root).as_posix()
                row["reason"] += f" | CONFLICT with {other}"
            seen[key] = row["src"]
    return rows


def apply_flatten(
    rows: Sequence[Dict[str, str]],
    src_root: Path,
    dest_flat: Path,
    *,
    report: Optional[Path] = None,
) -> int:
    """Copy the planned files and optionally append the mapping to a CSV report.

    Parameters
    ----------
    rows : sequence of dict
        Result of :func:`plan_flatten` (must not contain conflicts).
    src_root : pathlib.Path
        Root folder of the delivery (for relative paths in the report).
    dest_flat : pathlib.Path
        Flat measurement folder (created if needed).
    report : pathlib.Path, optional
        CSV file (``;`` separated) to append the mapping to.

    Returns
    -------
    int
        Number of copied files.

    Raises
    ------
    ValueError
        If the plan contains name conflicts.
    """
    if any("CONFLICT" in row["reason"] for row in rows):
        raise ValueError("the plan contains name conflicts; nothing was copied")
    dest_flat.mkdir(parents=True, exist_ok=True)
    copied = 0
    for row in rows:
        if row["dst"]:
            shutil.copy2(row["src"], dest_flat / row["dst"])
            copied += 1
    if report is not None:
        exists = report.exists()
        with open(report, "a", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter=";")
            if not exists:
                writer.writerow(["source", "target", "renamed", "note"])
            for row in rows:
                rel = Path(row["src"]).relative_to(src_root).as_posix()
                writer.writerow([rel, row["dst"], row["renamed"], row["reason"]])
    return copied
