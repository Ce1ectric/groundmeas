"""Tests for groundmeas.core.units (parsing and conversion of units)."""

from __future__ import annotations

import math
import warnings
from typing import Any, get_args

import pytest

from groundmeas.core.models import MeasurementType
from groundmeas.core.units import (
    BASE_UNITS,
    MEASUREMENT_TYPE_QUANTITIES,
    SI_PREFIXES,
    Quantity,
    UnitError,
    UnitWarning,
    check_unit,
    common_units,
    default_unit,
    expected_quantities,
    item_to_base_units,
    items_to_base_units,
    known_units,
    parse_unit,
    prefix_factor,
    to_base_unit,
)

MICRO = "µ"  # MICRO SIGN
MU = "μ"  # GREEK SMALL LETTER MU
OMEGA = "Ω"  # GREEK CAPITAL LETTER OMEGA
OHM_SIGN = "Ω"  # OHM SIGN


# ------------------------------------------------------------------- consistency
def test_every_measurement_type_has_a_quantity() -> None:
    assert set(MEASUREMENT_TYPE_QUANTITIES) == set(get_args(MeasurementType))
    for quantities in MEASUREMENT_TYPE_QUANTITIES.values():
        assert quantities and set(quantities) <= set(BASE_UNITS)


def test_quantities_and_base_units_agree() -> None:
    assert set(get_args(Quantity)) == set(BASE_UNITS)
    for quantity, base in BASE_UNITS.items():
        unit = parse_unit(base, quantity)
        assert (unit.symbol, unit.quantity, unit.factor) == (base, quantity, 1.0)


def test_known_units_are_canonical() -> None:
    for quantity in BASE_UNITS:
        for symbol, factor in known_units(quantity).items():
            unit = parse_unit(symbol)
            assert (unit.symbol, unit.quantity, unit.factor) == (
                symbol,
                quantity,
                factor,
            )
    with pytest.raises(ValueError, match="unknown quantity"):
        known_units("speed")


# ----------------------------------------------------------------------- parsing
@pytest.mark.parametrize(
    ("text", "symbol", "quantity", "exponent"),
    [
        ("A", "A", "current", 0),
        ("mA", "mA", "current", -3),
        (f"{MICRO}A", f"{MU}A", "current", -6),
        (f"{MU}A", f"{MU}A", "current", -6),
        ("uA", f"{MU}A", "current", -6),
        ("nA", "nA", "current", -9),
        ("kA", "kA", "current", 3),
        ("Ampere", "A", "current", 0),
        ("milliamps", "mA", "current", -3),
        ("ma", "mA", "current", -3),
        ("KA", "kA", "current", 3),
        ("V", "V", "voltage", 0),
        ("mV", "mV", "voltage", -3),
        (f"{MICRO}V", f"{MU}V", "voltage", -6),
        ("uV", f"{MU}V", "voltage", -6),
        ("kV", "kV", "voltage", 3),
        ("[mV]", "mV", "voltage", -3),
        ("(V)", "V", "voltage", 0),
        ("kilovolt", "kV", "voltage", 3),
        ("v", "V", "voltage", 0),
        (OMEGA, OMEGA, "resistance", 0),
        (OHM_SIGN, OMEGA, "resistance", 0),
        ("Ohm", OMEGA, "resistance", 0),
        ("ohms", OMEGA, "resistance", 0),
        ("OHM", OMEGA, "resistance", 0),
        (f"m{OMEGA}", f"m{OMEGA}", "resistance", -3),
        (f"m{OHM_SIGN}", f"m{OMEGA}", "resistance", -3),
        ("mOhm", f"m{OMEGA}", "resistance", -3),
        ("milliohm", f"m{OMEGA}", "resistance", -3),
        (f"{MICRO}{OMEGA}", f"{MU}{OMEGA}", "resistance", -6),
        (f"{MU}{OHM_SIGN}", f"{MU}{OMEGA}", "resistance", -6),
        ("uOhm", f"{MU}{OMEGA}", "resistance", -6),
        (f"k{OMEGA}", f"k{OMEGA}", "resistance", 3),
        ("kOhm", f"k{OMEGA}", "resistance", 3),
        (f"K{OMEGA}", f"k{OMEGA}", "resistance", 3),
        (f"M{OMEGA}", f"M{OMEGA}", "resistance", 6),
        ("MOhm", f"M{OMEGA}", "resistance", 6),
        ("V/A", "V/A", "resistance", 0),
        ("mV/A", "mV/A", "resistance", -3),
        (f"{OMEGA}m", f"{OMEGA}m", "resistivity", 0),
        (f"{OHM_SIGN}m", f"{OMEGA}m", "resistivity", 0),
        (f"{OMEGA} m", f"{OMEGA}m", "resistivity", 0),
        (f"{OMEGA}·m", f"{OMEGA}m", "resistivity", 0),
        (f"{OMEGA}⋅m", f"{OMEGA}m", "resistivity", 0),
        (f"{OMEGA}*m", f"{OMEGA}m", "resistivity", 0),
        (f"{OMEGA}.m", f"{OMEGA}m", "resistivity", 0),
        ("Ohm-m", f"{OMEGA}m", "resistivity", 0),
        ("ohm-m", f"{OMEGA}m", "resistivity", 0),
        ("Ohmm", f"{OMEGA}m", "resistivity", 0),
        ("ohm metre", f"{OMEGA}m", "resistivity", 0),
        (f"k{OMEGA}m", f"k{OMEGA}m", "resistivity", 3),
        ("kOhm m", f"k{OMEGA}m", "resistivity", 3),
        (f"m{OMEGA}m", f"m{OMEGA}m", "resistivity", -3),
        (f"M{OMEGA}m", f"M{OMEGA}m", "resistivity", 6),
        (f"{OMEGA}cm", f"{OMEGA}cm", "resistivity", -2),
        ("Ohm-cm", f"{OMEGA}cm", "resistivity", -2),
        ("m", "m", "distance", 0),
        ("mm", "mm", "distance", -3),
        ("cm", "cm", "distance", -2),
        ("km", "km", "distance", 3),
        ("Hz", "Hz", "frequency", 0),
        ("[Hz]", "Hz", "frequency", 0),
        ("kHz", "kHz", "frequency", 3),
    ],
)
def test_parse_unit(text: str, symbol: str, quantity: str, exponent: int) -> None:
    unit = parse_unit(text)
    assert unit.symbol == symbol
    assert unit.quantity == quantity
    assert unit.base == BASE_UNITS[quantity]
    # two methods: factor of the parser vs. the decimal exponent of the prefix
    assert unit.factor == pytest.approx(10.0**exponent, rel=1e-15)
    assert math.log10(unit.factor) == pytest.approx(exponent)


def test_foot_is_converted_exactly() -> None:
    assert parse_unit("ft").factor == 0.3048
    assert parse_unit("feet").symbol == "ft"
    assert to_base_unit(100.0, "ft") == pytest.approx(30.48)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "furlong",
        "°",
        "%",
        "1V",
        "[1V]",
        f"{OMEGA}/m",  # resistance per length, not a resistivity
        f"{OMEGA}ft",
        "MA",  # mega-ampere: most likely a typing error for mA
        "MV",
        "Ma",
        "GA",
    ],
)
def test_unknown_units_are_rejected(text: str) -> None:
    with pytest.raises(UnitError):
        parse_unit(text)


def test_quantity_is_checked() -> None:
    assert parse_unit("mA", "current").factor == 1e-3
    assert parse_unit("Ohm-m", ("resistivity", "resistance")).quantity == (
        "resistivity"
    )
    with pytest.raises(UnitError, match="is a current unit, expected voltage"):
        parse_unit("mA", "voltage")
    with pytest.raises(UnitError, match="expected resistivity or resistance"):
        parse_unit("V", ("resistivity", "resistance"))
    with pytest.raises(ValueError, match="unknown quantity"):
        parse_unit("V", "speed")


def test_unit_error_is_a_value_error() -> None:
    assert issubclass(UnitError, ValueError)
    assert issubclass(UnitWarning, UserWarning)


@pytest.mark.parametrize(
    ("prefix", "factor"),
    [("", 1.0), ("m", 1e-3), (MICRO, 1e-6), (MU, 1e-6), ("u", 1e-6), ("k", 1e3)]
    + [("K", 1e3), ("M", 1e6), ("n", 1e-9), ("G", 1e9)],
)
def test_prefix_factor(prefix: str, factor: float) -> None:
    assert prefix_factor(prefix) == factor
    # two methods: the table of SI prefixes
    key = {MICRO: MU, "u": MU, "K": "k"}.get(prefix, prefix)
    assert prefix_factor(prefix) == SI_PREFIXES.get(key, 1.0)


def test_unknown_prefix() -> None:
    with pytest.raises(UnitError, match="SI prefix"):
        prefix_factor("x")


def test_to_base_unit_round_trip() -> None:
    for quantity in BASE_UNITS:
        for symbol, factor in known_units(quantity).items():
            # two methods: parser vs. explicit multiplication with the factor
            assert to_base_unit(7.25, symbol) == pytest.approx(7.25 * factor)
            assert to_base_unit(7.25, symbol, quantity) == pytest.approx(7.25 * factor)


def test_base_unit_values_are_returned_unchanged() -> None:
    value = 0.1 + 0.2  # not exactly representable: must not be touched
    assert to_base_unit(value, "Ohm") is value


# ------------------------------------------------------------- measurement types
@pytest.mark.parametrize(
    ("measurement_type", "unit", "common"),
    [
        ("earthing_impedance", OMEGA, [OMEGA, f"m{OMEGA}", f"k{OMEGA}"]),
        ("earthing_resistance", OMEGA, [OMEGA, f"m{OMEGA}", f"k{OMEGA}"]),
        ("earthing_current", "A", ["A", "mA", "kA"]),
        ("earth_fault_current", "A", ["A", "mA", "kA"]),
        ("shield_current", "A", ["A", "mA", "kA"]),
        ("touch_voltage", "V", ["V", "mV", "kV"]),
        ("prospective_touch_voltage", "V", ["V", "mV", "kV"]),
        ("earth_potential_rise", "V", ["V", "mV", "kV"]),
        ("step_voltage", "V", ["V", "mV", "kV"]),
        ("transferred_potential", "V", ["V", "mV", "kV"]),
        (
            "soil_resistivity",
            f"{OMEGA}m",
            [f"{OMEGA}m", f"k{OMEGA}m", OMEGA, f"m{OMEGA}", f"k{OMEGA}"],
        ),
        ("unknown_type", "", []),
    ],
)
def test_default_and_common_units(
    measurement_type: str, unit: str, common: list[str]
) -> None:
    assert default_unit(measurement_type) == unit
    assert common_units(measurement_type) == common
    for suggestion in common:
        assert check_unit(suggestion, measurement_type) is None


def test_expected_quantities() -> None:
    assert expected_quantities("touch_voltage") == ("voltage",)
    assert expected_quantities("soil_resistivity") == ("resistivity", "resistance")
    assert expected_quantities("unknown") is None
    assert expected_quantities(None) is None


@pytest.mark.parametrize(
    ("unit", "measurement_type", "message"),
    [
        ("mV", "touch_voltage", None),
        ("A", "touch_voltage", "is a current unit, expected voltage"),
        ("V", "earthing_impedance", "is a voltage unit, expected resistance"),
        ("ohm-m", "soil_resistivity", None),
        ("mOhm", "soil_resistivity", None),
        ("furlong", "earthing_impedance", "unknown unit"),
        ("", "touch_voltage", "no unit given; the values are taken as V"),
        (None, "earthing_current", "no unit given; the values are taken as A"),
    ],
)
def test_check_unit(unit: Any, measurement_type: str, message: Any) -> None:
    problem = check_unit(unit, measurement_type)
    if message is None:
        assert problem is None
    else:
        assert problem is not None and message in problem


# ------------------------------------------------------------- item conversion
def test_item_to_base_units_scales_all_value_fields() -> None:
    item = {
        "id": 7,
        "measurement_type": "earthing_impedance",
        "value": 118.1,
        "value_angle_deg": -36.0,
        "value_real": 95.5,
        "value_imag": -69.4,
        "unit": "mOhm",
        "measurement_distance_m": 20.0,
        "additional_resistance_ohm": 1000.0,
    }
    converted, problem = item_to_base_units(item)
    assert problem is None
    assert converted["unit"] == OMEGA
    # two methods: hand conversion and the parsed factor
    assert converted["value"] == pytest.approx(0.1181)
    assert converted["value_real"] == pytest.approx(item["value_real"] * 1e-3)
    assert converted["value_imag"] == pytest.approx(item["value_imag"] * 1e-3)
    # angle and fields with a unit in their name are untouched
    assert converted["value_angle_deg"] == -36.0
    assert converted["measurement_distance_m"] == 20.0
    assert converted["additional_resistance_ohm"] == 1000.0
    # the input is not modified and a second pass changes nothing
    assert item["value"] == 118.1 and item["unit"] == "mOhm"
    again, problem = item_to_base_units(converted)
    assert problem is None and again == converted


def test_item_without_unit_is_taken_as_base_unit() -> None:
    for unit in (None, "", "  "):
        item = {"value": 3.0, "unit": unit}
        converted, problem = item_to_base_units(item, "earthing_current")
        assert converted == item and problem is None


def test_item_with_unusable_unit_is_returned_unchanged() -> None:
    item = {"id": 3, "value": 5.0, "unit": "A"}
    converted, problem = item_to_base_units(item, "touch_voltage")
    assert converted == item
    assert problem == "'A' is a current unit, expected voltage"


def test_measurement_type_of_the_item_and_override() -> None:
    item = {"measurement_type": "earthing_current", "value": 2.5, "unit": "kA"}
    assert item_to_base_units(item)[0]["value"] == 2500.0
    # an explicit type or quantity overrides the item's own type
    assert item_to_base_units(item, "touch_voltage")[1] is not None
    assert item_to_base_units(item, quantities=("current",))[0]["value"] == 2500.0
    # unknown types accept every quantity
    assert item_to_base_units({**item, "measurement_type": "x"})[0]["unit"] == "A"


def test_non_numeric_values_are_left_for_the_caller() -> None:
    converted, problem = item_to_base_units({"value": "n/a", "unit": "mA"})
    assert problem is None
    assert converted["value"] == "n/a"


def test_items_to_base_units_warns_once_per_call() -> None:
    items = [
        {"id": 1, "value": 13.5, "unit": "mV"},
        {"id": 2, "value": 0.02, "unit": "A"},
        {"id": 3, "value": 0.03, "unit": "A"},
        {"id": 4, "value": 1.0, "unit": "furlong"},
    ]
    with pytest.warns(UnitWarning) as record:
        converted = items_to_base_units(items, "touch_voltage", context="Measurement 9")
    assert len(record) == 1
    message = str(record[0].message)
    assert message.startswith("Measurement 9: touch_voltage unit not converted")
    assert "'A' is a current unit, expected voltage (items 2, 3)" in message
    assert "unknown unit 'furlong' (item 4)" in message
    assert [c["value"] for c in converted] == pytest.approx([0.0135, 0.02, 0.03, 1.0])


def test_items_to_base_units_is_silent_for_convertible_units() -> None:
    items = [{"id": 1, "value": 2.0, "unit": "kA"}, {"id": 2, "value": 9.0}]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        converted = items_to_base_units(items, "earth_fault_current")
    assert [c["value"] for c in converted] == [2000.0, 9.0]
