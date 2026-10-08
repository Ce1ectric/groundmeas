"""
Compatibility shim: re-export analytics from
:mod:`groundmeas.services.analytics`.

.. deprecated:: 1.5.2
    Import analytics helpers from :mod:`groundmeas` (top-level package)
    or directly from :mod:`groundmeas.services.analytics`. This shim
    module is retained for backwards compatibility with versions
    ``< 1.5`` and will be removed in a future major release.

A :class:`DeprecationWarning` is emitted on attribute access through
this shim. The deprecation pattern is implemented via
:func:`groundmeas._shim.make_shim` so it stays consistent with the
other six shims (``db``, ``models``, ``plots``, ``export``,
``vision_import``, ``cli``).
"""

from __future__ import annotations

from groundmeas.services import analytics as _canonical
from groundmeas._shim import make_shim

__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.analytics",
    canonical_name="groundmeas.services.analytics",
)
