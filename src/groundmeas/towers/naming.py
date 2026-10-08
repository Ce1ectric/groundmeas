"""Line and tower identifiers and the measurement file naming scheme.

Measurement files are matched to towers by their file names, e.g.
``ZE_LX-01_8.xml`` (fall-of-potential export) and ``UT_LX-01_8.txt``
(touch-voltage report) both belong to tower ``8`` of line ``LX-01``. The
helpers in this module make that matching robust against the usual
variations found in real deliveries:

* leading zeros and letter case of tower numbers (``008n`` equals ``8N``),
* Unicode normalisation of file names (macOS may report decomposed umlauts),
* letter case of file extensions (``.XML`` equals ``.xml``).

They also turn identifiers into file names that are valid on Windows, macOS
and Linux (`safe_filename`).
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Final

__all__ = [
    "FILE_NAME_STRUCTURES",
    "extract_line_and_tower",
    "has_extension",
    "is_soil_resistivity_file",
    "normalize_text",
    "normalize_tower_id",
    "safe_filename",
    "tower_number",
    "tower_sort_key",
]

FILE_NAME_STRUCTURES: Final[tuple[str, ...]] = (
    "PREFIX_LINENUMBER_TOWER",
    "LINENUMBER_TOWER",
    "TOWER_LINENUMBER",
)
"""Supported layouts of the measurement file names (``_`` separates the parts)."""

_TOWER_RE = re.compile(r"^0*(\d+)(.*)$")
_DIGITS_RE = re.compile(r"\d+")
# Characters that are not allowed in Windows file names (plus control characters).
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def normalize_text(value: object) -> str:
    """Return ``value`` as a stripped string in Unicode normalisation form NFC.

    Parameters
    ----------
    value : object
        Any value; ``None`` becomes an empty string.

    Returns
    -------
    str
        The normalised text. NFC makes names typed on Windows/Linux compare
        equal to names read from macOS file systems, which may use the
        decomposed form (NFD) for characters such as ``ö``.
    """
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip()


def normalize_tower_id(tower: object) -> str:
    """Normalise a tower identifier for comparisons.

    Leading zeros of the numeric part are removed, a trailing ``.0`` (tower
    numbers read from Excel as floats) is dropped and letters are upper-cased.

    Parameters
    ----------
    tower : object
        Tower identifier such as ``"008"``, ``"28n"``, ``8`` or ``8.0``.

    Returns
    -------
    str
        Canonical form, e.g. ``"8"`` or ``"28N"``.

    Examples
    --------
    >>> normalize_tower_id("008n")
    '8N'
    >>> normalize_tower_id(12.0)
    '12'
    """
    text = normalize_text(tower)
    if text.endswith(".0"):
        text = text[:-2]
    match = _TOWER_RE.match(text)
    return (match.group(1) + match.group(2)).upper() if match else text.upper()


def tower_number(tower: object) -> int | None:
    """Return the numeric part of a tower identifier.

    Parameters
    ----------
    tower : object
        Tower identifier such as ``"28N"``, ``"08"`` or ``"2M"``.

    Returns
    -------
    int or None
        The first group of digits (``28``, ``8``, ``2``) or ``None`` if the
        identifier contains no digit.
    """
    match = _DIGITS_RE.search(str(tower))
    return int(match.group()) if match else None


def tower_sort_key(tower: object) -> tuple[int, str]:
    """Sort key that orders tower identifiers numerically.

    Parameters
    ----------
    tower : object
        Tower identifier.

    Returns
    -------
    tuple of (int, str)
        ``(number, suffix)``; identifiers without a leading number are sorted
        after all numbered towers.
    """
    match = _TOWER_RE.match(str(tower))
    return (int(match.group(1)), match.group(2)) if match else (10**9, str(tower))


def extract_line_and_tower(
    filename: str, structure: str
) -> tuple[str | None, str | None]:
    """Extract the line and tower identifier from a measurement file name.

    Parameters
    ----------
    filename : str
        File name (not a path), e.g. ``"ZE_LX-01_8.xml"``.
    structure : str
        One of `FILE_NAME_STRUCTURES`:

        * ``"PREFIX_LINENUMBER_TOWER"`` - ``ZE_<line>_<tower>.xml``
        * ``"LINENUMBER_TOWER"`` - ``<line>_<tower>.xml``
        * ``"TOWER_LINENUMBER"`` - ``<tower>_<line>.xml``

    Returns
    -------
    tuple of (str or None, str or None)
        ``(line, tower)``, or ``(None, None)`` if the name does not follow the
        structure. Line identifiers must therefore not contain ``_``.

    Examples
    --------
    >>> extract_line_and_tower("ZE_LX-01_8.xml", "PREFIX_LINENUMBER_TOWER")
    ('LX-01', '8')
    """
    root, _extension = os.path.splitext(unicodedata.normalize("NFC", filename))
    parts = root.split("_")
    if structure == "LINENUMBER_TOWER":
        if len(parts) == 2:
            return parts[0], parts[1]
    elif structure == "TOWER_LINENUMBER":
        if len(parts) == 2:
            return parts[1], parts[0]
    elif structure == "PREFIX_LINENUMBER_TOWER" and len(parts) == 3:
        return parts[1], parts[2]
    return None, None


def has_extension(filename: str, *extensions: str) -> bool:
    """Check the file extension case-insensitively.

    Parameters
    ----------
    filename : str
        File name or path.
    *extensions : str
        Accepted extensions including the dot, e.g. ``".xml"``.

    Returns
    -------
    bool
        ``True`` if the extension matches one of ``extensions``.
    """
    suffix = os.path.splitext(filename)[1].lower()
    return suffix in {ext.lower() for ext in extensions}


def is_soil_resistivity_file(filename: str) -> bool:
    """Return ``True`` for COMPANO soil-resistivity exports (``*_spez*.xml``).

    Parameters
    ----------
    filename : str
        File name.

    Returns
    -------
    bool
        Whether the file is a Schlumberger soil-resistivity measurement.
    """
    return has_extension(filename, ".xml") and "spez" in filename.lower()


def safe_filename(name: str, replacement: str = "_") -> str:
    r"""Make ``name`` usable as a file name on Windows, macOS and Linux.

    Characters that Windows forbids (``<>:"/\|?*`` and control characters)
    are replaced, trailing dots and blanks are removed and reserved device
    names (``CON``, ``NUL``, ...) are prefixed. Ordinary identifiers such as
    ``LX-01_8`` are returned unchanged.

    Parameters
    ----------
    name : str
        Proposed file name without directory.
    replacement : str, optional
        Replacement for invalid characters, by default ``"_"``.

    Returns
    -------
    str
        A file name that can be created on all three operating systems.
    """
    cleaned = _INVALID_FILENAME_CHARS.sub(replacement, normalize_text(name)).rstrip(
        " ."
    )
    if not cleaned:
        cleaned = replacement
    if cleaned.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        cleaned = replacement + cleaned
    return cleaned
