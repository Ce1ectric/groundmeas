# ADR-0001 — Compatibility-shim deprecation strategy

- **Status:** Accepted
- **Date:** 2026-05-24

## Context

Before `groundmeas 1.5`, the public surface lived in a flat layout where
`groundmeas.db`, `groundmeas.analytics`, `groundmeas.models`,
`groundmeas.plots`, `groundmeas.export`, `groundmeas.vision_import` and
`groundmeas.cli` were real modules. The `1.5` line moved the
implementation into a layered package (`core/`, `services/`,
`visualization/`, `ui/`) and turned the seven historical names into thin
re-export modules — *compatibility shims* — so that pre-1.5 user code
kept working.

Several recurring problems emerged around these shims:

1. Five of the seven shims did not emit a `DeprecationWarning`, so users
   never received a signal to migrate.
2. The two shims that did warn (`db`, `analytics`) used copy-pasted
   boilerplate that drifted between modules — for example, `db.py` warned
   even on private symbols such as `_get_session`.
3. Tutorial pages continued to teach the legacy shim imports, so new
   users adopted the deprecated style.
4. No ADR existed in the repository that pinned the migration timeline
   or the deprecation contract.

This ADR records the architectural decision that closes findings 1–4.

## Decision

`groundmeas` uses a single helper, `groundmeas._shim.make_shim`, as the
**single source of truth** for the seven compatibility shims. Every
shim module reduces to a docstring plus one call:

```python
from groundmeas.core import db as _canonical
from groundmeas._shim import make_shim

__all__, __getattr__, __dir__ = make_shim(
    canonical=_canonical,
    shim_name="groundmeas.db",
    canonical_name="groundmeas.core.db",
)
```

The helper enforces the following contract:

1. **Lazy `DeprecationWarning` on first attribute access.** The warning
   message names both the shim path and the canonical replacement and
   uses `stacklevel=2` so the user-visible source location is the
   caller, not the shim itself.
2. **Private symbols never warn.** Any attribute name starting with
   underscore raises `AttributeError` without firing a warning, mirroring
   the behaviour of `import _private_name` on the canonical module.
   This closes the `db._get_session` finding.
3. **Opt-in private re-exports.** A shim may pass `extra_attrs=` to keep
   a specific private name accessible — currently only
   `groundmeas.models._compute_magnitude`. Other private names remain
   silent.
4. **`__dir__` returns the canonical surface** so `dir(groundmeas.db)`
   and IDE completion still work.

The seven shims covered by this decision are:

| Shim                       | Canonical replacement                  |
|----------------------------|----------------------------------------|
| `groundmeas.db`            | `groundmeas.core.db`                   |
| `groundmeas.analytics`     | `groundmeas.services.analytics`        |
| `groundmeas.models`        | `groundmeas.core.models`               |
| `groundmeas.plots`         | `groundmeas.visualization.plots`       |
| `groundmeas.export`        | `groundmeas.services.export`           |
| `groundmeas.vision_import` | `groundmeas.services.vision_import`    |
| `groundmeas.cli`           | `groundmeas.ui.cli`                    |

The recommended migration path is **the top-level package**:
`import groundmeas as gm` and then `gm.connect_db`, `gm.distance_profile_value`,
`gm.plot_value_over_distance`, etc. The canonical submodule path is
acceptable for advanced consumers that need to address a single subsystem.

## Removal timeline

| Version | Status        | Action                                                            |
|---------|---------------|-------------------------------------------------------------------|
| `1.5.2` | Current line  | All seven shims warn through `make_shim`; tutorials migrated.     |
| `1.5.x` | Bug-fix line  | Shims kept; warnings continue.                                    |
| `1.6.0` | Minor release | Tutorials and reference docs use canonical imports exclusively.   |
| `2.0.0` | Major release | Shims removed. `from groundmeas.db import …` raises `ImportError`. |

A user who only uses `import groundmeas as gm` will not hit the removal
boundary. The 1.6 line is the migration window for downstream consumers
who still rely on the seven shim modules.

## Consequences

- New code in `groundmeas` **must not** import from the shim modules.
  The pytest suite enforces this against `src/groundmeas/`.
- Documentation **must** use `import groundmeas as gm` in tutorial code
  blocks; reference and analytics pages MAY still show
  `groundmeas.core.db` / `groundmeas.services.analytics` to highlight
  the canonical submodule layout.
- Adding an eighth shim would re-open this ADR. A new shim must justify
  its existence (which pre-1.5 surface does it preserve?) and must use
  `make_shim` from day one.
- The cross-repo `show_versions` convention (candidate ADR-0013 in
  `groundfield`) will reuse the migration window semantics codified
  here: bug-fix line keeps the legacy path, minor release switches the
  recommended docs, major release removes.

## References

- `src/groundmeas/_shim.py` — helper implementation.
- `src/groundmeas/{db,analytics,models,plots,export,vision_import,cli}.py`
  — seven shim modules.
- Regression tests under `tests/` cover the `make_shim` contract
  (public-warn, private-no-warn, `extra_attrs`, unknown-attribute) and
  the tutorial-canonical-imports invariant.
