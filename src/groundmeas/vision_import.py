"""
Compatibility shim: re-export OCR helpers from
:mod:`groundmeas.services.vision_import`.

.. deprecated:: 1.5.2
    Import OCR / vision helpers from :mod:`groundmeas` (top-level
    package) or from :mod:`groundmeas.services.vision_import` directly.
    The shim emits a :class:`DeprecationWarning` on first attribute
    access and will be removed in a future major release.
"""

from __future__ import annotations

from groundmeas.services import vision_import as _canonical
from groundmeas._shim import make_shim

__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.vision_import",
    canonical_name="groundmeas.services.vision_import",
)
