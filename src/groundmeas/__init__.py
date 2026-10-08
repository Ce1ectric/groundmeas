"""
groundmeas
==========

A Python package for managing, storing, analyzing, and plotting earthing measurements.

Features:
- SQLite + SQLModel (Pydantic) data models for Measurement, MeasurementItem, and Location.
- CRUD operations with simple `connect_db`, `create_*`, `read_*`, `update_*`, and `delete_*` APIs.
- Analytics: impedance vs frequency, real/imag mappings, and rho–f modeling.
- Plotting helpers wrapping matplotlib for quick visualizations.

Examples
--------
>>> import groundmeas as gm
>>> gm.connect_db("ground.db")
>>> mid = gm.create_measurement({...})
>>> items, ids = gm.read_items_by(measurement_id=mid)
>>> fig = gm.plot_imp_over_f(mid)
>>> fig.show()
"""

import logging

# Configure a library logger with a NullHandler by default
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__version__ = "1.5.2"
__author__ = "Ce1ectric"
__license__ = "MIT"

try:
    # core
    from .core.db import (
        connect_db,
        disconnect_db,
        create_measurement,
        create_item,
        create_items,
        create_measurement_with_items,
        create_measurements_with_items,
        read_measurements,
        read_measurements_by,
        read_items_by,
        update_measurement,
        update_item,
        delete_measurement,
        delete_item,
    )
    from .core.models import Location, Measurement, MeasurementItem

    # services
    from .services.analytics import (
        calculate_split_factor,
        impedance_over_frequency,
        real_imag_over_frequency,
        rho_f_model,
        shield_currents_for_location,
        distance_profile_value,
        value_over_distance,
        value_over_distance_detailed,
        soil_resistivity_profile,
        soil_resistivity_profile_detailed,
        soil_resistivity_curve,
        layered_earth_forward,
        invert_layered_earth,
        invert_soil_resistivity_layers,
        multilayer_soil_model,
        value_at_62_percent,
        voltage_vt_epr,
    )
    from .services.export import (
        export_measurements_to_json,
        export_measurements_to_csv,
        export_measurements_to_xml,
    )
    from .services.json_import import (
        import_measurements,
        import_measurements_from_json,
    )
    from .services.omicron_import import (
        import_fall_of_potential,
        import_soil_resistivity,
        import_step_touch,
    )
    from .services.vision_import import import_items_from_images

    # visualization
    from .visualization.plots import (
        plot_imp_over_f,
        plot_rho_f_model,
        plot_voltage_vt_epr,
        plot_value_over_distance,
        plot_soil_model,
        plot_soil_inversion,
    )
    from .visualization.vis_plotly import (
        plot_imp_over_f_plotly,
        plot_rho_f_model_plotly,
        plot_voltage_vt_epr_plotly,
        plot_value_over_distance_plotly,
        plot_soil_model_plotly,
        plot_soil_inversion_plotly,
    )
    from .visualization.map_vis import generate_map
except ImportError as e:
    logger.error("Failed to import groundmeas submodule: %s", e)
    raise

__all__ = [
    # database
    "connect_db",
    "disconnect_db",
    "create_measurement",
    "create_item",
    "create_items",
    "create_measurement_with_items",
    "create_measurements_with_items",
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
    "distance_profile_value",
    "value_at_62_percent",
    "voltage_vt_epr",
    "import_items_from_images",
    "export_measurements_to_json",
    "export_measurements_to_csv",
    "export_measurements_to_xml",
    "import_measurements",
    "import_measurements_from_json",
    "import_fall_of_potential",
    "import_step_touch",
    "import_soil_resistivity",
    "soil_resistivity_profile",
    "soil_resistivity_profile_detailed",
    "soil_resistivity_curve",
    "layered_earth_forward",
    "invert_layered_earth",
    "invert_soil_resistivity_layers",
    "multilayer_soil_model",
    # plotting
    "plot_imp_over_f",
    "plot_rho_f_model",
    "plot_voltage_vt_epr",
    "plot_value_over_distance",
    "plot_soil_model",
    "plot_soil_inversion",
    "plot_imp_over_f_plotly",
    "plot_rho_f_model_plotly",
    "plot_voltage_vt_epr_plotly",
    "plot_value_over_distance_plotly",
    "plot_soil_model_plotly",
    "plot_soil_inversion_plotly",
    "generate_map",
    # analytics helpers
    "value_over_distance",
    "value_over_distance_detailed",
    # metadata
    "__version__",
    "__author__",
    "__license__",
]
