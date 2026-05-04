# Changelog

All notable changes to `groundmeas` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Change categories follow the Keep-a-Changelog vocabulary:

- **Added** — new features and public API.
- **Changed** — behaviour changes to existing public API.
- **Deprecated** — features that still work but will be removed.
- **Removed** — features taken out of the public API.
- **Fixed** — bug fixes.
- **Security** — vulnerability fixes.
- **Docs** — documentation-only changes.
- **Internal** — refactors, tests, packaging, CI; no observable behaviour change.

The backlog of ideas that are not yet scheduled is kept at the end of this
file under **Roadmap**. Unsorted user-submitted proposals live in the
**Ideas inbox** subsection at the very bottom — add a bullet there whenever
something comes up, and it will be triaged into the appropriate roadmap
category (or pulled straight into `[Unreleased]`) in the next cycle.

During regular work, add your entry under the matching category in
`[Unreleased]`; the release script (`scripts/release.py`) moves the whole
`[Unreleased]` block into a new version section when a release is cut.

---

## [Unreleased]

---

## [1.5.0] — 2026-05-04

### Added

- `CHANGELOG.md` (this file) with a Keep-a-Changelog structure, an
  `[Unreleased]` staging block, and a Roadmap / Ideas-inbox section for
  triaging future work.

### Changed

- `scripts/release.py` now moves the `[Unreleased]` block in
  `CHANGELOG.md` into a dated `## [X.Y.Z] — YYYY-MM-DD` section, inserts
  a fresh empty `[Unreleased]` block above it, and refreshes the
  compare-link footer. The bump aborts when `[Unreleased]` carries no
  bullet entries unless `--allow-empty` is passed. `CHANGELOG.md` is
  added to the release commit.
- `scripts/release.py` validates `CITATION.cff` via
  `cffconvert --validate` immediately after bumping the version. A
  missing `cffconvert` is a warning only; a real validation error
  aborts the release.

### Docs

- `docs/99_contributing.md` extended with a "Changelog" and an updated
  "Release process" section: Keep-a-Changelog conventions, the local
  reproduction of the CI changelog check, and the new
  `--allow-empty` escape hatch for packaging-only releases.

### Internal

- New stdlib-only helper module `scripts/_changelog.py` exposing
  `bump_changelog(...)`, kept free of `typer` / `rich` so the changelog
  rewrite can be unit-tested without the CLI dependencies.
- `tests/test_release.py` covers the changelog move, compare-link
  rewrite, empty-block rejection, `--allow-empty` path and regression
  cases (idempotency, blank-line preservation, trailing-text
  invariants).
- New `scripts/check_changelog.py` with pure helpers
  (`changes_touch_src`, `parse_diff_hunks`,
  `find_unreleased_line_range`, `diff_touches_unreleased`); CI step in
  `.github/workflows/ci-cd.yml` rejects PRs that change files under
  `src/groundmeas/` without touching the `[Unreleased]` block. Opt-out
  via the `skip-changelog` PR label.
- `tests/test_check_changelog.py` covers the helper functions over a
  set of synthetic unified diffs.
- CI step `Validate CITATION.cff` runs the `cffconvert` GitHub Action
  on every push and pull request.
- `actions/checkout` now runs with `fetch-depth: 0` so the changelog
  check can diff against the PR base ref.
- `cffconvert` and `pre-commit` added to the dev dependency group so
  `poetry run release` finds the validator without a global install
  and contributors get a frictionless `pre-commit install` flow.
- New `.pre-commit-config.yaml` mirrors the CI gates locally: `black`
  and basic hygiene hooks on every commit, the changelog check
  (against `origin/main`) and `cffconvert --validate` on every push.
  Generated artefacts (`THIRD_PARTY_LICENSES_RAW.txt`,
  `THIRD_PARTY_NOTICES.md`, `site/`, `dist/`,
  `src/groundmeas/__pycache__/`) are excluded so the hygiene hooks do
  not fight the licenses generator on every regenerate.

---

## [1.4.3] — 2026-04-22

Stability patch collecting fixes from the first code-review pass.

### Fixed

- `create_measurement` / `update_measurement` no longer insert duplicate
  `Location` rows when the same coordinates are supplied through different
  call sites. Existing rows at the same `(name, latitude, longitude)` are
  reused instead of shadowed.

### Internal

- Follow-ups from the `fix/code-review-bugs-1-9` batch.

> Note: version `1.4.2` was skipped — no tag was published.

---

## [1.4.1] — 2026-04-21

Dashboard UX polish for multi-site campaigns.

### Added

- Streamlit dashboard now groups map markers by `Location` coordinates:
  each site renders as a single marker, and selecting a marker filters
  the measurement table and plots to every campaign at that site.

### Changed

- Location matching in the dashboard is done by coordinate tuple instead
  of primary key, so measurements imported with the same physical site
  but a fresh DB row are still aggregated correctly.

### Internal

- `CLAUDE.md` project file added at the repo root.
- `.gitignore` extended to cover notebook artefacts, exports
  (`*.csv`, `*.json`, `*.xml`, `*.db`) and generated license reports.

---

## [1.4.0] — 2026-01-14

First pass at multilayer soil modelling.

### Added

- Multilayer soil model for Wenner and Schlumberger arrays:
  - `layered_earth_forward(...)` — forward apparent-resistivity curve
    for a given 1–3-layer model (`rho_1..3`, `h_1..2`).
  - `invert_layered_earth(...)` / `invert_soil_resistivity_layers(...)` —
    non-linear least-squares inversion from a measured
    `rho_a(a)` curve to a layered model.
  - `multilayer_soil_model(...)` — convenience wrapper that picks the
    best-fitting 1-, 2- or 3-layer model by residual and AIC.
- `plot_soil_model` / `plot_soil_inversion` (matplotlib) and
  `plot_soil_model_plotly` / `plot_soil_inversion_plotly` (Plotly).
- Public API re-exports in `src/groundmeas/__init__.py`.

### Docs

- `docs/15_analytics.md` extended with a layered-earth section.

---

## [1.3.1] – [1.3.4]

Maintenance releases between the first dashboard cut (`1.3.0`) and the
multilayer-soil work in `1.4.0`. Bundled here because no entry was
written at release time and the diffs are tooling/packaging only.

### Internal

- Restructured the package into `core/`, `services/`, `visualization/`
  and `ui/` subpackages; flat shim modules kept at the package root for
  backwards compatibility (`1.3.1`).
- `scripts/generate_third_party_licenses.py` and the `licenses` entry
  point added; built `site/` directory removed from the repo and added
  to `.gitignore` (`1.3.1`).
- MkDocs configuration and initial documentation site under `docs/`
  (`1.3.1`).
- Release script (`scripts/release.py`) reworked to keep
  `pyproject.toml`, `CITATION.cff` and `__init__.__version__` in sync
  on bump (`1.3.2`).
- CI/CD pipeline tweaks for the PyPI Trusted Publishing flow (`1.3.4`).

> Note: `1.3.3` was a version bump only and contains no functional
> changes.

---

## [1.3.0] — 2025-12-24

First Streamlit dashboard release.

### Added

- Streamlit dashboard (`gm-cli dashboard` / `streamlit run
  src/groundmeas/ui/dashboard.py`) with folium map, per-measurement
  filtering and embedded plotly charts.
- `visualization/map_vis.py` — folium helper `generate_map(...)`.
- Public Plotly plotting layer (`visualization/vis_plotly.py`).

### Docs

- `docs/16_dashboard.md` added.

---

## [1.0.0] – [1.2.x]

Earlier development releases building up the core feature set:

- SQLite + SQLModel data model (`Location`, `Measurement`,
  `MeasurementItem`) with polar / rectangular value sync on insert and
  update.
- CRUD API: `connect_db`, `create_*`, `read_*`, `update_*`, `delete_*`.
- Analytics core:
  - `impedance_over_frequency`, `real_imag_over_frequency`
  - `rho_f_model` — `Z(ρ,f) = k1·ρ + (k2+jk3)·f + (k4+jk5)·ρ·f` fit
  - `distance_profile_value`, `value_over_distance`,
    `value_over_distance_detailed` — reduction algorithms
    (`maximum`, `62_percent`, `minimum_gradient`, `minimum_stddev`,
    `inverse`)
  - `soil_resistivity_profile`, `soil_resistivity_curve`
  - `calculate_split_factor`, `shield_currents_for_location`,
    `voltage_vt_epr`
- Matplotlib plotting helpers (`plots.py`).
- OCR import from measurement-instrument screenshots
  (`services/vision_import.py`, pytesseract + OpenCV).
- JSON / CSV / XML export (`services/export.py`).
- Typer-based CLI (`gm-cli`) and MkDocs documentation site.

See the git log (`git log v1.0.0..v1.3.0`) for the per-version
breakdown — these releases predate this changelog and are not
back-filled by category.

---

[Unreleased]: https://github.com/Ce1ectric/groundmeas/compare/v1.5.0...HEAD
[1.5.0]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.3...v1.5.0
[1.4.3]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.1...v1.4.3
[1.4.1]: https://github.com/Ce1ectric/groundmeas/compare/v1.4.0...v1.4.1
[1.4.0]: https://github.com/Ce1ectric/groundmeas/compare/v1.3.4...v1.4.0
[1.3.4]: https://github.com/Ce1ectric/groundmeas/compare/v1.3.0...v1.3.4
[1.3.0]: https://github.com/Ce1ectric/groundmeas/releases/tag/v1.3.0

---

## Roadmap

Feature ideas and scheduled work. Graduate an item from here into the
appropriate category of `[Unreleased]` once it is implemented and ready
for release. Unsorted raw proposals live in the **Ideas inbox** at the
bottom of this section.

### Scope boundary

`groundmeas` is the **measurement-data** layer of the grounding toolchain:
acquisition, storage, cleaning, analytics and visualisation of field
measurements (earthing impedance, soil resistivity, split-factor studies,
shield-current profiles). Explicit non-goals — handled in companion
packages — are listed at the end.

### Near term — changelog & release workflow (target: 1.5.0)

- **Teach `scripts/release.py` about `CHANGELOG.md`** — on a release
  bump, move the `[Unreleased]` block into a new
  `## [X.Y.Z] — YYYY-MM-DD` section, insert a fresh empty
  `[Unreleased]`, and update the compare-link at the bottom. Abort the
  release when `[Unreleased]` is empty unless `--allow-empty` is
  passed. Mirrors the groundinsight flow.
- **CI check**: fail the PR if `CHANGELOG.md`'s `[Unreleased]` section
  was not touched by a commit that changed `src/` — a simple
  `scripts/check_changelog.py` step in `ci-cd.yml`. Opt-out via a
  `skip-changelog` label on the PR.
- **`CITATION.cff` validation in CI** (`cff-validator`) and a
  `citation` check in the release script.

### Near term — bridge to `groundinsight` (target: 1.5.0 – 1.6.0)

These items define the data-exchange surface between measurement data in
`groundmeas` and reduced circuit models in `groundinsight`.

- **`Measurement → ImpedanceTable` exporter** — produce the
  `Dict[Tuple[rho, f], ComplexNumber]` format that `groundinsight`'s
  `BusType` / `BranchType` accepts directly, so a measured `Z(f)` curve
  can be dropped into a network model without reformatting.
- **Soil-model hand-off** — export the best 1–3-layer model from
  `multilayer_soil_model(...)` as a `SoilModel` payload
  (`rho_1`, `rho_2`, `h_12`) matching groundinsight's upcoming
  two-layer type.
- **Campaign → `Network` skeleton builder** — for a campaign that has
  a repeatable topology (TN-Ortsnetz measurement with auxiliary
  electrode at distances `d_i`), emit a `Network` skeleton with one
  bus per measurement location pre-populated with the measured
  impedance table. Saves the hand-transcription step in AP 1 reference
  cases.

### Near term — analytics & data model

- **N-layer soil model** — generalise the 1–3-layer inversion to an
  arbitrary number of layers using Koefoed-filter / linear-filter
  forward kernels, with AIC-based layer-count selection. Current
  implementation caps at 3.
- **Confidence bands on inversion results** — propagate the measurement
  covariance through `invert_layered_earth` (Jacobian at the optimum)
  and plot 1-σ / 2-σ bands on `plot_soil_inversion*`. AP 1 reviewers
  always ask.
- **Touch- and step-voltage `measurement_type`** — new `Literal` values
  plus unit defaults; ensure CLI completers and dashboard filters
  pick them up.
- **Measurement uncertainty fields** — add optional `uncertainty_abs`
  / `uncertainty_rel` on `MeasurementItem`, carried through analytics
  and plotting (error bars on rho–f plots, weighted fits).
- **Time-domain / impulse measurements** — new `measurement_type` and
  storage for waveform traces (blob + sample-rate), forward-FFT helper
  into the existing frequency-domain analytics.

### Near term — I/O & import

- **Native importers for common instruments** — file-format parsers
  for Omicron COMPANO 100 and CPC 100 + HGT1. Replaces the OCR path for instruments that already
  export CSV / XML.
- **EXIF metadata in `import_items_from_images`** — read lat/lon and
  timestamp from image EXIF where present, pre-fill the `Location`
  and `Measurement.timestamp` instead of requiring a second step.
- **Bulk CSV importer** — schema-mapping importer for long-format CSVs
  (one row per `MeasurementItem`), complementing the OCR path.
- generate a output pdf protocol of specific measurements based on a template file, it needs some user inputs or default values like earth fault current, tripping time, relevant national standard etc. to create a measurement protocol

### Near term — UX & tooling

- **Dashboard auth layer** — optional simple auth (HTTP basic or
  single-token) so the dashboard can be exposed internally without
  dropping the whole DB on the network.
- **CLI `campaign` subcommand** — group measurements that share a
  location, operator and date into a campaign view, with bulk edit
  and export.
- **Dependabot** for Python and GitHub Actions dependencies.
- **Codecov integration** — upload the coverage XML from CI and show
  a PR diff badge; currently the report is only a workflow artifact.

### Medium term

- **Measurement-campaign report generator** — render a per-campaign
  PDF (reportlab) or `.docx` with metadata, map, plots and a
  soil-model summary, suitable as an appendix in field reports.
- **REST API surface** — FastAPI wrapper around the CRUD layer and
  a read-only view of the analytics functions. Scope to decide: thin
  RPC vs. job-oriented with background workers.
- **Grey-box parameter identification** — fit bus grounding
  impedances and coupling parameters in a `groundinsight` `Network`
  from a measurement set. The `ImpedanceTable` interface above is the
  data side; the identification algorithm (non-linear LS over a
  parameterised `Network`) is the new piece.
- **Plausibility / QA checks** — flag obviously suspect rows
  (negative magnitudes, phase outside `±π`, impedance-magnitude
  ratios across frequency that violate passivity) at import time and
  in a dashboard panel.
- **Anonymised export** — strip `Location.name`, `description` and
  `operator` for data releases; keep coordinates quantised to a chosen
  grid size.

### Long term

- **Cloud sync / multi-user** — move the SQLite backend to an
  optional Postgres / libsql layer so multiple field teams can share
  a DB. Keep SQLite as the default single-user store.
- **ML-assisted classification of impedance curves** — label curves
  by soil type / grounding-quality class from a training set; mostly
  a research hook, not a user-facing feature.
- **Public benchmark dataset** — a small open test corpus of
  anonymised real measurements (impedance sweeps, Wenner profiles)
  that both `groundmeas` and `groundinsight` example notebooks can
  depend on, so tutorials stop relying on synthetic data.

### Explicit non-goals

- **Reduced-model network solve** (nodal admittance, EPR / reduction
  factor over a network topology). Handled by the companion package
  `groundinsight`. `groundmeas` only produces the measurement data
  and the `ImpedanceTable` / `SoilModel` handoff.
- **PDE / FEM field computation** (3-D potential `φ(x, y, z, f)`,
  surface-potential fields in soil). Handled by the planned companion
  package `groundfield`. `groundmeas` stays free of heavy native
  dependencies (gmsh, VTK, pyvista).

---

### Ideas inbox

Unsorted proposals. Drop a bullet here whenever an idea comes up —
in any language, any level of detail. Items get triaged into the
Roadmap categories above (or straight into `[Unreleased]`) in the next
cycle.

<!--
Format suggestion (free-form is fine too):
- **short title** — one-line sketch of the idea and why it matters.
  Constraints / open questions in parentheses.
-->

_No entries yet. Add your first idea below this line._
