"""
Compatibility shim: re-export database helpers from
:mod:`groundmeas.core.db`.

.. deprecated:: 1.5.2
    Import from :mod:`groundmeas` (top-level package) or from
    :mod:`groundmeas.core.db` directly. This shim module is retained for
    backwards compatibility with versions ``< 1.5`` and will be removed
    in a future major release.

The lazy :class:`DeprecationWarning` pattern was originally wired up
manually. All seven shims were later consolidated onto the single
:func:`groundmeas._shim.make_shim` helper, which also fixed the
private-attribute leak that caused ``from groundmeas.db import _get_session``
to emit a deprecation warning. Private names now raise ``AttributeError``
through the shim, exactly as ``import _get_session`` would behave on the
canonical module.
"""

from __future__ import annotations

from groundmeas.core import db as _canonical
from groundmeas._shim import make_shim

__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.db",
    canonical_name="groundmeas.core.db",
)
