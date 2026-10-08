"""
Compatibility shim: re-export matplotlib plots from
:mod:`groundmeas.visualization.plots`.

.. deprecated:: 1.5.2
    Import plotting helpers from :mod:`groundmeas` (top-level package)
    or from :mod:`groundmeas.visualization.plots` directly. The shim
    emits a :class:`DeprecationWarning` on first attribute access and
    will be removed in a future major release.
"""

from __future__ import annotations

from groundmeas.visualization import plots as _canonical
from groundmeas._shim import make_shim

__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.plots",
    canonical_name="groundmeas.visualization.plots",
)
