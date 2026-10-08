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

from sqlalchemy import Column, String, event, inspect as sa_inspect
from sqlmodel import SQLModel, Field, Relationship

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
    "wenner",
    "schlumberger",
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
    Geographic location where measurements are taken.

    Attributes
    ----------
    id : int, optional
        Auto-generated primary key.
    name : str
        Human-readable site name.
    latitude : float, optional
        Decimal degrees latitude.
    longitude : float, optional
        Decimal degrees longitude.
    altitude : float, optional
        Altitude in meters.
    measurements : list[Measurement]
        Back-reference to measurements at this site.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(..., description="Site name")
    latitude: Optional[float] = Field(None, description="Latitude (°)")
    longitude: Optional[float] = Field(None, description="Longitude (°)")
    altitude: Optional[float] = Field(None, description="Altitude (m)")
    measurements: List["Measurement"] = Relationship(back_populates="location")


class Measurement(SQLModel, table=True):
    """
    Single earthing measurement event.

    Attributes
    ----------
    id : int, optional
        Auto-generated primary key.
    timestamp : datetime
        UTC datetime when the measurement occurred.
    location_id : int, optional
        Foreign key to Location.
    location : Location, optional
        Relationship to the Location object.
    method : MethodType
        Measurement method used.
    voltage_level_kv : float, optional
        System voltage in kilovolts.
    asset_type : AssetType
        Type of asset under test.
    fault_resistance_ohm : float, optional
        Fault resistance in ohms.
    operator : str, optional
        Operator name/identifier.
    description : str, optional
        Free-text notes.
    items : list[MeasurementItem]
        Related measurement items.
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
    A single data point within a measurement.

    Supports both real/imaginary and magnitude/angle representations.

    Attributes
    ----------
    id : int, optional
        Auto-generated primary key.
    measurement_type : MeasurementType
        Type of this data point.
    value : float, optional
        Scalar magnitude (Ω or other unit).
    value_real : float, optional
        Real component if complex.
    value_imag : float, optional
        Imaginary component if complex.
    value_angle_deg : float, optional
        Phase angle in degrees.
    unit : str
        Unit string, e.g., "Ω", "m".
    description : str, optional
        Free-text notes.
    frequency_hz : float, optional
        Frequency in Hz.
    additional_resistance_ohm : float, optional
        Extra series resistance.
    input_impedance_ohm : float, optional
        Instrument input impedance.
    measurement_distance_m : float, optional
        Depth/distance (e.g., for soil or Fall-of-Potential).
    distance_to_current_injection_m : float, optional
        Distance to the current injection point (m).
    measurement_id : int, optional
        Foreign key to parent Measurement.
    measurement : Measurement, optional
        Relationship to the Measurement object.
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


_POLAR_ATTRS = ("value", "value_angle_deg")
_RECT_ATTRS = ("value_real", "value_imag")


def _polar_from_rect(target: MeasurementItem) -> None:
    """Derive ``value`` and ``value_angle_deg`` from the rectangular components."""
    r = target.value_real or 0.0
    i = target.value_imag or 0.0
    target.value = math.hypot(r, i)
    target.value_angle_deg = float(np.degrees(np.arctan2(i, r)))


def _rect_from_polar(target: MeasurementItem) -> None:
    """Derive ``value_real`` and ``value_imag`` from the polar components."""
    if target.value is None or target.value_angle_deg is None:
        return
    angle_rad = math.radians(target.value_angle_deg)
    target.value_real = float(target.value * math.cos(angle_rad))
    target.value_imag = float(target.value * math.sin(angle_rad))


def _history_has_real_change(target: MeasurementItem, attrs: tuple[str, ...]) -> bool:
    """
    Return True if any of ``attrs`` has a *persisted-value* change.

    Unlike :meth:`History.has_changes`, this comparison ignores the
    "initial None vs. currently None" case that SQLAlchemy reports for
    transient/freshly-loaded instances where an attribute was touched but
    never actually set to a non-default value. The comparison is therefore
    reliable for the ``before_update`` listener, which is the only place
    this helper is used.
    """
    state = sa_inspect(target)
    for name in attrs:
        try:
            hist = state.attrs[name].history
        except KeyError:
            continue
        if not hist.has_changes():
            continue
        added = hist.added or ()
        deleted = hist.deleted or ()
        current = tuple(added) + tuple(deleted)
        if any(v is not None for v in current):
            return True
    return False


def _compute_magnitude(mapper, connection, target: MeasurementItem):
    """
    Insert-time listener that fills in the missing representation.

    * If ``value`` is None but real/imag are set, computes magnitude and phase angle.
    * If ``value`` and ``value_angle_deg`` are set, computes ``value_real`` and ``value_imag``.
    * If neither representation is present, raises ``ValueError``.

    Raises
    ------
    ValueError
        If no valid value is provided.
    """
    try:
        # Case A: only rectangular given → compute scalar and angle
        if target.value is None:
            if target.value_real is not None or target.value_imag is not None:
                _polar_from_rect(target)
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
            _rect_from_polar(target)
    except Exception:
        logger.exception(
            "Failed to compute magnitude/angle for MeasurementItem %s",
            getattr(target, "id", "<new>"),
        )
        raise


def _sync_magnitude_on_update(mapper, connection, target: MeasurementItem):
    """
    Keep polar (magnitude/angle) and rectangular (real/imag) in sync on update.

    Decides, using SQLAlchemy attribute history, which representation the
    caller actually modified in this flush and refreshes the other one:

    * Only rectangular components changed → magnitude and phase angle are
      recomputed from them.
    * Only polar components changed → the rectangular fields are recomputed
      from the new magnitude/angle.
    * Both sides were modified in the same flush → the polar representation
      wins and a warning is logged.

    Rows that were not touched on the value axis are left alone so unrelated
    updates (e.g., editing ``description`` only) never clobber existing data.
    """
    try:
        polar_changed = _history_has_real_change(target, _POLAR_ATTRS)
        rect_changed = _history_has_real_change(target, _RECT_ATTRS)

        if polar_changed and rect_changed:
            logger.warning(
                "MeasurementItem %s updated both polar and rectangular "
                "components in one flush; polar representation wins.",
                getattr(target, "id", "<new>"),
            )
            _rect_from_polar(target)
            return

        if rect_changed and not polar_changed:
            _polar_from_rect(target)
            return

        if polar_changed and not rect_changed:
            if target.value is not None and target.value_angle_deg is not None:
                _rect_from_polar(target)
            elif target.value is None and (
                target.value_real is not None or target.value_imag is not None
            ):
                _polar_from_rect(target)
    except Exception:
        logger.exception(
            "Failed to sync magnitude/angle on update for MeasurementItem %s",
            getattr(target, "id", "<new>"),
        )
        raise


event.listen(MeasurementItem, "before_insert", _compute_magnitude, propagate=True)
event.listen(
    MeasurementItem, "before_update", _sync_magnitude_on_update, propagate=True
)
