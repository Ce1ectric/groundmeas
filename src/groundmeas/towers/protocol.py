"""Create the per-tower protocols (the ``print`` and ``zip`` steps).

For every JSON result of the ``calc`` step the diagrams are drawn, the map
image (``Map_<line>_<tower>.<ext>``) is looked up and the protocol is rendered
as HTML and PDF into the folder ``html_files`` next to the JSON files.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any

import numpy as np

from . import plots, results
from .config import read_config
from .i18n import translate
from .naming import (
    has_extension,
    normalize_text,
    normalize_tower_id,
    safe_filename,
)
from .paths import ensure_directory, sorted_listdir
from .pdf import export_html, zip_pdfs

__all__ = ["HTML_FOLDER", "print_protocol", "process_single_protocol", "zip_protocols"]

logger = logging.getLogger(__name__)

HTML_FOLDER = "html_files"
"""Sub-folder of ``json_export_path`` that receives HTML, PDF and diagrams."""
_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")
# Texts that identified the termination before 0.2 (old JSON files without
# "Messpunkte_UT_Termination").
_WITHOUT_RESISTOR_TEXTS = ("kein Zusatzwiderstand", "no additional resistor")
_WITH_RESISTOR_TEXTS = ("mit Zusatzwiderstand", "with additional resistor")


def _normalize(line: object) -> str:
    """Line identifier without the prefix ``LH-``/``LH`` (used in map file names)."""
    text = normalize_text(line)
    if text.startswith("LH-"):
        return text.replace("LH-", "", 1)
    if text.startswith("LH"):
        return text.replace("LH", "", 1)
    return text


def _split_by_termination(
    import_data: dict[str, Any],
) -> tuple[list[str], list[Any], list[Any]]:
    """Touch voltages without / with additional resistor and the point names."""
    labels = import_data.get("Messpunkte_UT") or []
    values = import_data.get("UT_V") or []
    codes = import_data.get("Messpunkte_UT_Termination") or []
    if len(codes) == len(values) and any(codes):
        without = [v for c, v in zip(codes, values, strict=True) if c == "1k"]
        with_resistor = [v for c, v in zip(codes, values, strict=True) if c == "2x1k"]
        locations = [
            str(label).split(" (")[0].strip()
            for label, c in zip(labels, codes, strict=False)
            if c == "1k"
        ]
        return locations, without, with_resistor
    without = [
        v
        for lab, v in zip(labels, values, strict=False)
        if any(t in str(lab) for t in _WITHOUT_RESISTOR_TEXTS)
    ]
    with_resistor = [
        v
        for lab, v in zip(labels, values, strict=False)
        if any(t in str(lab) for t in _WITH_RESISTOR_TEXTS)
    ]
    locations = [
        str(lab).split(" (")[0].strip()
        for lab in labels
        if any(t in str(lab) for t in _WITHOUT_RESISTOR_TEXTS)
    ]
    return locations, without, with_resistor


def _find_map(line_number: str, tower: str, folders: Sequence[str]) -> str | None:
    """Return the first map image ``Map_<line>_<tower>.<ext>`` in ``folders``."""
    wanted_line = _normalize(line_number)
    wanted_tower = normalize_tower_id(tower)
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for filename in sorted_listdir(folder):
            if not has_extension(filename, *_IMAGE_EXTENSIONS):
                continue
            parts = normalize_text(filename).split("_")
            if len(parts) != 3 or not parts[0].lower().startswith("map"):
                continue
            map_line, map_tower = parts[1], parts[2].split(".")[0]
            if (
                _normalize(map_line) == wanted_line
                and normalize_tower_id(map_tower) == wanted_tower
            ):
                return os.path.join(folder, filename)
    return None


def process_single_protocol(
    import_data: dict[str, Any],
    dir: str,
    html_path: str,
    map_dirs: Sequence[str] | None = None,
    *,
    language: str = "en",
    logo_path: str | None = None,
    print_pdf: bool = True,
) -> str:
    """Create the diagrams and the protocol of one tower.

    Parameters
    ----------
    import_data : dict
        Content of the tower's JSON file.
    dir : str
        Folder of the JSON files (searched first for the map image).
    html_path : str
        Output folder for diagrams, HTML and PDF.
    map_dirs : sequence of str or None, optional
        Further folders to search for the map image (usually the measurement
        folder).
    language : str, optional
        Language of the protocol.
    logo_path : str or None, optional
        Logo for the protocol header.
    print_pdf : bool, optional
        Create the PDF in addition to the HTML file.

    Returns
    -------
    str
        Path of the created HTML file.
    """

    def tr(key: str) -> str:
        return translate(key, language)

    html_data: dict[str, Any] = {}
    line_number = str(import_data["Leitung"])
    tower = str(import_data["Mast"])
    stem = safe_filename(f"{line_number}_{tower}")

    Ik = import_data["Ik_kA"]
    r = import_data["r_pu"]
    distance = [0, *import_data["Distanz_m"]]
    grounding_impedance = [0, *import_data["ZE_Ohm"]]
    residual_resistance = import_data["RA_Ohm"]
    if isinstance(residual_resistance, list):
        residual_resistance = [0, *residual_resistance]
    grounding_impedance_62 = import_data["ZE_62_Ohm"]
    residual_resistance_62 = import_data["RA_62_Ohm"]
    distance_62 = import_data["Distanz_62_m"]
    step_voltage = import_data["US_V"]
    html_data["grounding_impedance_62"] = grounding_impedance_62
    html_data["residual_resistance_62"] = residual_resistance_62
    html_data["ra_hinweis"] = import_data.get("RA_Quelle_Hinweis", "")

    # earth potential along the profile in kV: I_E (kA) * Z (Ohm)
    grounding_voltage = Ik * r * np.array(grounding_impedance)

    if len(distance) > 1:
        name = f"ZE_{stem}.png"
        plots.impedance_distance_plot(
            export_path=os.path.join(html_path, name),
            distance=distance,
            grounding_impedance=grounding_impedance,
            xlabel=tr("plot_distance"),
            ylabel=tr("plot_earthing_impedance"),
            dist_62=distance_62,
            impedance_62=grounding_impedance_62,
            voltage_profile=grounding_voltage,
            measured_label=tr("plot_measured_values"),
            value_62_label=tr("plot_value_62"),
            voltage_label=tr("plot_voltage_kv"),
        )
        html_data["x_y_ZE_image"] = name
        if isinstance(residual_resistance, list) and len(residual_resistance) == len(
            distance
        ):
            name = f"RA_{stem}.png"
            plots.impedance_distance_plot(
                export_path=os.path.join(html_path, name),
                distance=distance,
                grounding_impedance=residual_resistance,
                xlabel=tr("plot_distance"),
                ylabel=tr("plot_footing_resistance"),
                dist_62=distance_62,
                impedance_62=residual_resistance_62,
                measured_label=tr("plot_measured_values"),
                value_62_label=tr("plot_value_62"),
                voltage_label=tr("plot_voltage_kv"),
            )
            html_data["x_y_RA_image"] = name
        name = f"US_{stem}.png"
        plots.step_voltage_plot(
            export_path=os.path.join(html_path, name),
            distance=distance,
            step_voltage=step_voltage,
            xlabel=tr("plot_distance"),
            ylabel=tr("plot_step_voltage"),
        )
        html_data["x_y_US_image"] = name

    # bar chart: touch voltage with vs. without the additional 1 kOhm resistor
    ut_locations, ut_without, ut_with = _split_by_termination(import_data)
    if ut_without or ut_with:
        name = f"UTbar_{stem}.png"
        plots.touch_voltage_bar_plot(
            os.path.join(html_path, name),
            ut_locations,
            ut_without,
            ut_with,
            label_without=tr("plot_without_resistor"),
            label_with=tr("plot_with_resistor"),
            label_max_without=tr("plot_max_without"),
            label_max_with=tr("plot_max_with"),
            xlabel=tr("plot_measuring_point"),
            ylabel=tr("plot_touch_voltage"),
        )
        html_data["x_y_UT_bar_image"] = name

    html_data.update(
        {
            "line_number": line_number,
            "tower": tower,
            "measuring_device": import_data["Messtechnik_Name"],
            "weather": import_data["Witterung"],
            "distance_current_probe": import_data["Entfernung_Hilfserder_m"],
            "angle_current_probe_voltage_probe": import_data[
                "Winkel_Sonde_Hilfserder_grad"
            ],
            "angle_current_probe_line": import_data["Winkel_Leitung_Hilfserder_grad"],
            "grounding_impedance_current": float(import_data["IE_A"]) * 1e3,
            "residual_resistance_current": import_data["IA_A"],
            "impedances_table": {
                "Distanz": distance,
                "ZE": grounding_impedance,
                "RA": residual_resistance,
            },
            "touchvoltages_table": {
                "Ort": import_data["Messpunkte_UT"],
                "UT": import_data["UT_V"],
            },
            "visual_findings": import_data["Sichtbefund"],
            "tripping_time": import_data["Abschaltzeit_s"],
            "tripping_hint": import_data.get("Abschaltzeit_Hinweis", "") or "",
            "UD_curve": import_data["UD_Kurve_50341"],
            "UD_value": import_data["UD_V"],
            "Ik": Ik,
            "r": r,
            "IE": float(np.round(r * Ik, decimals=2)),
            "UT_max_measured": int(np.ceil(import_data["UT_max_Messung_V"])),
            "final_evaluation": import_data["Auslegung_korrekt"],
            "first_name": import_data["Vorname"],
            "family_name": import_data["Name"],
            "company": import_data["Firma"],
            "eval_first_name": import_data.get("Auswertung_Vorname", ""),
            "eval_family_name": import_data.get("Auswertung_Name", ""),
            "eval_company": import_data.get("Auswertung_Firma", ""),
            "date": import_data["Datum"],
        }
    )

    # map: next to the JSON files first, then in the measurement folder
    map_file = _find_map(
        line_number, tower, [dir, *[d for d in (map_dirs or []) if d and d != dir]]
    )
    if map_file is not None:
        target = os.path.join(html_path, os.path.basename(map_file))
        shutil.copy(map_file, target)
        html_data["map_image"] = os.path.basename(map_file)

    html_file, _pdf = export_html(
        data=html_data,
        export_path=html_path,
        print_pdf=print_pdf,
        language=language,
        logo_path=logo_path,
    )
    return html_file


def print_protocol(
    worker_count: int = 1,
    config_path: str | os.PathLike[str] | None = None,
    print_pdf: bool = True,
) -> int:
    """Create the protocols of all evaluated towers.

    Parameters
    ----------
    worker_count : int, optional
        Number of parallel worker processes (1 = sequential).
    config_path : str, os.PathLike or None, optional
        Configuration file (default: see
        `resolve_config_path`).
    print_pdf : bool, optional
        Create PDF files (``False`` writes HTML only).

    Returns
    -------
    int
        Number of protocols created.
    """
    config = read_config(config_path)
    json_dir = config["json_export_path"]
    data_list = results.json_reader(path=json_dir)
    html_path = os.fspath(ensure_directory(os.path.join(json_dir, HTML_FOLDER)))
    options: dict[str, Any] = {
        "dir": json_dir,
        "html_path": html_path,
        "map_dirs": [config["directory_path"]],
        "language": config["language"],
        "logo_path": config["logo_path"] or None,
        "print_pdf": print_pdf,
    }
    if worker_count > 1:
        logger.info(
            "Creating %d protocols with %d workers ...", len(data_list), worker_count
        )
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            list(executor.map(partial(process_single_protocol, **options), data_list))
    else:
        for import_data in data_list:
            process_single_protocol(import_data, **options)
    logger.info("Protocols written to %s", html_path)
    return len(data_list)


def zip_protocols(config_path: str | os.PathLike[str] | None = None) -> int:
    """Pack all PDF protocols into the archive ``export_path_pdf``.

    Parameters
    ----------
    config_path : str, os.PathLike or None, optional
        Configuration file.

    Returns
    -------
    int
        Number of PDF files in the archive.
    """
    config = read_config(config_path)
    source_directory = os.path.join(config["json_export_path"], HTML_FOLDER)
    return zip_pdfs(
        source_directory=source_directory, zip_file_path=config["export_path_pdf"]
    )
