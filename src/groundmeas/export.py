# src/groundmeas/export.py

import json
import csv
import xml.etree.ElementTree as ET
from typing import Any
from .db import read_measurements_by
import datetime


def export_measurements_to_json(path: str, **filters: Any) -> None:
    """
    Export measurements (and nested items) matching filters to a JSON file.
    Uses the same **filters as read_measurements_by().
    """
    data, _ = read_measurements_by(**filters)
    # Use `default` to convert datetime to ISO strings
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            default=lambda o: o.isoformat()
            if isinstance(o, datetime.datetime)
            else str(o),
        )


def export_measurements_to_csv(path: str, **filters: Any) -> None:
    """
    Export measurements matching filters to a CSV file.
    Each row is one measurement; items are serialized as a JSON string in the 'items' column.
    """
    data, _ = read_measurements_by(**filters)
    if not data:
        return
    # determine measurement columns
    cols = [c for c in data[0].keys() if c != "items"]
    fieldnames = cols + ["items"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for m in data:
            row = {c: m.get(c) for c in cols}
            row["items"] = json.dumps(m.get("items", []))
            writer.writerow(row)


def export_measurements_to_xml(path: str, **filters: Any) -> None:
    """
    Export measurements (and nested items) matching filters to an XML file.
    """
    data, _ = read_measurements_by(**filters)
    root = ET.Element("measurements")
    for m in data:
        m_elem = ET.SubElement(root, "measurement", id=str(m.get("id")))
        # top‐level fields
        for key, val in m.items():
            if key == "items":
                items_elem = ET.SubElement(m_elem, "items")
                for it in val:
                    it_elem = ET.SubElement(items_elem, "item", id=str(it.get("id")))
                    for k, v in it.items():
                        if k == "id":
                            continue
                        child = ET.SubElement(it_elem, k)
                        child.text = "" if v is None else str(v)
            else:
                if key == "id":
                    continue
                child = ET.SubElement(m_elem, key)
                child.text = "" if val is None else str(val)
    tree = ET.ElementTree(root)
    tree.write(path, encoding="utf-8", xml_declaration=True)
