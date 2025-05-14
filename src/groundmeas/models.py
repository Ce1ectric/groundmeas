# src/groundmeas/models.py

import numpy as np
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, timezone
from typing import Optional, List, Literal
from sqlalchemy import Column, String, event

MeasurementType = Literal[
    "prospective_touch_voltage",
    "touch_voltage",
    "earth_potential_rise",
    "step_voltage",
    "transferred_potential",
    "earth_fault_current",
    "earthing_current",
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
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    measurements: List["Measurement"] = Relationship(back_populates="location")


class Measurement(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    location_id: Optional[int] = Field(default=None, foreign_key="location.id")
    location: Optional[Location] = Relationship(back_populates="measurements")
    method: MethodType = Field(sa_column=Column(String, nullable=False))
    voltage_level_kv: Optional[float] = None
    asset_type: AssetType = Field(sa_column=Column(String, nullable=False))
    fault_resistance_ohm: Optional[float] = None
    operator: Optional[str] = None
    description: Optional[str] = None
    items: List["MeasurementItem"] = Relationship(back_populates="measurement")


class MeasurementItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    measurement_type: MeasurementType = Field(sa_column=Column(String, nullable=False))
    value: Optional[float] = None
    value_real: Optional[float] = None
    value_imag: Optional[float] = None
    value_angle_deg: Optional[float] = None
    unit: str
    description: Optional[str] = None
    frequency_hz: Optional[float] = None
    additional_resistance_ohm: Optional[float] = None
    input_impedance_ohm: Optional[float] = None
    measurement_distance_m: Optional[float] = None
    measurement_id: Optional[int] = Field(default=None, foreign_key="measurement.id")
    measurement: Optional[Measurement] = Relationship(back_populates="items")


# event listener to calculate the magnitude of a measurement item
@event.listens_for(MeasurementItem, "before_insert", propagate=True)
@event.listens_for(MeasurementItem, "before_update", propagate=True)
def _compute_magnitude(mapper, connection, target: MeasurementItem):
    if target.value is None:
        if target.value_real is not None or target.value_imag is not None:
            r = target.value_real or 0.0
            i = target.value_imag or 0.0
            target.value = (r**2 + i**2) ** 0.5
            target.value_angle_deg = np.degrees(np.arctan2(i, r))
        else:
            # raise a ValueError("Either value or (value_real and value_imag) must be provided.")
            raise ValueError(
                f"MeasurementItem(id={getattr(target, 'id', None)}) has no value or real/imag parts"
            )
    elif target.value_angle_deg is not None:
        # Convert degrees to radians
        angle_rad = target.value_angle_deg * np.pi / 180
        # Calculate the real and imaginary parts
        r = target.value * np.cos(angle_rad)
        i = target.value * np.sin(angle_rad)
        target.value_real = r
        target.value_imag = i
