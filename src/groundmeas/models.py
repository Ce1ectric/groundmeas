"""
Compatibility shim: re-export models from groundmeas.core.models.
"""

from groundmeas.core import models as _models

Location = _models.Location
Measurement = _models.Measurement
MeasurementItem = _models.MeasurementItem
MeasurementType = _models.MeasurementType
MethodType = _models.MethodType
AssetType = _models.AssetType
_compute_magnitude = _models._compute_magnitude

__all__ = [
    "Location",
    "Measurement",
    "MeasurementItem",
    "MeasurementType",
    "MethodType",
    "AssetType",
    "_compute_magnitude",
]
