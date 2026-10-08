r"""Read and validate the campaign configuration (JSON).

A campaign configuration describes where the measurement data of one
measurement campaign are stored, where results are written and which
assessment parameters apply. See `EXAMPLE_CONFIG` (written by
``gm-cli towers example-config``) and the *Tower campaigns* pages of the
documentation for all keys.

Path handling
-------------
Every path in the ``directory`` section may be

* absolute (``/Users/me/data``, ``C:\Data``),
* relative to the folder that contains the configuration file
  (``../measurements``) - recommended, because the configuration then works
  unchanged on Windows, macOS and Linux,
* written with ``~`` or environment variables (``$HOME``, ``%USERPROFILE%``).

Which configuration is used
---------------------------
`resolve_config_path` picks, in this order, the explicitly passed path,
the file named in the environment variable ``GROUNDMEAS_TOWER_CONFIG`` (set
by the CLI option ``--config``; the former name ``TOWER_GROUNDING_CONFIG`` is
still accepted) and finally ``config.json`` in the current working directory.

The module also holds the template of the per-tower JSON result
(`EXPORT_TEMPLATE`, `read_export_json`).
"""

from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
from typing import Any, TypedDict

from .i18n import DEFAULT_LANGUAGE, normalize_language
from .naming import FILE_NAME_STRUCTURES, extract_line_and_tower
from .paths import resolve_path

__all__ = [
    "CONFIG_ENV_VAR",
    "EXAMPLE_CONFIG",
    "EXPORT_TEMPLATE",
    "LEGACY_CONFIG_ENV_VAR",
    "TOUCH_VOLTAGE_EVALUATION_MODES",
    "ConfigDict",
    "ConfigError",
    "extract_line_and_tower",
    "read_config",
    "read_export_json",
    "resolve_config_path",
    "write_example_config",
]

CONFIG_ENV_VAR = "GROUNDMEAS_TOWER_CONFIG"
"""Environment variable that names the configuration file (set by ``--config``)."""

LEGACY_CONFIG_ENV_VAR = "TOWER_GROUNDING_CONFIG"
"""Name used by ``tower-grounding-measurement``; still read if `CONFIG_ENV_VAR` is unset."""

TOUCH_VOLTAGE_EVALUATION_MODES = ("with_resistor", "without_resistor", "all")
"""Allowed values of ``touch_voltage_evaluation``."""

DEFAULT_CONFIG_NAME = "config.json"


EXPORT_TEMPLATE: dict[str, Any] = {
    "Name": "",
    "Vorname": "",
    "Firma": "",
    "Datum": "",
    "Leitung": "",
    "Mast": 0,
    "Entfernung_Hilfserder_m": 0,
    "Winkel_Sonde_Hilfserder_grad": 0,
    "Winkel_Leitung_Hilfserder_grad": 0,
    "Witterung": "",
    "Messtechnik_Name": "",
    "Messfehler_Z_pu": 0.05,
    "Messfehler_U_pu": 0.02,
    "Ik_kA": 10,
    "r_pu": 0.8,
    "IA_A": 0,
    "Distanz_m": [],
    "Distanz_62_m": 0,
    "RA_Ohm": [],
    "RA_62_Ohm": 0,
    "RA_Quelle_Hinweis": "",
    "IE_A": 0,
    "ZE_Ohm": [],
    "ZE_62_Ohm": 0,
    "Messpunkte_UT": [],
    "Messpunkte_UT_Termination": [],
    "UT_V": [],
    "US_V": [],
    "rhoE_Distanz_m": 0,
    "rhoE_OhmMeter": 0,
    "Sichtbefund": "",
    "Abschaltzeit_s": 0,
    "Abschaltzeit_Hinweis": "",
    "Lage_Leitung_Prozent": "",
    "Netzform": "",
    "UD_Kurve_50341": "UD1",
    "UD_V": 0,
    "UT_max_Messung_V": 0,
    "Auslegung_korrekt": "",
    "Bewertung_Kategorie": "",
    "Auswertung_Vorname": "",
    "Auswertung_Name": "",
    "Auswertung_Firma": "",
    "Bodenwiderstand_Schlumberger": {
        "vorhanden": False,
        "rho_OhmMeter": [],
        "DistanzA_m": [],
        "DistanzB_m": [],
        "DistanzC_m": [],
    },
    "Erdungsspannung_Nachbarmast": {
        "vorhanden": False,
        "Nachbarmast": "",
        "UT_gemessen_V": [],
    },
}
"""Keys and default values of the per-tower JSON result.

The key names are German for compatibility with existing results (former
``export_format.json`` of ``tower-grounding-measurement``); their meaning is
documented on the *Tower campaign results* page.
"""

EXAMPLE_CONFIG: dict[str, Any] = {
    "_comment": "Example campaign configuration. Copy this file next to your measurement "
    "data, adjust the paths and run `gm-cli towers run --config "
    "path/to/config.json`. Relative paths are resolved against the folder of "
    "this file; ~ and environment variables ($HOME, %USERPROFILE%) are "
    "expanded. The unit of a value is given by the characters after the last "
    "underscore of its key (*_V volt, *_s seconds, *_kA kiloampere, *_Hz "
    "hertz).",
    "language": "en",
    "logo": "",
    "nominal_frequency_Hz": 50,
    "touch_voltages": {
        "_comment": "Permissible touch voltage over the fault duration "
        "t_s: U_TP_V without additional resistances (curve "
        "UD1), U_TP_ext_V with additional resistances (curve "
        "UD2, currently not used for the assessment). "
        "Intermediate durations are interpolated linearly. "
        "Check the values against the edition of EN 50522 / EN "
        "50341 and the national annex you apply.",
        "t_s": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 10.0],
        "U_TP_V": [633, 528, 410, 300, 204, 170, 140, 130, 120, 107, 80],
        "U_TP_ext_V": [1878, 1561, 1270, 831, 538, 397, 327, 287, 260, 244, 80],
    },
    "directory": {
        "path_measurements": "measurements",
        "path_grid_data": "grid_data.xlsx",
        "sc_current_data_path": "short_circuit_data.xlsx",
        "measurement_description_path": "measurement_description.xlsx",
        "json_export_path": "results",
        "path_summary": "results/summary.xlsx",
        "export_path_pdf": "results/protocols.zip",
        "grounding_impedance_structure": "PREFIX_LINENUMBER_TOWER",
    },
    "contacts": {
        "evaluation_first_name": "",
        "evaluation_last_name": "",
        "evaluation_company": "",
    },
    "default_grid_data": {
        "_comment": "Fallback values for towers without an entry in the "
        "grid-data workbook: reduction factor r, fault "
        "clearing time in s and fault current in kA.",
        "r": 0.66,
        "tripping_time": 0.4,
        "fault_current_kA": 12,
    },
    "touch_voltage_evaluation": "with_resistor",
    "line_protection": {
        "_comment": "Position-dependent fault clearing time per tower "
        "from the sheet 'Leitungsschutz' of the short-circuit "
        "workbook (sc_current_data_path). Lines that are not "
        "listed keep the value of the grid-data workbook or "
        "default_grid_data.tripping_time.",
        "enabled": False,
        "sheet_name": "Leitungsschutz",
    },
}
"""Example campaign configuration (former ``config.example.json``)."""


def read_export_json(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Return the per-tower JSON template.

    Parameters
    ----------
    path : str, os.PathLike or None, optional
        Custom template file (JSON object). By default a copy of
        `EXPORT_TEMPLATE` is returned.

    Returns
    -------
    dict
        A new dictionary on every call (safe to modify).

    Raises
    ------
    FileNotFoundError
        If ``path`` does not exist (message starts with
        ``"No json file in the given path"``).
    ValueError
        If the file is not valid JSON or does not contain an object.
    """
    if path is None:
        return copy.deepcopy(EXPORT_TEMPLATE)
    template_path = Path(path)
    try:
        with open(template_path, encoding="utf-8-sig") as file:
            template = json.load(file)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"No json file in the given path: {template_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {template_path}: {exc}") from exc
    if not isinstance(template, dict):
        raise ValueError(f"{template_path} must contain a JSON object")
    return template


def write_example_config(
    path: str | os.PathLike[str], *, overwrite: bool = False
) -> Path:
    """Write `EXAMPLE_CONFIG` as a starting point for a new campaign.

    Parameters
    ----------
    path : str or os.PathLike
        Target file (usually ``config.json`` next to the measurement data).
    overwrite : bool, optional
        Replace an existing file.

    Returns
    -------
    pathlib.Path
        The written file.

    Raises
    ------
    FileExistsError
        If the file exists and ``overwrite`` is false.
    """
    target = Path(path)
    if target.exists() and not overwrite:
        raise FileExistsError(f"{target} exists; pass overwrite=True to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(EXAMPLE_CONFIG, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


class ConfigError(ValueError):
    """Raised when the configuration is incomplete or inconsistent."""


class ConfigDict(TypedDict):
    """Flat dictionary returned by `read_config`.

    All paths are absolute strings. Optional paths that are not configured are
    empty strings.
    """

    t_s: list[float]
    U_TP_V: list[float]
    U_TP_ext_V: list[float]
    directory_path: str
    export_path: str
    grid_data_path: str
    grounding_impedance_structure: str
    measurement_description_path: str
    json_export_path: str
    sc_current_data_path: str
    default_r: float
    default_t: float
    default_fault_current: float
    export_path_pdf: str
    evaluation_first_name: str
    evaluation_last_name: str
    evaluation_company: str
    touch_voltage_evaluation: str
    line_protection_enabled: bool
    line_protection_sheet: str
    language: str
    logo_path: str
    nominal_frequency_Hz: float
    config_path: str
    config_dir: str


def resolve_config_path(config_path: str | os.PathLike[str] | None = None) -> str:
    """Return the path of the configuration file to use.

    Parameters
    ----------
    config_path : str, os.PathLike or None, optional
        Explicit configuration file. If omitted, the environment variable
        `CONFIG_ENV_VAR` is used, otherwise ``config.json`` in the
        current working directory.

    Returns
    -------
    str
        Absolute path (the file is not required to exist).
    """
    if config_path is None or str(config_path).strip() == "":
        config_path = (
            os.environ.get(CONFIG_ENV_VAR)
            or os.environ.get(LEGACY_CONFIG_ENV_VAR)
            or DEFAULT_CONFIG_NAME
        )
    expanded = os.path.expandvars(os.path.expanduser(str(config_path)))
    return os.path.abspath(expanded)


def _number(value: Any, name: str) -> float:
    """Validate that ``value`` is a finite real number (not a bool) and return it."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ConfigError(f"{name} must be a number, got {value!r}")
    return value


def _curve(values: Any, name: str) -> list[float]:
    """Validate one list of the touch-voltage table."""
    if not isinstance(values, list) or not values:
        raise ConfigError(f"touch_voltages.{name} must be a non-empty list of numbers")
    return [_number(v, f"touch_voltages.{name}") for v in values]


def _require_existing(path: Path | None, key: str, kind: str) -> Path:
    """Raise `ConfigError` unless ``path`` exists."""
    if path is None:
        raise ConfigError(f"directory.{key} is not set")
    if not path.exists():
        raise ConfigError(f"directory.{key}: {kind} does not exist: {path}")
    return path


def read_config(config_path: str | os.PathLike[str] | None = None) -> ConfigDict:
    """Read, validate and flatten the campaign configuration.

    Parameters
    ----------
    config_path : str, os.PathLike or None, optional
        Configuration file; see `resolve_config_path` for the default.

    Returns
    -------
    ConfigDict
        Flat dictionary with all settings. Relative paths are resolved
        against the folder of the configuration file.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    ConfigError
        If a required key is missing, a value has the wrong type or a
        required input path does not exist. ``ConfigError`` is a subclass of
        `ValueError`.
    """
    path = resolve_config_path(config_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Configuration file not found: {path}. Pass --config PATH or set "
            f"{CONFIG_ENV_VAR}; create a starting point with "
            "`gm-cli towers demo DIR` or `gm-cli towers example-config PATH`."
        )
    # utf-8-sig also accepts files saved with a byte-order mark (Windows editors).
    with open(path, encoding="utf-8-sig") as config_file:
        try:
            config_data = json.load(config_file)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    base_dir = os.path.dirname(path)

    # --- touch-voltage limit curves -------------------------------------
    touch = config_data.get("touch_voltages")
    if not isinstance(touch, dict):
        raise ConfigError("The section 'touch_voltages' is missing")
    t_s = _curve(touch.get("t_s"), "t_s")
    u_tp = _curve(touch.get("U_TP_V"), "U_TP_V")
    u_tp_ext = _curve(touch.get("U_TP_ext_V", u_tp), "U_TP_ext_V")
    for name, values in (("U_TP_V", u_tp), ("U_TP_ext_V", u_tp_ext)):
        if len(values) != len(t_s):
            raise ConfigError(
                f"touch_voltages: the length of t_s ({len(t_s)}) does not match "
                f"the length of {name} ({len(values)})"
            )

    # --- default grid data ----------------------------------------------
    grid = config_data.get("default_grid_data", {}) or {}
    t_tripping = _number(
        grid.get("tripping_time", 0.4), "default_grid_data.tripping_time"
    )
    reduction_factor = _number(grid.get("r", 1.0), "default_grid_data.r")
    fault_current_kA = _number(
        grid.get("fault_current_kA", 12.0), "default_grid_data.fault_current_kA"
    )

    # --- directories ----------------------------------------------------
    directory = config_data.get("directory")
    if not isinstance(directory, dict):
        raise ConfigError("The section 'directory' is missing")

    def _path(key: str) -> Path | None:
        return resolve_path(directory.get(key), base_dir)

    measurements = _require_existing(
        _path("path_measurements"), "path_measurements", "directory"
    )
    grid_data = _require_existing(_path("path_grid_data"), "path_grid_data", "file")
    description = _require_existing(
        _path("measurement_description_path"), "measurement_description_path", "file"
    )
    json_export = _path("json_export_path")
    if json_export is None:
        raise ConfigError("directory.json_export_path is not set")
    summary = _path("path_summary") or json_export / "summary.xlsx"
    short_circuit = _path("sc_current_data_path")
    zip_path = _path("export_path_pdf") or json_export / "protocols.zip"

    structure = directory.get(
        "grounding_impedance_structure", "PREFIX_LINENUMBER_TOWER"
    )
    if structure not in FILE_NAME_STRUCTURES:
        raise ConfigError(
            f"directory.grounding_impedance_structure must be one of {FILE_NAME_STRUCTURES}, "
            f"got {structure!r}"
        )

    # --- contacts and options -------------------------------------------
    contacts = config_data.get("contacts", {}) or {}
    mode = config_data.get("touch_voltage_evaluation", "with_resistor")
    if mode not in TOUCH_VOLTAGE_EVALUATION_MODES:
        raise ConfigError(
            "touch_voltage_evaluation must be one of "
            f"{TOUCH_VOLTAGE_EVALUATION_MODES}, got {mode!r}"
        )
    line_protection = config_data.get("line_protection", {}) or {}
    try:
        language = normalize_language(config_data.get("language", DEFAULT_LANGUAGE))
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    logo = resolve_path(config_data.get("logo"), base_dir)
    if logo is not None and not logo.is_file():
        raise ConfigError(f"logo: file does not exist: {logo}")
    nominal_frequency = _number(
        config_data.get("nominal_frequency_Hz", 50.0), "nominal_frequency_Hz"
    )
    if nominal_frequency <= 0:
        raise ConfigError("nominal_frequency_Hz must be positive")

    return {
        "t_s": t_s,
        "U_TP_V": u_tp,
        "U_TP_ext_V": u_tp_ext,
        "directory_path": os.fspath(measurements),
        "export_path": os.fspath(summary),
        "grid_data_path": os.fspath(grid_data),
        "grounding_impedance_structure": structure,
        "measurement_description_path": os.fspath(description),
        "json_export_path": os.fspath(json_export),
        "sc_current_data_path": os.fspath(short_circuit) if short_circuit else "",
        "default_r": reduction_factor,
        "default_t": t_tripping,
        "default_fault_current": fault_current_kA * 1e3,
        "export_path_pdf": os.fspath(zip_path),
        "evaluation_first_name": str(contacts.get("evaluation_first_name", "")),
        "evaluation_last_name": str(contacts.get("evaluation_last_name", "")),
        "evaluation_company": str(contacts.get("evaluation_company", "")),
        "touch_voltage_evaluation": mode,
        "line_protection_enabled": bool(line_protection.get("enabled", False)),
        "line_protection_sheet": str(
            line_protection.get("sheet_name", "Leitungsschutz")
        ),
        "language": language,
        "logo_path": os.fspath(logo) if logo else "",
        "nominal_frequency_Hz": float(nominal_frequency),
        "config_path": path,
        "config_dir": base_dir,
    }
