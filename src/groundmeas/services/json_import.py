"""
groundmeas.services.json_import
===============================

Import measurements (with nested location and items) from JSON.

Accepts the files written by :func:`groundmeas.export_measurements_to_json`
as well as hand-written files with the same structure:

* one measurement dict or a list of measurement dicts,
* an optional nested ``location`` dict and an optional ``items`` list,
* or a pair ``X_measurement.json`` + ``X_items.json``.

Exported files carry database keys (``id``, ``location_id``,
``measurement_id``, ``location.id``) and ISO 8601 timestamps. Both are
handled here: the keys are dropped (the target database assigns new ones and
the location is matched by name/coordinates), timestamps are parsed and
converted to UTC.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from ..core.db import create_measurements_with_items

logger = logging.getLogger(__name__)

_MEASUREMENT_DB_KEYS = ("id", "location_id")
_LOCATION_DB_KEYS = ("id",)
_ITEM_DB_KEYS = ("id", "measurement_id")


def parse_timestamp(value: Any) -> Optional[datetime]:
    """
    Convert a timestamp from JSON into a naive UTC ``datetime``.

    Parameters
    ----------
    value : str, datetime or None
        ISO 8601 string (``"2026-05-12T09:00:00"``, ``"2026-05-12 09:00"``,
        ``"2026-05-12"``, with or without offset or ``Z``) or a ``datetime``.
        Values without offset are taken as UTC, values with offset are
        converted to UTC.

    Returns
    -------
    datetime or None
        Naive datetime in UTC, or ``None`` for ``None``/empty strings.

    Raises
    ------
    ValueError
        If the value is not a valid ISO 8601 timestamp.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(
                f"Invalid timestamp {value!r}: expected ISO 8601, "
                "e.g. '2026-05-12T09:00:00'"
            ) from exc
    else:
        raise ValueError(
            f"Invalid timestamp {value!r}: expected an ISO 8601 string, "
            f"got {type(value).__name__}"
        )
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def prepare_measurement_for_import(
    data: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Turn one measurement dict from JSON into arguments for the CRUD layer.

    Parameters
    ----------
    data : dict
        Measurement fields with optional nested ``location`` and ``items``.

    Returns
    -------
    measurement : dict
        Payload for :func:`groundmeas.create_measurement` (``timestamp`` as
        ``datetime``, without database keys).
    items : list of dict
        Payloads for :func:`groundmeas.create_item` (without database keys).

    Raises
    ------
    ValueError
        If ``data`` is not a dict, the timestamp is invalid or an item is not
        a dict.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected a measurement object, got {type(data).__name__}")
    measurement = {k: v for k, v in data.items() if k not in _MEASUREMENT_DB_KEYS}
    raw_items = measurement.pop("items", None) or []

    if "timestamp" in measurement:
        timestamp = parse_timestamp(measurement["timestamp"])
        if timestamp is None:
            # explicit null: let the model fill in the current time
            measurement.pop("timestamp")
        else:
            measurement["timestamp"] = timestamp

    location = measurement.get("location")
    if isinstance(location, dict):
        measurement["location"] = {
            k: v for k, v in location.items() if k not in _LOCATION_DB_KEYS
        }
    elif location is None:
        measurement.pop("location", None)

    if not isinstance(raw_items, list):
        raise ValueError("'items' must be a list of objects")
    items: List[Dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            raise ValueError(f"Expected an item object, got {type(item).__name__}")
        items.append({k: v for k, v in item.items() if k not in _ITEM_DB_KEYS})
    return measurement, items


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_json_measurements(
    path: Union[str, Path],
) -> List[Tuple[Path, List[Dict[str, Any]]]]:
    """
    Read measurement dicts from a JSON file or a directory of JSON files.

    ``X_measurement.json`` files are merged with an ``X_items.json`` file next
    to them (``{"items": [...]}`` or a plain list); ``X_items.json`` files are
    never read on their own.

    Parameters
    ----------
    path : str or Path
        JSON file or directory.

    Returns
    -------
    list of (Path, list of dict)
        Source file and the measurement dicts it contains.

    Raises
    ------
    ValueError
        If a file does not contain a measurement object or a list of them.
    json.JSONDecodeError
        If a file is not valid JSON.
    """
    source = Path(path)
    if source.is_dir():
        files = sorted(
            p for p in source.glob("*.json") if not p.name.endswith("_items.json")
        )
    else:
        files = [source]

    collected: List[Tuple[Path, List[Dict[str, Any]]]] = []
    for file in files:
        data = _load_json(file)
        if isinstance(data, dict):
            measurements = [data]
        elif isinstance(data, list):
            measurements = data
        else:
            raise ValueError(f"{file.name}: unsupported JSON structure")
        if file.name.endswith("_measurement.json") and measurements:
            items_file = file.with_name(
                file.name.replace("_measurement.json", "_items.json")
            )
            if items_file.exists():
                extra = _load_json(items_file)
                if isinstance(extra, dict):
                    extra = extra.get("items", [])
                measurements[0] = dict(measurements[0])
                measurements[0]["items"] = list(
                    measurements[0].get("items") or []
                ) + list(extra)
        collected.append((file, measurements))
    return collected


def import_measurements(
    data: Union[Dict[str, Any], List[Dict[str, Any]]],
) -> List[Tuple[int, int]]:
    """
    Insert measurement dicts (as exported to JSON) into the connected database.

    Parameters
    ----------
    data : dict or list of dict
        One measurement or a list of measurements with nested ``location``
        and ``items``.

    Returns
    -------
    list of (int, int)
        ``(measurement_id, number_of_items)`` for every imported measurement.

    Raises
    ------
    ValueError
        If a measurement is malformed (see
        :func:`prepare_measurement_for_import`) or an item carries no value.
        Nothing is imported in this case.
    RuntimeError
        On database errors (nothing is imported).
    """
    entries = [data] if isinstance(data, dict) else list(data)
    prepared = [prepare_measurement_for_import(entry) for entry in entries]
    # one transaction for all measurements: all or nothing
    stored = create_measurements_with_items(prepared)
    created = [(measurement_id, len(item_ids)) for measurement_id, item_ids in stored]
    logger.info("Imported %d measurements from JSON", len(created))
    return created


def import_measurements_from_json(path: Union[str, Path]) -> List[Tuple[int, int]]:
    """
    Import a JSON file (or a directory of JSON files) into the connected database.

    Round-trips with :func:`groundmeas.export_measurements_to_json`: database
    keys of the export are dropped, timestamps are parsed, and locations are
    matched by name/coordinates, so the same file can be imported into a
    database that already contains data.

    Parameters
    ----------
    path : str or Path
        JSON file or directory (see :func:`collect_json_measurements`).

    Returns
    -------
    list of (int, int)
        ``(measurement_id, number_of_items)`` for every imported measurement.

    Raises
    ------
    ValueError, json.JSONDecodeError
        If a file or a measurement in it is malformed; all files are read and
        checked first, so nothing is imported in this case.
    RuntimeError
        On database errors.

    Examples
    --------
    >>> import groundmeas as gm
    >>> gm.connect_db("ground.db")                            # doctest: +SKIP
    >>> gm.export_measurements_to_json("export.json")         # doctest: +SKIP
    >>> gm.import_measurements_from_json("export.json")       # doctest: +SKIP
    [(12, 25), (13, 7)]
    """
    measurements: List[Dict[str, Any]] = []
    for _file, entries in collect_json_measurements(path):
        measurements.extend(entries)
    return import_measurements(measurements)
