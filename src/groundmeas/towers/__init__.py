"""
groundmeas.towers
=================

Evaluation of earthing measurements of overhead-line towers (formerly the
package ``tower-grounding-measurement``).

A *campaign* is a folder of OMICRON COMPANO 100 fall-of-potential exports and
HGT1 touch-voltage reports plus two Excel workbooks (measurement description,
grid data) and a JSON configuration. The evaluation determines earthing
impedance (62 % method), footing resistance, touch and step voltages at the
earth-fault current, assesses every tower against the permissible touch
voltage (EN 50522 / EN 50341) and writes JSON, Excel, HTML/PDF and statistics
results. Most users run ``gm-cli towers run --config config.json``;
``gm-cli towers import-db`` copies the instrument data of a campaign into the
groundmeas database (one location per tower).

The building blocks are imported lazily, so ``import groundmeas.towers`` stays
fast::

    from groundmeas.towers import GroundingSystemAnalysis, calculate_summary
"""

from __future__ import annotations

import importlib
from typing import Any, List

_LAZY = {
    "GroundingSystemAnalysis": "groundmeas.towers.analysis",
    "LineModel": "groundmeas.towers.analysis",
    "permitted_voltage_for_time": "groundmeas.towers.analysis",
    "LineProtectionTable": "groundmeas.towers.line_protection",
    "calculate_summary": "groundmeas.towers.campaign",
    "read_config": "groundmeas.towers.config",
    "ConfigError": "groundmeas.towers.config",
    "write_example_config": "groundmeas.towers.config",
    "read_from_device": "groundmeas.towers.files",
    "print_protocol": "groundmeas.towers.protocol",
    "zip_protocols": "groundmeas.towers.protocol",
    "generate_pdf": "groundmeas.towers.pdf",
    "generate_asset_report": "groundmeas.towers.stats",
    "write_demo_campaign": "groundmeas.towers.demo",
    "import_campaign": "groundmeas.towers.database",
    "find_tower_files": "groundmeas.towers.database",
}

__all__ = sorted(_LAZY)


def __getattr__(name: str) -> Any:
    """Import the public API on first access (PEP 562)."""
    if name in _LAZY:
        return getattr(importlib.import_module(_LAZY[name]), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> List[str]:
    return sorted(set(globals()) | set(_LAZY))
