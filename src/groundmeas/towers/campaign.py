"""Evaluate a complete measurement campaign (the ``calc`` step).

`calculate_summary` reads every measurement of the campaign folder,
determines fault current, reduction factor and clearing time per tower,
assesses each tower with
`GroundingSystemAnalysis`
and writes

* one JSON file per tower (input for the protocols and statistics),
* the Excel summary of all towers,
* the updated grid-data workbook (fault current, reduction factor, clearing
  time and position of every measured tower).

Priority of the grid values per tower (highest first):

* fault current: flat value from the ``Leitungsschutz`` sheet > short-circuit
  line model > value already in the grid-data workbook > configuration default,
* reduction factor: flat value from ``Leitungsschutz`` > workbook > default,
* clearing time: ``Leitungsschutz`` (position on the line) > workbook > default.
"""

from __future__ import annotations

import copy
import datetime
import json
import logging
import math
import numbers
import os
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..instruments.omicron import informative_locations
from .analysis import GroundingSystemAnalysis, LineModel
from .config import ConfigDict, read_config, read_export_json
from .files import read_from_device
from .i18n import translate
from .line_protection import LineProtectionTable
from .naming import (
    normalize_text,
    normalize_tower_id,
    safe_filename,
    tower_sort_key,
)
from .paths import ensure_directory

__all__ = [
    "CATEGORY_MEASURES",
    "CATEGORY_UT",
    "CATEGORY_ZE",
    "DESCRIPTION_REQUIRED_COLUMNS",
    "GRID_COLUMNS",
    "assessment_category",
    "assessment_text",
    "build_touch_voltage_labels",
    "calculate_summary",
    "find_unique_line_tower",
    "load_line_protection",
    "sc_data_to_excel",
    "select_footing_resistance",
    "split_locations",
    "train_sc_line_model",
]

logger = logging.getLogger(__name__)

GRID_COLUMNS = [
    "Mast",
    "Leitung",
    "Reduktionsfaktor",
    "Abschaltzeit",
    "Fehlerstrom",
    "Lage_Prozent",
    "Hinweis_Abschaltzeit",
]
"""Columns written to the grid-data workbook (further columns are kept)."""

DESCRIPTION_REQUIRED_COLUMNS = [
    "Leitung",
    "Mast",
    "Messung_RA_Profil_bool",
    "Messung_RA_Einzelwert_Ohm",
    "Entfernung_Hilfserder_m",
    "Messpunkte_UT",
]
"""Columns the measurement-description workbook must provide."""

# Assessment categories stored in the JSON field ``Bewertung_Kategorie``.
CATEGORY_ZE = "ZE"
r"""Compliant because the earth potential rise is limited: $U_E \le 2\,U_{TP}$."""
CATEGORY_UT = "UT"
r"""Compliant because all measured touch voltages are permissible: $U_T \le U_{TP}$."""
CATEGORY_MEASURES = "MASS"
"""Not compliant, measures required (German *Maßnahmen*)."""

_VERDICT_KEYS = {
    CATEGORY_MEASURES: "verdict_measures",
    CATEGORY_UT: "verdict_ut_ok",
    CATEGORY_ZE: "verdict_ze_ok",
}

RA_DEVIATION_LIMIT = 0.20
"""Maximum relative deviation between the fall-of-potential footing resistance
and the high-frequency single value before the latter is used.
"""


# --------------------------------------------------------------------------- helpers
def _is_number(value: object) -> bool:
    """Return ``True`` for real numbers (incl. NumPy scalars) except bool and NaN."""
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, (bool, np.bool_))
        and not math.isnan(float(value))
    )


def _write_excel(df: pd.DataFrame, path: str | os.PathLike[str], **kwargs: Any) -> None:
    """Write ``df`` to ``path`` with a helpful message if the file is locked."""
    ensure_directory(Path(path).parent)
    try:
        df.to_excel(path, **kwargs)
    except PermissionError as exc:
        raise PermissionError(
            f"Cannot write {path}. The file is probably open in Excel - close it and run again."
        ) from exc


def _json_default(value: Any) -> Any:
    """Convert NumPy/pandas scalars for `json.dump`."""
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (datetime.date, datetime.datetime, pd.Timestamp)):
        return str(value)
    return str(value)


def _rounded_list(values: pd.Series, decimals: int) -> list[float]:
    """Round a numeric column and return it as a list of Python floats."""
    return [float(v) for v in np.round(values.to_numpy(dtype=float), decimals=decimals)]


def _cell(value: Any) -> Any:
    """Prepare a value copied from the measurement description for the JSON export."""
    if isinstance(value, (pd.Timestamp, datetime.date, datetime.datetime)):
        return str(value.strftime("%Y-%m-%d"))
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if (
        value is None
        or value is pd.NaT
        or (isinstance(value, float) and math.isnan(value))
    ):
        # empty cell: NaN is not valid JSON
        return ""
    return value


def _rows_for(df: pd.DataFrame, line_number: str, tower: str) -> pd.DataFrame:
    """Rows of ``df`` that belong to ``line_number`` / ``tower``."""
    lines = df["Leitung"].map(normalize_text)
    towers = df["Mast"].map(normalize_tower_id)
    return df[
        (lines == normalize_text(line_number)) & (towers == normalize_tower_id(tower))
    ]


# ------------------------------------------------------------------- grid data
def train_sc_line_model(
    line_number_list: Iterable[str], config_dict: ConfigDict | None = None
) -> LineModel:
    """Fit the short-circuit model of every line that has a training sheet.

    Parameters
    ----------
    line_number_list : iterable of str
        Lines of the campaign.
    config_dict : ConfigDict or None, optional
        Configuration; read from disk if omitted.

    Returns
    -------
    LineModel
        Model with one fitted curve per line that has a sheet in the
        short-circuit workbook (``sc_current_data_path``).
    """
    config = config_dict if config_dict is not None else read_config()
    model = LineModel()
    path = config.get("sc_current_data_path")
    try:
        available_sheets: set[str] = set()
        if path:
            with pd.ExcelFile(path, engine="openpyxl") as workbook:
                available_sheets = {str(name) for name in workbook.sheet_names}
    except Exception as exc:
        logger.warning("Short-circuit data not readable (%s): %s", path, exc)
        available_sheets = set()
    for line_number in line_number_list:
        if line_number not in available_sheets:
            logger.info("No short-circuit data sheet for line %s.", line_number)
            continue
        if model.read_training_parameter(path=path, line_number=line_number) is None:
            continue
        try:
            model.train_curve_model(line_number=line_number)
        except Exception as exc:
            logger.warning(
                "Skipping the short-circuit fit for line %s: %s", line_number, exc
            )
    return model


def load_line_protection(config_dict: ConfigDict | None = None) -> LineProtectionTable:
    """Read the ``Leitungsschutz`` sheet if the feature is enabled.

    Parameters
    ----------
    config_dict : ConfigDict or None, optional
        Configuration; read from disk if omitted.

    Returns
    -------
    LineProtectionTable
        The table, or an empty table if ``line_protection.enabled`` is false.
    """
    config = config_dict if config_dict is not None else read_config()
    if not config.get("line_protection_enabled", False):
        return LineProtectionTable()
    table = LineProtectionTable.from_excel(
        config.get("sc_current_data_path"),
        config.get("line_protection_sheet", "Leitungsschutz"),
    )
    if not table.lines():
        logger.warning(
            "Line protection is enabled, but the sheet '%s' was not found; "
            "the default clearing time is used.",
            config.get("line_protection_sheet"),
        )
    return table


def sc_data_to_excel(
    model: LineModel,
    line_number_tower_dict: dict[str, set[str]],
    protection: LineProtectionTable | None = None,
    config_dict: ConfigDict | None = None,
) -> None:
    """Write fault current, reduction factor and clearing time to the grid-data workbook.

    The workbook (``path_grid_data``) is updated in place: missing towers are
    added, duplicate rows (same line and tower) are merged and the rows are
    sorted by line and tower. See the module docstring for the priorities.

    Parameters
    ----------
    model : LineModel
        Trained short-circuit model.
    line_number_tower_dict : dict
        ``{line: {tower, ...}}`` of all measured towers.
    protection : LineProtectionTable or None, optional
        Position-dependent clearing times.
    config_dict : ConfigDict or None, optional
        Configuration; read from disk if omitted.
    """
    config = config_dict if config_dict is not None else read_config()
    protection = protection if protection is not None else LineProtectionTable()
    language = config.get("language", "en")

    export_path = config["grid_data_path"]
    df = pd.read_excel(export_path, engine="openpyxl")
    for col in GRID_COLUMNS:
        if col not in df.columns:
            dtype = (
                object if col in ("Mast", "Leitung", "Hinweis_Abschaltzeit") else float
            )
            df[col] = pd.Series(dtype=dtype)
    df["Mast"] = df["Mast"].astype(str).str.replace(r"\.0$", "", regex=True)
    df["Leitung"] = df["Leitung"].astype(str)
    for col in ("Fehlerstrom", "Reduktionsfaktor", "Abschaltzeit", "Lage_Prozent"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    df["Hinweis_Abschaltzeit"] = df["Hinweis_Abschaltzeit"].astype(object)

    # merge duplicate rows (historically the same tower was appended many times)
    keys = df["Leitung"].map(normalize_text) + "|" + df["Mast"].map(normalize_tower_id)
    n_before = len(df)
    df = df.loc[~keys.duplicated(keep="first")].reset_index(drop=True)
    if len(df) != n_before:
        logger.info("Grid data: merged %d duplicate rows.", n_before - len(df))
    keys = df["Leitung"].map(normalize_text) + "|" + df["Mast"].map(normalize_tower_id)
    index = {key: i for i, key in enumerate(keys)}

    r_default = config["default_r"]
    t_default = config["default_t"]
    ik_default = config["default_fault_current"]

    for line_number, tower_set in line_number_tower_dict.items():
        has_model = line_number in model.curve_data
        for tower in sorted(tower_set):
            key = f"{normalize_text(line_number)}|{normalize_tower_id(tower)}"
            if key not in index:
                df.loc[len(df), ["Mast", "Leitung"]] = [str(tower), line_number]
                index[key] = len(df) - 1
            i = index[key]
            prot = protection.lookup(line_number, tower)

            # fault current
            model_current = None
            if has_model and (prot is None or prot.fault_current_A is None):
                try:
                    model_current = (
                        model.get_sc_current(line_number=line_number, tower=tower) * 1e3
                    )
                except ValueError as exc:
                    logger.warning(
                        "Short-circuit model not usable for tower %s: %s", tower, exc
                    )
            if prot is not None and prot.fault_current_A is not None:
                df.at[i, "Fehlerstrom"] = prot.fault_current_A
            elif model_current is not None:
                df.at[i, "Fehlerstrom"] = model_current
            elif pd.isna(df.at[i, "Fehlerstrom"]):
                df.at[i, "Fehlerstrom"] = ik_default
                logger.info(
                    "No short-circuit data for line %s tower %s: default %.1f kA.",
                    line_number,
                    tower,
                    ik_default * 1e-3,
                )

            # reduction factor
            if prot is not None and prot.reduction_factor is not None:
                df.at[i, "Reduktionsfaktor"] = prot.reduction_factor
            elif pd.isna(df.at[i, "Reduktionsfaktor"]):
                df.at[i, "Reduktionsfaktor"] = r_default

            # clearing time
            if prot is not None:
                df.at[i, "Abschaltzeit"] = prot.tripping_time_s
                df.at[i, "Lage_Prozent"] = (
                    round(prot.position_percent, 1)
                    if prot.position_percent is not None
                    else np.nan
                )
                df.at[i, "Hinweis_Abschaltzeit"] = prot.hint(language)
            elif pd.isna(df.at[i, "Abschaltzeit"]):
                df.at[i, "Abschaltzeit"] = t_default
                df.at[i, "Hinweis_Abschaltzeit"] = translate(
                    "clearing_time_default", language
                )

    df = df.sort_values(
        ["Leitung", "Mast"],
        key=lambda s: s.map(tower_sort_key) if s.name == "Mast" else s,
    )
    ordered = df[GRID_COLUMNS + [c for c in df.columns if c not in GRID_COLUMNS]]
    _write_excel(ordered, export_path, index=False, engine="openpyxl")


def find_unique_line_tower(data_list: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """Group the measured towers by line.

    Parameters
    ----------
    data_list : iterable of dict
        Measurements as returned by
        `read_from_device`.

    Returns
    -------
    dict
        ``{line: {tower, ...}}``.
    """
    unique_lines_tower: dict[str, set[str]] = defaultdict(set)
    for item in data_list:
        unique_lines_tower[str(item["Leitung"])].add(str(item["Mast"]))
    return unique_lines_tower


# --------------------------------------------------------------- touch voltages
def split_locations(value: object) -> list[str]:
    """Split the ``Messpunkte_UT`` cell of the measurement description.

    Parameters
    ----------
    value : object
        Comma- (or semicolon-) separated list of measuring points, e.g.
        ``"Mast, Mast, Fence"``; empty cells give an empty list.

    Returns
    -------
    list of str
        Stripped names (empty entries are kept as ``""``).
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    text = normalize_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;]", text)]


def _location_key(name: str) -> str:
    """Comparison key for location names (case, umlauts, separators ignored)."""
    text = normalize_text(name).upper()
    for umlaut, replacement in (
        ("Ä", "AE"),
        ("Ö", "OE"),
        ("Ü", "UE"),
        ("ß", "SS"),
        ("ẞ", "SS"),
    ):
        text = text.replace(umlaut, replacement)
    return re.sub(r"[\s\-_.]", "", text)


def _pretty_location(name: str) -> str:
    """Readable form of an HGT1 location (``"E-SAEULE"`` -> ``"E-Saeule"``)."""
    text = normalize_text(name)
    return text.title() if text.isupper() else text


def _map_description(locations: Sequence[str], n: int) -> list[str] | None:
    """Assign description entries to ``n`` readings (one each, or one per pair)."""
    m = len(locations)
    if m == n:
        return list(locations)
    if m and 2 * m == n:
        # every measuring point is measured twice (termination 1k and 2x1k)
        return [locations[i // 2] for i in range(n)]
    return None


def build_touch_voltage_labels(
    touch_voltage: pd.DataFrame,
    description_locations: Sequence[str],
    language: str = "en",
    context: str = "",
) -> tuple[list[str], list[str]]:
    """Label every touch-voltage reading with its measuring point.

    The measuring point of each reading is taken from the HGT1 report
    (column ``Location``) when the instrument recorded real names. Otherwise
    the list from the measurement description is used: one entry per reading,
    or one entry per measuring point when every point was measured twice
    (with and without additional resistor). If neither fits, the list is
    repeated cyclically and a warning is logged.

    Parameters
    ----------
    touch_voltage : pandas.DataFrame
        HGT1 readings (columns ``Location`` and ``Termination`` if available).
    description_locations : sequence of str
        Measuring points from the measurement description, see
        `split_locations`.
    language : str, optional
        Language of the termination suffix.
    context : str, optional
        Text used in log messages (e.g. ``"LX-01 tower 8"``).

    Returns
    -------
    labels : list of str
        E.g. ``"Mast (with additional resistor 1kOhm)"``.
    terminations : list of str
        Raw HGT1 termination per reading (``"1k"``, ``"2x1k"``, ...).
    """
    n = len(touch_voltage)
    if "Termination" in touch_voltage.columns:
        terminations = [str(t).strip() for t in touch_voltage["Termination"]]
    else:
        terminations = [""] * n
    term_labels = {
        "1k": translate("termination_1k", language),
        "2x1k": translate("termination_2x1k", language),
    }
    hgt_locations = (
        [normalize_text(x) for x in touch_voltage["Location"]]
        if "Location" in touch_voltage.columns
        else []
    )
    mapped = _map_description(description_locations, n)

    if hgt_locations and informative_locations(hgt_locations):
        bases = []
        mismatch = False
        for i, location in enumerate(hgt_locations):
            if mapped is not None and _location_key(mapped[i]) == _location_key(
                location
            ):
                bases.append(mapped[i])
            else:
                bases.append(_pretty_location(location))
                mismatch = mismatch or mapped is not None
        if mismatch:
            logger.warning(
                "%s: the measuring points of the description (%s) differ from the HGT1 "
                "report; the locations recorded by the HGT1 are used.",
                context,
                ", ".join(description_locations),
            )
    elif mapped is not None:
        bases = mapped
    elif description_locations:
        logger.warning(
            "%s: %d measuring points in the description for %d readings; the list is "
            "repeated cyclically - please check the labels.",
            context,
            len(description_locations),
            n,
        )
        bases = [
            description_locations[i % len(description_locations)] for i in range(n)
        ]
    else:
        bases = [""] * n

    unknown = translate("unknown_location", language)
    labels = []
    for base, termination in zip(bases, terminations, strict=True):
        name = base.strip() or unknown
        suffix = term_labels.get(termination, termination)
        labels.append(f"{name} ({suffix})" if suffix else name)
    return labels, terminations


# --------------------------------------------------------------- assessment
def select_footing_resistance(
    ra_compano: float | None, ra_hf: float | None, language: str = "en"
) -> tuple[float | None, str]:
    """Choose the footing resistance shown in the protocol.

    The fall-of-potential value (COMPANO) is preferred. The high-frequency
    single value is used if no COMPANO value exists or if both deviate by more
    than `RA_DEVIATION_LIMIT` (relative to the high-frequency value).

    Parameters
    ----------
    ra_compano : float or None
        Footing resistance at 62 % from the COMPANO profile in Ohm.
    ra_hf : float or None
        High-frequency single value from the measurement description in Ohm.
    language : str, optional
        Language of the source hint.

    Returns
    -------
    tuple of (float or None, str)
        Selected value and a hint (empty for the COMPANO value).
    """
    hint = translate("ra_hint_high_frequency", language)
    if ra_compano is not None and ra_hf is not None:
        if abs(ra_compano - ra_hf) / ra_hf > RA_DEVIATION_LIMIT:
            return ra_hf, hint
        return ra_compano, ""
    if ra_hf is not None:
        return ra_hf, hint
    if ra_compano is not None:
        return ra_compano, ""
    return None, ""


def assessment_category(gsa: GroundingSystemAnalysis) -> str:
    r"""Return the assessment category of an evaluated tower.

    Parameters
    ----------
    gsa : GroundingSystemAnalysis
        Evaluated tower.

    Returns
    -------
    str
        `CATEGORY_ZE` if the earthing impedance criterion
        ($U_E \le 2 U_{TP}$) is met, otherwise `CATEGORY_UT` if the
        measured touch voltages are permissible, else `CATEGORY_MEASURES`.
    """
    if gsa.impedance_to_high and gsa.touch_voltage_to_high:
        return CATEGORY_MEASURES
    if gsa.impedance_to_high:
        return CATEGORY_UT
    return CATEGORY_ZE


def assessment_text(category: str, language: str = "en") -> str:
    """Readable verdict for an assessment category.

    Parameters
    ----------
    category : str
        One of `CATEGORY_ZE`, `CATEGORY_UT`, `CATEGORY_MEASURES`.
    language : str, optional
        Output language.

    Returns
    -------
    str
        Sentence for the protocol (``"No assessment possible."`` for unknown
        categories).
    """
    return translate(_VERDICT_KEYS.get(category, "verdict_none"), language)


# --------------------------------------------------------------------- main step
def calculate_summary(
    excel_export: bool = True,
    json_export: bool = True,
    config_path: str | os.PathLike[str] | None = None,
) -> pd.DataFrame:
    """Evaluate all towers of a campaign.

    Parameters
    ----------
    excel_export : bool, optional
        Write the Excel summary (``path_summary``).
    json_export : bool, optional
        Write one JSON file per tower into ``json_export_path``.
    config_path : str, os.PathLike or None, optional
        Configuration file; see
        `resolve_config_path`.

    Returns
    -------
    pandas.DataFrame
        One row per evaluated tower (same content as the Excel summary).

    Raises
    ------
    FileNotFoundError, ConfigError
        If the configuration is missing or invalid.
    ValueError
        If the measurement description lacks required columns.
    """
    config = read_config(config_path)
    language = config["language"]
    json_export_path = config["json_export_path"]
    curve = dict(zip(config["t_s"], config["U_TP_V"], strict=True))
    curve_extended = dict(zip(config["t_s"], config["U_TP_ext_V"], strict=True))

    device_data_list = read_from_device(
        directory_path=config["directory_path"],
        structure=config["grounding_impedance_structure"],
        nominal_frequency=config["nominal_frequency_Hz"],
        language=language,
    )
    lines_and_towers = dict(find_unique_line_tower(device_data_list))
    model = train_sc_line_model(list(lines_and_towers), config)
    protection = load_line_protection(config)
    sc_data_to_excel(model, lines_and_towers, protection, config)

    grid_data_df = pd.read_excel(config["grid_data_path"])
    description_df = pd.read_excel(config["measurement_description_path"])
    missing = [
        c for c in DESCRIPTION_REQUIRED_COLUMNS if c not in description_df.columns
    ]
    if missing:
        raise ValueError(
            f"The measurement description {config['measurement_description_path']} lacks the "
            f"columns {missing}"
        )
    json_template_base = read_export_json() if json_export else {}
    if json_export:
        ensure_directory(json_export_path)
    grid_changed = False
    summary_rows: list[dict[str, Any]] = []

    for measurement in device_data_list:
        line_number = measurement["Leitung"]
        tower = str(measurement["Mast"])
        context = f"{line_number} tower {tower}"
        if measurement.get("UT_V") is None:
            logger.warning("Skipping %s: no touch-voltage (HGT1) data.", context)
            continue

        # ---- grid values -------------------------------------------------
        grid_row = _rows_for(grid_data_df, line_number, tower)
        if not grid_row.empty:
            fault_current = grid_row["Fehlerstrom"].iloc[0]
            fault_duration = grid_row["Abschaltzeit"].iloc[0]
            reduction_factor = grid_row["Reduktionsfaktor"].iloc[0]
            position_percent = (
                grid_row["Lage_Prozent"].iloc[0]
                if "Lage_Prozent" in grid_row
                else np.nan
            )
            tripping_hint = (
                grid_row["Hinweis_Abschaltzeit"].iloc[0]
                if "Hinweis_Abschaltzeit" in grid_row
                else ""
            )
        else:
            position_percent = np.nan
            tripping_hint = translate("clearing_time_default", language)
            fault_current = None
            if line_number in model.curve_data:
                try:
                    fault_current = (
                        model.get_sc_current(line_number=line_number, tower=tower) * 1e3
                    )
                except Exception as exc:
                    logger.warning(
                        "Short-circuit model failed for %s: %s", context, exc
                    )
            if fault_current is None:
                fault_current = config["default_fault_current"]
                logger.info(
                    "No grid data or short-circuit model for %s; default fault current %.1f kA.",
                    context,
                    fault_current * 1e-3,
                )
            fault_duration = config["default_t"]
            reduction_factor = config["default_r"]
            new_row = pd.DataFrame(
                {
                    "Mast": [tower],
                    "Leitung": [line_number],
                    "Reduktionsfaktor": [reduction_factor],
                    "Abschaltzeit": [fault_duration],
                    "Fehlerstrom": [fault_current],
                }
            )
            grid_data_df = pd.concat([grid_data_df, new_row], ignore_index=True)
            grid_changed = True

        # ---- measurement description ------------------------------------
        description_row = _rows_for(description_df, line_number, tower)
        if description_row.empty:
            logger.warning(
                "Skipping %s: no row in the measurement description.", context
            )
            continue
        # NB: an empty cell counts as "profile measured" (bool(NaN) is True)
        ra_profile_measured = bool(description_row["Messung_RA_Profil_bool"].iloc[0])
        ra_single = description_row["Messung_RA_Einzelwert_Ohm"].iloc[0]
        current_probe_dist = description_row["Entfernung_Hilfserder_m"].iloc[0]
        touch_locations = split_locations(description_row["Messpunkte_UT"].iloc[0])

        updated: dict[str, Any] = {
            "Auswertung_Vorname": config["evaluation_first_name"],
            "Auswertung_Name": config["evaluation_last_name"],
            "Auswertung_Firma": config["evaluation_company"],
        }
        analysis_kwargs: dict[str, Any] = {
            "impedance_to_ground": measurement["ZE_Ohm"],
            "touch_voltage": measurement["UT_V"],
            "fault_current": fault_current,
            "fault_duration": fault_duration,
            "reduction_factor": reduction_factor,
            "extended_resistance": False,  # U_D2 is not used for the assessment
            "current_probe_dist": current_probe_dist,
            "touch_voltage_curve": curve,
            "touch_voltage_curve_extended": curve_extended,
            "touch_voltage_evaluation": config["touch_voltage_evaluation"],
        }

        ra_compano = None
        gsa = None
        try:
            if ra_profile_measured:
                try:
                    gsa = GroundingSystemAnalysis(
                        residual_resistance=measurement["RA_Ohm"], **analysis_kwargs
                    )
                    residual = gsa.residual_resistance
                    residual_62 = gsa.residual_resistance_62
                    if residual is None or residual_62 is None:
                        raise ValueError("rejected by the plausibility check")
                    ra_compano = float(residual_62)
                    residual_current = residual["ResidualCurrent"].mean()
                    updated["IA_A"] = float(
                        np.round(np.abs(residual_current), decimals=3)
                    )
                    updated["RA_Ohm"] = _rounded_list(residual["Impedance"], 3)
                except Exception as exc:
                    logger.warning(
                        "Footing-resistance profile of %s not usable (%s); evaluated without it.",
                        context,
                        exc,
                    )
                    gsa, ra_compano = None, None
            if gsa is None:
                gsa = GroundingSystemAnalysis(**analysis_kwargs)
                updated["IA_A"] = ""
                updated["RA_Ohm"] = ""
        except Exception as exc:
            logger.error(
                "Skipping %s: evaluation failed (%s: %s).",
                context,
                type(exc).__name__,
                exc,
            )
            continue

        ra_hf = float(ra_single) if _is_number(ra_single) and ra_single > 0 else None
        ra_used, ra_hint = select_footing_resistance(ra_compano, ra_hf, language)
        updated["RA_62_Ohm"] = (
            float(np.round(ra_used, decimals=3)) if ra_used is not None else ""
        )
        updated["RA_Quelle_Hinweis"] = ra_hint
        output_summary = gsa.get_summary()
        category = assessment_category(gsa)

        if json_export:
            json_template = copy.deepcopy(json_template_base)
            common_keys = set(json_template) & set(description_row.columns)
            touch = gsa.touch_voltage
            updated["ZE_Ohm"] = _rounded_list(gsa.impedance_to_ground["Impedance"], 3)
            updated["ZE_62_Ohm"] = float(
                np.round(gsa.grounding_impedance_62, decimals=3)
            )
            updated["IE_A"] = float(
                np.round(
                    np.abs(gsa.impedance_to_ground.StepTouchCurrent.mean()), decimals=3
                )
            )
            updated["Distanz_m"] = list(gsa.impedance_to_ground.Distance.values)
            updated["Distanz_62_m"] = int(gsa.dist_62)
            updated["UT_V"] = [
                int(np.ceil(v))
                for v in touch["CalculatedTouchVoltage"].to_numpy(dtype=float)
            ]
            updated["Abschaltzeit_s"] = gsa.fault_duration
            updated["Lage_Leitung_Prozent"] = (
                float(np.round(position_percent, 1))
                if pd.notna(position_percent)
                else ""
            )
            updated["Abschaltzeit_Hinweis"] = (
                tripping_hint if isinstance(tripping_hint, str) else ""
            )
            prot = protection.lookup(line_number, tower)
            updated["Netzform"] = prot.network if prot is not None else ""
            updated["US_V"] = [float(np.round(v, decimals=3)) for v in gsa.step_voltage]
            updated["r_pu"] = float(np.round(reduction_factor, decimals=2))
            updated["Ik_kA"] = float(np.round(fault_current * 1e-3, decimals=2))
            if gsa.extended_resistance:
                updated["UD_Kurve_50341"] = "UD2"
                updated["UD_V"] = gsa.permitted_touch_voltage_extended
            else:
                updated["UD_Kurve_50341"] = "UD1"
                updated["UD_V"] = gsa.permitted_touch_voltage
            updated["UT_max_Messung_V"] = int(np.ceil(gsa.touch_voltage_max))
            updated["Auslegung_korrekt"] = assessment_text(category, language)
            updated["Bewertung_Kategorie"] = category

            for key in common_keys:
                updated[key] = _cell(description_row[key].iloc[0])

            labels, terminations = build_touch_voltage_labels(
                touch, touch_locations, language, context=context
            )
            updated["Messpunkte_UT"] = labels
            updated["Messpunkte_UT_Termination"] = terminations

            # Structured sections for further analyses (JSON only, not in the PDF).
            soil = measurement.get("rhoE_profile") or {}
            updated["Bodenwiderstand_Schlumberger"] = {
                "vorhanden": bool(soil),
                "rho_OhmMeter": [
                    float(np.round(x, 2)) for x in soil.get("rho_OhmMeter", [])
                ],
                "DistanzA_m": soil.get("DistanzA_m", []),
                "DistanzB_m": soil.get("DistanzB_m", []),
                "DistanzC_m": soil.get("DistanzC_m", []),
            }
            neighbour_df = measurement.get("neighbor_ut")
            neighbour_ut: list[float] = []
            if neighbour_df is not None:
                # neighbour readings are scaled like the own touch voltages: I_E / I_meas
                mean_step = float(
                    np.abs(gsa.impedance_to_ground["StepTouchCurrent"]).mean()
                )
                ut_scale = gsa.earth_current / mean_step if mean_step else 0.0
                neighbour_ut = [
                    float(np.round(x * ut_scale, 3))
                    for x in neighbour_df["Level50"].to_numpy(dtype=float)
                ]
            updated["Erdungsspannung_Nachbarmast"] = {
                "vorhanden": neighbour_df is not None,
                "Nachbarmast": (
                    measurement.get("neighbor_tower", "")
                    if neighbour_df is not None
                    else ""
                ),
                "UT_gemessen_V": neighbour_ut,
            }

            json_template.update(updated)
            file_path = os.path.join(
                json_export_path, safe_filename(f"{line_number}_{tower}") + ".json"
            )
            with open(file_path, "w", encoding="utf-8") as file:
                json.dump(json_template, file, indent=4, default=_json_default)

        summary_rows.append(
            {
                "Leitung": line_number,
                "Mast": tower,
                "Fehlerstrom": fault_current,
                "Abschaltzeit": fault_duration,
                "Reduktionsfaktor": reduction_factor,
                "Erweiterte_UTP": False,
                "ZE": output_summary[0],
                "ZE_zu_hoch": output_summary[1],
                "UT": output_summary[2],
                "UT_zu_hoch": output_summary[3],
                "Lage_Prozent": position_percent,
                "UT_zulaessig_V": gsa.permitted_touch_voltage,
                "ZE_62": float(gsa.grounding_impedance_62),
                "Hinweis_Abschaltzeit": (
                    tripping_hint if isinstance(tripping_hint, str) else ""
                ),
            }
        )

    df_summary = pd.DataFrame(summary_rows)
    if excel_export:
        _write_excel(df_summary, config["export_path"], index=False)
        logger.info(
            "Summary written: %s (%d towers)", config["export_path"], len(df_summary)
        )
    if grid_changed:
        _write_excel(grid_data_df, config["grid_data_path"], index=False)
    return df_summary
