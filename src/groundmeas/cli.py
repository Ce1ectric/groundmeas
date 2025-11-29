"""
Command-line interface for groundmeas.

Provides:
  - Interactive wizard to add measurements and items with autocomplete.
  - Listing of measurements and items.
  - Import/export JSON helpers.

The CLI assumes a SQLite database path passed via --db, GROUNDMEAS_DB, or a
user config file at ~/.config/groundmeas/config.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence, Tuple, get_args

import typer
from prompt_toolkit import prompt
from prompt_toolkit.completion import WordCompleter

from .db import (
    connect_db,
    create_item,
    create_measurement,
    read_items_by,
    read_measurements_by,
)
from .export import export_measurements_to_json
from .models import MeasurementType

app = typer.Typer(help="CLI for managing groundmeas data")
logger = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".config" / "groundmeas" / "config.json"


# ─── HELPERS ────────────────────────────────────────────────────────────────────


def _word_choice(values: Iterable[str]) -> WordCompleter:
    return WordCompleter(list(values), ignore_case=True, sentence=True)


def _prompt_text(
    message: str, default: str | None = None, completer: WordCompleter | None = None
) -> str:
    suffix = f" [{default}]" if default else ""
    out = prompt(f"{message}{suffix}: ", completer=completer)
    return out.strip() or (default or "")


def _prompt_float(
    message: str,
    default: float | None = None,
    suggestions: Sequence[str] | None = None,
) -> Optional[float]:
    completer = _word_choice(suggestions) if suggestions else None
    while True:
        raw = _prompt_text(
            message,
            default=None if default is None else str(default),
            completer=completer,
        )
        if raw == "" and default is not None:
            return default
        if raw == "":
            return None
        try:
            return float(raw)
        except ValueError:
            typer.echo("Please enter a number (or leave empty).")


def _prompt_choice(
    message: str,
    choices: Sequence[str],
    default: str | None = None,
) -> str:
    completer = _word_choice(choices)
    suffix = f" [{default}]" if default else ""
    while True:
        val = prompt(f"{message}{suffix}: ", completer=completer).strip()
        if val == "" and default:
            return default
        if val in choices:
            return val
        typer.echo(f"Choose one of: {', '.join(choices)}")


def _measurement_types() -> List[str]:
    return sorted(get_args(MeasurementType))  # type: ignore[arg-type]


def _existing_locations() -> List[str]:
    try:
        measurements, _ = read_measurements_by()
    except Exception:
        return []
    names = {m.get("location", {}).get("name") for m in measurements if m.get("location")}
    return sorted({n for n in names if n})


def _existing_measurement_values(field: str) -> List[str]:
    try:
        measurements, _ = read_measurements_by()
    except Exception:
        return []
    vals = [m.get(field) for m in measurements if m.get(field) not in (None, "")]
    return sorted({str(v) for v in vals})


def _existing_item_units(measurement_type: str) -> List[str]:
    try:
        items, _ = read_items_by(measurement_type=measurement_type)
    except Exception:
        return []
    vals = [it.get("unit") for it in items if it.get("unit")]
    return sorted({str(v) for v in vals})


def _existing_item_values(field: str, measurement_type: str | None = None) -> List[str]:
    filters: dict[str, Any] = {}
    if measurement_type:
        filters["measurement_type"] = measurement_type
    try:
        items, _ = read_items_by(**filters)
    except Exception:
        return []
    vals = [it.get(field) for it in items if it.get(field) not in (None, "")]
    return sorted({str(v) for v in vals})


def _resolve_db(db: Optional[str]) -> str:
    if db:
        return db
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            cfg_path = cfg.get("db_path")
            if cfg_path:
                return cfg_path
        except Exception:
            pass
    return str(Path("groundmeas.db").resolve())


def _save_default_db(db_path: str) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"db_path": db_path}, indent=2))


def _print_measurement_summary(mid: int, measurement: dict[str, Any], items: List[dict[str, Any]]) -> None:
    typer.echo("\nSummary")
    typer.echo("-------")
    typer.echo(f"Measurement id={mid}")
    loc = measurement.get("location") or {}
    loc_name = loc.get("name", "n/a")
    typer.echo(
        f"Location: {loc_name} "
        f"(lat={loc.get('latitude')}, lon={loc.get('longitude')}, alt={loc.get('altitude')})"
    )
    typer.echo(
        f"Method={measurement.get('method')} | Asset={measurement.get('asset_type')} | "
        f"Voltage kV={measurement.get('voltage_level_kv')} | Fault R Ω={measurement.get('fault_resistance_ohm')}"
    )
    if measurement.get("description"):
        typer.echo(f"Description: {measurement['description']}")
    if measurement.get("operator"):
        typer.echo(f"Operator: {measurement['operator']}")
    typer.echo(f"Items ({len(items)}):")
    for it in items:
        typer.echo(
            f"  - id={it.get('id','?')} type={it.get('measurement_type')} "
            f"freq={it.get('frequency_hz')}Hz unit={it.get('unit')} "
            f"value={it.get('value')} angle={it.get('value_angle_deg')} "
            f"real={it.get('value_real')} imag={it.get('value_imag')}"
        )


# ─── APP CALLBACK ───────────────────────────────────────────────────────────────


@app.callback()
def _connect(
    db: Optional[str] = typer.Option(
        None,
        "--db",
        envvar="GROUNDMEAS_DB",
        help="Path to SQLite database (created if missing).",
    )
) -> None:
    """Connect to the database before running any command."""
    db_path = _resolve_db(db)
    db_parent = Path(db_path).expanduser().resolve().parent
    db_parent.mkdir(parents=True, exist_ok=True)
    connect_db(db_path)
    typer.echo(f"Connected to {db_path}")


# ─── COMMANDS ───────────────────────────────────────────────────────────────────


@app.command("add-measurement")
def add_measurement() -> None:
    """Interactive wizard to add a measurement and its items."""
    typer.echo("Add a new measurement (press Enter to accept defaults).")

    existing_locs = _existing_locations()
    loc_default = existing_locs[0] if existing_locs else None
    loc_name = _prompt_text("Location name", default=loc_default, completer=_word_choice(existing_locs))

    lat = _prompt_float("Latitude (optional)", default=None)
    lon = _prompt_float("Longitude (optional)", default=None)
    alt = _prompt_float("Altitude (optional)", default=None)

    method = _prompt_choice(
        "Method",
        choices=["staged_fault_test", "injection_remote_substation", "injection_earth_electrode"],
    )
    asset = _prompt_choice(
        "Asset type",
        choices=[
            "substation",
            "overhead_line_tower",
            "cable",
            "cable_cabinet",
            "house",
            "pole_mounted_transformer",
            "mv_lv_earthing_system",
        ],
    )
    voltage_choices = _existing_measurement_values("voltage_level_kv")
    fault_res_choices = _existing_measurement_values("fault_resistance_ohm")
    operator_choices = _existing_measurement_values("operator")

    voltage = _prompt_float("Voltage level kV (optional)", default=None, suggestions=voltage_choices)
    fault_res = _prompt_float("Fault resistance Ω (optional)", default=None, suggestions=fault_res_choices)
    description = _prompt_text("Description (optional)", default="")
    operator_default = operator_choices[0] if operator_choices else ""
    operator = _prompt_text(
        "Operator (optional)",
        default=operator_default,
        completer=_word_choice(operator_choices),
    )

    measurement_data: dict[str, Any] = {
        "method": method,
        "asset_type": asset,
        "voltage_level_kv": voltage,
        "fault_resistance_ohm": fault_res,
        "description": description or None,
        "operator": operator or None,
        "location": {"name": loc_name, "latitude": lat, "longitude": lon, "altitude": alt},
    }

    measurement_snapshot = json.loads(json.dumps(measurement_data))
    mid = create_measurement(measurement_data)
    typer.echo(f"Created measurement id={mid} at '{loc_name}'.")

    # Add items
    created_items: List[dict[str, Any]] = []
    mtypes = _measurement_types()
    while True:
        mtype = _prompt_choice(
            "Measurement type (or type 'done' to finish)",
            choices=mtypes + ["done"],
            default="done",
        )
        if mtype == "done":
            break

        freq_choices = _existing_item_values("frequency_hz", mtype)
        freq = _prompt_float("Frequency Hz (optional)", default=50.0, suggestions=freq_choices)

        entry_mode = _prompt_choice(
            "Value entry mode",
            choices=["magnitude_angle", "real_imag"],
            default="magnitude_angle",
        )

        item: dict[str, Any] = {
            "measurement_type": mtype,
            "frequency_hz": freq,
        }

        angle_choices = _existing_item_values("value_angle_deg", mtype)
        if entry_mode == "magnitude_angle":
            item["value"] = _prompt_float("Value (magnitude)", default=None)
            item["value_angle_deg"] = _prompt_float(
                "Angle deg (optional)", default=0.0, suggestions=angle_choices
            )
        else:
            item["value_real"] = _prompt_float("Real part", default=None)
            item["value_imag"] = _prompt_float("Imag part", default=None)

        # Optional fields depending on measurement type
        if mtype == "soil_resistivity":
            dist_choices = _existing_item_values("measurement_distance_m", mtype)
            item["measurement_distance_m"] = _prompt_float(
                "Measurement distance m (optional)", default=None, suggestions=dist_choices
            )
        if mtype in {"earthing_impedance", "earthing_resistance"}:
            add_res_choices = _existing_item_values("additional_resistance_ohm", mtype)
            item["additional_resistance_ohm"] = _prompt_float(
                "Additional series resistance Ω (optional)",
                default=None,
                suggestions=add_res_choices,
            )

        suggested_unit = "Ω" if "impedance" in mtype or "resistance" in mtype else "A"
        unit_choices = _existing_item_units(mtype)
        unit_default = unit_choices[0] if unit_choices else suggested_unit
        item["unit"] = _prompt_text(
            "Unit",
            default=unit_default,
            completer=_word_choice(unit_choices or [suggested_unit]),
        )
        item["description"] = _prompt_text("Item description (optional)", default="")

        iid = create_item(item, measurement_id=mid)
        item["id"] = iid
        created_items.append(item)
        typer.echo(f"  Added item id={iid} ({mtype})")

    typer.echo("Done.")
    try:
        meas, _ = read_measurements_by(id=mid)
        measurement_summary = meas[0] if meas else measurement_data
        items_summary = meas[0]["items"] if meas else created_items
    except Exception:
        measurement_summary = measurement_snapshot
        items_summary = created_items
    _print_measurement_summary(mid, measurement_summary, items_summary)


@app.command("list-measurements")
def list_measurements() -> None:
    """List measurements with basic metadata."""
    measurements, _ = read_measurements_by()
    if not measurements:
        typer.echo("No measurements found.")
        return

    for m in measurements:
        loc = m.get("location") or {}
        loc_name = loc.get("name") or "n/a"
        typer.echo(
            f"[id={m.get('id')}] {loc_name} | method={m.get('method')} | asset={m.get('asset_type')} | items={len(m.get('items', []))}"
        )


@app.command("list-items")
def list_items(
    measurement_id: int = typer.Argument(..., help="Measurement ID"),
    measurement_type: Optional[str] = typer.Option(None, "--type", help="Filter by measurement_type"),
) -> None:
    """List items for a given measurement."""
    filters: dict[str, Any] = {"measurement_id": measurement_id}
    if measurement_type:
        filters["measurement_type"] = measurement_type

    items, _ = read_items_by(**filters)
    if not items:
        typer.echo("No items found.")
        return

    for it in items:
        typer.echo(
            f"[id={it.get('id')}] type={it.get('measurement_type')} freq={it.get('frequency_hz')} value={it.get('value')} unit={it.get('unit')}"
        )


@app.command("add-item")
def add_item(
    measurement_id: int = typer.Argument(..., help="Measurement ID to attach the item to")
) -> None:
    """Interactive wizard to add a single item to an existing measurement."""
    mtypes = _measurement_types()
    mtype = _prompt_choice("Measurement type", choices=mtypes)
    freq_choices = _existing_item_values("frequency_hz", mtype)
    freq = _prompt_float("Frequency Hz (optional)", default=50.0, suggestions=freq_choices)
    entry_mode = _prompt_choice(
        "Value entry mode",
        choices=["magnitude_angle", "real_imag"],
        default="magnitude_angle",
    )

    item: dict[str, Any] = {
        "measurement_type": mtype,
        "frequency_hz": freq,
    }

    angle_choices = _existing_item_values("value_angle_deg", mtype)
    if entry_mode == "magnitude_angle":
        item["value"] = _prompt_float("Value (magnitude)", default=None)
        item["value_angle_deg"] = _prompt_float(
            "Angle deg (optional)", default=0.0, suggestions=angle_choices
        )
    else:
        item["value_real"] = _prompt_float("Real part", default=None)
        item["value_imag"] = _prompt_float("Imag part", default=None)

    if mtype == "soil_resistivity":
        dist_choices = _existing_item_values("measurement_distance_m", mtype)
        item["measurement_distance_m"] = _prompt_float(
            "Measurement distance m (optional)", default=None, suggestions=dist_choices
        )
    if mtype in {"earthing_impedance", "earthing_resistance"}:
        add_res_choices = _existing_item_values("additional_resistance_ohm", mtype)
        item["additional_resistance_ohm"] = _prompt_float(
            "Additional series resistance Ω (optional)", default=None, suggestions=add_res_choices
        )

    suggested_unit = "Ω" if "impedance" in mtype or "resistance" in mtype else "A"
    unit_choices = _existing_item_units(mtype)
    unit_default = unit_choices[0] if unit_choices else suggested_unit
    item["unit"] = _prompt_text(
        "Unit",
        default=unit_default,
        completer=_word_choice(unit_choices or [suggested_unit]),
    )
    item["description"] = _prompt_text("Item description (optional)", default="")

    iid = create_item(item, measurement_id=measurement_id)
    typer.echo(f"Added item id={iid} to measurement id={measurement_id}")


@app.command("import-json")
def import_json(path: Path = typer.Argument(..., exists=True, help="Path to JSON with measurement data")) -> None:
    """
    Import measurement(s) from JSON.

    Accepts either:
      - a list of measurement dicts (each optionally containing 'items'), or
      - a single measurement dict with optional 'items'.
    """
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        raise typer.Exit(code=1) from exc

    measurements: List[dict[str, Any]]
    if isinstance(data, list):
        measurements = data
    elif isinstance(data, dict):
        measurements = [data]
    else:
        typer.echo("Unsupported JSON structure; expected object or array.")
        raise typer.Exit(code=1)

    created: List[Tuple[int, int]] = []
    for m in measurements:
        items = m.pop("items", [])
        mid = create_measurement(m)
        for it in items:
            create_item(it, measurement_id=mid)
        created.append((mid, len(items)))

    typer.echo(f"Imported {len(created)} measurement(s): " + ", ".join(f"id={mid} items={count}" for mid, count in created))


@app.command("export-json")
def export_json(
    path: Path = typer.Argument(..., help="Output JSON file"),
    measurement_ids: Optional[List[int]] = typer.Option(
        None,
        "--measurement-id",
        "-m",
        help="Restrict to these measurement IDs (repeatable).",
    ),
) -> None:
    """Export measurements (and nested items) to JSON."""
    filters: dict[str, Any] = {}
    if measurement_ids:
        filters["id__in"] = measurement_ids
    export_measurements_to_json(str(path), **filters)
    typer.echo(f"Wrote {path}")


@app.command("set-default-db")
def set_default_db(path: Path = typer.Argument(..., help="Path to store as default DB")) -> None:
    """Store a default database path in ~/.config/groundmeas/config.json."""
    resolved = str(path.expanduser().resolve())
    Path(resolved).parent.mkdir(parents=True, exist_ok=True)
    _save_default_db(resolved)
    typer.echo(f"Default DB path saved to {CONFIG_PATH} → {resolved}")


def _main() -> None:
    app()


if __name__ == "__main__":
    _main()
