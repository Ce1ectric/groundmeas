"""Translations for user-facing texts of the per-tower protocol.

All texts that end up in a protocol (HTML/PDF), in the plots or in the
human-readable fields of the per-tower JSON are looked up here. The language
is selected with the ``language`` key of the campaign configuration.

Supported languages are English (``"en"``, default) and German (``"de"``).
Adding a language means adding one dictionary to `STRINGS` with the same
keys as the English one; `missing_keys` (used by the test suite) lists
keys that are not translated yet.

Examples
--------
>>> from .i18n import translate, format_number
>>> translate("verdict_measures", "en")
'The touch voltages exceed the permissible values. Further measures are required.'
>>> format_number(0.398, "de")
'0,398'
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = [
    "DEFAULT_LANGUAGE",
    "STRINGS",
    "SUPPORTED_LANGUAGES",
    "format_number",
    "get_strings",
    "missing_keys",
    "normalize_language",
    "translate",
]

DEFAULT_LANGUAGE = "en"

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        # ------------------------------------------------------------ protocol
        "html_title": "Earthing measurement protocol",
        "logo_alt": "Company logo",
        "protocol_header": "Earthing measurement protocol",
        "section_installation": "Installation data",
        "label_line": "Line:",
        "label_tower": "Tower:",
        "label_device": "Measuring device:",
        "label_date": "Date:",
        "section_setup": "Measurement setup",
        "label_weather": "Weather:",
        "label_current_probe_distance": "Distance to the current electrode:",
        "label_angle_probe_current_electrode": (
            "Angle between current electrode and potential probe:"
        ),
        "label_angle_line_current_electrode": "Angle between current electrode and line:",
        "label_measuring_current": "Measuring current (earthing impedance):",
        "section_map": "Map",
        "map_missing": "no map available",
        "section_measurements": "Measured values",
        "heading_impedances": "Impedances",
        "col_distance": "Distance in m",
        "col_ze": "Z<sub>E</sub> in Ohm",
        "col_ra": "R<sub>A</sub> in Ohm",
        "heading_touch_voltages": "Touch voltages related to the earth fault current",
        "col_measuring_point": "Measuring point",
        "col_ut": "U<sub>T</sub> in V",
        "section_plots": "Diagrams",
        "heading_plot_ze": "Earthing impedance Z<sub>E</sub>",
        "plot_ze_missing": "no diagram of the earthing impedance available",
        "heading_plot_ra": "Footing resistance R<sub>A</sub>",
        "plot_ra_missing": "no diagram of the footing resistance available",
        "heading_plot_us": "Open-circuit step voltage U<sub>S</sub>",
        "plot_us_missing": "no diagram of the step voltages available",
        "heading_plot_ut": "Touch voltage with and without additional resistor",
        "plot_ut_missing": "no diagram of the touch voltages available",
        "section_assessment": "Assessment",
        "label_visual_findings": "Visual inspection:",
        "label_clearing_time": "Fault clearing time:",
        "label_ud_curve": "U<sub>D</sub> curve according to EN 50341-1:",
        "label_ud_value": "U<sub>D</sub> for the clearing time:",
        "label_fault_current": "Earth fault current:",
        "label_reduction_factor": "Reduction factor:",
        "label_relevant_current": "Current relevant for the touch-voltage assessment:",
        "label_earthing_impedance": "Earthing impedance:",
        "not_measured": "Not measured",
        "label_footing_resistance": "Footing resistance:",
        "label_ut_max": "Highest touch voltage from the measurements:",
        "label_design_ok": "Earthing system design adequate:",
        "section_contacts": "Contact details",
        "heading_measurement_by": "Measurement performed by",
        "heading_evaluation_by": "Network calculation and evaluation",
        "label_first_name": "First name:",
        "label_last_name": "Last name:",
        "label_company": "Company:",
        "signature": "Signature",
        "page_footer": "Page {page} of {pages}",
        # ---------------------------------------------------------- evaluation
        "verdict_measures": (
            "The touch voltages exceed the permissible values. Further measures are required."
        ),
        "verdict_ut_ok": (
            "The touch-voltage measurements at selected points show that the highest expected "
            "touch voltage is below the permissible touch voltage. No further measures are "
            "required."
        ),
        "verdict_ze_ok": (
            "The earthing-impedance measurement shows that the touch voltage is below the "
            "permissible touch voltage. No further measures are required."
        ),
        "verdict_none": "No assessment possible.",
        "ra_hint_high_frequency": "measured with the high-frequency method",
        "clearing_time_default": "default value from the configuration",
        "unknown_location": "unknown measuring point",
        "termination_1k": "no additional resistor",
        "termination_2x1k": "with additional resistor 1kOhm",
        "hint_fast": (
            "Position {position} % of the line length: instantaneous tripping from both line "
            "ends (distance protection)"
        ),
        "hint_end": (
            "Position {position} % of the line length: end zone, the remote end trips with "
            "time delay"
        ),
        "hint_flat": "Flat clearing time for the whole line",
        "hint_unknown": (
            "Position on the line unknown; the longer clearing time is used (conservative)"
        ),
        # --------------------------------------------------------------- plots
        "plot_distance": "Distance in m",
        "plot_earthing_impedance": "Earthing impedance in Ohm",
        "plot_footing_resistance": "Footing resistance in Ohm",
        "plot_measured_values": "Measured values",
        "plot_value_62": "Value at 62 % of the current-electrode distance",
        "plot_voltage_kv": "Voltage in kV",
        "plot_step_voltage": "Step voltage in V",
        "plot_without_resistor": "without additional resistor",
        "plot_with_resistor": "with additional resistor",
        "plot_max_without": "Max. without add. resistor: {value:.0f} V",
        "plot_max_with": "Max. with add. resistor: {value:.0f} V",
        "plot_measuring_point": "Measuring point",
        "plot_touch_voltage": "Touch voltage in V",
    },
    "de": {
        # ------------------------------------------------------------ protocol
        "html_title": "Protokoll Erdungsmessung",
        "logo_alt": "Firmenlogo",
        "protocol_header": "Protokoll Erdungsmessung",
        "section_installation": "Anlagendaten",
        "label_line": "Leitungsnummer:",
        "label_tower": "Mast:",
        "label_device": "Messgerät:",
        "label_date": "Datum:",
        "section_setup": "Messkonfiguration",
        "label_weather": "Witterung:",
        "label_current_probe_distance": "Entfernung zum Hilfserder:",
        "label_angle_probe_current_electrode": "Winkel zwischen Hilfserder und Sonde:",
        "label_angle_line_current_electrode": "Winkel zwischen Hilfserder und Leitung:",
        "label_measuring_current": "Messstrom Erdungsimpedanz:",
        "section_map": "Kartendarstellung",
        "map_missing": "keine Kartendarstellung",
        "section_measurements": "Messwerte",
        "heading_impedances": "Impedanzen",
        "col_distance": "Distanz in m",
        "col_ze": "Z<sub>E</sub> in Ohm",
        "col_ra": "R<sub>A</sub> in Ohm",
        "heading_touch_voltages": "Berührungsspannungen bezogen auf den Erdfehlerstrom",
        "col_measuring_point": "Messpunkt",
        "col_ut": "U<sub>T</sub> in V",
        "section_plots": "Grafische Darstellungen",
        "heading_plot_ze": "Erdungsimpedanz Z<sub>E</sub>",
        "plot_ze_missing": "keine Darstellung der Erdungsimpedanz verfügbar",
        "heading_plot_ra": "Ausbreitungswiderstand R<sub>A</sub>",
        "plot_ra_missing": "keine Darstellung des Ausbreitungswiderstands verfügbar",
        "heading_plot_us": "Leerlauf-Schrittspannung U<sub>S</sub>",
        "plot_us_missing": "keine Darstellung der Schrittspannungen verfügbar",
        "heading_plot_ut": "Berührungsspannung mit und ohne Zusatzwiderstand",
        "plot_ut_missing": "keine Darstellung der Berührungsspannungen verfügbar",
        "section_assessment": "Bewertung",
        "label_visual_findings": "Sichtbefund:",
        "label_clearing_time": "Abschaltzeit:",
        "label_ud_curve": "UD-Kurve nach DIN EN 50341-1:",
        "label_ud_value": "UD nach Abschaltzeit:",
        "label_fault_current": "Erdfehlerstrom:",
        "label_reduction_factor": "Reduktionsfaktor:",
        "label_relevant_current": "Relevanter Strom für die Bewertung der Berührungsspannungen:",
        "label_earthing_impedance": "Erdungsimpedanz:",
        "not_measured": "Nicht gemessen",
        "label_footing_resistance": "Ausbreitungswiderstand:",
        "label_ut_max": "Maximale Berührungsspannung aus den Messungen:",
        "label_design_ok": "Auslegung der Erdungsanlage korrekt:",
        "section_contacts": "Kontaktdaten",
        "heading_measurement_by": "Messung durchgeführt",
        "heading_evaluation_by": "Netzberechnung und Auswertung",
        "label_first_name": "Vorname:",
        "label_last_name": "Name:",
        "label_company": "Firma:",
        "signature": "Unterschrift",
        "page_footer": "Seite {page} von {pages}",
        # ---------------------------------------------------------- evaluation
        "verdict_measures": (
            "Die Berührungsspannungen überschreiten die maximal zulässigen Werte. "
            "Weitere Maßnahmen sind notwendig."
        ),
        "verdict_ut_ok": (
            "Die Messung der Berührungsspannung an ausgewählten Punkten zeigt, dass die maximal "
            "zu erwartende Spannung kleiner als die zulässige Berührungsspannung ist. Es sind "
            "keine weiteren Maßnahmen notwendig."
        ),
        "verdict_ze_ok": (
            "Die Messung der Erdungsimpedanz zeigt, dass die Berührungsspannung unterhalb der "
            "maximal zulässigen Berührungsspannung ist. Es sind keine weiteren Maßnahmen "
            "notwendig."
        ),
        "verdict_none": "Keine Bewertung möglich.",
        "ra_hint_high_frequency": "Messung über Hochfrequenz-Verfahren",
        "clearing_time_default": "Standardwert aus Config",
        "unknown_location": "Unbekannter Messort",
        "termination_1k": "kein Zusatzwiderstand",
        "termination_2x1k": "mit Zusatzwiderstand 1kOhm",
        "hint_fast": (
            "Lage {position} % der Leitungslänge: beidseitige Schnellzeit des Distanzschutzes"
        ),
        "hint_end": (
            "Lage {position} % der Leitungslänge: Endbereich, Gegenseite löst in Staffelzeit aus"
        ),
        "hint_flat": "Pauschale Abschaltzeit der Leitung",
        "hint_unknown": "Lage auf der Leitung unbekannt, konservativ längere Abschaltzeit",
        # --------------------------------------------------------------- plots
        "plot_distance": "Entfernung in m",
        "plot_earthing_impedance": "Erdungsimpedanz in Ohm",
        "plot_footing_resistance": "Ausbreitungswiderstand in Ohm",
        "plot_measured_values": "Messwerte",
        "plot_value_62": "Berechnungswert 62 % vom Hilfserder",
        "plot_voltage_kv": "Spannung in kV",
        "plot_step_voltage": "Schrittspannung in V",
        "plot_without_resistor": "ohne Zusatzwiderstand",
        "plot_with_resistor": "mit Zusatzwiderstand",
        "plot_max_without": "Max. ohne Zusatzw.: {value:.0f} V",
        "plot_max_with": "Max. mit Zusatzw.: {value:.0f} V",
        "plot_measuring_point": "Messpunkt",
        "plot_touch_voltage": "Berührungsspannung in V",
    },
}

SUPPORTED_LANGUAGES: tuple[str, ...] = tuple(STRINGS)

# Decimal separator per language (used for numbers in protocols).
_DECIMAL_SEPARATOR = {"en": ".", "de": ","}


def normalize_language(language: str | None) -> str:
    """Return a supported language code for ``language``.

    Parameters
    ----------
    language : str or None
        Language code such as ``"de"``, ``"DE"`` or ``"de-AT"``. ``None`` or an
        empty string selects `DEFAULT_LANGUAGE`.

    Returns
    -------
    str
        Two-letter code contained in `SUPPORTED_LANGUAGES`.

    Raises
    ------
    ValueError
        If the language is not supported.
    """
    if not language:
        return DEFAULT_LANGUAGE
    code = str(language).strip().lower().replace("_", "-").split("-")[0]
    if code not in STRINGS:
        supported = ", ".join(SUPPORTED_LANGUAGES)
        raise ValueError(f"Unsupported language {language!r}; supported: {supported}")
    return code


def get_strings(language: str | None) -> Mapping[str, str]:
    """Return all texts of one language.

    Parameters
    ----------
    language : str or None
        Language code, see `normalize_language`.

    Returns
    -------
    Mapping[str, str]
        Read-only view of the text table; missing keys fall back to English
        when looked up through `translate`.
    """
    return STRINGS[normalize_language(language)]


def translate(key: str, language: str | None, /, **values: Any) -> str:
    """Translate ``key`` and fill in ``str.format`` placeholders.

    Parameters
    ----------
    key : str
        Text identifier, e.g. ``"verdict_ut_ok"``.
    language : str or None
        Language code, see `normalize_language`.
    **values
        Values for the placeholders of the text (e.g. ``position=12.5``).

    Returns
    -------
    str
        The translated text. Keys missing in the requested language fall back
        to the English text.

    Raises
    ------
    KeyError
        If the key does not exist at all.
    """
    table = STRINGS[normalize_language(language)]
    text = table.get(key, STRINGS[DEFAULT_LANGUAGE][key])
    return text.format(**values) if values else text


def format_number(value: Any, language: str | None) -> str:
    """Format a number with the decimal separator of ``language``.

    The number is converted with `str` first (no rounding), so the
    precision of the stored value is kept. Non-numeric values are returned as
    strings unchanged apart from the separator replacement.

    Parameters
    ----------
    value : Any
        Number (or string) to format.
    language : str or None
        Language code, see `normalize_language`.

    Returns
    -------
    str
        For example ``"0,398"`` for German and ``"0.398"`` for English.
    """
    separator = _DECIMAL_SEPARATOR.get(normalize_language(language), ".")
    text = str(value)
    return text.replace(".", separator) if separator != "." else text


def missing_keys(language: str) -> set[str]:
    """Return the keys of the English table that ``language`` does not define.

    Parameters
    ----------
    language : str
        Language code to check.

    Returns
    -------
    set of str
        Untranslated keys (empty when the translation is complete).
    """
    return set(STRINGS[DEFAULT_LANGUAGE]) - set(STRINGS[normalize_language(language)])
