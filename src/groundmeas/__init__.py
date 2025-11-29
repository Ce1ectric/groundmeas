"""
groundmeas
==========

A Python package for managing, storing, analyzing, and plotting earthing measurements.

Features:
- SQLite + SQLModel (Pydantic) data models for Measurement, MeasurementItem, and Location.
- CRUD operations with simple `connect_db`, `create_*`, `read_*`, `update_*`, and `delete_*` APIs.
- Analytics: impedance vs frequency, real/imag mappings, and rho–f modeling.
- Plotting helpers wrapping matplotlib for quick visualizations.

Example:
    import groundmeas as gm

    gm.connect_db("ground.db")
    mid = gm.create_measurement({...})
    items, ids = gm.read_items_by(measurement_id=mid)
    fig = gm.plot_imp_over_f(mid)
    fig.show()
"""

import logging

# Configure a library logger with a NullHandler by default
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__version__ = "0.3.0"
__author__ = "Ce1ectric"
__license__ = "MIT"

try:
    from .db import (
        connect_db,
        create_measurement,
        create_item,
        read_measurements,
        read_measurements_by,
        read_items_by,
        update_measurement,
        update_item,
        delete_measurement,
        delete_item,
    )
    from .models import Location, Measurement, MeasurementItem
    from .analytics import (
        calculate_split_factor,
        impedance_over_frequency,
        real_imag_over_frequency,
        rho_f_model,
        shield_currents_for_location,
    )
    from .plots import plot_imp_over_f, plot_rho_f_model
except ImportError as e:
    logger.error("Failed to import groundmeas submodule: %s", e)
    raise

__all__ = [
    # database
    "connect_db",
    "create_measurement",
    "create_item",
    "read_measurements",
    "read_measurements_by",
    "read_items_by",
    "update_measurement",
    "update_item",
    "delete_measurement",
    "delete_item",
    # data models
    "Location",
    "Measurement",
    "MeasurementItem",
    # analytics
    "calculate_split_factor",
    "impedance_over_frequency",
    "real_imag_over_frequency",
    "rho_f_model",
    "shield_currents_for_location",
    # plotting
    "plot_imp_over_f",
    "plot_rho_f_model",
    # metadata
    "__version__",
    "__author__",
    "__license__",
]
