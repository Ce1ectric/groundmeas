"""Collect all measurements of a campaign from the measurement folder.

The measurement folder is *flat*: every file name encodes the line and the
tower (see :mod:`groundmeas.towers.naming`):

    ZE_<line>_<tower>.xml                COMPANO 100 fall-of-potential export
    ZE_<line>_<tower>_spez.Erdw..xml     COMPANO soil-resistivity export (optional)
    UT_<line>_<tower>.txt                HGT1 touch-voltage report
    UT_<line>_<tower>-<neighbour>.txt    HGT1 report at a neighbouring tower (optional)
    Map_<line>_<tower>.png               map for the protocol (optional)

`read_from_device` returns one dictionary per COMPANO export with the
parsed data frames; matching of tower numbers ignores leading zeros, letter
case and Unicode normalisation.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import pandas as pd

from .config import read_config
from ..instruments.omicron import (
    CompanoXMLReader,
    Hgt1TXTReader,
)
from .naming import (
    extract_line_and_tower,
    has_extension,
    is_soil_resistivity_file,
    normalize_text,
    normalize_tower_id,
    tower_sort_key,
)
from .paths import sorted_listdir

__all__ = [
    "find_neighbor_touch_voltage_file",
    "find_soil_file",
    "find_touch_voltage_file",
    "read_from_device",
    "read_from_omicron",
]

logger = logging.getLogger(__name__)


def _suffix_after(name: str, prefix: str, extension: str) -> str | None:
    """Return the part of ``name`` between ``prefix`` and ``extension``.

    The comparison ignores letter case and Unicode normalisation; ``None`` is
    returned if ``name`` does not start with ``prefix`` or has another
    extension.
    """
    text = normalize_text(name)
    if not has_extension(text, extension):
        return None
    stem = os.path.splitext(text)[0]
    head = normalize_text(prefix)
    if stem[: len(head)].casefold() != head.casefold():
        return None
    return stem[len(head) :]


def find_touch_voltage_file(
    directory_path: str, line_number: str, tower: str
) -> str | None:
    """Find the HGT1 report ``UT_<line>_<tower>.txt`` of a tower.

    Parameters
    ----------
    directory_path : str
        Flat measurement folder.
    line_number : str
        Line identifier.
    tower : str
        Tower identifier; leading zeros and letter case are ignored.

    Returns
    -------
    str or None
        Path of the report or ``None`` if there is none.
    """
    exact = os.path.join(directory_path, f"UT_{line_number}_{tower}.txt")
    if os.path.isfile(exact):
        return exact
    target = normalize_tower_id(tower)
    for name in sorted_listdir(directory_path):
        rest = _suffix_after(name, f"UT_{line_number}_", ".txt")
        if rest is not None and normalize_tower_id(rest) == target:
            return os.path.join(directory_path, name)
    return None


def find_soil_file(
    directory_path: str,
    line_number: str,
    tower: str,
    structure: str = "PREFIX_LINENUMBER_TOWER",
) -> str | None:
    """Find a Schlumberger soil-resistivity export (``*_spez*.xml``) of a tower.

    Parameters
    ----------
    directory_path : str
        Flat measurement folder.
    line_number : str
        Line identifier.
    tower : str
        Tower identifier.
    structure : str, optional
        File-name structure, see `FILE_NAME_STRUCTURES`.

    Returns
    -------
    str or None
        Path of the export or ``None``.
    """
    target = normalize_tower_id(tower)
    for name in sorted_listdir(directory_path):
        if not is_soil_resistivity_file(name):
            continue
        base = re.split(r"_spez", normalize_text(name), flags=re.IGNORECASE)[0]
        line, found_tower = extract_line_and_tower(base + ".xml", structure)
        if (
            line == line_number
            and found_tower is not None
            and normalize_tower_id(found_tower) == target
        ):
            return os.path.join(directory_path, name)
    return None


def find_neighbor_touch_voltage_file(
    directory_path: str, line_number: str, tower: str
) -> tuple[str | None, str | None]:
    """Find an HGT1 report measured at a neighbouring tower.

    Such reports are named ``UT_<line>_<tower>-<neighbour>.txt`` and contain
    the voltage that the earth fault at ``tower`` causes at ``neighbour``.

    Parameters
    ----------
    directory_path : str
        Flat measurement folder.
    line_number : str
        Line identifier.
    tower : str
        Tower with the injected current.

    Returns
    -------
    tuple of (str or None, str or None)
        ``(path, neighbour_tower)`` or ``(None, None)``.
    """
    target = normalize_tower_id(tower)
    for name in sorted_listdir(directory_path):
        rest = _suffix_after(name, f"UT_{line_number}_", ".txt")
        if rest is None or "-" not in rest:
            continue
        own, neighbour = rest.split("-", 1)
        if normalize_tower_id(own) == target:
            return os.path.join(directory_path, name), neighbour
    return None, None


def read_from_omicron(
    path_COMPANO: str,
    path_HGT: str | None = None,
    *,
    nominal_frequency: float = 50.0,
    language: str = "en",
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame | None]:
    """Read one COMPANO export and the matching HGT1 report.

    Parameters
    ----------
    path_COMPANO : str
        COMPANO 100 XML export (fall-of-potential).
    path_HGT : str or None, optional
        HGT1 report of the same tower.
    nominal_frequency : float, optional
        Power frequency for the HGT1 interpolation, by default 50 Hz.
    language : str, optional
        Language of the termination labels.

    Returns
    -------
    tuple
        ``(impedance_to_ground, residual_resistance, touch_voltage)``. All three
        are ``None`` if the XML cannot be read; ``touch_voltage`` is ``None`` if
        the HGT1 report is missing or unreadable.
    """
    try:
        impedance, residual = CompanoXMLReader(
            path_COMPANO
        ).get_impedance_to_ground_dataframe()
    except Exception as exc:
        logger.warning(
            "COMPANO XML could not be read (%s): %s",
            os.path.basename(path_COMPANO),
            exc,
        )
        return None, None, None
    if path_HGT is None:
        return impedance, residual, None
    try:
        touch = Hgt1TXTReader(
            path_HGT, nominal_frequency=nominal_frequency, language=language
        ).get_touchvoltage_dataframe()
    except Exception as exc:
        logger.warning(
            "HGT1 report could not be read (%s): %s", os.path.basename(path_HGT), exc
        )
        return impedance, residual, None
    return impedance, residual, touch


def read_from_device(
    directory_path: str,
    device: str = "COMPANO",
    *,
    structure: str | None = None,
    nominal_frequency: float | None = None,
    language: str | None = None,
) -> list[dict[str, Any]]:
    """Read every measurement in the flat measurement folder.

    Parameters
    ----------
    directory_path : str
        Flat measurement folder.
    device : str, optional
        Instrument family; only ``"COMPANO"`` (COMPANO 100 + HGT1) is
        supported.
    structure : str or None, optional
        File-name structure. ``None`` reads it (and the other two optional
        settings) from the active configuration.
    nominal_frequency : float or None, optional
        Power frequency for the HGT1 interpolation.
    language : str or None, optional
        Language of the termination labels.

    Returns
    -------
    list of dict
        One entry per readable COMPANO export with the keys ``Leitung``,
        ``Mast``, ``ZE_Ohm`` (data frame), ``RA_Ohm`` (data frame), ``UT_V``
        (data frame or ``None``) and optionally ``rhoE_profile``,
        ``neighbor_ut`` and ``neighbor_tower``. Entries are sorted by line and
        tower number.

    Raises
    ------
    ValueError
        If ``device`` is not supported.
    """
    if device != "COMPANO":
        raise ValueError(f"Unsupported device {device!r}; supported: 'COMPANO'")
    if structure is None or nominal_frequency is None or language is None:
        config = read_config()
        structure = structure or config["grounding_impedance_structure"]
        nominal_frequency = nominal_frequency or config["nominal_frequency_Hz"]
        language = language or config["language"]

    export_list: list[dict[str, Any]] = []
    for filename in sorted_listdir(directory_path):
        if not has_extension(filename, ".xml"):
            continue
        line_number, tower = extract_line_and_tower(
            filename=filename, structure=structure
        )
        if line_number is None or tower is None:
            if is_soil_resistivity_file(filename):
                logger.debug(
                    "Soil-resistivity export, read together with its tower: %s",
                    filename,
                )
            else:
                logger.warning("Skipping file with unrecognised name: %s", filename)
            continue
        xml_file = os.path.join(directory_path, filename)
        txt_file = find_touch_voltage_file(directory_path, line_number, tower)
        if txt_file is None:
            logger.warning(
                "No HGT1 report for %s; only the COMPANO export is used.", filename
            )
        impedance, residual, touch = read_from_omicron(
            xml_file, txt_file, nominal_frequency=nominal_frequency, language=language
        )
        if impedance is None:
            logger.warning(
                "Skipping %s: the COMPANO measurement could not be read.", filename
            )
            continue

        entry: dict[str, Any] = {
            "Leitung": line_number,
            "Mast": tower,
            "ZE_Ohm": impedance,
            "UT_V": touch,
            "RA_Ohm": residual,
        }
        soil_file = find_soil_file(directory_path, line_number, tower, structure)
        if soil_file is not None:
            try:
                entry["rhoE_profile"] = CompanoXMLReader(
                    soil_file
                ).get_soil_resistivity()
            except Exception as exc:
                logger.warning(
                    "Could not read soil resistivity for %s: %s", filename, exc
                )
        neighbour_file, neighbour_tower = find_neighbor_touch_voltage_file(
            directory_path, line_number, tower
        )
        if neighbour_file is not None:
            try:
                entry["neighbor_ut"] = Hgt1TXTReader(
                    neighbour_file,
                    nominal_frequency=nominal_frequency,
                    language=language,
                ).get_touchvoltage_dataframe()
                entry["neighbor_tower"] = neighbour_tower
            except Exception as exc:
                logger.warning(
                    "Could not read the neighbour-tower report for %s: %s",
                    filename,
                    exc,
                )
        export_list.append(entry)
    export_list.sort(
        key=lambda item: (normalize_text(item["Leitung"]), tower_sort_key(item["Mast"]))
    )
    return export_list
