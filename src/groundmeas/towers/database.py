"""
groundmeas.towers.database
==========================

Import the instrument files of a tower campaign into the groundmeas database.

Every tower becomes a :class:`~groundmeas.core.models.Location` named
``"<line> tower <tower>"`` with one ``overhead_line_tower`` measurement per
test, created with the importers of :mod:`groundmeas.services.omicron_import`:

==========================================  ==================================
File (flat measurement folder)              Measurement
==========================================  ==================================
``ZE_<line>_<tower>.xml``                   fall-of-potential profile
                                            (``injection_earth_electrode``);
                                            the current-electrode distance
                                            ``Entfernung_Hilfserder_m`` comes
                                            from the measurement description
``UT_<line>_<tower>.txt``                   touch voltages (reference current
                                            from the COMPANO export)
``UT_<line>_<tower>-<neighbour>.txt``       ``transferred_potential`` at the
                                            neighbouring tower
``ZE_<line>_<tower>_spez.Erdw..xml``        soil resistivity (``wenner`` or
                                            ``schlumberger``)
==========================================  ==================================

The measurement description also provides the operator (``Vorname``,
``Name``, ``Firma``), notes for the measurement description (``Witterung``,
``Messtechnik_Name``, ``Winkel_Sonde_Hilfserder_grad``) and, if present,
tower coordinates (``latitude``/``longitude``/``altitude`` or
``Breitengrad``/``Längengrad``). Files that are already in the database (same
location, file name in the measurement description) are skipped, so the
import can be repeated after further deliveries. The evaluation results
(assessment, protocols) stay in the JSON/Excel output of the campaign.

Used by ``gm-cli towers import-db``.
"""

from __future__ import annotations

import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from ..core.db import read_measurements_by
from ..services.omicron_import import (
    import_fall_of_potential,
    import_soil_resistivity,
    import_step_touch,
)
from .config import read_config
from .files import (
    find_neighbor_touch_voltage_file,
    find_soil_file,
    find_touch_voltage_file,
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
    "ASSET_TYPE",
    "TowerFiles",
    "find_tower_files",
    "import_campaign",
    "location_name",
]

logger = logging.getLogger(__name__)

ASSET_TYPE = "overhead_line_tower"
"""Asset type of the imported measurements."""

TESTS = ("fall_of_potential", "touch_voltage", "transferred_potential", "soil")
"""Tests in import order (values of the ``test`` key of the import records)."""

_COORDINATE_COLUMNS: Dict[str, Sequence[str]] = {
    "latitude": ("latitude", "Breitengrad"),
    "longitude": ("longitude", "Längengrad", "Laengengrad"),
    "altitude": ("altitude", "Hoehe_m", "Höhe_m"),
}


@dataclass(frozen=True)
class TowerFiles:
    """Instrument files of one tower in the flat measurement folder.

    Attributes
    ----------
    line, tower : str
        Line and tower identifier as written in the file name.
    fall_of_potential : pathlib.Path
        COMPANO 100 export with the fall-of-potential test.
    touch_voltage : pathlib.Path, optional
        HGT1 report of the tower.
    neighbour_touch_voltage : pathlib.Path, optional
        HGT1 report measured at a neighbouring tower.
    neighbour_tower : str, optional
        Identifier of that neighbouring tower.
    soil : pathlib.Path, optional
        COMPANO 100 export with a soil-resistivity measurement.
    """

    line: str
    tower: str
    fall_of_potential: Path
    touch_voltage: Optional[Path] = None
    neighbour_touch_voltage: Optional[Path] = None
    neighbour_tower: Optional[str] = None
    soil: Optional[Path] = None

    @property
    def location_name(self) -> str:
        """Name of the groundmeas location (see `location_name`)."""
        return location_name(self.line, self.tower)


def location_name(line: object, tower: object) -> str:
    """Return the location name of a tower, e.g. ``"LH-01-0815 tower 8N"``.

    Parameters
    ----------
    line, tower : object
        Line and tower identifier; leading zeros of the tower number are
        dropped and letters upper-cased, so ``"008n"`` and ``8N`` give the
        same location.

    Returns
    -------
    str
        Location name.
    """
    return f"{normalize_text(line)} tower {normalize_tower_id(tower)}"


def find_tower_files(
    directory_path: str | os.PathLike[str],
    structure: str = "PREFIX_LINENUMBER_TOWER",
) -> List[TowerFiles]:
    """Collect the instrument files of every tower in a flat measurement folder.

    Parameters
    ----------
    directory_path : str or os.PathLike
        Flat measurement folder (``path_measurements`` of the configuration).
    structure : str, optional
        File-name structure, see
        `groundmeas.towers.naming.FILE_NAME_STRUCTURES`.

    Returns
    -------
    list of TowerFiles
        One entry per fall-of-potential export, sorted by line and tower.
    """
    directory = os.fspath(directory_path)
    found: List[TowerFiles] = []
    for filename in sorted_listdir(directory):
        if not has_extension(filename, ".xml") or is_soil_resistivity_file(filename):
            continue
        line, tower = extract_line_and_tower(filename, structure)
        if line is None or tower is None:
            logger.warning("Skipping file with unrecognised name: %s", filename)
            continue
        touch = find_touch_voltage_file(directory, line, tower)
        neighbour, neighbour_tower = find_neighbor_touch_voltage_file(
            directory, line, tower
        )
        soil = find_soil_file(directory, line, tower, structure)
        found.append(
            TowerFiles(
                line=line,
                tower=tower,
                fall_of_potential=Path(directory, filename),
                touch_voltage=Path(touch) if touch else None,
                neighbour_touch_voltage=Path(neighbour) if neighbour else None,
                neighbour_tower=neighbour_tower,
                soil=Path(soil) if soil else None,
            )
        )
    found.sort(key=lambda t: (normalize_text(t.line), tower_sort_key(t.tower)))
    return found


# ------------------------------------------------------------------ metadata
def _value(row: Optional[pd.Series], *columns: str) -> Any:
    """First non-empty cell of ``columns`` in ``row`` (``None`` if there is none)."""
    if row is None:
        return None
    for column in columns:
        if column not in row.index:
            continue
        value = row[column]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _description_row(
    description: Optional[pd.DataFrame], line: str, tower: str
) -> Optional[pd.Series]:
    if description is None:
        return None
    lines = description["Leitung"].map(normalize_text)
    towers = description["Mast"].map(normalize_tower_id)
    rows = description[
        (lines == normalize_text(line)) & (towers == normalize_tower_id(tower))
    ]
    return None if rows.empty else rows.iloc[0]


def _location(files: TowerFiles, row: Optional[pd.Series]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"name": files.location_name}
    for field, columns in _COORDINATE_COLUMNS.items():
        number = _number(_value(row, *columns))
        if number is not None:
            payload[field] = number
    return payload


def _operator(row: Optional[pd.Series]) -> Optional[str]:
    person = " ".join(
        str(part).strip()
        for part in (_value(row, "Vorname"), _value(row, "Name"))
        if part is not None
    )
    company = _value(row, "Firma")
    parts = [p for p in (person, str(company).strip() if company else "") if p]
    return ", ".join(parts) or None


def _notes(files: TowerFiles, row: Optional[pd.Series]) -> List[str]:
    notes = [f"tower campaign: line {files.line}, tower {files.tower}"]
    for label, column in (
        ("weather", "Witterung"),
        ("instrument", "Messtechnik_Name"),
    ):
        value = _value(row, column)
        if value is not None:
            notes.append(f"{label}: {str(value).strip()}")
    return notes


def _already_imported() -> Dict[str, List[str]]:
    """Descriptions of the imported tower measurements per location name."""
    records, _ids = read_measurements_by(asset_type=ASSET_TYPE)
    imported: Dict[str, List[str]] = {}
    for record in records:
        name = (record.get("location") or {}).get("name")
        if name:
            imported.setdefault(name, []).append(record.get("description") or "")
    return imported


def _tests(files: TowerFiles) -> List[Tuple[str, Path, str]]:
    """``(test, file, description head)`` of the files present for a tower."""
    candidates: List[Tuple[str, Optional[Path], str]] = [
        (
            "fall_of_potential",
            files.fall_of_potential,
            "Fall-of-potential test, OMICRON COMPANO 100",
        ),
        ("touch_voltage", files.touch_voltage, "Touch voltages, OMICRON HGT1"),
        (
            "transferred_potential",
            files.neighbour_touch_voltage,
            f"Transferred potential at tower {files.neighbour_tower}, OMICRON HGT1",
        ),
        ("soil", files.soil, "Soil resistivity, OMICRON COMPANO 100"),
    ]
    return [(test, path, head) for test, path, head in candidates if path is not None]


def _run_import(
    test: str,
    files: TowerFiles,
    description: str,
    *,
    current_electrode_distance_m: Optional[float],
    nominal_frequency_hz: float,
    per_frequency: bool,
    **common: Any,
) -> int:
    """Import one test of a tower and return the measurement ID."""
    if test == "fall_of_potential":
        return import_fall_of_potential(
            files.fall_of_potential,
            current_electrode_distance_m=current_electrode_distance_m,
            per_frequency=per_frequency,
            description=description,
            **common,
        )
    if test in ("touch_voltage", "transferred_potential"):
        transferred = test == "transferred_potential"
        report = files.neighbour_touch_voltage if transferred else files.touch_voltage
        assert report is not None
        return import_step_touch(
            report,
            compano_xml_path=files.fall_of_potential,
            nominal_frequency_hz=nominal_frequency_hz,
            per_frequency=per_frequency,
            transferred=transferred,
            description=description,
            **common,
        )
    assert files.soil is not None
    return import_soil_resistivity(files.soil, description=description, **common)


# -------------------------------------------------------------------- import
def import_campaign(
    config_path: str | os.PathLike[str] | None = None,
    *,
    per_frequency: bool = True,
    voltage_level_kv: Optional[float] = None,
    timezone: Optional[str] = None,
    skip_existing: bool = True,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    """Import the instrument files of a tower campaign into the database.

    The database must be connected (:func:`groundmeas.connect_db`) unless
    ``dry_run`` is true.

    Parameters
    ----------
    config_path : str, os.PathLike or None, optional
        Campaign configuration; see
        `groundmeas.towers.config.resolve_config_path`.
    per_frequency : bool, default True
        Also store the profiles and touch voltages at both test frequencies.
    voltage_level_kv : float, optional
        Nominal voltage of the line(s).
    timezone : str, optional
        IANA time zone of the instrument clocks (e.g. ``"Europe/Berlin"``);
        converts the time stamps to UTC.
    skip_existing : bool, default True
        Skip files whose measurement is already in the database (same
        location, file name in the description).
    dry_run : bool, default False
        Only list what would be imported; the database is not used.

    Returns
    -------
    list of dict
        One record per test with the keys ``line``, ``tower``, ``location``,
        ``test`` (see `TESTS`), ``file``, ``status`` (``"imported"``,
        ``"skipped"``, ``"failed"`` or ``"planned"``), ``measurement_id``
        and ``message``.

    Raises
    ------
    FileNotFoundError, groundmeas.towers.config.ConfigError
        If the configuration is missing or invalid.
    """
    config = read_config(config_path)
    towers = find_tower_files(
        config["directory_path"], config["grounding_impedance_structure"]
    )
    try:
        description: Optional[pd.DataFrame] = pd.read_excel(
            config["measurement_description_path"]
        )
    except (OSError, ValueError) as exc:
        logger.warning("Measurement description not readable (%s)", exc)
        description = None
    if description is not None and not {"Leitung", "Mast"} <= set(description.columns):
        logger.warning(
            "The measurement description lacks the columns Leitung/Mast; "
            "importing without metadata"
        )
        description = None
    imported = {} if (dry_run or not skip_existing) else _already_imported()
    nominal = config["nominal_frequency_Hz"]

    records: List[Dict[str, Any]] = []
    for files in towers:
        row = _description_row(description, files.line, files.tower)
        if description is not None and row is None:
            logger.warning(
                "%s: no row in the measurement description; importing without "
                "metadata",
                files.location_name,
            )
        distance = _number(_value(row, "Entfernung_Hilfserder_m"))
        if distance is not None and distance <= 0:
            distance = None
        common: Dict[str, Any] = {
            "location": _location(files, row),
            "asset_type": ASSET_TYPE,
            "operator": _operator(row),
            "voltage_level_kv": voltage_level_kv,
            "timezone": timezone,
        }
        notes = _notes(files, row)
        fop_notes = list(notes)
        if distance is not None:
            fop_notes.append(f"current electrode {distance:g} m")
        angle = _value(row, "Winkel_Sonde_Hilfserder_grad")
        if _number(angle) is not None:
            fop_notes.append(f"angle probe/current electrode {_number(angle):g} deg")

        existing: Set[str] = set(imported.get(files.location_name, []))
        for test, path, head in _tests(files):
            text = "; ".join(
                [f"{head} ({path.name})"]
                + (fop_notes if test == "fall_of_potential" else notes)
            )
            record: Dict[str, Any] = {
                "line": files.line,
                "tower": files.tower,
                "location": files.location_name,
                "test": test,
                "file": path.name,
                "status": "planned",
                "measurement_id": None,
                "message": "",
            }
            if test == "fall_of_potential" and distance is None:
                record["message"] = (
                    "no current-electrode distance (Entfernung_Hilfserder_m); "
                    "62 % method not available"
                )
            if dry_run:
                records.append(record)
                continue
            if any(f"({path.name})" in old for old in existing):
                record.update(status="skipped", message="already imported")
                records.append(record)
                continue
            try:
                record["measurement_id"] = _run_import(
                    test,
                    files,
                    text,
                    current_electrode_distance_m=distance,
                    nominal_frequency_hz=nominal,
                    per_frequency=per_frequency,
                    **common,
                )
                record["status"] = "imported"
            except Exception as exc:  # report and continue with the next file
                logger.error(
                    "%s: %s not imported (%s: %s)",
                    files.location_name,
                    path.name,
                    type(exc).__name__,
                    exc,
                )
                record.update(status="failed", message=f"{type(exc).__name__}: {exc}")
            records.append(record)
    return records
