"""
groundmeas._shim
================

Single source of truth for the "compatibility shim" module pattern used
throughout the package.

Background
----------
Pre-1.5 versions of groundmeas exposed several submodules at the top
level (``groundmeas.db``, ``groundmeas.analytics``, ``groundmeas.models``,
``groundmeas.plots``, ``groundmeas.export``, ``groundmeas.vision_import``,
``groundmeas.cli``). With the move to ``core/``, ``services/``,
``visualization/`` and ``ui/`` subpackages those top-level modules became
thin re-export shims so existing user code kept working.

Two of them (``db`` and ``analytics``) were originally retrofitted with
a lazy :class:`DeprecationWarning` and an explicit canonical-attribute
table. The remaining five (``models``, ``plots``, ``export``,
``vision_import``, ``cli``) received the same treatment, and the
boilerplate was consolidated into a single helper rather than being
copy-pasted between modules.

The :func:`make_shim` factory builds the trio of names (``__all__``,
``__getattr__``, ``__dir__``) every compatibility shim needs. Each shim
file therefore reduces to a docstring plus a single ``make_shim(...)``
call.

Examples
--------
A typical shim now looks like this::

    \"\"\"Compatibility shim — see :func:`groundmeas._shim.make_shim`.\"\"\"

    from groundmeas.core import models as _canonical
    from groundmeas._shim import make_shim

    __all__, __getattr__, __dir__ = make_shim(
        canonical=_canonical,
        shim_name="groundmeas.models",
        canonical_name="groundmeas.core.models",
    )
"""

from __future__ import annotations

import warnings as _warnings
from types import ModuleType
from typing import Callable, Iterable, List, Optional, Sequence, Tuple


def _public_names(canonical: ModuleType) -> List[str]:
    """Return the public symbol surface of *canonical*."""
    explicit = getattr(canonical, "__all__", None)
    if explicit is not None:
        return [name for name in explicit if not name.startswith("_")]
    return [name for name in dir(canonical) if not name.startswith("_")]


def make_shim(
    canonical: ModuleType,
    shim_name: str,
    canonical_name: Optional[str] = None,
    extra_attrs: Optional[Sequence[str]] = None,
    warn_category: type = DeprecationWarning,
) -> Tuple[List[str], Callable[[str], object], Callable[[], List[str]]]:
    """
    Build the ``(__all__, __getattr__, __dir__)`` trio for a shim module.

    Parameters
    ----------
    canonical : module
        The replacement module the shim re-exports from.
    shim_name : str
        Dotted name of the deprecated shim module (e.g. ``"groundmeas.models"``).
    canonical_name : str, optional
        Dotted name of the canonical replacement module
        (e.g. ``"groundmeas.core.models"``). Defaults to ``canonical.__name__``.
    extra_attrs : sequence[str], optional
        Additional attribute names that must be exposed even though they
        are not part of the canonical module's public surface. Useful for
        intentionally re-exporting private helpers (``_compute_magnitude``
        in :mod:`groundmeas.models`) without triggering the deprecation
        warning on a *different* private symbol.
    warn_category : type, default DeprecationWarning
        Warning category emitted on first attribute access.

    Returns
    -------
    tuple
        ``(__all__, __getattr__, __dir__)`` ready to be assigned at module
        level in the shim file.

    Notes
    -----
    * Only public names (and names listed in *extra_attrs*) trigger the
      deprecation warning. Other private symbols raise ``AttributeError``,
      mirroring the underscore-prefix short-circuit (the shim must not
      warn on private names such as ``_get_session``).
    * The warning carries ``stacklevel=2`` so the user-visible source
      location is the caller, not the shim itself.
    """
    if canonical_name is None:
        canonical_name = canonical.__name__

    extra = list(extra_attrs or [])
    public = _public_names(canonical)
    # Preserve order while de-duplicating.
    seen: dict = {}
    for name in list(public) + list(extra):
        seen.setdefault(name, None)
    all_names: List[str] = list(seen.keys())

    def __getattr__(name: str) -> object:
        if name.startswith("_") and name not in extra:
            # Private symbols (``_get_session`` and friends) must not
            # trigger the deprecation warning.
            raise AttributeError(f"module {shim_name!r} has no attribute {name!r}")
        if name in all_names or hasattr(canonical, name):
            _warnings.warn(
                f"{shim_name} is a compatibility shim and will be removed in a "
                f"future major release; import {name!r} from 'groundmeas' or "
                f"'{canonical_name}' instead.",
                warn_category,
                stacklevel=2,
            )
            return getattr(canonical, name)
        raise AttributeError(f"module {shim_name!r} has no attribute {name!r}")

    def __dir__() -> List[str]:
        return sorted(set(all_names))

    return all_names, __getattr__, __dir__


__all__ = ["make_shim"]
