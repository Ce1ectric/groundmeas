"""
groundmeas.instruments
======================

Readers for instrument exports. They return plain Python/NumPy/pandas data
and do not touch the database; see :mod:`groundmeas.services.omicron_import`
for the import into a groundmeas database.

Currently supported:

* OMICRON COMPANO 100 XML exports (fall-of-potential, reduction factor,
  step/touch output current, soil resistivity) — :class:`CompanoXMLReader`
* OMICRON HGT1 *StepTouch* reports — :class:`Hgt1TXTReader`
"""

from .omicron import (
    TERMINATION_LABELS,
    CompanoXMLReader,
    FallOfPotentialData,
    Hgt1TXTReader,
    MeasurementFileError,
    ReductionFactorData,
    SoilResistivityData,
    informative_locations,
)

__all__ = [
    "CompanoXMLReader",
    "FallOfPotentialData",
    "Hgt1TXTReader",
    "MeasurementFileError",
    "ReductionFactorData",
    "SoilResistivityData",
    "TERMINATION_LABELS",
    "informative_locations",
]
