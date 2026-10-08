"""
Compatibility shim: re-export models from :mod:`groundmeas.core.models`.

.. deprecated:: 1.5.2
    Import data models from :mod:`groundmeas` (top-level package) or from
    :mod:`groundmeas.core.models` directly. This shim emits a
    :class:`DeprecationWarning` on first attribute access and will be
    removed in a future major release.

The deprecation pattern is implemented via :func:`groundmeas._shim.make_shim`
so the seven compatibility shims (``db``, ``analytics``, ``models``,
``plots``, ``export``, ``vision_import``, ``cli``) share a single source
of truth.
"""

from __future__ import annotations

from groundmeas.core import models as _canonical
from groundmeas._shim import make_shim

# Pre-1.5 callers occasionally reach for ``_compute_magnitude`` through
# the shim path. Exactly one private re-export is allowed here while the
# rest of the underscore-prefix space stays silent.
__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.models",
    canonical_name="groundmeas.core.models",
    extra_attrs=("_compute_magnitude",),
)
