"""
Compatibility shim: re-export the CLI entry point from
:mod:`groundmeas.ui.cli`.

.. deprecated:: 1.5.2
    Import the Typer app from :mod:`groundmeas.ui.cli` directly. The
    shim emits a :class:`DeprecationWarning` on first attribute access
    and will be removed in a future major release.

The packaged ``gm-cli`` entry point already points at
``groundmeas.ui.cli:app`` in ``pyproject.toml``; only third-party scripts
that imported ``groundmeas.cli.app`` directly are affected by this
deprecation.
"""

from __future__ import annotations

from groundmeas.ui import cli as _canonical
from groundmeas._shim import make_shim

# ``app`` is the only public symbol the legacy module ever exposed.
__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.cli",
    canonical_name="groundmeas.ui.cli",
    extra_attrs=("app",),
)
