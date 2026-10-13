"""
groundmeas.core.units
=====================

Units of measured values: parsing, conversion to the SI base unit and the
unit expected for each ``measurement_type``.

``MeasurementItem.unit`` is free text and values are stored as entered
(``118.1`` with ``"mΩ"``). Every calculation converts them to the SI base
unit of their physical quantity first, so that items in ``Ω`` and ``mΩ``,
``A`` and ``kA`` or ``V`` and ``mV`` can be combined. This module is the
single place that knows which spellings exist and what they are worth; the
instrument readers, the OCR import, the analytics and the CLI use it.

===========  =========  ==============================================
quantity     base unit  accepted units (canonical symbols)
===========  =========  ==============================================
current      A          nA, μA, mA, A, kA
voltage      V          μV, mV, V, kV
resistance   Ω          μΩ, mΩ, Ω, kΩ, MΩ, GΩ, V/A, mV/A
resistivity  Ωm         mΩm, Ωm, kΩm, MΩm, Ωcm
distance     m          mm, cm, m, km, ft
frequency    Hz         Hz, kHz
===========  =========  ==============================================

Accepted spellings:

* micro as MICRO SIGN ``µ`` (U+00B5), GREEK SMALL LETTER MU ``μ``
  (U+03BC) or ASCII ``u`` (``µA``, ``μA``, ``uA``);
* ohm as GREEK CAPITAL LETTER OMEGA ``Ω`` (U+03A9), OHM SIGN ``Ω``
  (U+2126) or the words ``Ohm``, ``ohm``, ``ohms`` (``mOhm``, ``kohm``);
* products with or without separator (``Ωm``, ``Ω m``, ``Ω·m``, ``Ω*m``,
  ``Ohm-m``, ``ohm-m``, ``Ohmm``, ``Ω.m``);
* words for prefixes and units (``milliohm``, ``kilovolt``, ``amperes``,
  ``metre``);
* units in brackets as written by instruments (``[mV]``);
* ``K`` for kilo and a lower-case ``a`` / ``v`` (``KV``, ``ma``).

SI prefixes are case-sensitive (``m`` milli, ``M`` mega). Only the prefixes
that occur for a quantity in earthing measurements are accepted, so ``MA``
or ``MV`` -- most likely a typing error for ``mA`` / ``mV`` -- are rejected
instead of being scaled by 10⁹.

Examples
--------
>>> from groundmeas.core.units import parse_unit
>>> parse_unit("mOhm").factor
0.001
>>> parse_unit("µV").symbol, parse_unit("uV").symbol
('μV', 'μV')
>>> parse_unit("Ohm-m").quantity
'resistivity'
>>> item_to_base_units({"value": 118.1, "unit": "mΩ"}, "earthing_impedance")[0]
{'value': 0.1181, 'unit': 'Ω'}
"""

from __future__ import annotations

import re
import unicodedata
import warnings
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

__all__ = [
    "BASE_UNITS",
    "MEASUREMENT_TYPE_QUANTITIES",
    "Quantity",
    "SI_PREFIXES",
    "Unit",
    "UnitError",
    "UnitWarning",
    "VALUE_FIELDS",
    "check_unit",
    "common_units",
    "default_unit",
    "expected_quantities",
    "item_to_base_units",
    "items_to_base_units",
    "known_units",
    "parse_unit",
    "prefix_factor",
    "to_base_unit",
]

Quantity = Literal[
    "current", "voltage", "resistance", "resistivity", "distance", "frequency"
]
"""Physical quantities with a unit known to groundmeas."""

BASE_UNITS: dict[str, str] = {
    "current": "A",
    "voltage": "V",
    "resistance": "Ω",
    "resistivity": "Ωm",
    "distance": "m",
    "frequency": "Hz",
}
"""SI base unit (canonical symbol) per quantity."""

SI_PREFIXES: dict[str, float] = {
    "n": 1e-9,
    "μ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "M": 1e6,
    "G": 1e9,
}
"""SI prefixes known to groundmeas (micro as U+03BC GREEK SMALL LETTER MU)."""

_PREFIXES_PER_QUANTITY: dict[str, str] = {
    "current": "nμmk",
    "voltage": "μmk",
    "resistance": "μmkMG",
    "resistivity": "mkM",
    "frequency": "k",
}
"""Prefixes accepted per quantity (the distance units are listed explicitly)."""

MEASUREMENT_TYPE_QUANTITIES: dict[str, tuple[Quantity, ...]] = {
    "prospective_touch_voltage": ("voltage",),
    "touch_voltage": ("voltage",),
    "earth_potential_rise": ("voltage",),
    "step_voltage": ("voltage",),
    "transferred_potential": ("voltage",),
    "earth_fault_current": ("current",),
    "earthing_current": ("current",),
    "shield_current": ("current",),
    "earthing_resistance": ("resistance",),
    "earthing_impedance": ("resistance",),
    # resistivity, or the measured resistance (``value_kind="resistance"``)
    "soil_resistivity": ("resistivity", "resistance"),
}
"""Quantity of the values per ``measurement_type`` (first entry: default)."""

VALUE_FIELDS: tuple[str, ...] = ("value", "value_real", "value_imag")
"""Fields of a MeasurementItem that carry its unit (the angle does not)."""

_COMMON_UNITS: dict[str, tuple[str, ...]] = {
    "current": ("A", "mA", "kA"),
    "voltage": ("V", "mV", "kV"),
    "resistance": ("Ω", "mΩ", "kΩ"),
    "resistivity": ("Ωm", "kΩm"),
    "distance": ("m", "cm", "km"),
    "frequency": ("Hz", "kHz"),
}


class UnitError(ValueError):
    """Raised when a unit is unknown or belongs to another quantity."""


class UnitWarning(UserWarning):
    """Emitted when values are used as stored because their unit is not usable."""


@dataclass(frozen=True)
class Unit:
    """A parsed unit.

    Attributes
    ----------
    symbol : str
        Canonical symbol, e.g. ``"mΩ"``, ``"μV"`` or ``"Ωm"``.
    quantity : str
        Physical quantity (see :data:`BASE_UNITS`).
    factor : float
        Multiply a value in this unit by ``factor`` to get the SI base unit.
    """

    symbol: str
    quantity: Quantity
    factor: float

    @property
    def base(self) -> str:
        """Canonical symbol of the SI base unit of the quantity."""
        return BASE_UNITS[self.quantity]

    def to_base(self, value: float) -> float:
        """Convert ``value`` from this unit to the SI base unit.

        Parameters
        ----------
        value : float
            Value in this unit.

        Returns
        -------
        float
            Value in the base unit; returned unchanged if the unit is the base
            unit.
        """
        if self.factor == 1.0:
            return value
        return value * self.factor


def _build_table() -> dict[str, tuple[Quantity, float]]:
    """Canonical symbol -> (quantity, factor to the base unit)."""
    table: dict[str, tuple[Quantity, float]] = {}
    bases: tuple[tuple[Quantity, str], ...] = (
        ("current", "A"),
        ("voltage", "V"),
        ("resistance", "Ω"),
        ("frequency", "Hz"),
    )
    for quantity, base in bases:
        table[base] = (quantity, 1.0)
        for prefix in _PREFIXES_PER_QUANTITY[quantity]:
            table[prefix + base] = (quantity, SI_PREFIXES[prefix])
    # resistivity: the prefix belongs to the ohm (kΩm = kΩ·m)
    table["Ωm"] = ("resistivity", 1.0)
    for prefix in _PREFIXES_PER_QUANTITY["resistivity"]:
        table[f"{prefix}Ωm"] = ("resistivity", SI_PREFIXES[prefix])
    table["Ωcm"] = ("resistivity", 1e-2)
    table.update(
        {
            "m": ("distance", 1.0),
            "mm": ("distance", 1e-3),
            "cm": ("distance", 1e-2),
            "km": ("distance", 1e3),
            "ft": ("distance", 0.3048),
            # impedance written as volt per ampere
            "V/A": ("resistance", 1.0),
            "mV/A": ("resistance", 1e-3),
        }
    )
    return table


_TABLE: dict[str, tuple[Quantity, float]] = _build_table()

_WORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"ohms?", re.IGNORECASE), "Ω"),
    (re.compile(r"volts?", re.IGNORECASE), "V"),
    (re.compile(r"amp(?:ere)?s?", re.IGNORECASE), "A"),
    (re.compile(r"hertz|hz", re.IGNORECASE), "Hz"),
    (re.compile(r"met(?:er|re)s?", re.IGNORECASE), "m"),
    (re.compile(r"feet|foot", re.IGNORECASE), "ft"),
    (re.compile(r"milli", re.IGNORECASE), "m"),
    (re.compile(r"micro", re.IGNORECASE), "μ"),
    (re.compile(r"centi", re.IGNORECASE), "c"),
    (re.compile(r"kilo", re.IGNORECASE), "k"),
    (re.compile(r"mega", re.IGNORECASE), "M"),
)
"""Words replaced by symbols (applied in this order)."""

_SEPARATORS = re.compile(r"[\s·∙⋅*_.\-]")
"""Characters dropped between symbols (blank, middle dot, dot operators, ...)."""


def _canonical(text: str) -> str:
    """Normalise the spelling of a unit (see the module docstring)."""
    # NFKC maps U+2126 OHM SIGN to Ω (U+03A9) and U+00B5 MICRO SIGN to μ (U+03BC)
    unit = unicodedata.normalize("NFKC", text).strip()
    while len(unit) >= 2 and unit[0] in "[({" and unit[-1] in "])}":
        unit = unit[1:-1].strip()
    for pattern, replacement in _WORDS:
        unit = pattern.sub(replacement, unit)
    return _SEPARATORS.sub("", unit)


def _variants(unit: str) -> list[str]:
    """Lenient alternatives of a canonical spelling, most literal first."""
    heads = [unit]
    if len(unit) > 1 and unit[0] == "u":
        heads.append("μ" + unit[1:])  # ASCII micro
    if len(unit) > 1 and unit[0] == "K":
        heads.append("k" + unit[1:])  # K is not an SI prefix; kilo meant
    variants: list[str] = []
    for head in heads:
        variants.append(head)
        if head and head[-1] in "av":
            variants.append(head[:-1] + head[-1].upper())
    return variants


@lru_cache(maxsize=1024)
def _lookup(text: str) -> tuple[str, Quantity, float] | None:
    """Return ``(symbol, quantity, factor)`` of a unit or ``None``."""
    for candidate in _variants(_canonical(text)):
        hit = _TABLE.get(candidate)
        if hit is not None:
            return candidate, hit[0], hit[1]
    return None


def _allowed(quantity: str | Iterable[str] | None) -> tuple[str, ...]:
    if quantity is None:
        return ()
    if isinstance(quantity, str):
        return (quantity,)
    return tuple(quantity)


def parse_unit(unit: str, quantity: str | Iterable[str] | None = None) -> Unit:
    """Parse a unit string.

    Parameters
    ----------
    unit : str
        Unit as written, e.g. ``"mΩ"``, ``"mOhm"``, ``"µA"``, ``"[mV]"`` or
        ``"Ohm-m"``.
    quantity : str or iterable of str, optional
        Expected quantity (or quantities); a unit of another quantity raises
        :class:`UnitError`.

    Returns
    -------
    Unit
        Canonical symbol, quantity and factor to the SI base unit.

    Raises
    ------
    UnitError
        If the unit is empty or unknown, or does not belong to ``quantity``.

    Examples
    --------
    >>> parse_unit("kOhm").factor
    1000.0
    >>> parse_unit("μΩ").symbol
    'μΩ'
    >>> parse_unit("mA", "voltage")
    Traceback (most recent call last):
    ...
    groundmeas.core.units.UnitError: 'mA' is a current unit, expected voltage
    """
    if unit is None or not str(unit).strip():
        raise UnitError("no unit given")
    for name in _allowed(quantity):
        if name not in BASE_UNITS:
            raise ValueError(f"unknown quantity {name!r}")
    hit = _lookup(str(unit))
    if hit is None:
        raise UnitError(f"unknown unit {unit!r}")
    symbol, found, factor = hit
    allowed = _allowed(quantity)
    if allowed and found not in allowed:
        raise UnitError(f"{unit!r} is a {found} unit, expected {' or '.join(allowed)}")
    return Unit(symbol=symbol, quantity=found, factor=factor)


def to_base_unit(
    value: float, unit: str, quantity: str | Iterable[str] | None = None
) -> float:
    """Convert ``value`` given in ``unit`` to the SI base unit.

    Parameters
    ----------
    value : float
        Value in ``unit``.
    unit : str
        Unit as written (see :func:`parse_unit`).
    quantity : str or iterable of str, optional
        Expected quantity.

    Returns
    -------
    float
        Value in the SI base unit of the quantity.

    Raises
    ------
    UnitError
        See :func:`parse_unit`.

    Examples
    --------
    >>> to_base_unit(2.5, "kA")
    2500.0
    """
    return parse_unit(unit, quantity).to_base(value)


def prefix_factor(prefix: str) -> float:
    """Factor of an SI prefix (``""`` -> 1; micro as ``µ``, ``μ`` or ``u``).

    Parameters
    ----------
    prefix : str
        ``""``, ``"n"``, ``"µ"``/``"μ"``/``"u"``, ``"m"``, ``"k"`` (also ``"K"``),
        ``"M"`` or ``"G"``.

    Returns
    -------
    float
        The factor, e.g. ``1e-3`` for ``"m"``.

    Raises
    ------
    UnitError
        If ``prefix`` is not an SI prefix known to groundmeas.
    """
    key = unicodedata.normalize("NFKC", prefix).strip()
    key = {"u": "μ", "K": "k"}.get(key, key)
    if key == "":
        return 1.0
    if key not in SI_PREFIXES:
        raise UnitError(f"unknown SI prefix {prefix!r}")
    return SI_PREFIXES[key]


def known_units(quantity: str) -> dict[str, float]:
    """Canonical symbols of ``quantity`` and their factor to the base unit.

    Parameters
    ----------
    quantity : str
        One of the keys of :data:`BASE_UNITS`.

    Returns
    -------
    dict
        ``{symbol: factor}``, e.g. ``{"A": 1.0, "mA": 0.001, ...}``.
    """
    if quantity not in BASE_UNITS:
        raise ValueError(f"unknown quantity {quantity!r}")
    return {symbol: f for symbol, (q, f) in _TABLE.items() if q == quantity}


def expected_quantities(measurement_type: str | None) -> tuple[Quantity, ...] | None:
    """Quantities a value of ``measurement_type`` may have.

    Parameters
    ----------
    measurement_type : str or None
        A ``MeasurementType``.

    Returns
    -------
    tuple of str or None
        ``None`` for an unknown type (any quantity is accepted then).
    """
    if measurement_type is None:
        return None
    return MEASUREMENT_TYPE_QUANTITIES.get(str(measurement_type))


def default_unit(measurement_type: str) -> str:
    """SI base unit of ``measurement_type`` (``""`` if the type is unknown).

    Parameters
    ----------
    measurement_type : str
        A ``MeasurementType``.

    Returns
    -------
    str
        E.g. ``"Ω"`` for ``earthing_impedance``, ``"V"`` for ``touch_voltage``,
        ``"Ωm"`` for ``soil_resistivity``.
    """
    quantities = expected_quantities(measurement_type)
    return BASE_UNITS[quantities[0]] if quantities else ""


def common_units(measurement_type: str) -> list[str]:
    """Usual units of ``measurement_type``, the base unit first.

    Parameters
    ----------
    measurement_type : str
        A ``MeasurementType``.

    Returns
    -------
    list of str
        Suggestions for input completion (empty for an unknown type).
    """
    units: list[str] = []
    for quantity in expected_quantities(measurement_type) or ():
        units.extend(u for u in _COMMON_UNITS[quantity] if u not in units)
    return units


def check_unit(unit: str | None, measurement_type: str) -> str | None:
    """Tell whether ``unit`` can be converted for ``measurement_type``.

    Parameters
    ----------
    unit : str or None
        Unit as entered.
    measurement_type : str
        A ``MeasurementType``.

    Returns
    -------
    str or None
        ``None`` if the unit is usable, otherwise a readable explanation.
    """
    if unit is None or not str(unit).strip():
        base = default_unit(measurement_type) or "the base unit"
        return f"no unit given; the values are taken as {base}"
    try:
        parse_unit(str(unit), expected_quantities(measurement_type))
    except UnitError as exc:
        return str(exc)
    return None


def item_to_base_units(
    item: Mapping[str, Any],
    measurement_type: str | None = None,
    quantities: Sequence[str] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Copy a MeasurementItem dict with its values in the SI base unit.

    ``value``, ``value_real`` and ``value_imag`` are multiplied by the factor
    of ``unit`` and ``unit`` is replaced by the base unit; the phase angle and
    the fields with a unit in their name (``*_m``, ``*_ohm``, ``*_hz``) are
    left alone. Converting twice is harmless (the second pass finds the base
    unit).

    Parameters
    ----------
    item : mapping
        MeasurementItem fields (e.g. a record of ``read_items_by``).
    measurement_type : str, optional
        Type that defines the expected quantity; defaults to the item's own
        ``measurement_type``.
    quantities : sequence of str, optional
        Expected quantities; overrides ``measurement_type``.

    Returns
    -------
    item : dict
        The converted copy. Items without unit are taken to be in the base
        unit and returned unchanged.
    problem : str or None
        Why the unit could not be used (unknown, or of another quantity); the
        copy is unchanged then.
    """
    converted = dict(item)
    unit = item.get("unit")
    if unit is None or not str(unit).strip():
        return converted, None
    allowed = (
        tuple(quantities)
        if quantities is not None
        else expected_quantities(measurement_type or item.get("measurement_type"))
    )
    try:
        parsed = parse_unit(str(unit), allowed)
    except UnitError as exc:
        return converted, str(exc)
    if parsed.factor != 1.0:
        for name in VALUE_FIELDS:
            value = converted.get(name)
            if value is None:
                continue
            try:
                converted[name] = parsed.to_base(float(value))
            except (TypeError, ValueError):
                continue  # left for the caller's own validation
    converted["unit"] = parsed.base
    return converted, None


def items_to_base_units(
    items: Iterable[Mapping[str, Any]],
    measurement_type: str | None = None,
    *,
    quantities: Sequence[str] | None = None,
    context: str | None = None,
    stacklevel: int = 3,
) -> list[dict[str, Any]]:
    """Convert MeasurementItem dicts to SI base units (see :func:`item_to_base_units`).

    Items whose unit cannot be used keep their stored values; one
    :class:`UnitWarning` lists them.

    Parameters
    ----------
    items : iterable of mapping
        MeasurementItem records.
    measurement_type : str, optional
        Type that defines the expected quantity; defaults to each item's
        ``measurement_type``.
    quantities : sequence of str, optional
        Expected quantities; overrides ``measurement_type``.
    context : str, optional
        Prefix of the warning (e.g. ``"Measurement 3"``).
    stacklevel : int, default 3
        Passed to :func:`warnings.warn`.

    Returns
    -------
    list of dict
        Converted copies in the order of ``items``.
    """
    converted_items: list[dict[str, Any]] = []
    problems: dict[str, list[str]] = {}
    for item in items:
        converted, problem = item_to_base_units(item, measurement_type, quantities)
        converted_items.append(converted)
        if problem is not None:
            problems.setdefault(problem, []).append(str(item.get("id", "?")))
    if problems:
        details = "; ".join(
            f"{problem} (item{'s' if len(ids) > 1 else ''} {', '.join(ids)})"
            for problem, ids in problems.items()
        )
        where = f"{context}: " if context else ""
        what = f"{measurement_type} " if measurement_type else ""
        warnings.warn(
            f"{where}{what}unit not converted: {details}; "
            "the values are used as stored",
            UnitWarning,
            stacklevel=stacklevel,
        )
    return converted_items
