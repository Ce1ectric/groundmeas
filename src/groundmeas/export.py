"""
groundmeas.export
=================

Export utilities for the groundmeas package.

Provides functions to export Measurement data (with nested items) to JSON, CSV, and XML formats.
"""

import json
import csv
import xml.etree.ElementTree as ET
import datetime
import logging
from pathlib import Path
from typing import Any

from .db import read_measurements_by

logger = logging.getLogger(__name__)


def export_measurements_to_json(path: str, **filters: Any) -> None:
    """
    Export measurements (and nested items) matching filters to a JSON file.

    Uses the same keyword filters as read_measurements_by().

    Args:
        path: Filesystem path where the JSON file will be written.
        **filters: Field lookups passed through to read_measurements_by().

    Raises:
        RuntimeError: if reading the data fails.
        IOError: if writing the file fails.
    """
    try:
        data, _ = read_measurements_by(**filters)
    except Exception as e:
        logger.exception(
            "Failed to retrieve measurements for JSON export with filters %s", filters
        )
        raise RuntimeError(f"Could not read measurements: {e}") from e

    try:
        out_path = Path(path)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                default=lambda o: (
                    o.isoformat() if isinstance(o, datetime.datetime) else str(o)
                ),
            )
        logger.info("Exported %d measurements to JSON: %s", len(data), path)
    except Exception as e:
        logger.exception("Failed to write JSON export to %s", path)
        raise IOError(f"Could not write JSON file '{path}': {e}") from e


def export_measurements_to_csv(path: str, **filters: Any) -> None:
    """
    Export measurements (and nested items) matching filters to a CSV file.

    Each row is one measurement; the 'items' column contains a JSON-encoded list.

    Args:
        path: Filesystem path where the CSV file will be written.
        **filters: Field lookups passed through to read_measurements_by().

    Raises:
        RuntimeError: if reading the data fails.
        IOError: if writing the file fails.
    """
    try:
        data, _ = read_measurements_by(**filters)
    except Exception as e:
        logger.exception(
            "Failed to retrieve measurements for CSV export with filters %s", filters
        )
        raise RuntimeError(f"Could not read measurements: {e}") from e

    if not data:
        logger.warning("No data to export to CSV with filters %s", filters)
        return

    # Determine columns (exclude nested 'items')
    cols = [c for c in data[0].keys() if c != "items"]
    fieldnames = cols + ["items"]

    try:
        out_path = Path(path)
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for m in data:
                row = {c: m.get(c) for c in cols}
                row["items"] = json.dumps(m.get("items", []))
                writer.writerow(row)
        logger.info("Exported %d measurements to CSV: %s", len(data), path)
    except Exception as e:
        logger.exception("Failed to write CSV export to %s", path)
        raise IOError(f"Could not write CSV file '{path}': {e}") from e


def export_measurements_to_xml(path: str, **filters: Any) -> None:
    """
    Export measurements (and nested items) matching filters to an XML file.

    The XML structure:
        <measurements>
          <measurement id="...">
            <field1>...</field1>
            ...
            <items>
              <item id="...">
                <subfield>...</subfield>
                ...
              </item>
              ...
            </items>
          </measurement>
          ...
        </measurements>

    Args:
        path: Filesystem path where the XML file will be written.
        **filters: Field lookups passed through to read_measurements_by().

    Raises:
        RuntimeError: if reading the data fails.
        IOError: if writing the file fails.
    """
    try:
        data, _ = read_measurements_by(**filters)
    except Exception as e:
        logger.exception(
            "Failed to retrieve measurements for XML export with filters %s", filters
        )
        raise RuntimeError(f"Could not read measurements: {e}") from e

    root = ET.Element("measurements")
    for m in data:
        meas_elem = ET.SubElement(root, "measurement", id=str(m.get("id")))
        for key, val in m.items():
            if key == "id":
                continue
            if key == "items":
                items_elem = ET.SubElement(meas_elem, "items")
                for it in val:
                    item_elem = ET.SubElement(items_elem, "item", id=str(it.get("id")))
                    for subkey, subval in it.items():
                        if subkey == "id":
                            continue
                        child = ET.SubElement(item_elem, subkey)
                        child.text = "" if subval is None else str(subval)
            else:
                child = ET.SubElement(meas_elem, key)
                child.text = "" if val is None else str(val)

    try:
        out_path = Path(path)
        tree = ET.ElementTree(root)
        tree.write(out_path, encoding="utf-8", xml_declaration=True)
        logger.info("Exported %d measurements to XML: %s", len(data), path)
    except Exception as e:
        logger.exception("Failed to write XML export to %s", path)
        raise IOError(f"Could not write XML file '{path}': {e}") from e
