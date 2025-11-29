# tests/test_models.py

import pytest
import math
from datetime import datetime, timezone

import numpy as np
from pydantic import ValidationError

from groundmeas.models import (
    Location,
    Measurement,
    MeasurementItem,
    _compute_magnitude,
)


def test_location_instantiation():
    """Location should accept name, latitude, longitude and leave id None."""
    loc = Location(name="Test Site", latitude=1.23, longitude=4.56)
    assert loc.id is None
    assert loc.name == "Test Site"
    assert loc.latitude == 1.23
    assert loc.longitude == 4.56
    assert loc.altitude is None
    # relationship default is empty list
    assert isinstance(loc.measurements, list)
    assert loc.measurements == []


def test_measurement_instantiation_defaults():
    """Measurement should require method and asset_type, set UTC timestamp, and have no items."""
    m = Measurement(method="staged_fault_test", asset_type="cable")
    assert m.id is None
    # timestamp should be a timezone-aware datetime in UTC
    assert isinstance(m.timestamp, datetime)
    assert m.timestamp.tzinfo == timezone.utc
    # relationships default
    assert m.location is None
    assert isinstance(m.items, list) and m.items == []
    # fields
    assert m.method == "staged_fault_test"
    assert m.asset_type == "cable"


def test_measurement_item_allows_shield_current():
    """shield_current should be accepted as a MeasurementItem measurement_type."""
    item = MeasurementItem(
        measurement_type="shield_current",
        value=5.0,
        value_angle_deg=30.0,
        unit="A",
    )
    assert item.measurement_type == "shield_current"


def test_compute_magnitude_rectangular():
    """
    If value is None but value_real/value_imag set,
    _compute_magnitude should compute magnitude and angle.
    """
    item = MeasurementItem(
        measurement_type="earthing_impedance",
        value_real=3.0,
        value_imag=4.0,
        unit="Ω"
    )
    # Manually invoke the SQLAlchemy event listener logic
    _compute_magnitude(None, None, item)
    assert item.value == pytest.approx(5.0)
    expected_angle = math.degrees(math.atan2(4.0, 3.0))
    assert item.value_angle_deg == pytest.approx(expected_angle)


def test_compute_magnitude_polar():
    """
    If value and value_angle_deg are set,
    _compute_magnitude should compute real and imaginary parts.
    """
    angle_deg = math.degrees(math.atan2(4.0, 3.0))
    item = MeasurementItem(
        measurement_type="earthing_impedance",
        value=5.0,
        value_angle_deg=angle_deg,
        unit="Ω"
    )
    _compute_magnitude(None, None, item)
    assert item.value_real == pytest.approx(3.0)
    assert item.value_imag == pytest.approx(4.0)


def test_compute_magnitude_scalar_only():
    """
    If only value (scalar) is provided, the event listener should leave
    real/imag/angle unset (None).
    """
    item = MeasurementItem(
        measurement_type="soil_resistivity",
        value=10.0,
        unit="Ω"
    )
    _compute_magnitude(None, None, item)
    assert item.value == 10.0
    assert item.value_real is None
    assert item.value_imag is None
    assert item.value_angle_deg is None


def test_compute_magnitude_missing_all():
    """
    If neither value nor value_real/value_imag are provided, should raise ValueError.
    """
    item = MeasurementItem(
        measurement_type="soil_resistivity",
        unit="Ω"
    )
    with pytest.raises(ValueError):
        _compute_magnitude(None, None, item)
