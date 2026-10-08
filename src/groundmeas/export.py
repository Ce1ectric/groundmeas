"""
Compatibility shim: re-export export helpers from
:mod:`groundmeas.services.export`.

.. deprecated:: 1.5.2
    Import exporters from :mod:`groundmeas` (top-level package) or from
    :mod:`groundmeas.services.export` directly. The shim emits a
    :class:`DeprecationWarning` on first attribute access and will be
    removed in a future major release.
"""

from __future__ import annotations

from groundmeas.services import export as _canonical
from groundmeas._shim import make_shim

__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.export",
    canonical_name="groundmeas.services.export",
)
