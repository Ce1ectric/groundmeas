"""
groundmeas.models
=================

Pydantic/SQLModel data models for earthing measurements.

Defines:
- Location: a measurement site with geographic coordinates.
- Measurement: a test event with metadata and related items.
- MeasurementItem: a measured data point (e.g. impedance, resistivity) with
  magnitude and optional complex components.

Includes an SQLAlchemy event listener to ensure consistency between
value, value_real/value_imag, and value_angle_deg fields.
"""

import logging
import math
import numpy as np
from datetime import datetime, timezone
from typing import Optional, List, Literal

from sqlalchemy import Column, String, event
from sqlmodel import SQLModel, Field, Relationship

from pydantic import field_validator

logger = logging.getLogger(__name__)


MeasurementType = Literal[
    "prospective_touch_voltage",
    "touch_voltage",
    "earth_potential_rise",
    "step_voltage",
    "transferred_potential",
    "earth_fault_current",
    "earthing_current",
    "shield_current",
    "earthing_resistance",
    "earthing_impedance",
    "soil_resistivity",
]

MethodType = Literal[
    "staged_fault_test",
    "injection_remote_substation",
    "injection_earth_electrode",
]

AssetType = Literal[
    "substation",
    "overhead_line_tower",
    "cable",
    "cable_cabinet",
    "house",
    "pole_mounted_transformer",
    "mv_lv_earthing_system",
]


class Location(SQLModel, table=True):
    """
    A geographic location where measurements are taken.

    Attributes:
        id: Auto-generated primary key.
        name: Human-readable site name.
        latitude: Decimal degrees latitude.
        longitude: Decimal degrees longitude.
        altitude: Altitude in meters (optional).
        measurements: Back-reference to Measurement records for this site.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(..., description="Site name")
    latitude: Optional[float] = Field(None, description="Latitude (°)")
    longitude: Optional[float] = Field(None, description="Longitude (°)")
    altitude: Optional[float] = Field(None, description="Altitude (m)")
    measurements: List["Measurement"] = Relationship(back_populates="location")


class Measurement(SQLModel, table=True):
    """
    A single earthing measurement event.

    Attributes:
        id: Auto-generated primary key.
        timestamp: UTC datetime when the measurement occurred.
        location_id: FK to Location.
        location: Relationship to the Location object.
        method: Measurement method used.
        voltage_level_kv: System voltage in kilovolts (optional).
        asset_type: Type of asset under test.
        fault_resistance_ohm: Fault resistance in ohms (optional).
        operator: Name or identifier of the operator (optional).
        description: Free-text notes (optional).
        items: List of MeasurementItem objects associated to this event.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of measurement",
    )
    location_id: Optional[int] = Field(default=None, foreign_key="location.id")
    location: Optional[Location] = Relationship(back_populates="measurements")
    method: MethodType = Field(
        sa_column=Column(String, nullable=False), description="Measurement method"
    )
    voltage_level_kv: Optional[float] = Field(None, description="Voltage level in kV")
    asset_type: AssetType = Field(
        sa_column=Column(String, nullable=False), description="Type of asset"
    )
    fault_resistance_ohm: Optional[float] = Field(
        None, description="Fault resistance (Ω)"
    )
    operator: Optional[str] = Field(None, description="Operator name")
    description: Optional[str] = Field(None, description="Notes")
    items: List["MeasurementItem"] = Relationship(back_populates="measurement")


class MeasurementItem(SQLModel, table=True):
    """
    A single data point within a Measurement.

    Supports both real/imaginary and magnitude/angle representations.

    Attributes:
        id: Auto-generated primary key.
        measurement_type: Type of this data point.
        value: Scalar magnitude (Ω or other unit).
        value_real: Real component, if complex (Ω).
        value_imag: Imaginary component, if complex (Ω).
        value_angle_deg: Phase angle in degrees (optional).
        unit: Unit string, e.g. "Ω", "m".
        description: Free-text notes (optional).
        frequency_hz: Frequency in Hz (optional).
        additional_resistance_ohm: Extra series resistance (optional).
        input_impedance_ohm: Instrument input impedance (optional).
        measurement_distance_m: Depth or distance for resistivity (optional).
        measurement_id: FK to parent Measurement.
        measurement: Relationship to the Measurement object.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    measurement_type: MeasurementType = Field(
        sa_column=Column(String, nullable=False), description="Data point type"
    )
    value: Optional[float] = Field(None, description="Magnitude or scalar value")
    value_real: Optional[float] = Field(None, description="Real part of complex value")
    value_imag: Optional[float] = Field(
        None, description="Imaginary part of complex value"
    )
    value_angle_deg: Optional[float] = Field(None, description="Phase angle in degrees")
    unit: str = Field(..., description="Unit of the measurement")
    description: Optional[str] = Field(None, description="Item notes")
    frequency_hz: Optional[float] = Field(None, description="Frequency (Hz)")
    additional_resistance_ohm: Optional[float] = Field(
        None, description="Additional series resistance (Ω)"
    )
    input_impedance_ohm: Optional[float] = Field(
        None, description="Instrument input impedance (Ω)"
    )
    measurement_distance_m: Optional[float] = Field(
        None, description="Depth/distance for soil resistivity (m)"
    )
    distance_to_current_injection_m: Optional[float] = Field(
        None, description="Distance to the current injection point (m)"
    )
    measurement_id: Optional[int] = Field(default=None, foreign_key="measurement.id")
    measurement: Optional[Measurement] = Relationship(back_populates="items")


@event.listens_for(MeasurementItem, "before_insert", propagate=True)
@event.listens_for(MeasurementItem, "before_update", propagate=True)
def _compute_magnitude(mapper, connection, target: MeasurementItem):
    """
    SQLAlchemy event listener to enforce and propagate between
    complex and polar representations:

      - If `value` is None but real/imag are set, computes magnitude
        and phase angle (degrees).
      - If `value` is set and `value_angle_deg` is set, computes
        `value_real` and `value_imag`.
      - If neither representation is present, raises ValueError.

    Raises:
        ValueError: if no valid value is provided.
    """
    try:
        # Case A: only rectangular given → compute scalar and angle
        if target.value is None:
            if target.value_real is not None or target.value_imag is not None:
                r = target.value_real or 0.0
                i = target.value_imag or 0.0
                target.value = math.hypot(r, i)
                target.value_angle_deg = float(np.degrees(np.arctan2(i, r)))
            else:
                logger.error(
                    "MeasurementItem %s lacks both magnitude and real/imag components",
                    getattr(target, "id", "<new>"),
                )
                raise ValueError(
                    "Either `value` or at least one of (`value_real`, `value_imag`) must be provided"
                )
        # Case B: polar given → compute rectangular components
        elif target.value_angle_deg is not None:
            angle_rad = math.radians(target.value_angle_deg)
            target.value_real = float(target.value * math.cos(angle_rad))
            target.value_imag = float(target.value * math.sin(angle_rad))
    except Exception:
        # Ensure that any unexpected error in conversion is logged
        logger.exception(
            "Failed to compute magnitude/angle for MeasurementItem %s",
            getattr(target, "id", "<new>"),
        )
        raise
