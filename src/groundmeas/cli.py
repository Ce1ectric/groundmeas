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
    update_item,
    update_measurement,
)
from .export import export_measurements_to_json
from .models import MeasurementType
from .analytics import (
    calculate_split_factor,
    impedance_over_frequency,
    real_imag_over_frequency,
    rho_f_model,
    shield_currents_for_location,
    voltage_vt_epr,
)
from .plots import plot_imp_over_f, plot_rho_f_model, plot_voltage_vt_epr

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


def _load_measurement(measurement_id: int) -> dict[str, Any]:
    recs, _ = read_measurements_by(id=measurement_id)
    if not recs:
        raise typer.Exit(f"Measurement id={measurement_id} not found")
    return recs[0]


def _load_item(item_id: int) -> dict[str, Any]:
    recs, _ = read_items_by(id=item_id)
    if not recs:
        raise typer.Exit(f"MeasurementItem id={item_id} not found")
    return recs[0]


def _dump_or_print(data: Any, json_out: Optional[Path]) -> None:
    if json_out:
        json_out.write_text(json.dumps(data, indent=2))
        typer.echo(f"Wrote {json_out}")
    else:
        typer.echo(json.dumps(data, indent=2))


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


@app.command("edit-measurement")
def edit_measurement(
    measurement_id: int = typer.Argument(..., help="Measurement ID to edit")
) -> None:
    """Edit a measurement with defaults pulled from the database."""
    rec = _load_measurement(measurement_id)
    loc = rec.get("location") or {}

    typer.echo(f"Editing measurement id={measurement_id}. Press Enter to keep existing values.")

    existing_locs = _existing_locations()
    loc_name = _prompt_text("Location name", default=loc.get("name"), completer=_word_choice(existing_locs))
    lat = _prompt_float("Latitude (optional)", default=loc.get("latitude"))
    lon = _prompt_float("Longitude (optional)", default=loc.get("longitude"))
    alt = _prompt_float("Altitude (optional)", default=loc.get("altitude"))

    method = _prompt_choice(
        "Method",
        choices=["staged_fault_test", "injection_remote_substation", "injection_earth_electrode"],
        default=rec.get("method"),
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
        default=rec.get("asset_type"),
    )

    voltage_choices = _existing_measurement_values("voltage_level_kv")
    fault_res_choices = _existing_measurement_values("fault_resistance_ohm")
    operator_choices = _existing_measurement_values("operator")

    voltage = _prompt_float(
        "Voltage level kV (optional)",
        default=rec.get("voltage_level_kv"),
        suggestions=voltage_choices,
    )
    fault_res = _prompt_float(
        "Fault resistance Ω (optional)",
        default=rec.get("fault_resistance_ohm"),
        suggestions=fault_res_choices,
    )
    description = _prompt_text("Description (optional)", default=rec.get("description") or "")
    operator_default = rec.get("operator") or (operator_choices[0] if operator_choices else "")
    operator = _prompt_text(
        "Operator (optional)",
        default=operator_default,
        completer=_word_choice(operator_choices),
    )

    updates: dict[str, Any] = {
        "method": method,
        "asset_type": asset,
        "voltage_level_kv": voltage,
        "fault_resistance_ohm": fault_res,
        "description": description or None,
        "operator": operator or None,
        "location": {
            "name": loc_name,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
        },
    }

    updated = update_measurement(measurement_id, updates)
    if not updated:
        raise typer.Exit(f"Measurement id={measurement_id} not found")

    rec_after = _load_measurement(measurement_id)
    _print_measurement_summary(measurement_id, rec_after, rec_after.get("items", []))


@app.command("edit-item")
def edit_item(item_id: int = typer.Argument(..., help="MeasurementItem ID to edit")) -> None:
    """Edit a measurement item with defaults from the database."""
    item = _load_item(item_id)
    mtypes = _measurement_types()
    mtype = _prompt_choice("Measurement type", choices=mtypes, default=item.get("measurement_type"))

    freq_choices = _existing_item_values("frequency_hz", mtype)
    freq = _prompt_float("Frequency Hz (optional)", default=item.get("frequency_hz"), suggestions=freq_choices)

    # decide entry mode based on existing data
    entry_mode_default = "real_imag" if item.get("value_real") is not None or item.get("value_imag") is not None else "magnitude_angle"
    entry_mode = _prompt_choice(
        "Value entry mode",
        choices=["magnitude_angle", "real_imag"],
        default=entry_mode_default,
    )

    angle_choices = _existing_item_values("value_angle_deg", mtype)
    if entry_mode == "magnitude_angle":
        val = item.get("value")
        ang = item.get("value_angle_deg")
        value = _prompt_float("Value (magnitude)", default=val)
        angle = _prompt_float("Angle deg (optional)", default=ang, suggestions=angle_choices)
        item_updates = {"value": value, "value_angle_deg": angle, "value_real": None, "value_imag": None}
    else:
        val_r = item.get("value_real")
        val_i = item.get("value_imag")
        value_real = _prompt_float("Real part", default=val_r)
        value_imag = _prompt_float("Imag part", default=val_i)
        item_updates = {"value_real": value_real, "value_imag": value_imag, "value": None, "value_angle_deg": None}

    dist = None
    add_res = None
    if mtype == "soil_resistivity":
        dist_choices = _existing_item_values("measurement_distance_m", mtype)
        dist = _prompt_float(
            "Measurement distance m (optional)",
            default=item.get("measurement_distance_m"),
            suggestions=dist_choices,
        )
    if mtype in {"earthing_impedance", "earthing_resistance"}:
        add_res_choices = _existing_item_values("additional_resistance_ohm", mtype)
        add_res = _prompt_float(
            "Additional series resistance Ω (optional)",
            default=item.get("additional_resistance_ohm"),
            suggestions=add_res_choices,
        )

    suggested_unit = "Ω" if "impedance" in mtype or "resistance" in mtype else "A"
    unit_choices = _existing_item_units(mtype)
    unit_default = item.get("unit") or (unit_choices[0] if unit_choices else suggested_unit)
    unit = _prompt_text(
        "Unit",
        default=unit_default,
        completer=_word_choice(unit_choices or [suggested_unit]),
    )
    desc = _prompt_text("Item description (optional)", default=item.get("description") or "")

    updates: dict[str, Any] = {
        "measurement_type": mtype,
        "frequency_hz": freq,
        "unit": unit,
        "description": desc or None,
        "measurement_distance_m": dist if mtype == "soil_resistivity" else None,
        "additional_resistance_ohm": add_res if mtype in {"earthing_impedance", "earthing_resistance"} else None,
    }
    updates.update(item_updates)

    updated = update_item(item_id, updates)
    if not updated:
        raise typer.Exit(f"MeasurementItem id={item_id} not found")
    typer.echo(f"Updated item id={item_id}")


@app.command("impedance-over-frequency")
def cli_impedance_over_frequency(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement ID(s)"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write result to JSON file"),
) -> None:
    """Return impedance over frequency for the given measurement IDs."""
    ids = measurement_ids if len(measurement_ids) > 1 else measurement_ids[0]
    data = impedance_over_frequency(ids)
    _dump_or_print(data, json_out)


@app.command("real-imag-over-frequency")
def cli_real_imag_over_frequency(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement ID(s)"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write result to JSON file"),
) -> None:
    """Return real/imag over frequency for the given measurement IDs."""
    ids = measurement_ids if len(measurement_ids) > 1 else measurement_ids[0]
    data = real_imag_over_frequency(ids)
    _dump_or_print(data, json_out)


@app.command("rho-f-model")
def cli_rho_f_model(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement IDs to fit"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write coefficients to JSON"),
) -> None:
    """Fit the rho–f model and output coefficients."""
    coeffs = rho_f_model(measurement_ids)
    result = {
        "k1": coeffs[0],
        "k2": coeffs[1],
        "k3": coeffs[2],
        "k4": coeffs[3],
        "k5": coeffs[4],
    }
    _dump_or_print(result, json_out)


@app.command("voltage-vt-epr")
def cli_voltage_vt_epr(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement ID(s)"),
    frequency: float = typer.Option(50.0, "--frequency", "-f", help="Frequency in Hz"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write result to JSON file"),
) -> None:
    """Calculate per-ampere touch voltages and EPR for measurements."""
    ids = measurement_ids if len(measurement_ids) > 1 else measurement_ids[0]
    data = voltage_vt_epr(ids, frequency=frequency)
    _dump_or_print(data, json_out)


@app.command("shield-currents")
def cli_shield_currents(
    location_id: int = typer.Argument(..., help="Location ID to search under"),
    frequency_hz: Optional[float] = typer.Option(None, "--frequency", "-f", help="Optional frequency filter"),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write result to JSON file"),
) -> None:
    """List shield_current items available for a location."""
    data = shield_currents_for_location(location_id=location_id, frequency_hz=frequency_hz)
    _dump_or_print(data, json_out)


@app.command("calculate-split-factor")
def cli_calculate_split_factor(
    earth_fault_current_id: int = typer.Option(..., "--earth-fault-id", help="MeasurementItem id for earth_fault_current"),
    shield_current_ids: List[int] = typer.Option(..., "--shield-id", help="Shield current item id(s)", show_default=False),
    json_out: Optional[Path] = typer.Option(None, "--json-out", help="Write result to JSON file"),
) -> None:
    """Compute split factor and local earthing current."""
    data = calculate_split_factor(earth_fault_current_id=earth_fault_current_id, shield_current_ids=shield_current_ids)
    _dump_or_print(data, json_out)


@app.command("plot-impedance")
def cli_plot_impedance(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement ID(s)"),
    normalize_freq_hz: Optional[float] = typer.Option(None, "--normalize", help="Normalize by impedance at this frequency"),
    output: Path = typer.Option(..., "--out", "-o", help="Output image file (e.g., plot.png)"),
) -> None:
    """Generate impedance vs frequency plot and save to a file."""
    fig = plot_imp_over_f(measurement_ids, normalize_freq_hz=normalize_freq_hz)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    typer.echo(f"Wrote {output}")


@app.command("plot-rho-f-model")
def cli_plot_rho_f_model(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement IDs"),
    rho_f_coeffs: Optional[List[float]] = typer.Option(
        None,
        "--rho-f",
        help="Coefficients k1 k2 k3 k4 k5 (if omitted, they are fitted).",
    ),
    rho: List[float] = typer.Option([100.0], "--rho", help="Rho values to plot (repeatable)"),
    output: Path = typer.Option(..., "--out", "-o", help="Output image file"),
) -> None:
    """Plot measured impedance and rho–f model, save to file."""
    if rho_f_coeffs and len(rho_f_coeffs) != 5:
        raise typer.Exit("Provide exactly five coefficients for --rho-f")
    coeffs = tuple(rho_f_coeffs) if rho_f_coeffs else rho_f_model(measurement_ids)
    fig = plot_rho_f_model(measurement_ids, coeffs, rho=rho)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    typer.echo(f"Wrote {output}")


@app.command("plot-voltage-vt-epr")
def cli_plot_voltage_vt_epr(
    measurement_ids: List[int] = typer.Argument(..., help="Measurement ID(s)"),
    frequency: float = typer.Option(50.0, "--frequency", "-f", help="Frequency in Hz"),
    output: Path = typer.Option(..., "--out", "-o", help="Output image file"),
) -> None:
    """Plot EPR and touch voltages, save to file."""
    fig = plot_voltage_vt_epr(measurement_ids, frequency=frequency)
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output)
    typer.echo(f"Wrote {output}")

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
