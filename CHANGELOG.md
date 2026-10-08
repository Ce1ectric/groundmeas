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

### Added (Tower-grounding integration — 2026-10)

> Integration of the overhead-line tower evaluation of the former
> companion package `tower-grounding-measurement` (TGM) into
> `groundmeas`; `groundmeas` becomes the single maintained program.

- **`gm.create_items(payloads, measurement_id)`** inserts many
  `MeasurementItem`s in one transaction (one session, one commit;
  all-or-nothing). Closes the `gm.bulk_create_items` idea from the
  inbox; profiles and file imports no longer pay one commit per row.
- **`gm.import_measurements(...)` / `gm.import_measurements_from_json(path)`**
  — Python API for the JSON import (file, directory or
  `X_measurement.json` + `X_items.json` pair) that round-trips with
  `export_measurements_to_json`.
- **`gm.value_at_62_percent(distances, values, injection_distance_m,
  conservative=False)`** — the 62 % method as a pure function. With
  `conservative=True` it applies the procedure of the tower evaluation:
  linear extrapolation outside the three nearest points, the profile
  maximum when 0.62 D lies beyond the profile, and the highest value of a
  closer point when that exceeds the interpolated value. Verified
  bit-identical to `tower-grounding-measurement` on 160 measured and
  20 000 random profiles.
- **`distance_profile_value(..., frequency_hz=None, conservative=False)`**
  and `gm-cli distance-profile --frequency/-f --conservative`: evaluate
  one frequency of a profile stored at several frequencies (e.g. the
  30/50/70 Hz values of a COMPANO 100 export).
- **`voltage_vt_epr(..., profile_algorithm="62_percent", conservative=False,
  additional_resistance_ohm=None)`** and `gm-cli voltage-vt-epr
  --profile-algorithm --additional-resistance`;
  **`impedance_over_frequency(..., profile_algorithm="62_percent",
  conservative=False)`** and `gm-cli impedance-over-frequency
  --profile-algorithm`.

- **`groundmeas.instruments`** — readers for OMICRON instrument exports
  (moved from `tower-grounding-measurement` and extended):
  `CompanoXMLReader` reads the fall-of-potential test of a COMPANO 100 XML
  export with the complex voltages and currents at both test frequencies
  (`read_fall_of_potential()`, `FallOfPotentialData.impedance(f)`), the
  reduction-factor clamp readings (`read_reduction_factor()`), the
  step/touch output currents and the soil-resistivity readings with their
  electrode geometry (`read_soil_resistivity()`: `AB/2 = c + a/2`,
  `MN/2 = a/2`, Wenner detection); `Hgt1TXTReader` reads HGT1
  *StepTouch* reports and interpolates them to the power frequency. Units
  (`mA`, `mV`, `kV`, `cm`, `km`, `ft`) are converted to SI, malformed files
  raise `MeasurementFileError` with the file name.

- **Import of OMICRON exports into the database** —
  `gm.import_fall_of_potential(...)`, `gm.import_step_touch(...)`,
  `gm.import_soil_resistivity(...)` and
  `gm-cli import-omicron --location ... --asset-type ... [--ze ZE.xml]
  [--ut UT.txt] [--transferred UT2.txt] [--soil SOIL.xml] [-D 100]`. One
  measurement per test: the fall-of-potential profile at the power
  frequency and both test frequencies with footing resistance, injected
  current and (from the clamp readings) `earth_fault_current` +
  `shield_current` so that `calculate_split_factor` returns the footing
  share; HGT1 touch voltages with `input_impedance_ohm` /
  `additional_resistance_ohm` per termination and the reference current of
  the step/touch test; soil resistivity as Wenner (`a`) or Schlumberger
  (`AB/2`, `MN/2`). Instrument time stamps can be converted to UTC with
  `--timezone Europe/Berlin`. Replaces the OCR path for these instruments
  (roadmap item *Native importers for common instruments*).

- **`groundmeas.towers` and `gm-cli towers`** — the campaign evaluation
  of overhead-line towers, moved from `tower-grounding-measurement` 0.2
  (which is discontinued). A campaign is a flat folder of COMPANO 100 /
  HGT1 exports, a measurement-description and a grid-data workbook and a
  JSON configuration. `gm-cli towers run --config config.json` evaluates
  every tower (earthing impedance with the conservative 62 % method,
  footing resistance, touch and step voltages at the earth-fault current,
  permissible touch voltage after EN 50522 / EN 50341, short-circuit
  current from the line model, clearing time from the line-protection
  table) and writes one JSON result per tower, an Excel summary,
  HTML/PDF protocols in German or English (`--print`, `--worker N`,
  `--no-pdf`), a ZIP archive (`--zip`) and a statistics report
  (`--stats`). Further commands: `gm-cli towers demo DIR [--language de]`
  (synthetic campaign), `gm-cli towers example-config`,
  `gm-cli towers install-browser` and `gm-cli towers flatten SRC DEST
  [--apply] [--report mapping.csv]` (copies a delivery with one folder
  per line and tower into the flat layout; the former
  `scripts/flatten_measurements.py`). The `towers` commands do not open
  the groundmeas database. Results are identical to
  `tower-grounding-measurement` 0.2 (JSON results and Excel summary of
  the demo campaign compared field by field); touch voltages in the
  results are still rounded up (`np.ceil`). The configuration file is
  taken from `--config`, `GROUNDMEAS_TOWER_CONFIG` (the former
  `TOWER_GROUNDING_CONFIG` is still read) or `./config.json`; the PDF
  browser from `GROUNDMEAS_BROWSER` (formerly
  `TOWER_GROUNDING_BROWSER`). Python API: `groundmeas.towers`
  (`calculate_summary`, `GroundingSystemAnalysis`, `read_config`, ...).
- **Optional extra `groundmeas[pdf]`** (Playwright) for the PDF protocols;
  without it `gm-cli towers run --no-pdf` writes HTML protocols.
- **`gm-cli towers import-db --config config.json`** and
  `groundmeas.towers.import_campaign(...)` copy the instrument data of a
  tower campaign into the database: one location per tower
  (`"<line> tower <tower>"`, coordinates from optional `latitude` /
  `longitude` or `Breitengrad` / `Längengrad` columns of the measurement
  description) and one `overhead_line_tower` measurement per test —
  fall-of-potential profile (current-electrode distance from the
  description), touch voltages, transferred potential at the neighbouring
  tower and soil resistivity — with operator, weather and instrument from
  the measurement description. Files already in the database are skipped
  (`--reimport` to import them again), `--dry-run` lists the files without
  opening the database, `--timezone` converts the instrument clocks to UTC.
  The imported data reproduce the evaluation: the conservative 62 % value
  of `distance_profile_value` equals `ZE_62_Ohm` and the touch voltages
  scaled to the earth-fault current equal `UT_V` of the JSON results
  (tested on the demo campaign).

### Changed (Tower-grounding integration — 2026-10)

- **`impedance_over_frequency` returns one value per frequency from all
  items at that frequency**: a distance profile is reduced with
  `profile_algorithm`, several items without distance are averaged (with a
  `UserWarning`). Before, the last item silently won — for a profile that
  was the value at the largest probe distance.

### Fixed (Tower-grounding integration — 2026-10)

- **`gm-cli import-json` could not import JSON with timestamps** — the
  ISO string was passed unparsed to SQLite (`SQLite DateTime type only
  accepts Python datetime`), so even files written by `export-json`
  failed. Timestamps are now parsed (offsets converted to UTC).
- **`gm-cli import-json` re-used the exported database keys** (`id`,
  `location_id`, `measurement_id`, `location.id`) and failed with
  `UNIQUE constraint failed` on a non-empty database. The keys are now
  dropped; locations are matched by name/coordinates as for new data.
- **`gm-cli import-json` committed every item separately**; it now uses
  `create_items` (one transaction per measurement).
- **`voltage_vt_epr` averaged a fall-of-potential profile** — with a
  profile stored in the measurement, `z_per_amp` was the mean of all
  probe distances (e.g. 0.098 Ω instead of Z_E = 0.121 Ω). Profiles are
  now reduced with `profile_algorithm` (62 % by default).
- **`voltage_vt_epr(single_id)` raised `KeyError`** when the measurement
  was skipped (missing impedance or current) instead of returning the
  documented empty dict.
- **`distance_profile_value` mixed frequencies silently**; it now warns
  when the items span several frequencies and accepts `frequency_hz`.
- `voltage_vt_epr` warns when several `earthing_current` rows match the
  frequency (the first one is used, as before); `real_imag_over_frequency`
  warns when several items share a frequency (the last one is used, as
  before).

### Docs (Tower-grounding integration — 2026-10)

- New section **Tower campaigns** (`docs/towers/`): overview and
  installation, quickstart with the demo campaign, campaign preparation
  (file names, workbooks, `towers flatten`), configuration reference,
  command line, results (JSON fields, Excel summary, protocol), campaigns in
  the database (`towers import-db`), Python API, troubleshooting, physical
  background, assessment procedure and a migration guide from
  `tower-grounding-measurement` (commands, environment variables, module
  mapping). Ported from the TGM documentation; examples re-run with
  groundmeas.
- New tutorial **Import from OMICRON instruments**
  (`docs/17_instrument_import.md`); the import/export tutorial documents
  the JSON round trip (`import_measurements_from_json`).
- API and CLI references list `create_items`, `value_at_62_percent`, the
  JSON and OMICRON importers, `groundmeas.instruments`, `groundmeas.towers`,
  `import-omicron`, the new analytics options and the `towers` commands.
- MkDocs: admonitions, collapsible blocks, tabs, task lists, card grids
  (`md_in_html` + emoji icons) and Mermaid diagrams are enabled
  (existing `!!! note` blocks now render as notes).

### Internal (Tower-grounding integration — 2026-10)

- `gm-cli towers install-browser` explains that the `pdf` extra is missing
  instead of failing with `No module named playwright`.
- New runtime dependencies `openpyxl` (Excel workbooks of the tower
  campaigns) and `jinja2` (protocol templates); `playwright` only in the
  `pdf` extra.
- `click` is pinned to `<8.2`: with click 8.2 the pinned `typer` 0.15
  crashes when rendering `--help` (`Parameter.make_metavar() missing
  'ctx'`).
- The synthetic instrument exports for the tests live in `tests/data/`
  (re-included in `.gitignore`, kept byte-exact via `.gitattributes`).
  The tower tests (`tests/test_towers_*.py`) build their campaigns with
  the demo generator; no measured data is part of the repository.

### Fixed (Audit pass 8 — implemented 2026-05-24)

> The bugs in this block were *implemented* on 2026-05-24 from the
> eighth audit pass; they close the items the pass 6 / 7 implementation
> run on 2026-05-18 explicitly deferred (see
> `Claude Audits/audit-implementation-report-groundmeas-2026-05-18-pass6-7.md`
> §"Bewusst NICHT umgesetzt"). Each item is covered by regression
> tests in `tests/test_audit_pass8_2026_05_24.py` and
> `tests/test_repo_hygiene.py`, and by a reproducible notebook
> walkthrough in `notebooks/audit_pass8_fixes_2026_05_24.ipynb`.

- **Tutorial pages migrated to canonical imports.** The four tutorial
  pages flagged across passes 1–7 (`docs/02_quickstart.md`,
  `docs/10_tutorial_intro.md`, `docs/11_create_measurements.md`,
  `docs/14_import_export.md`) now use the recommended
  `import groundmeas as gm` idiom and call API symbols via `gm.*`.
  The legacy `from groundmeas.db import …` / `from groundmeas.analytics
  import …` / `from groundmeas.plots import …` /
  `from groundmeas.export import …` / `from groundmeas.vision_import
  import …` lines that taught the deprecated shim style have been
  removed. The pass-6/7 deprecation warnings continue to back the
  legacy form for downstream consumers; the documentation no longer
  teaches it.
- **ADR directory opened.** `docs/adr/` is new in 1.5.2 with an index
  (`docs/adr/README.md`) and the first decision record
  (`docs/adr/0001-compatibility-shim-deprecation-strategy.md`). The
  ADR pins the `make_shim` contract from pass 6 / 7, enumerates the
  seven shims and their canonical replacements, and codifies the
  1.5 → 1.6 → 2.0 migration window (legacy paths kept through 1.5.x,
  docs migrated in 1.6, shims removed in 2.0). `mkdocs.yml` carries
  an `ADRs:` nav section so the records render alongside the API
  reference. The pass-7 recommendation
  "ADR-0001 — Compatibility-shim deprecation strategy als natürlicher
  Startpunkt" is closed.
- **`tests/test_repo_hygiene.py` is the dedicated forcing function.**
  The previous `test_audit_pass6_7_2026_05_18.py::test_no_runtime_artefacts_tracked`
  guarded the on-disk state implicitly. Pass 8 promotes it to its
  own module with two `xfail`-marked tests (on-disk layer and
  git-tracking layer) plus a positive assertion that the pass-6/7
  `.gitignore` hygiene patterns stay in place. Once a maintainer
  runs the documented `git rm --cached` + `rm -rf` cleanup on a
  developer machine, both `xfail` markers flip to passing
  automatically (`pytest --runxfail` reports `XPASS`). The CI image
  therefore turns green on the cleanup commit without any test
  rewriting required.

### Docs (Audit pass 8 — implemented 2026-05-24)

- **`docs/02_quickstart.md`** — the Python route now opens with a
  paragraph that names `import groundmeas as gm` as the recommended
  import style and points at `docs/21_ref_api.md` for the full shim
  table. Both code blocks (staged-fault and soil-survey) call
  through `gm.*`.
- **`docs/10_tutorial_intro.md`** — same migration; the
  "Python API examples" section header now carries the canonical-
  import note.
- **`docs/11_create_measurements.md`** — staged-fault and soil-survey
  examples use `import groundmeas as gm`; the read-back call
  (`read_items_by`) goes through `gm.read_items_by`.
- **`docs/14_import_export.md`** — export and OCR-import examples now
  use `gm.export_measurements_to_json`, `gm.export_measurements_to_csv`
  and `gm.import_items_from_images`.
- **`docs/adr/README.md`** — new ADR index page (when to write an
  ADR, format pointer, cross-link to `groundfield/docs/adr/`).
- **`docs/adr/0001-compatibility-shim-deprecation-strategy.md`** —
  new ADR-0001.
- **`mkdocs.yml`** — new `ADRs:` nav section listing the index and
  ADR-0001 explicitly.

### Tests (Audit pass 8 — implemented 2026-05-24)

- **`tests/test_audit_pass8_2026_05_24.py`** — new regression tests
  covering (a) the four migrated tutorial pages must not import via
  shim paths anymore (parametrised), (b) `docs/02_quickstart.md`
  must showcase the recommended `import groundmeas as gm` idiom,
  (c) the ADR directory and ADR-0001 file exist, (d) ADR-0001 has
  the three required sections (Context / Decision / Consequences)
  and enumerates all seven shims, (e) `mkdocs.yml` lists the new
  `ADRs:` nav section, (f) the CHANGELOG carries an *Audit pass 8*
  block dated `2026-05-24`.
- **`tests/test_repo_hygiene.py`** — new dedicated module with two
  `xfail`-marked tests for the on-disk and git-tracking layers, and
  one positive assertion for the `.gitignore` hygiene patterns.
  Replaces the implicit guard previously sitting inside the pass
  6 / 7 module.

### Fixed (Backlog — eighth 2026-05-25 review pass)

> The eighth audit pass was run on 2026-05-25, one day after the
> Pass-8 *implementation* run on 2026-05-24 (which closed the four
> deferred Pass-6/7 items: tutorial-page canonical imports, ADR
> directory + ADR-0001, `tests/test_repo_hygiene.py` forcing
> function, README snippet migration). The Pass-6/7 + Pass-8
> implementation blocks **still sit uncommitted** on
> `feature/audit-pass8-2026-05-24` (61 modified / untracked files
> in the working tree). Only the CHANGELOG is edited in this pass;
> no program code is touched.

- **`feature/audit-pass8-2026-05-24` carries the entire
  Pass-5 → Pass-8 implementation set as uncommitted work — release
  cut blocked.** `git log` is at `4b794d1  chore: bump version to
  1.5.1`. `src/groundmeas/__init__.py` and `pyproject.toml` both
  carry `1.5.2` (uncommitted), the new `_shim.py` is untracked,
  `docs/adr/` is untracked, `graphify-out/` is untracked, four
  audit test modules (`test_audit_fixes_2026_05_13.py`,
  `test_audit_pass5_2026_05_13.py`,
  `test_audit_pass6_7_2026_05_18.py`,
  `test_audit_pass8_2026_05_24.py`) and
  `tests/test_repo_hygiene.py` are all untracked. The `1.5.2`
  release cannot be tagged until the working tree is committed via
  the two-commit sequence documented in
  `Claude Audits/audit-implementation-report-groundmeas-2026-05-24-pass8.md`
  §"Branch / Working-Tree" — eighth pass elevates this to the
  single most urgent maintenance item.
- **Repo-root junk still present on disk — eighth pass in a row.**
  The eight-file ledger
  (`Python=3.14/`, `Users/`, `dummy.xml`, `feature.txt`,
  `tmp_test.db`, `groundmeas.db`, `groundmeas.db-journal`,
  `test_write_check.tmp`) is still in the working tree.
  `tests/test_repo_hygiene.py` (Pass-8 implementation) marks the
  cleanup as `xfail` so CI does not fail today; on the cleanup
  commit both `xfail` markers flip to `XPASS` automatically. The
  `git rm --cached` + `rm -rf` sequence documented in
  `audit-implementation-report-groundmeas-2026-05-24-pass8.md`
  §"Nächste Schritte (empfohlen)" is the one-line operator action
  that closes the eighth-pass-in-a-row finding.
- **`scripts/generate_graphify_report.py` is untracked and has no
  CHANGELOG entry.** A new maintainer-side script (used to refresh
  `graphify-out/GRAPH_REPORT.md` after each release) sits in the
  working tree with no documentation pointer. Either add it to a
  Pass-8 `Internal` block or treat it as a private helper and
  add it to `.gitignore`.
- **`tests/conftest.py` is untracked.** The file appeared between
  Pass-7 and Pass-8 with no CHANGELOG note. Audit what it
  configures (likely a session-scoped DB fixture for the new
  audit tests) and document the contract in
  `docs/22_ref_cli.md` or a new `docs/testing.md` page so the
  pytest fixture surface is not invisible.
- **Four tutorial pages still use shim imports — Pass-8
  implementation only migrated four of eight.** The Pass-8
  `Fixed` block above migrated `docs/02_quickstart.md`,
  `docs/10_tutorial_intro.md`, `docs/11_create_measurements.md`
  and `docs/14_import_export.md` to the `import groundmeas as gm`
  idiom. The remaining four (`docs/12_read_measurements.md`,
  `docs/13_change_measurements.md`, `docs/15_analytics.md`,
  `docs/16_dashboard.md`) still teach `from groundmeas.db import
  …` / `from groundmeas.analytics import …` patterns and will
  trigger the new `DeprecationWarning` on every example run. The
  Pass-8 implementation report explicitly defers these „pass 9 or
  with the 1.6.0 doc-sweep iteration"; this entry pins the
  deferral so the 1.6.0 cut does not forget them.
- **`gm.show_versions()` still missing — cross-repo convention
  open on the `groundmeas` side.** Pass-7 *Roadmap*-bullet is
  unchanged; ADR-0013 in `groundfield` (the prerequisite) is
  still unwritten. Track the cross-repo dependency in the
  `groundmeas` Roadmap section below.
- **`gm.cross_repo` namespace + `docs/cross-repo.md` still open
  — eighth pass in a row.**
- **`gm-cli doctor` subcommand still missing — Pass-7 Roadmap
  bullet still open.** The pass-7 proposal pinned this as the
  CLI mirror of `gi.show_versions()` + `gf.show_versions()`;
  defer until ADR-0013 lands.
- **`scripts/release.py` still does not move `[Unreleased]` into a
  new version section automatically.** Pass-6/7 implementation
  report flagged the cross-repo „shared `_release_shared.py`
  module" as an ADR-0002 candidate; ADR-0002 is still unwritten
  (only `0001-compatibility-shim-deprecation-strategy.md` exists).
  Tie the eighth-pass-in-a-row backlog to the ADR opening.
- **`graphify-out/manifest.json` is untracked but the
  `.gitignore` does not list `graphify-out/`.** The untracked
  directory sits in the working tree but is not tracked and not
  ignored — a developer running `git add .` will pull it into the
  next commit unintentionally. Add `graphify-out/` to
  `.gitignore` in the same commit as the repo-root cleanup
  above.
- **`docs/16_dashboard.md` does not document the new
  Streamlit-rerun behaviour of `init_db()`.** The Pass-7
  implementation widened `init_db()` to call `disconnect_db()`
  before `connect_db()` when the resolved path differs from the
  active path (preventing a stale engine bound to a read-only
  mount surviving a rerun). The dashboard reference page does
  not mention the new behaviour; users running the dashboard
  against multiple databases lose the implicit-rebind contract.
  Add a "Rerun behaviour" subsection to
  `docs/16_dashboard.md`.
- **`docs/15_analytics.md` does not document the
  `distance_profile_value` warning contract** (Pass-7 Docs
  backlog re-flagged).
- **`docs/21_ref_api.md` shim table still incomplete** —
  Pass-7 Docs backlog re-flagged. The page now mentions the
  ADR-0001 cross-link (Pass-8 implementation) but the full
  seven-shim table (`db`, `analytics`, `models`, `plots`,
  `export`, `vision_import`, `cli`) is split across two
  sections without a single „canonical-to-shim" lookup table.

### Docs (Backlog — eighth 2026-05-25 review pass)

- **README Python-version range honesty.** Pass-7 Docs backlog
  re-flagged. README says „Python 3.12+" while
  `pyproject.toml` was bumped to 3.14 in commit `5d55b89`. The
  README mismatch was flagged in Pass-6 and still has not been
  corrected.
- **README `dev` install section does not mention the new audit
  test modules.** `tests/test_audit_pass5_2026_05_13.py`,
  `tests/test_audit_pass6_7_2026_05_18.py`,
  `tests/test_audit_pass8_2026_05_24.py`,
  `tests/test_repo_hygiene.py` are all new in 1.5.2; the
  README's „Development" section enumerates the original
  pytest layout. Add a bullet so contributors know which
  modules to update on the next audit pass.
- **ADR-0001 cross-link to the matching `groundfield`
  ADR-0008 (groundinsight bridge) is missing.** Pass-8
  implementation opened the ADR directory and wrote ADR-0001
  but the ADR's „See also" section does not cross-link to the
  cross-repo bridge ADR in `groundfield/docs/adr/`. Add a
  one-line bidirectional pointer (same finding as the
  `groundfield` ADR-0003/0009 ↔ ADR-0011/0012 entry above).
- **`docs/adr/README.md` index does not list the planned
  ADR-0002 (cross-repo release-script convention) or ADR-0003
  (cross-repo `show_versions` mirror of `groundfield`
  ADR-0013).** A „Planned ADRs" bullet list under the index
  pins the roadmap so the audit reports stop re-listing them
  every pass.

### Tests (Backlog — eighth 2026-05-25 review pass)

- **`mkdocs build --strict` CI hook still missing — eighth pass
  in a row** (cross-repo). The new ADR-0001 page and the
  Pass-8 `Tutorials:` nav edits would all be flagged by
  `--strict` immediately if a stale link survived the tutorial
  migration.
- **No regression test against `graphify-out/manifest.json`
  staleness.** Same pattern as the `groundfield` and
  `groundinsight` proposals: read the *„Built from commit"*
  line from `graphify-out/GRAPH_REPORT.md`, compare against
  `git rev-parse HEAD`. The `groundmeas` graph report at
  `graphify-out/GRAPH_REPORT.md` reports commit `4b794d18`
  (the 1.5.1 release) while the working tree carries 1.5.2
  uncommitted — the staleness check would catch this at PR
  time.
- **`tests/test_audit_pass8_2026_05_24.py` is untracked.**
  Treat the untracked state as the regression: a follow-up
  test asserting that every `test_audit_pass*_*.py` file is
  tracked by `git` (the natural extension of
  `test_repo_hygiene.py`) would catch a maintainer accidentally
  not staging a new audit-test module before the release tag.

### Roadmap — Additions from the eighth 2026-05-25 review pass

- **Commit the Pass-5 → Pass-8 implementation set and cut
  `1.5.2` immediately.** Five audit passes have flagged the
  missing release; eight passes have flagged the repo-root
  junk. The single PR closes both backlogs in one stroke.
- **Open ADR-0002 — Cross-repo release-script convention.**
  Pass-6/7 implementation report flagged the
  `_release_shared.py` module as an ADR-0002 candidate. With
  ADR-0001 (Compatibility-shim deprecation strategy) merged
  in Pass 8, ADR-0002 is the natural next entry.
- **`gm.repo_hygiene.check()` public helper.** Promote the
  Pass-7 / Pass-8 forcing-function test into a public API call
  so users embedding the package in CI pipelines can call
  `gm.repo_hygiene.check()` instead of vendoring the test
  helper.
- **`gm.show_versions()` + `gm-cli doctor`** — blocked on
  ADR-0013 in `groundfield`.
- **`gm.cross_repo` namespace + `docs/cross-repo.md`** —
  blocked on ADR-0013 in `groundfield`.
- **`gm.audit_apply(report_path)` helper.** Same cross-repo
  proposal as in `groundinsight` Pass-8. A single CLI entry
  point that reads a CHANGELOG-formatted audit report and
  appends the bullets into `[Unreleased] → Fixed (Backlog)`
  ends the manual copy-and-paste drift that has produced
  eight audit reports with the same backlog structure.

### Fixed (Audit pass 6 / 7 — implemented 2026-05-18)

> The bugs in this block were *implemented* on 2026-05-18 from the
> sixth and seventh audit passes
> (`Claude Audits/audit-report-changelogs-2026-05-14-pass6.md`,
> `Claude Audits/audit-report-changelogs-2026-05-18-pass7.md`). Each
> item is covered by regression tests in
> `tests/test_audit_pass6_7_2026_05_18.py` and by a reproducible
> notebook walkthrough in
> `notebooks/audit_pass6_7_fixes_2026_05_18.ipynb`.

- **`groundmeas._shim` helper introduced** —
  `groundmeas._shim.make_shim(canonical, shim_name, …)` is the single
  source of truth for the lazy `DeprecationWarning` / `__getattr__` /
  `__dir__` / `__all__` boilerplate that every compatibility shim
  needs. The factory honours a configurable `extra_attrs` allow-list
  for the rare private re-exports (`groundmeas.models._compute_magnitude`)
  and short-circuits all *other* underscore-prefix names to a clean
  `AttributeError` without firing a warning. Pass-6/7 reference:
  "extract the `__getattr__` pattern from `db.py` into `_shim.py`".
- **Five-shim cross-rollout.** `groundmeas.models`, `groundmeas.plots`,
  `groundmeas.export`, `groundmeas.vision_import` and
  `groundmeas.cli` were rewritten on top of `_shim.make_shim` and now
  emit a `DeprecationWarning` on first attribute access. `groundmeas.db`
  and `groundmeas.analytics` (retrofitted in pass 5) were ported to
  the same helper so all seven shims share one implementation.
  Pass-6/7 reference: "five shims still without `DeprecationWarning` —
  seventh pass in a row".
- **`groundmeas.db` shim no longer warns on private attributes.**
  Accessing `groundmeas.db._get_session` (or any other underscore-
  prefixed name) now raises `AttributeError` without emitting a
  `DeprecationWarning`. The previous shim filtered through
  `_CANONICAL_ATTRS` which included `_get_session`, leaking a warning
  on a private symbol. Pass-6 finding closed.
- **`core.db._engine_path` + `current_db_path()` accessor.**
  `connect_db` now records the path it last bound to, and
  `disconnect_db` clears it. The accessor is exposed as
  `groundmeas.core.db.current_db_path()` and replaces the previous
  ad-hoc state inspection the dashboard had to do.
- **`ui.dashboard.init_db()` is rerun-aware.** The function now reads
  `current_db_path()`, returns immediately when the resolved path
  equals the active engine binding, and calls `disconnect_db()`
  before `connect_db()` when the paths diverge. A user who fixes
  permissions and then updates `GROUNDMEAS_DB` no longer keeps
  talking to the previous (read-only) mount. Pass-6/7 reference:
  "`ui.dashboard.init_db()` still does not call `disconnect_db()`
  before `connect_db()`".
- **`invert_layered_earth` emits a `UserWarning` on non-convergence.**
  When the damped Gauss-Newton loop exhausts `max_iter` without the
  RMSE-change falling below `tol`, a `UserWarning` is now raised
  (`stacklevel=2`) and the result payload carries `converged: False`
  at the top level and inside `misfit`. `misfit` also records the
  effective `tol` for downstream diagnostics. `invert_soil_resistivity_layers`
  inherits the contract because it delegates to the underlying
  helper. Pass-6/7 reference: "`invert_layered_earth` /
  `invert_soil_resistivity_layers` still swallow
  `OptimizeResult.success=False`".
- **`__version__` bumped to `1.5.2`.** Cross-file pinning in
  `pyproject.toml` and `src/groundmeas/__init__.py`. The release-
  cut is now overdue by five passes; the in-tree implementation
  blocks (Pass 4 / Pass 5 / Pass 6 / Pass 7) ship as a single
  `1.5.2` bundle.
- **Repo-root hygiene gitignore patterns added.** `.gitignore` now
  filters the recurring scratch artefacts `feature.txt`,
  `dummy.xml`, `tmp_test.db`, `test_write_check.tmp`,
  `groundmeas.db`, `groundmeas.db-journal`, `src/test_marker.tmp`,
  `Users/` and `Python=3.14/`. The new
  `tests/test_audit_pass6_7_2026_05_18.py::test_no_runtime_artefacts_at_repo_root`
  guards against re-tracking; the on-disk removal must be done
  manually because the implementation sandbox cannot run
  `git rm --cached`.

### Docs (Audit pass 6 / 7 — implemented 2026-05-18)

- **`docs/16_dashboard.md`** — new "Reconnecting after a path change
  (1.5.2+)" subsection documenting the rerun-aware `init_db()`,
  the `current_db_path()` accessor and the
  `connect_db(..., force=True)` escape hatch.
- **`docs/21_ref_api.md`** — "Compatibility shims — full list" table
  added, enumerating all seven shims and their canonical
  replacements. The note explicitly mentions the private-symbol
  short-circuit so the pass-6 `_get_session` finding does not
  surface again in user-facing docs.
- **`docs/15_analytics.md`** — new "Convergence handling (1.5.2+)"
  subsection documenting the `UserWarning`, the `converged` /
  `misfit` payload contract and the `stacklevel=2` semantics for
  `invert_layered_earth`. A second new subsection captures the
  pass-5 `distance_profile_value` duplicate-distance warning
  contract (payload format, `stacklevel=3` notebook-friendly
  reporting).
- **`docs/22_ref_cli.md`** — new "`set-default-db` end-to-end
  (1.5.2+)" subsection documenting the JSON config file location,
  the env-var precedence chain and how to inspect the active
  configuration.

### Tests (Audit pass 6 / 7 — implemented 2026-05-18)

- **`tests/test_audit_pass6_7_2026_05_18.py`** — new regression
  tests covering the `_shim.make_shim` helper (public-warn,
  private-no-warn, `extra_attrs`, unknown-attribute),
  the five-shim cross-rollout (`models`, `plots`, `export`,
  `vision_import`, `cli` — each parametrised), the
  `db._get_session` no-warn case, `__version__` parity
  between `pyproject.toml` and `groundmeas.__version__`,
  the `init_db()` rerun reconnect path (different + same path),
  the `invert_layered_earth` `max_iter=1` non-convergence
  warning, the `current_db_path()` engine-state mirror, and a
  git-aware repo-hygiene test that asserts no runtime artefacts
  are tracked.

### Fixed (Audit pass 5 — implemented 2026-05-13)

> The bugs in this block were *implemented* on 2026-05-13 from the
> fifth audit pass (`audit-report-changelogs-2026-05-13.md`). Each
> item is covered by regression tests in
> `tests/test_audit_pass5_2026_05_13.py` and by a reproducible
> notebook walkthrough in
> `notebooks/audit_pass5_fixes_2026_05_13.ipynb`.

- **`groundmeas.db` shim** now re-exports `disconnect_db` and emits a
  `DeprecationWarning` on attribute access. The pre-pass-5 shim only
  re-exported `connect_db`/CRUD helpers, so
  `from groundmeas.db import disconnect_db` raised an `ImportError` —
  a direct follow-up of the pass-4 `disconnect_db` re-export which
  only patched `groundmeas/__init__.py`. Pass-5 reference:
  "`groundmeas/db.py`-Shim ohne `disconnect_db`-Re-Export".
- **`groundmeas.analytics` shim** emits a `DeprecationWarning` on
  attribute access. The legacy `from groundmeas.analytics import *`
  path still resolves all symbols (via `__all__` + lazy
  `__getattr__`), but each access now signals the canonical
  replacement path (`groundmeas` /
  `groundmeas.services.analytics`). Pass-5 reference:
  "`groundmeas/db.py` und `groundmeas/analytics.py` Shims ohne
  `DeprecationWarning`".
- **`services.vision_import.ocr_image` (OpenAI branch)** now parses
  the response envelope defensively: empty `choices`, `content=None`
  (content-filter / tool-call), and list-shaped multi-part `content`
  payloads all raise a single descriptive `RuntimeError` (or, in
  the list-content case, are concatenated into one string).
  Previously the code did `data["choices"][0]["message"]["content"]`
  unguarded and surfaced as `KeyError` / `IndexError` /
  `TypeError`. Pass-5 reference: "OpenAI-Branch greift …
  `content` ungeschützt zu".
- **`services.vision_import._normalize_ocr_text`** now accepts an
  optional whitespace between the `rn` bigram and the unit letter
  (`118.1 rn Ω` → `118.1 m Ω`), covering a real Megger OCR pattern
  that the pass-4 regex missed. Pass-5 reference:
  "`_normalize_ocr_text` Lookahead fehlt Whitespace-Toleranz".
- **`services.analytics.distance_profile_value`** now emits a
  `UserWarning` when its interpolation-based dedup collapses
  duplicate measurement distances. The warning names up to five
  affected distances plus the measurement id / type so downstream
  analyses can spot data-quality issues that were previously silent.
  Pass-5 reference: "`distance_profile_value` deduped duplikat-
  distance-Punkte ohne `UserWarning`".
- **`ui.dashboard.init_db`** now returns a `bool` and catches the
  `RuntimeError` that `connect_db` raises after the pass-4
  writability probe. Read-only NextCloud / Dropbox / Streamlit-Cloud
  mounts are rendered as an `st.error` panel with a remediation
  hint, and `main()` calls `st.stop()` so downstream queries no
  longer panic with `"Database not initialized"`. Streamlit
  auto-reruns that hit the "already initialised" guard are folded
  into a transient `st.info`. Pass-5 reference: "Dashboard fängt
  die neue `RuntimeError` aus der Writability-Probe nicht ab".

### Docs (Audit pass 5 — implemented 2026-05-13)

- **`docs/22_ref_cli.md`** — new "Database lifecycle" section
  documenting `connect_db(..., force=True)`, the writability probe,
  and the symmetric `disconnect_db` teardown.
- **`docs/21_ref_api.md`** — added a "Canonical vs. shim import
  paths" note pointing at the new `DeprecationWarning` strategy and
  the canonical top-level / `groundmeas.core.db` /
  `groundmeas.services.analytics` paths. The Database table now
  documents `force=True` and `disconnect_db`.
- **`docs/16_dashboard.md`** — new "Filesystem requirements
  (read-only mounts)" subsection describing the eager writability
  probe and the remediation path (set `GROUNDMEAS_DB` to a writable
  directory, restart the dashboard).

### Tests (Audit pass 5 — implemented 2026-05-13)

- **`tests/test_audit_pass5_2026_05_13.py`** — 19 new regression
  tests covering the six fix areas (shim `disconnect_db` re-export,
  shim `DeprecationWarning` on both `db` and `analytics`,
  defensive OpenAI envelope handling with four payload shapes,
  whitespace-tolerant `rn` → `m`, duplicate-distance `UserWarning`,
  dashboard `init_db` happy + sad paths).
- **`tests/test_dashboard.py::test_main_runs_with_stubs`** — the
  `DummyStreamlit` test stub gained a `stop()` method and the test
  now patches `connect_db` / `resolve_db_path` so the new
  `init_db` return value does not abort the end-to-end stub run.

### Fixed (2026-05-13 audit implementation)

> The bugs in this block were *implemented* on 2026-05-13 from the four
> audit reports `audit-report-2026-05-09.md`,
> `audit-report-changelogs-2026-05-10[..pass2].md` and
> `audit-report-changelogs-2026-05-12[..pass4].md`.  Each item is covered
> by regression tests in `tests/test_audit_fixes_2026_05_13.py` and by a
> reproducible notebook walkthrough in
> `notebooks/audit_fixes_2026_05_13.ipynb`.

- **`services.analytics.calculate_split_factor`** now computes the split
  factor from the *vector* residual:
  `split_factor = |I_E - Σ I_shield| / |I_E|`.  The pre-1.5.2 magnitude
  formula `1 - |Σ shield| / |I_E|` silently went negative on
  phase-shifted shield currents (AP 1 shielded-cable case).  Audit
  reference: Pass 4 — "calculate_split_factor uses the magnitude
  formula".
- **`services.analytics.voltage_vt_epr`** now emits the per-ampere
  earthing impedance under the key `z_per_amp` (V/A = Ω); the legacy
  key `epr` is preserved as a backwards-compatible alias that carries
  the same value.  Audit reference: Pass 4 — "`voltage_vt_epr` stores
  the impedance under the `epr` key".  In addition:
  * The bare `except Exception` blocks around `read_items_by` were
    replaced with positive checks (`if not items`), so genuine DB or
    schema errors propagate instead of being hidden behind the
    "missing data" warning (Pass 2).
  * The `raise ValueError("zero current")` sentinel inside the `try`
    has been replaced with an explicit zero check (Pass 2).
  * Multiple matching `earthing_impedance` rows now emit a
    `UserWarning` and are averaged instead of being silently
    disambiguated by `imp_items[0]` (Pass 1).
- **`services.analytics.rho_f_model`** depth selection is now an
  `O(D · n)` sliding-window pass over the sorted union of depths.  The
  pre-1.5.2 implementation used `itertools.product(*depth_choices)` and
  was exponential in the number of measurements; for 20 measurements ×
  6 depths the previous code visited 6²⁰ ≈ 4·10¹⁵ combinations and
  effectively hung.  A `UserWarning` is now raised when the selected
  window spans more than 0.5 m (mixing soil layers).  The auxiliary
  helper `_select_minimum_spread_depths` is unit-tested independently.
  Audit reference: Pass 1 — "exponential `itertools.product` over all
  depth combinations".
- **`services.analytics.LayeredEarthModel.__post_init__`** rejects
  non-finite values (`nan`, `inf`, `-inf`) in both `rho_layers` and
  `thicknesses_m` before the existing `> 0` check.  NaN comparisons are
  always `False`, so non-finite values used to slip through silently.
  Audit reference: Pass 3 — "`LayeredEarthModel.__post_init__` lets
  `nan` / `inf` through".
- **`services.vision_import._normalize_ocr_text`** restricts the
  `rn` → `m` substitution to the unit context (digit + optional
  decimal separator + `rn` + SI unit letter).  Operator names such as
  *Bernhard* and *Schwerin* in German measurement protocols are no
  longer corrupted.  Audit reference: Pass 3 — "`_normalize_ocr_text`
  does `text.replace('rn', 'm')` unconditionally".
- **`core.db.connect_db`** is now thread-safe (module-level
  `threading.Lock`), refuses a second connect unless `force=True` is
  passed, and runs a writability probe on the parent directory for
  on-disk paths.  A companion `core.db.disconnect_db` is exposed and
  is idempotent.  The top-level `groundmeas` package re-exports
  `disconnect_db` (and lists it in `__all__`).  Audit references:
  Pass 1 — "`_engine` as module-global silently replaced", Pass 1 —
  "`connect_db` does not echo failure when the file path is
  unwritable", Pass 4 — "`core/db._engine` without `threading.Lock`".

### Fixed (Backlog — pending implementation)

> The following bugs were identified in the code-review pass on
> 2026-05-10. They are queued for the next maintenance release; the
> entries are recorded here so each one ships with a referenced fix
> commit.

- **`core.db._engine` is a module-global** that is silently
  replaced when `connect_db` is called twice in the same
  interpreter, leaking the previous SQLAlchemy engine and any
  open sessions. Add a `disconnect_db()` helper and call
  `engine.dispose()` on reconnect, or refuse a second
  `connect_db` until the first has been disposed.
- **`services.analytics.voltage_vt_epr` divides voltage and
  prospective-touch-voltage items by a real-valued `I`** even when
  the underlying measurement carries `value_real` / `value_imag`.
  The result is a magnitude-divided-by-magnitude scalar, which
  silently throws away the phase information. Either compute the
  complex per-Ampere ratio from `(value_real + j*value_imag) /
  (I_real + j*I_imag)` or document the magnitude-only convention
  in the function docstring.
- **`services.analytics.voltage_vt_epr` reads
  `imp_items[0]["value"]`** without asserting that the items are
  filtered for the requested frequency *and* that exactly one
  matches. Multi-port locations with several earthing-impedance
  rows at the same frequency get a silently arbitrary pick. Either
  raise on the ambiguous case or aggregate explicitly (e.g. mean
  of the matching rows).
- **`services.analytics.rho_f_model` uses an exponential
  `itertools.product` over per-measurement depth lists** to find
  the depth combination with minimum spread. For a campaign with
  20 measurements × 6 depths the loop visits 6²⁰ ≈ 4 × 10¹⁵
  combinations. Replace with the closed-form one-pass minimum-
  range algorithm (sort all depths, sliding window of length
  `n_measurements`, pick the window with smallest range).
- **`services.analytics.rho_f_model` does not warn when the
  selected depths span more than a documented threshold.** A
  single soil-resistivity-curve outlier can pull the "best"
  depth selection across two completely different soil layers and
  produce a meaningless rho. Emit a `UserWarning` if
  `max(combo) - min(combo) > 0.5 m` (or any documented limit).
- **`core.db.connect_db` does not echo failure when the file path
  is unwritable**: SQLAlchemy lazily creates the file on the first
  query, so `connect_db("/readonly/path.db")` returns successfully
  and a `create_measurement` call later raises a confusing
  `OperationalError`. Either run a write-probe at connect time or
  open the engine with `connect_args={"check_same_thread": False}`
  + an explicit `BEGIN; ROLLBACK;` smoke test.
- **`services.analytics.invert_layered_earth` does not propagate
  the optimiser's covariance** to the caller, even though
  `scipy.optimize.least_squares` returns the Jacobian at the
  optimum. Confidence bands on the inversion curve are advertised
  in the roadmap; expose the residual covariance as part of the
  return value so the visualisation layer can plot ±1 σ /
  ±2 σ envelopes without re-running the optimiser.
- **`services.vision_import._parse_value_angle_unit` mixes Google
  and numpy docstring styles** (`Examples:` then numpy-style
  `Parameters` / `Returns`). Convert the `Examples:` heading to
  `Examples\n--------` to match the project-wide convention and
  the `mkdocstrings` configuration.

> Additional findings from the **second 2026-05-10 review pass**:

- **`services.analytics.voltage_vt_epr` swallows every
  `Exception`** from `read_items_by` (impedance, current,
  prospective-touch-voltage, touch-voltage), then issues a
  `UserWarning` and continues with the next measurement. This
  hides genuine errors (corrupted DB, schema mismatch,
  programmer typo on `frequency_hz`) behind the same "missing
  data" warning. Catch the narrow `LookupError` /
  `IndexError` / `KeyError` / explicit `ValueError("zero
  current")` instead and let everything else propagate.
- **`services.analytics.voltage_vt_epr` raises a `ValueError`
  inside the `try`** to surface a zero-current case
  (``raise ValueError("zero current")``) only to be re-caught
  by the surrounding `except Exception`. The control flow works
  but is a code smell: the bare-string `ValueError` doubles as
  a magic sentinel. Move the zero-check outside the `try` so
  the intent is explicit.
- **`services.analytics.rho_f_model` reuses the variable name
  `dt`** for the per-measurement `depth -> rho` dict — easily
  confused with the time-step abbreviation that crops up in the
  shielding analyses. Rename to `depth_rho` for readability;
  zero behaviour change.
- **`services.analytics.rho_f_model` reports neither residual
  norm nor R²** on the least-squares solution. The caller has
  no way to tell whether the fitted `k` vector explains the
  data or is dominated by noise. Either return a richer
  dataclass (`RhoFFitResult(k=..., residual_R=..., residual_X=...,
  r_squared=...)`) or expose a sister function
  `rho_f_model_with_diagnostics` so the existing tuple-returning
  API stays backwards compatible.
- **`core.db._get_session` calls bare `Session(_engine)` per
  invocation** — neither pooled nor wrapped in a context
  manager. Long-running notebooks therefore have to be careful
  to close the session manually. Either expose a
  `sessionmaker` and the resulting `Session` via
  `with gm.session() as s: ...`, or document that every public
  CRUD entry point already closes its own session.
- **`__init__.py` declares no `disconnect_db`, no
  `Measurement`-level `to_impedance_table()`, no
  `measurement_type_registry`** — the Ideas-inbox at the bottom
  of this changelog records every one of these as a planned
  helper. Promote them out of the inbox into the
  Changed/Added backlog once a target release is picked.
- **`feature.txt`** is tracked in the repository root with one
  line of stale brainstorming content (compare against the
  `Ideas inbox` block below). The file pre-dates the
  introduction of the changelog and is now duplicated by the
  inbox. Either delete it as part of the next maintenance
  release, or convert it into a stub that points at the inbox.
- **`tmp_test.db`, `dummy.xml`, `Users/`, `Python=3.14`,
  `THIRD_PARTY_LICENSES_RAW.txt`** all sit at the repo root
  even though none of them is a project artefact. Move them
  into `tests/fixtures/` (the temp DB) or delete (the others);
  add appropriate `.gitignore` patterns so they do not
  reappear.

> Additional findings from the **third 2026-05-12 review pass**
> (focus: OCR pipeline, dashboard import shim, analytics edge
> cases, multilayer model wrapper):

- **`services/vision_import._normalize_ocr_text` runs
  `text.replace("rn", "m")` unconditionally** (vision_import.py
  around line 66 of the OCR helper). The OCR-artefact correction
  is meant to fix Tesseract reading "rn" as "m" inside numbers /
  units, but the replace is global and silently corrupts operator
  names containing the literal `rn` ("Bernhard", "Schwerin",
  "burn", "turn"). Scope the substitution to digits/units, e.g.
  `re.sub(r"(\d)\s*rn\b", r"\1 m", text)`.
- **`ui/dashboard.py:~503` imports `from groundmeas.analytics
  import rho_f_model`** (i.e. the *shim*), while the rest of
  `dashboard.py` imports from `services.analytics`. Two import
  paths for the same symbol bloats the dependency graph and
  breaks the moment the shim is removed. Use
  `from groundmeas.services.analytics import rho_f_model`
  consistently.
- **`services/analytics._rhoa_collinear_integral` has no guard
  for `g → 0`** (geometric factor singularity). For Schlumberger
  geometries with MN approaching AB the denominator can collapse
  and the helper returns a wildly inflated apparent resistivity.
  Add `if abs(g) < eps: raise ValueError(...)`.
- **`services/analytics.invert_layered_earth` returns the last
  Gauss-Newton iterate, not the best-RMSE iterate.** The
  termination test breaks on `|prev_rmse - rmse| < tol` *before*
  the new step is committed, so a successful step that improved
  RMSE by less than `tol` reports the un-stepped parameter
  vector. Track `(best_params, best_rmse)` explicitly inside the
  loop and return that.
- **`services/analytics.value_kind` auto-detection** classifies a
  unit string of bare `"Ω"` (no `m`) as **resistance**, while a
  user who recorded "Ω" thinking "ohm-meter" gets a silent
  factor-spacing mis-application in the Wenner / Schlumberger
  formula. Either narrow `"resistivity"` detection to require an
  explicit `m` / `*m` / `·m`, or warn when the unit is ambiguous.
- **`services/analytics.rho_f_model` reads raw stored
  `soil_resistivity` `value`s and treats them as ρ directly** —
  regardless of `unit`. If items were stored with
  `value_kind="resistance"` (which `soil_resistivity_profile`
  fully supports), the fit silently mixes resistance and
  resistivity. Route the read through
  `soil_resistivity_profile(..., value_kind="auto")` instead of
  the lower-level `read_items_by`.
- **`services/analytics.multilayer_soil_model` does not actually
  pick the best-fitting 1-, 2- or 3-layer model** even though the
  changelog entry for the helper advertises an "AIC-based
  selection". The current implementation just constructs a
  `LayeredEarthModel` from whatever layer count the user passes
  in. Either implement the advertised behaviour (fit each of 1 /
  2 / 3 layers, return the one with the lowest AIC) or rewrite
  the changelog and the docstring.
- **`services/analytics` (`rho_f_model` docstring) names the model
  `Z(ρ,f) = k1·ρ + (k2+jk3)·f + (k4+jk5)·ρ·f` but builds the
  design matrix as if `k2` and `k4` were real coefficients**, with
  `k3` / `k5` carrying the imaginary part. The parenthesisation is
  technically consistent but misleading. Either rewrite the
  formula to the split form `k1·ρ + k2·f + k4·ρ·f + j·(k3·f +
  k5·ρ·f)` or add a one-line clarifying sentence to the
  docstring.
- **`core/db.create_measurement` / `update_measurement` pop
  nested keys from the caller's dict in place** (e.g. `data.pop
  ("location")`). A retry loop or a list comprehension reusing
  the same dict raises `KeyError("location")` on the second
  call. Shallow-copy the dict at the top of each helper.
- **`core/models._sync_magnitude_on_update` is reachable on
  partial updates but the validator chain does not guard against
  zero-magnitude inputs.** Setting `magnitude_value=0` with
  `angle_value=None` leaves the rectangular shadow at `(0, 0)`
  silently. Decide whether zero-magnitude items should be
  rejected or pinned to `angle=0`.
- **`core/models.LayeredEarthModel.__post_init__` does not reject
  `nan` / `inf` for `rho_i` or `h_i`.** NaN passes the
  `value > 0` checks (NaN comparisons are always `False` → not
  re-raised), then propagates silently through every Wenner /
  Schlumberger forward call.

> Additional findings from the **fourth 2026-05-12 review pass**
> (focus: `calculate_split_factor` magnitude formula, `voltage_vt_epr`
> key naming, distance-profile value-kind handling, OCR backend
> selection):

- **`services/analytics.calculate_split_factor` computes
  ``split_factor = 1 - abs(shield_sum) / abs(earth_current)``**,
  but the function also computes the correct vector difference
  ``local_current = earth_current - shield_sum`` two lines below.
  The two are equivalent *only* when ``shield_sum`` and
  ``earth_current`` are co-linear in the complex plane; for any
  non-zero phase difference (the AP 1 realistic case with cable
  shields, PEN return current, transformer-station coupling) the
  magnitude-only formula gives a *negative* split factor where the
  vector formula gives a valid positive one. Either replace with
  ``split_factor = abs(local_current) / abs(earth_current)`` (and
  document the per-phasor convention), or rename the field to
  ``split_factor_magnitude`` and add a sister ``split_factor_vector``
  return key. Currently the function is silently wrong for every
  realistic field campaign on a meshed MV grid.
- **`services/analytics.voltage_vt_epr` stores the impedance under
  the key ``epr``** (`entry["epr"] = Z`). ``Z`` is the earthing
  *impedance* in Ω, not the Earth Potential Rise (V). With the
  function's per-Ampere convention this happens to equal the EPR
  per Ampere numerically, but the docstring says *"Calculate
  per-ampere touch voltages **and EPR** at a given frequency"* —
  a reader cannot tell that ``entry["epr"]`` is actually the
  earthing impedance unless they read the source. Either rename
  the key to ``Z`` or ``epr_per_amp`` or multiply by ``I`` to
  return the true EPR in volts.
- **`services/analytics.distance_profile_value` is `value_kind`-
  blind.** The helper reduces a distance profile by min / 62 % /
  inverse / gradient algorithms but treats every value as if it
  were an impedance (resistance-scaled by the spacing factor where
  appropriate). For a soil-resistivity profile (ρ × geometric
  factor) the *value* attribute is already in Ω·m and the
  reduction algorithms still pretend it is in Ω. Either route the
  read through the same `_normalise_value_kind(...)` helper used
  by `soil_resistivity_profile`, or fail loudly when
  `value_kind != "impedance"`.
- **`services/vision_import.ocr_image` silently falls back to
  tesseract** when the requested backend (``"openai:<model>"`` /
  ``"ollama:<model>"``) returns an empty string. The user expects
  an error so they can re-attempt or switch backends; today the
  pipeline continues with garbage OCR and the only diagnostic is a
  `UserWarning` deep inside `parse_measurement_rows`. Promote the
  empty-string return to a `RuntimeError` (or at least a structured
  result indicating which backend produced the empty payload).
- **`services/vision_import.parse_measurement_rows` regex catalogue
  does not include the German thousand-separator
  ``"."``** for values like ``1.234 mΩ``. The OCR pipeline reads
  the dot as a decimal separator, halving every measured value
  silently. Add an explicit ``thousands_separator: Literal[",",
  ".", " "]`` argument with a sensible locale-aware default and a
  warning on auto-detection ambiguity.
- **`core/db._engine` is a Python-level singleton without a
  `threading.Lock`.** Two threads calling `connect_db` concurrently
  (a likely pattern once the dashboard auth layer lands) end up
  with a partially-initialised engine: the second thread sees
  `_engine is None` *before* the first thread's `create_all` has
  returned. Wrap both `connect_db` and the planned `disconnect_db`
  with a module-level lock.
- **`services/analytics.invert_layered_earth` accepts
  ``damping=0``** in its argument signature, which short-circuits
  the Gauss-Newton step length to zero and silently returns the
  initial guess as the "best fit". Either clamp `damping` to a
  positive minimum (e.g. `1e-6`) or raise on `damping <= 0` at
  function entry.
- **`__init__.py` re-exports `rho_f_model` from the
  `groundmeas.analytics` shim** even though the dashboard, every
  notebook example, and the docs use the canonical
  `groundmeas.services.analytics` path. The shim has been on a
  deprecation track since `1.3.1`; surface a `DeprecationWarning`
  on first access through `__getattr__` and schedule the removal
  for `1.6.0` so the import-graph fork (pass 3 dashboard finding)
  does not regress.
- **`scripts/release.py` does not synchronise `CLAUDE.md`** with
  the bumped version. `groundmeas/CLAUDE.md` reads `1.4.0` while
  `pyproject.toml` already declares `1.5.1` — the same drift
  reported in three previous passes is still present.

> Additional findings from the **fifth 2026-05-13 review pass**
> (focus: shim deprecation gaps, dashboard read-only fall-out from
> the Pass-4 writability probe, OCR backend exception surface,
> doc/code import-path drift, missing CLI documentation for the
> already-shipped `--force` reconnect handle):

- **`groundmeas/db.py` shim does not re-export `disconnect_db`.**
  The Pass-4 audit-implementation block added `disconnect_db` to
  `core.db` and re-exported it from the package root, but the
  legacy `groundmeas.db` shim still hard-codes the old curated
  symbol list. `from groundmeas.db import disconnect_db` raises
  `ImportError`, even though `from groundmeas.db import connect_db`
  works. Either back-fill `disconnect_db` in
  `src/groundmeas/db.py` or replace the curated list with a
  `from groundmeas.core.db import *  # noqa: F401,F403` plus an
  updated `__all__`.
- **`groundmeas/db.py` and `groundmeas/analytics.py` shims do not
  emit a `DeprecationWarning`** on import or first attribute
  access. Pass 4 flagged this for `analytics`, but the `db.py`
  shim has the same problem and the dashboard, every notebook
  example and several docs pages still import from the shims.
  The fix is a module-level `__getattr__` that warns once per
  process and forwards to the canonical sub-module.
- **`services/vision_import.ocr_image` (OpenAI branch) parses the
  response with `data["choices"][0]["message"]["content"]`**
  without guarding against the documented "empty completion"
  shape (`choices[0]["finish_reason"] == "content_filter"`,
  `choices == []` on 5xx error envelopes, `message.content` of
  `None` for tool-call-only completions). Today these surface as
  `KeyError` / `IndexError` / `TypeError` inside `_parse_value_
  angle_unit` rather than as a structured `RuntimeError`. Wrap
  the lookup with `data.get("choices", [{}])[0].get("message",
  {}).get("content") or ""`, then raise `RuntimeError` on the
  empty-string case (this naturally subsumes the Pass-4 silent-
  fallback bug).
- **`ui/dashboard.py` does not catch the new `RuntimeError`
  from the writability probe.** Pass-4 implementation made
  `connect_db("/readonly/path")` raise eagerly; the dashboard's
  startup path (`connect_db(_default_db_path())`) now surfaces a
  raw Streamlit traceback on read-only filesystems and on a
  NextCloud share that is mounted read-only. Wrap the
  `connect_db` call in a `try/except RuntimeError` and render a
  human-readable `st.error(...)` with the resolved DB path.
- **`docs/02_quickstart.md`, `docs/12_read_measurements.md`,
  `docs/16_dashboard.md`, `docs/21_ref_api.md`** all import via
  the shim paths (`from groundmeas.db import ...`,
  `from groundmeas.analytics import ...`). Once the
  `DeprecationWarning` lands (Pass-4 entry), the very first
  `>>> import groundmeas` block in the docs emits a warning.
  Either canonicalise the docs on `groundmeas.core.db` /
  `groundmeas.services.analytics`, or hold off on the
  deprecation track until the docs are migrated.
- **`docs/22_ref_cli.md` does not document the new
  `connect_db(..., force=True)` keyword** that Pass-4
  implementation introduced. CLI users hitting the new
  ``RuntimeError`` ("engine already initialised") have no doc
  breadcrumb telling them the escape hatch exists. Add a
  configuration note under the **Configuration** section.
- **`services/vision_import._normalize_ocr_text` is still
  whitespace-insensitive between "rn" and the trailing unit
  letter.** Pass-3 implementation scoped the substitution to a
  digit-prefix; the trailing `[AVΩ0oO]` lookahead is greedy and
  does not allow a stray space (``118.1 rn Ω``). Real OCR output
  from the Megger DET2/2 and HT Italia GSC56 occasionally
  separates the unit letter from the prefix. Extend the
  lookahead with `\s*[AVΩ0oO]` to keep the fix robust.
- **`services/analytics.distance_profile_value`** silently drops
  duplicate-distance points via `_dedupe_by_interpolation` without
  warning the caller. For real Wenner / 62%-traverse data sets
  this can hide measurement repetitions that the operator
  intended as a noise estimate. Emit a `UserWarning` listing the
  collapsed item IDs whenever the dedup actually removes points.
- **`core/db._get_session` always opens an unmanaged
  `Session(_engine)`** (Pass-2 backlog entry) and additionally
  releases the GIL inside every CRUD helper while holding the
  session. Two concurrent `create_measurement` calls from the
  Streamlit dashboard's auto-rerun loop therefore race on the
  flush. Switch to `sessionmaker(bind=_engine, expire_on_commit=
  False)` and document the contract in
  `docs/01_datamodels.md → Threading and concurrency` (also
  Pass-4 doc gap).

### Changed (Backlog — pending implementation)

- **Add `gm.disconnect_db()`** as the symmetric counterpart of
  `connect_db`. Without it, downstream notebooks and the dashboard
  cannot cleanly switch between SQLite files.
- **Promote the `gm.read_*_by` API to a Polars-DataFrame
  accessor.** The current `(items, ids)` tuple of plain dicts is
  awkward for analytics work and forces every caller to build
  their own DataFrame anyway.
- **`gm-cli` `dashboard` subcommand should pass `--server.address
  127.0.0.1` and `--server.headless true` by default** so that
  starting the dashboard in a research VM does not silently bind
  on `0.0.0.0`. Easy hardening before the optional auth layer
  lands.

> Additional findings from the **sixth 2026-05-14 review pass**
> (focus: residual shim drift after the Pass-5 `db.py` /
> `analytics.py` `DeprecationWarning` rollout, version-string
> consistency, dashboard-side-effect of the Pass-5 `init_db`
> change, doc/code path drift in the tutorials):

- **Five compatibility shims still without `DeprecationWarning`.**
  Pass-5 retrofitted `groundmeas/db.py` and
  `groundmeas/analytics.py` with the `__getattr__`-based
  warning strategy, but `groundmeas/models.py`,
  `groundmeas/plots.py`, `groundmeas/export.py`,
  `groundmeas/vision_import.py` and `groundmeas/cli.py` still
  hard-bind their re-exports at module-import time and emit
  nothing. The five paths are part of the same shim family —
  the missing warning means a callsite that has migrated `db`
  and `analytics` to canonical paths but kept legacy imports
  for `models` / `plots` etc. has no signal to finish the
  migration. Fix: extract the `__getattr__` pattern from
  `db.py` into a small `groundmeas/_shim.py::make_shim(...)`
  helper, then apply it to all five.
- **`db.py` shim `__getattr__` warns even on `_get_session`
  access.** `_CANONICAL_ATTRS` includes `_get_session` (so it
  is reachable through the shim), but the `__getattr__` filter
  is `if name in _CANONICAL_ATTRS`, which is `True` for
  `_get_session`. Internal callers / test fixtures reaching
  `groundmeas.db._get_session` therefore see a
  `DeprecationWarning` for a *private* symbol. Add an
  `if name.startswith("_")` short-circuit before the warning,
  or split the table into a `_PUBLIC` set and an `_INTERNAL`
  set so the warning fires only on the public part.
- **`__version__` drift continues.** `src/groundmeas/__init__.py`
  pins `__version__ = "1.5.1"`, `pyproject.toml` is at
  `1.4.0` (per CLAUDE.md), but `groundmeas/db.py` and
  `groundmeas/analytics.py` advertise "deprecated since
  1.5.2" — three different version strings in the same
  package. The audit-readme-docs-2026-05-14 pass flagged
  this as "outside scope"; sixth-pass elevates it: bump
  `pyproject.toml` *and* `__init__.__version__` to `1.5.2`
  before the next release tag, or pin the shim docstrings to
  the same value that `__init__.py` reports.
- **`ui.dashboard.init_db()` cache reuse on a stale engine.**
  Pass 5 made `init_db` return a `bool` and stop the
  Streamlit script on failure. What is not yet guarded: on a
  *successful* Streamlit auto-rerun (after the user fixes
  permissions and reloads) `connect_db` short-circuits on
  `_engine is not None` and re-uses the *previous*
  (read-only-mount) engine. The user sees "already
  initialised" even after the underlying problem is fixed.
  Either call `disconnect_db()` before `connect_db()` in
  `init_db`, or expose `force=True` plumbing through a
  Streamlit sidebar button.
- **`services.vision_import.import_items_from_images` batch
  failure mode.** The Pass-5 `ocr_image` defensiveness now
  raises `RuntimeError` on a malformed OpenAI envelope
  instead of returning an empty result. The batch loop in
  `import_items_from_images` doesn't catch the new exception,
  so a single bad image aborts the entire campaign import.
  Wrap the per-image call in a `try / except RuntimeError`
  and log + skip, returning a per-image status list to the
  caller.
- **Docs/tutorial code still imports through shims.**
  `docs/02_quickstart.md`, `docs/10_tutorial_intro.md`,
  `docs/11_create_measurements.md`, `docs/12_read_measurements.md`,
  `docs/13_change_measurements.md` and others still write
  `from groundmeas.db import …` / `from groundmeas.analytics
  import …`. After the Pass-5 `DeprecationWarning` rollout
  every reader of those tutorials runs into the warning on
  the first cell of the very first notebook. Bulk-rewrite to
  the canonical top-level import (`import groundmeas as gm;
  gm.connect_db(…)`).
- **`distance_profile_value` `UserWarning` stacklevel.**
  Pass-5 added the duplicate-distance `UserWarning`, but the
  warning fires with the default `stacklevel=1`, which makes
  it point at `services/analytics.py` instead of at the
  caller's notebook cell. Set `stacklevel=2` (or `stacklevel=3`
  in the CLI path).
- **`services.analytics.invert_layered_earth` /
  `invert_soil_resistivity_layers` silently swallow
  `OptimizeResult.success=False`.** Both inversions return
  the (last) parameter vector and the residual norm even
  when the underlying `scipy.optimize.least_squares` flagged
  a non-convergence. A `UserWarning` with the
  `OptimizeResult.message` and the iteration count would put
  a hard floor on the data-quality story before the
  inversion result lands in a paper / dashboard.
- **`scripts/release.py` still bumps three of four version
  strings.** Five passes have now flagged the
  `[Unreleased]`-to-dated-section mover and the
  CITATION/CHANGELOG-CLAUDE drift. Sixth pass keeps the
  finding: cross-port the cross-repo `_release_shared.py`
  proposal (see Cross-cutting section in the audit report).

> Additional findings from the **seventh 2026-05-18 review pass**
> (focus: status check four days after the Pass-6 implementation
> deferral; five-shim deprecation rollout, repo-root hygiene,
> `__version__` drift, dashboard auto-rerun engine reuse):

- **Five shims still without `DeprecationWarning` — seventh pass
  in a row.** Verified on 2026-05-18: `src/groundmeas/models.py`,
  `src/groundmeas/plots.py`, `src/groundmeas/export.py`,
  `src/groundmeas/vision_import.py` and `src/groundmeas/cli.py`
  carry no ``warnings.warn(...)`` and no ``__getattr__`` lazy-warn
  pattern. Only `db.py` and `analytics.py` were retrofitted in
  Pass 5. The proposed `groundmeas/_shim.py::make_shim(...)` helper
  also does not exist on disk. The seventh pass keeps the
  recommendation: extract the `__getattr__` pattern from
  `db.py` into `_shim.py` and apply it to the five remaining
  shims in a single PR.
- **`db.py` shim still warns on `_get_session`.** Verified on
  2026-05-18: ``_CANONICAL_ATTRS`` includes ``"_get_session"`` and
  the ``__getattr__`` filter is ``if name in _CANONICAL_ATTRS``,
  which matches private symbols. A ``if name.startswith("_"): return
  _CANONICAL_ATTRS[name]`` short-circuit before the warning closes
  the gap — single-line edit. Pass-6 finding still open.
- **`__version__` still pinned at `1.5.1` cross-file.** Verified on
  2026-05-18: ``pyproject.toml`` carries ``version = "1.5.1"``,
  ``src/groundmeas/__init__.py`` carries ``__version__ = "1.5.1"``.
  The shim docstrings of `db.py` / `analytics.py` no longer carry
  the conflicting ``deprecated since 1.5.2`` string (sixth-pass
  finding resolved on the shim-doc side), but the package itself
  has not been bumped to `1.5.2` to ship the Pass-5
  implementation block. Cut `1.5.2` so the Pass-5 + Pass-6 fix
  blocks reach PyPI users.
- **Repo-root junk still present.** Verified on 2026-05-18:
  `feature.txt`, `dummy.xml`, `tmp_test.db`, `test_write_check.tmp`,
  `groundmeas.db`, `groundmeas.db-journal`, the `Users/` directory
  (containing a `christian/` snapshot from a test run) and the
  `Python=3.14/` virtual-environment directory all sit at the
  repository root. Six audit passes have flagged this; seven
  confirm the cleanup hasn't happened. Add the patterns to
  `.gitignore` *and* `git rm --cached` the existing entries so
  future clones don't pick them up.
- **`ui.dashboard.init_db()` still does not call
  `disconnect_db()` before `connect_db()`.** Verified on
  2026-05-18: the function only calls ``connect_db(db_path)``.
  When the previous engine was bound to a read-only mount and
  the user fixes permissions then reruns Streamlit, the
  ``with _engine_lock`` block in ``core.db.connect_db`` sees
  ``_engine is not None`` and short-circuits with
  ``RuntimeError("engine already initialised — pass force=True")``.
  The shim's "already initialised" branch then renders a
  green ``st.info`` banner but the underlying engine is still
  bound to the broken mount. Either call
  ``disconnect_db()`` at the top of ``init_db()`` when the
  resolved DB path differs from the engine's current path, or
  expose a "Reconnect with fresh engine" button in the
  Streamlit sidebar. Pass-6 finding still open.
- **`services.vision_import.import_items_from_images` still
  does not handle per-image batch failures.** Verified on
  2026-05-18: the batch loop has no ``try / except
  RuntimeError`` wrapping the per-image ``ocr_image`` call.
  A single malformed OpenAI envelope therefore aborts the
  entire campaign import — Pass-5 made the exception
  defensive, Pass-6 flagged the missing batch-level handler,
  Pass-7 confirms it remains unimplemented.
- **`services.analytics.invert_layered_earth` and
  `invert_soil_resistivity_layers` still swallow
  `OptimizeResult.success=False`.** Verified on 2026-05-18:
  both helpers return the (last) parameter vector and the
  residual norm even on non-convergence. A `UserWarning` with
  the ``OptimizeResult.message`` payload was Pass-6's
  proposal; pass 7 re-emphasises that the warning is the
  precondition for the planned data-quality lineage in
  `docs/15_analytics.md::OptimizeResult.success propagation`.
- **Tutorial pages still import through shims.** Verified on
  2026-05-18: `docs/02_quickstart.md`, `docs/10_tutorial_intro.md`,
  `docs/11_create_measurements.md`, `docs/14_import_export.md`
  still carry ``from groundmeas.db import …`` and
  ``from groundmeas.analytics import …``. With the Pass-5
  `DeprecationWarning` strategy now active on those two shims,
  every reader of the tutorials trips a warning on the first
  cell. Bulk-rewrite to the canonical
  ``import groundmeas as gm; gm.connect_db(…)`` form documented
  in `docs/21_ref_api.md`.

### Docs (Backlog — pending implementation)

- **`mkdocs.yml` is consistent with the project-wide numpy
  docstring style** as of `1.5.x` — the previous audit's claim
  that `docstring_style: numpy` was missing has been resolved.
  Cross-checked on 2026-05-10.
- **`docs/22_ref_cli.md`** does not yet describe the new
  `dashboard` subcommand, the Plotly plot helpers, or the
  layered-earth inversion entry point. The CLI reference lags
  one minor release.
- **No "Compatibility with `groundinsight`" page**: the planned
  `Measurement → ImpedanceTable` exporter and the
  `multilayer_soil_model → SoilModel` hand-off (both in roadmap)
  do not have a stub doc page that explains how the two
  packages talk to each other from the `groundmeas` side. Add
  `docs/17_groundinsight_bridge.md` once the exporter ships.
- **README**: there is no installation / quickstart entry for
  the optional `mlx` math backend. The analytics module already
  reaches for `mlx.core` opportunistically (and falls back to
  NumPy with a `UserWarning`); a one-liner under "Optional
  extras" prevents users on Apple Silicon from missing the
  speed-up.

> Additional doc gaps from the **second 2026-05-10 review pass**:

- **`docs/15_analytics.md`** documents `rho_f_model` only by
  signature; the underlying canonical
  ``Z(ρ, f) = k1·ρ + (k2+jk3)·f + (k4+jk5)·ρ·f`` form, the
  least-squares decomposition into the real and imaginary parts
  and the depth-selection step are nowhere on the doc site,
  even though the field-engineer reviewer in AP 1 needs to
  *trust* that algorithm. Add a "Methodology" subsection that
  spells out the design matrix and the depth-selection
  heuristic.
- **`docs/15_analytics.md`** does not yet describe the
  `voltage_vt_epr` magnitude-only convention (see the
  Fixed-backlog entry above). The user reading the docs would
  reasonably expect a complex per-Ampere ratio; the docstring
  silently returns magnitudes. Add a "Conventions" callout.
- **`docs/index.md`** lists the three core formulas
  (`Z_E = V_EPR / I`, `EPR = Z_E · I_E`, the rho-f model) but
  not the **multilayer Wenner / Schlumberger forward kernel**
  (Koefoed-filter style) that `services.analytics.layered_earth_forward`
  uses. Cross-reference the source of the linear-filter
  coefficients and the assumption (electrode size << probe
  spacing) so the limitations are visible from the index.
- **`docs/01_datamodels.md`** documents `MeasurementItem`
  fields but does not mention the new `value_real` /
  `value_imag` *vs.* polar `value` / `value_angle` synchronisation
  on insert / update. Round-trip behaviour is exercised in
  `tests/test_models.py` but invisible to a user reading the
  datamodel docs first.
- **README "Optional extras"** should list `mlx` *and* the
  Apple-Silicon caveat (no Linux/Windows wheels). The analytics
  module already gracefully falls back to NumPy with a
  `UserWarning`, but a new user installing on Ubuntu sees the
  warning and assumes the install is broken.
- **`docs/16_dashboard.md`** does not mention the impending
  `--server.address 127.0.0.1` / `--server.headless true`
  default change (see the Changed-backlog entry above). Update
  alongside the implementation.
- **No `docs/22_ref_cli.md` section on shell completion.**
  Typer ships shell completion for free; documenting how to
  enable it (`gm-cli --install-completion`) reduces the
  on-boarding cost.

> Additional doc gaps from the **third 2026-05-12 review pass**:

- **No documentation for the OCR pipeline.** `services/
  vision_import` supports `tesseract`, `openai:<model>` and
  `ollama:<model>` backends and reads the `OPENAI_API_KEY` env
  var, but neither the supported providers nor the env-var
  contract are documented outside the source. Add
  `docs/17_ocr_import.md` (or extend `docs/14_import_export.md`).
- **`docs/01_datamodels.md` does not enumerate the controlled
  vocabularies** (`MethodType` = Wenner / Schlumberger /
  staged_fault_test / …, `AssetType`, `ValueKind`,
  `ConductivityKind`). Users have to read
  `core/models.py:~43-59` to find the valid string literals.
  Add a "Controlled vocabularies" subsection.
- **`docs/16_dashboard.md` is silent on the
  `multi_select_mode` checkbox and the
  `focused_location_key` site picker** introduced in the
  recent dashboard refresh. Users who see two campaigns at
  the same site sharing one map marker have no documented
  way to disambiguate.
- **`docs/22_ref_cli.md` does not show the
  `gm-cli set-default-db` flow** end-to-end (where the default
  is stored, env-var precedence, how to inspect the active
  config). The Configuration table at the top of the page
  mentions the command but offers no example.
- **`mkdocs.yml` has no `edit_uri`** even though `repo_url` is
  set. One line (`edit_uri: edit/main/docs/`) enables the
  Material theme "Edit on GitHub" shortcut and lowers the
  contribution bar for the docs.
- **`GROUNDMEAS_MATH_BACKEND` env-var is undocumented.** The
  analytics module honours it (and falls back to NumPy with a
  warning when `mlx` is unavailable) but the variable is
  discoverable only by reading `services/analytics.py`. Mention
  it in `docs/15_analytics.md` together with the `mlx` extras
  note from the Apple-Silicon caveat above.

> Additional doc gaps from the **fourth 2026-05-12 review pass**:

- **`docs/15_analytics.md` does not document the magnitude-only
  convention of `calculate_split_factor`** (see the Fixed-backlog
  fourth-pass entry above). Even after the bug is fixed, the
  *intent* — magnitude vs. complex split factor — must be on the
  doc site so AP 1 reviewers can decide which quantity they want
  to plot. Add a "Split-factor conventions" admonition with a
  small worked phasor diagram.
- **`docs/15_analytics.md` does not document
  `voltage_vt_epr`'s per-Ampere convention.** The return key
  ``epr`` is per-Ampere (i.e. an impedance) and the touch-voltage
  keys ``vt_min/max`` are dimensionless (V/A). A reader expects
  voltages in volts. Add a one-paragraph callout that states the
  unit convention explicitly and points at the helper that
  multiplies by the prescribed fault current.
- **No `docs/17_ocr_import.md` cross-reference to the
  ``RuntimeError``-on-empty-backend-payload contract** flagged
  above. The OCR pipeline needs a "Backend selection and failure
  modes" section once the silent-fallback bug is fixed, including
  the env-var contract (``OPENAI_API_KEY``) and the
  Tesseract-must-be-on-PATH precondition.
- **`docs/15_analytics.md` does not name the
  ``GROUNDMEAS_MATH_BACKEND`` precedence chain** even after the
  pass-3 finding is addressed. The chain is
  ``backend="auto"`` → env-var → MLX-available → NumPy, but the
  user-facing prose must spell that out so users can flip the
  backend deterministically in CI.
- **`docs/01_datamodels.md` has no "Threading and concurrency"
  section.** Users running the dashboard against a remote SQLite
  file regularly trip over the SQLite default
  ``check_same_thread=True`` and the missing engine-level lock
  (Fixed-backlog fourth-pass entry above). Two paragraphs would
  spare future support tickets.
- **README "Quickstart" snippet still calls
  ``gm.connect_db("grounding.db")``** without an explicit
  ``Path.touch()`` precondition. On a read-only filesystem the
  call returns successfully and the failure mode is the same as
  the lazy-create bug already on the backlog; mention the
  smoke-test path in the README.

> Additional doc gaps from the **fifth 2026-05-13 review pass**:

- **`docs/21_ref_api.md` still labels sections "Database
  (groundmeas.db)" / "Analytics (groundmeas.analytics)"** —
  i.e. it instructs users to import from the deprecated shims.
  Either rename the sections to the canonical
  `groundmeas.core.db` / `groundmeas.services.analytics` paths
  *or* add a "Stable import surface" callout that names
  `groundmeas` as the top-level (`from groundmeas import
  connect_db, ...`) and demotes the `groundmeas.db` /
  `groundmeas.analytics` paths to deprecated-alias status.
- **`docs/22_ref_cli.md` does not list shell completion** —
  Typer ships `--install-completion` for free; documenting it
  closes the Pass-3 doc gap that was *also* recorded for
  `set-default-db` and lowers the on-boarding cost. A two-line
  block under the **Configuration** heading is enough.
- **`docs/01_datamodels.md` has no entry for the new
  `disconnect_db` lifecycle.** The Pass-4 implementation block
  added a paragraph but the rendered page (mkdocs) does not show
  the connect → disconnect handshake as a code example. Promote
  the paragraph to a "Lifecycle" subsection with a short
  notebook-style snippet (`connect_db → create_measurement →
  disconnect_db`).
- **`docs/14_import_export.md` Scenario B still imports
  `from groundmeas.vision_import import import_items_from_images`
  (the shim path).** Cross-reference to the fifth-pass Fixed-
  backlog entry above — the docs should follow whichever side
  of the shim deprecation the next release picks.
- **`README.md` lists the supported Python range as `>=3.10`
  but does not pin the CI matrix** in the project description
  ("Tested on 3.10, 3.11, 3.12"). The Pass-3 README "Optional
  extras" section is in place; this is the symmetric addition
  for the support contract.
- **`docs/15_analytics.md` does not document
  `multilayer_soil_model` honestly.** The current docstring and
  the Pass-3 finding both agree that the helper does *not*
  pick a best-fitting model; the doc page nevertheless lists
  it under "Analytics" with a one-line description that implies
  it does. Either drop the entry until the AIC-based variant
  ships or rewrite the line to make it clear that the helper
  is a thin wrapper around `LayeredEarthModel`.
- **`docs/16_dashboard.md` does not warn about the read-only
  filesystem failure mode.** Cross-reference to the fifth-pass
  Fixed-backlog entry: once the dashboard catches the
  `RuntimeError`, the docs should still call out that the
  Streamlit app needs a writable parent directory for its
  default `./groundmeas.db` and that the writable-mount caveat
  is the most common failure on Streamlit Cloud and on
  read-only NextCloud / SharePoint shares.

> Additional doc gaps from the **sixth 2026-05-14 review pass**:

- **Doc-code path drift.** `docs/02_quickstart.md`,
  `docs/10_tutorial_intro.md`, `docs/11..13_*.md` still use
  `from groundmeas.db import …` / `from groundmeas.analytics
  import …`. With the Pass-5 `DeprecationWarning` strategy
  now active on those two shims, every tutorial reader sees a
  warning on the first import. Bulk-rewrite to the canonical
  top-level form documented in the new
  `docs/21_ref_api.md::Canonical vs. shim import paths`
  note (Pass-5 already landed the convention sub-section;
  the example pages did not follow).
- **`docs/14_import_export.md` does not describe the
  multi-image batch-failure mode** of
  `import_items_from_images` after the Pass-5
  `RuntimeError`-on-malformed-envelope change. A reader who
  runs a 40-image OCR batch and hits one malformed envelope
  gets the entire batch aborted with a one-line traceback;
  the doc should call out either the proposed
  per-image-skip handler (sixth-pass Fixed-backlog above)
  or the user-side `try / except` recipe until the helper
  lands.
- **`docs/22_ref_cli.md` does not document `gm-cli doctor`**
  (proposed in Pass 5 Ideas-inbox). Once the proposal
  materialises the doc must follow.
- **No `docs/15_analytics.md` section for
  `OptimizeResult.success` propagation.** Tied to the
  sixth-pass Fixed-backlog "silent non-convergence" entry:
  when the inversion lands a `UserWarning` path, the docs
  should describe how the warning is structured and how the
  user can elevate it to an exception with
  `warnings.filterwarnings("error", ...)`.
- **No "Compatibility shims — full list" subsection in
  `docs/21_ref_api.md`.** Pass-5 documented `db` and
  `analytics`; the other five shims (`models`, `plots`,
  `export`, `vision_import`, `cli`) are not mentioned at
  all. With the sixth-pass `DeprecationWarning`
  cross-rollout there will be one warning class per shim
  module — the docs should enumerate them so the user has
  a single source of truth for the deprecation timeline.
- **`docs/16_dashboard.md` should describe the Pass-5
  `init_db()` return contract.** When the function returns
  `False` the dashboard renders an `st.error` panel and
  calls `st.stop()`; the docs should describe what the user
  sees, not just the writability probe. A one-screenshot
  inset would close the support-question loop.
- **mkdocs-jupyter is not wired.** The Pass-5 audit-readme
  pass migrated docstrings to numpy style; sixth pass
  notices that the `notebooks/` directory contains 17
  research notebooks (incl. `audit_pass5_fixes_2026_05_13.ipynb`)
  but `mkdocs.yml` does not load `mkdocs-jupyter` and
  none of the notebooks appears in the site nav. Either
  install the plugin and add a `Notebooks` nav entry, or
  document the convention "notebooks are research
  artifacts, not site content" in `docs/index.md`.

> Additional doc gaps from the **seventh 2026-05-18 review pass**:

- **`docs/15_analytics.md`** still does not cover the
  Pass-5 ``distance_profile_value`` ``UserWarning`` payload
  contract (the per-duplicate distance list, the
  ``measurement_id`` / ``measurement_type`` annotations,
  the ``stacklevel=3`` notebook-friendly reporting). Six-pass
  documentation gap; seventh-pass re-emphasis.
- **`docs/21_ref_api.md` "Compatibility shims — full list"
  subsection still missing.** Pass-5 documented `db` and
  `analytics`; the five remaining shims (`models`, `plots`,
  `export`, `vision_import`, `cli`) have no enumeration in
  the reference. Once the seventh-pass `_shim.make_shim(...)`
  rollout lands there will be seven `DeprecationWarning`
  classes — the docs need a single-source-of-truth table
  before the rollout, not after.
- **`docs/16_dashboard.md`** does not yet describe the
  Streamlit-rerun engine-reuse hazard flagged in the
  Pass-6 / Pass-7 Fixed-backlog entry on `init_db()`. A
  one-paragraph "Reconnecting after permission fixes"
  subsection that points users at
  `disconnect_db()` (and the planned sidebar button) closes
  the loop on a frequent support question.
- **`docs/22_ref_cli.md`** still does not describe
  `gm-cli set-default-db` end-to-end (where the default is
  stored, env-var precedence, how to inspect the active
  config). Pass-3 finding; seventh-pass confirms the
  Configuration table at the top of the page references the
  command but offers no example.
- **`README.md`** does not yet list the supported Python
  range honestly. ``pyproject.toml`` carries
  ``python = ">=3.14,<3.15"`` (the user's preferred matrix);
  README still says ``>=3.10``. Either tighten the README
  to the actual CI matrix or relax the
  `pyproject.toml` Python constraint — current state is
  install-time misleading.

### Tests (Backlog — pending implementation)

- **No regression test for `connect_db` / `disconnect_db`
  idempotency** once the helper exists. Important because the
  Streamlit dashboard reuses the same process across sessions.
- **No test that `voltage_vt_epr` correctly raises / warns on
  ambiguous (multi-row) earthing-impedance entries**.
- **No timing regression for `rho_f_model`** — once the
  closed-form depth selection lands, lock in a baseline runtime
  on a 20-measurement / 6-depth synthetic campaign so the
  exponential bug cannot return.

> Additional test gaps from the **third 2026-05-12 review pass**:

- **No test for `_sync_magnitude_on_update`** (`core/models.py`)
  — every polar ↔ rectangular round-trip on `update_item` is
  currently unverified.
- **No test for `multilayer_soil_model` with `nan` / `inf`
  inputs.** Build a fixture with one `nan` layer thickness and
  assert that the helper raises a clear `ValueError` (rather
  than silently producing a NaN-laden forward solve).
- **No round-trip test for `export_measurements_to_json` →
  `import_json`.** The shape that the exporter writes must be
  consumable by the importer; today the contract is implicit.
- **No regression test for `value_kind="auto"` with a unit
  string of bare `"Ω"`** (third-pass bug #4 above would have
  been caught).
- **No test for `read_measurements_by(..., field__in=[])`**.
  `SQLAlchemy.col.in_([])` is a well-known footgun (deprecation
  warning + dialect-dependent fallback to "all rows"). Pin the
  behaviour with an explicit `expected = []` assertion.

> Additional test gaps from the **fourth 2026-05-12 review pass**:

- **No regression test for `calculate_split_factor` with
  out-of-phase shield currents.** Build a fixture where
  `earth_fault_current = 1000 ∠ 0°` and `shield_currents =
  [300 ∠ 30°, 400 ∠ 60°]`. Assert that
  `split_factor == abs(local_current) / abs(earth_current)` and
  that `0 ≤ split_factor ≤ 1` even for non-zero shield-current
  phases. Today the magnitude-only formula yields a value below
  zero on this fixture.
- **No regression test for `distance_profile_value(...,
  measurement_type="soil_resistivity")`.** All current tests pin
  the algorithm against `earthing_impedance` items. Add a
  resistivity-typed fixture and lock in the expected return value
  unit (Ω·m, not Ω).
- **No regression test for the OCR backend silent-fallback bug.**
  Mock the `openai`-backend client to return an empty string and
  assert that `ocr_image` raises `RuntimeError` rather than
  passing the empty text on to `parse_measurement_rows`.
- **No regression test for German-locale OCR input.** Provide a
  fixture image (or a pre-extracted string with
  `"1.234 mΩ ; 5,67 Ω"`) and assert the importer reads the values
  as `1234 mΩ` and `5.67 Ω`, not the swapped interpretation.
- **No threading test on `connect_db`.** Spawn two threads that
  each call `connect_db("file:test?mode=memory&cache=shared")` and
  assert that exactly one engine ends up on the module-global
  after both threads have returned.
- **No regression test asserting the `analytics`-shim deprecation
  warning.** Import `from groundmeas.analytics import rho_f_model`
  inside a `pytest.warns(DeprecationWarning)` block.

> Additional test gaps from the **fifth 2026-05-13 review pass**:

- **No regression test for `from groundmeas.db import
  disconnect_db`.** Add a one-liner that re-imports through the
  shim and asserts the symbol round-trips to the same callable
  as `groundmeas.disconnect_db`.
- **No regression test for the OpenAI-OCR malformed-response
  surface.** Mock the OpenAI client to return
  `{"choices": [{"message": {"content": None,
  "finish_reason": "content_filter"}}]}` and assert
  `ocr_image` raises `RuntimeError` (not `TypeError`).
- **No regression test for the Streamlit dashboard read-only DB
  fallback.** Spin up the dashboard with a read-only target
  directory, drive the first interaction, and assert that the
  error path emits the structured `st.error` rather than the
  raw Streamlit traceback panel.
- **No regression test for `_normalize_ocr_text` with a
  whitespace-separated unit (``118.1 rn Ω``).** The third-pass
  fix locks the bigram in the no-space case; the German-locale
  Megger DET2/2 export also produces the spaced case.
- **No regression test for `distance_profile_value` on a profile
  with duplicate-distance items** asserting the `UserWarning`
  payload contains the dropped item IDs.
- **No regression test asserting that
  `from groundmeas.db import *` and
  `from groundmeas.analytics import *`** emit a single
  `DeprecationWarning` per process (and not one per attribute
  read) once the shim deprecation lands.
- **No regression test for `connect_db(..., force=True)`** —
  after the Pass-4 implementation, the `force` flag has no
  coverage outside the audit-fix file; add an explicit test
  exercising the dispose-and-replace path.

> Additional test gaps from the **sixth 2026-05-14 review pass**:

- **No regression test for the *five* still-silent shims**
  (`models`, `plots`, `export`, `vision_import`, `cli`). Once
  the sixth-pass Fixed-backlog cross-rollout lands, a single
  parametrised test `test_all_shims_warn_on_first_access`
  should walk the module list and assert exactly one
  `DeprecationWarning` per access.
- **No regression test that the `db.py` shim does *not* warn
  on `_get_session`.** Once the underscore-prefix
  short-circuit lands, pin it with a test that captures
  warnings and asserts `len(w) == 0` for a private-attr access.
- **No regression test for `ui.dashboard.init_db()` on a
  Streamlit *rerun*.** Stub `_engine` to a non-`None`
  sentinel, call `init_db()` twice and assert the second
  call honours the new "rerun-aware" path (whichever
  semantics the sixth-pass Fixed-backlog ultimately picks).
- **No regression test for `import_items_from_images` with a
  partially-failing batch.** Provide three image fixtures
  (two valid, one with a malformed OpenAI envelope); assert
  the function returns two successful imports and a
  structured per-image failure record for the third — no
  `RuntimeError` should propagate up to the caller.
- **No regression test for `invert_layered_earth` /
  `invert_soil_resistivity_layers` on `OptimizeResult.success
  = False`.** Construct a measurement set with too few
  observations to constrain three layers, assert the
  inversion completes *and* emits a `UserWarning` with the
  `OptimizeResult.message` payload.
- **No `mkdocs build --strict` test.** Once the doc-code
  drift fix lands (sixth-pass Docs-backlog), `mkdocs build
  --strict` should pass; pin that in CI.
- **No regression test that `services.analytics.distance_profile_value`
  emits the duplicate-distance `UserWarning` with
  `stacklevel >= 2`.** Use `warnings.catch_warnings(record=True)`
  and inspect `w[0].filename` — it should be the test file,
  not `services/analytics.py`.

> Additional test gaps from the **seventh 2026-05-18 review pass**:

- **No regression test for `ui.dashboard.init_db()` rerunning
  after a path change.** Stub the dashboard process: connect
  to a read-only mount path A, observe the ``False`` return
  and the ``st.error`` panel, then change ``GROUNDMEAS_DB``
  to a writable path B and re-call ``init_db()``. Assert
  that the second call connects to path B, not silently
  reuses path A. Pins the seventh-pass Fixed-backlog
  `init_db()` stale-engine fix.
- **No regression test for `pyproject.toml`-vs-`__init__.py`
  version parity.** ``tests/test_release.py`` covers the
  release-script flow but does not pin
  ``importlib.metadata.version("groundmeas") ==
  groundmeas.__version__``. A one-line ``test_version_parity``
  closes the multi-pass drift loop.
- **No repo-hygiene test.** Add
  ``tests/test_repo_hygiene.py::test_no_runtime_artefacts_at_root``
  that asserts ``feature.txt``, ``dummy.xml``, ``tmp_test.db``,
  ``test_write_check.tmp``, ``groundmeas.db``,
  ``groundmeas.db-journal``, ``Users/`` and ``Python=3.14/``
  are not present at the repository root. Without it, the
  seventh repo-hygiene finding will become the eighth.
- **No regression test for the five-shim deprecation
  rollout.** Once ``_shim.make_shim`` lands, walk
  ``["groundmeas.models", "groundmeas.plots",
  "groundmeas.export", "groundmeas.vision_import",
  "groundmeas.cli"]`` and assert each emits exactly one
  ``DeprecationWarning`` per process on first attribute
  access. Mirrors the proposed sixth-pass
  parametrised test.

### Roadmap — Ideas inbox (additions)

The Ideas-inbox section at the very bottom of this changelog has
been seeded with the following from the 2026-05-10 audit. Triage
into the appropriate roadmap section in the next planning cycle.

---

## [1.5.1] — 2026-05-04

### Fixed

- `scripts/release.py` now adds `THIRD_PARTY_NOTICES.md` and
  `THIRD_PARTY_LICENSES_RAW.txt` to the release commit. In `1.5.0`
  these files were regenerated as part of the release flow but
  excluded from `git add`, so the published tarball shipped with the
  pre-release notices. The next patch release will carry the
  up-to-date files.
- `.pre-commit-config.yaml` `cffconvert-validate` hook switched from
  ``language: system`` to ``language: python`` with
  ``additional_dependencies: [cffconvert]``. The previous variant
  required `cffconvert` on the system `PATH`, which was not the case
  outside an activated Poetry venv and caused the pre-push hook to
  fail with ``Executable `cffconvert` not found``.

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

[Unreleased]: https://github.com/Ce1ectric/groundmeas/compare/v1.5.1...HEAD
[1.5.1]: https://github.com/Ce1ectric/groundmeas/compare/v1.5.0...v1.5.1
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

- **`gm.disconnect_db()`** — symmetric counterpart of
  `connect_db`, calls `engine.dispose()` and resets the
  module-level engine. Currently you have to restart the
  interpreter to switch DBs.
- **`gm.measurements_summary(group_by={"location"|"operator"|"year"})`**
  — aggregate counts, average impedance magnitude at 50 Hz,
  date range, dominant `measurement_type` per group. Useful for
  campaign overviews in the dashboard and the planned
  measurement-protocol PDF.
- **Touch- / step-voltage measurement type** — first-class
  `measurement_type` value for `MeasurementItem` plus dashboard
  filters and a dedicated plot. Already in the roadmap; flag here
  so the dashboard work tracks with it.
- **`gm.assess_against_en50522(measurement_id, t_clearing_ms)`**
  — pull `prospective_touch_voltage` items for a measurement,
  compare them to the EN 50522 Table B.4 limit (which the
  `groundfield` companion already hosts in
  `postprocess.safety.permissible_touch_voltage_en50522`), return
  a per-row pass/fail. Closes the measurement-side safety loop.
- **Confidence bands on layered-earth inversion** — propagate
  the optimiser covariance from `invert_layered_earth` through
  to `plot_soil_inversion*` as ±1 σ / ±2 σ shaded
  envelopes. AP 1 reviewers always ask.
- **`Measurement.to_impedance_table()`** — produce the
  `Dict[Tuple[rho, f], ComplexNumber]` shape that
  `groundinsight.BusType` / `BranchType` accept directly. Hard
  dependency on the soil-resistivity profile of the same
  campaign.
- **`gm-cli protocol --measurement <id> --template <path>`** —
  render the planned measurement-protocol PDF (`reportlab` or
  `docx`) from a campaign and a Jinja template. Already
  mentioned in the roadmap; surface it as an inbox item so the
  template format is decided before the implementation lands.
- **Dashboard auth layer** — even a single token in a
  `secrets.toml` would let users share the dashboard URL with
  one collaborator without exposing the entire DB. Already in
  the roadmap.
- **Cross-validation against the `groundfield` reference fit** —
  pull a `RhoFStandardFit` from a `groundfield` JSON export and
  overlay it on the measured `Z(f)` for the same site, so
  reviewers can see at a glance how well the field model
  reproduces reality.
- **`gm.measurement_type_registry`** — surface the union of
  allowed `measurement_type` strings as a constant, so the CLI
  completers, dashboard filters and the planned protocol
  renderer all agree on the canonical list. Today the values
  live in `MeasurementItem.measurement_type: Literal[...]` and
  are duplicated in several places.

> Additions from the **second 2026-05-10 review pass**:

- **`RhoFFitResult` dataclass** — return value of a future
  `rho_f_model_v2(...)` that bundles `k = (k1..k5)` with
  residual norms, an R²-style diagnostic on the real and
  imaginary parts, the depth-selection metadata (chosen depths
  per measurement and the residual range), and a `to_polars()`
  long-format export. The current tuple-returning
  `rho_f_model` would stay as a thin shim around the new helper
  for one minor release before being deprecated.
- **`gm.session()` context manager** — exposes the SQLModel
  `Session` with `with gm.session() as s:` so power users can
  run hand-written SQLModel queries against the same engine
  without re-implementing `_get_session`. Keeps every
  high-level CRUD entry point as it is, but unblocks
  bulk-import scripts and the planned protocol renderer.
- **`gm.measurements_dataframe(group_by=..., aggregate=...)`**
  — Polars-DataFrame accessor companion to
  `gm.measurements_summary`. Returns one row per measurement
  with location, operator, timestamp, sampling-frequency
  vector, derived 50-Hz earthing impedance and a measurement-
  type tag — the natural input for cross-campaign comparisons
  and the planned protocol PDF.
- **Reproducible `from-fixtures` test corpus** — gather the
  XML / JSON / OCR-image fixtures currently scattered across
  `tests/` into a single `tests/fixtures/` tree and document
  them in `docs/99_contributing.md` so contributors know how to
  add a regression measurement without breaking the
  fixture-paths in every test file.
- **`gm-cli check` subcommand** — quick health-check entry point
  that runs the planned plausibility / QA checks
  (negative magnitudes, phase outside ±π, passivity violations
  across frequency) on a DB or a CSV and prints a summary table.
  Useful as a pre-commit hook on field data.
- **`groundfield-bridge` extra** — match the
  `groundinsight[pandapower]` style so the planned
  cross-validation against `groundfield`'s `RhoFStandardFit`
  does not pull the heavy `gmsh` / `pyvista` chain into the
  default install.

> Additions from the **third 2026-05-12 review pass**:

- **`gm.assess_against_iec61936(measurement_id, t_clearing_ms)`**
  — German users frequently work to IEC 61936 / DIN VDE 0101
  rather than EN 50522 alone. Expose the same touch-voltage
  limit lookup parametric on the standard family
  (`"EN50522" | "IEC61936" | "IEEE80"`) so the dissertation
  notebooks can switch between curves without re-implementing
  them.
- **`gm.distance_profile_value(..., return_all_algorithms=True)`**
  — `docs/15_analytics.md:~93` already recommends comparing the
  five reduction algorithms, but the API forces five round-trips
  to the DB to do so. Add a one-call multi-algorithm comparison
  that returns a Polars frame indexed by algorithm name.
- **`gm.bulk_create_items(measurement_id, payloads)`** —
  `core/db.create_item` opens / commits / refreshes one session
  per row. Importing 1 000 rows from a CSV today means 1 000
  commits. Batch with a single session + executemany; gives a
  10–50× speed-up on the typical AP 1 campaign size.
- **`gm.import_from_csv(path, schema=...)`** — long-form CSV
  importer to complement the OCR path. Most modern field
  instruments export CSV directly; the OCR pipeline is fragile
  for printed PDFs that already carry searchable text.
- **`LayeredEarthModel.aic()` plus a real
  `multilayer_soil_model(profile, max_layers=3)`** — replace the
  current pass-through wrapper with the AIC-based 1/2/3-layer
  selector the changelog already promised. Fits the existing
  `services.analytics.invert_layered_earth` and exposes the
  best-fitting model with diagnostics.

> Additions from the **fourth 2026-05-12 review pass**:

- **`gm.split_factor_vector(...)`** — companion to the
  magnitude-only `calculate_split_factor` once that helper is
  fixed. Returns the full complex phasor split, the in-phase /
  quadrature split and the maximum admissible magnitude error
  given the per-phasor measurement uncertainty. Closes the AP 1
  reviewer concern about silently-negative magnitude split
  factors on meshed grids.
- **`gm.epr_from_voltage_vt_epr(..., fault_current_A)`** — thin
  helper that multiplies the per-Ampere ``vt_*`` / ``epr`` dict
  by a user-supplied fault current and returns volts. Closes the
  unit-confusion footgun documented in the Fixed-backlog
  fourth-pass entry without forcing a backwards-incompatible
  rename of the existing function.
- **`gm.ocr_with_fallback(path, primary, secondary)`** —
  explicit two-backend retry helper. Calls the primary backend
  (e.g. ``openai:gpt-4o-mini``), validates the result with a
  one-line regex, falls back to tesseract on failure, and
  attaches the chain of attempts as diagnostic metadata on the
  returned `ParsedRow`. Replaces the silent-fallback path
  flagged above.
- **`gm.set_db_locale(locale)`** / `gm.connect_db(...,
  locale=...)` — configure the thousands- and decimal-separator
  defaults at DB level so that subsequent OCR / CSV imports
  parse German vs. English numbers without per-call kwargs.
  Defaults to the active system locale.
- **`gm.measurements_audit_trail(measurement_id)`** — return a
  long-format DataFrame of every `create_*` / `update_*` /
  `delete_*` operation that has touched a measurement, useful
  for the planned protocol PDF and for cross-checking against
  field logs. Requires a small `MeasurementAuditLog` SQLModel
  but is otherwise self-contained.
- **`gm-cli health`** — symmetric CLI entry to the planned
  `gm-cli check` plausibility subcommand: runs the schema
  integrity check, prints engine status, reports the active
  `GROUNDMEAS_MATH_BACKEND`, and lists the resolved default DB
  path (closes the `set-default-db` documentation gap).
- **`gm.measurement_diff(id_a, id_b)`** — long-format diff of
  two measurements at the item level, used to compare two
  campaigns at the same site. Saves AP 1 reviewers from
  hand-tabulating per-frequency deltas across campaigns.

> Additions from the **fifth 2026-05-13 review pass**:

- **`gm.set_db_lifecycle(strict | force | reuse)`** — wrap the
  Pass-4 engine-guard policy in a single configuration knob so
  notebooks (`reuse`), the dashboard (`force`) and the test
  suite (`strict`) can each pick the right semantics without
  rewriting `connect_db` call sites.
- **`gm.ocr_image(..., on_empty="raise" | "tesseract" |
  "return")`** — explicit empty-payload policy for the OpenAI /
  Ollama backends so the silent-fallback bug cannot regress.
  Pairs with the planned `gm.ocr_with_fallback` from the
  fourth-pass roadmap.
- **`gm-cli doctor`** — superset of the planned `gm-cli health`
  / `gm-cli check`: writability probe on the configured DB
  path, version drift detection between `pyproject.toml`,
  `__version__`, `CITATION.cff` and `CLAUDE.md`, shim-import
  scan, OCR backend availability, math-backend resolution.
  One command, one summary table — first thing a user runs
  before opening an issue.
- **`gm.session()`** context-manager API — promote the
  Pass-2 backlog entry into a real proposal. `with
  gm.session() as s: ...` exposes the SQLModel session under
  a documented contract (auto-commit on success, rollback on
  exception, no `_engine` access for the caller).
- **`gm.deprecation_status()`** — quick helper that returns a
  dict of "module → status" for every shim that is on a
  deprecation track. Lets the dashboard's `gm-cli doctor`
  output and the docs builder both consume the same source of
  truth.
- **`docs/17_ocr_import.md` as a real tutorial page** — collect
  the OCR-related callouts (backend selection, env vars,
  failure modes, German-locale handling, retry-on-empty) into a
  single dedicated page rather than scattering them across
  Pass-3 and Pass-4 doc-backlog items.

> Additions from the **sixth 2026-05-14 review pass**:

- **`gm._shim.make_shim(canonical_module, *, warning_message)`** —
  one-shot factory that produces the Pass-5 `__getattr__`-based
  shim wrapper, with private-attribute short-circuit and
  `__all__` synchronisation built in. Use it to retrofit
  `models`, `plots`, `export`, `vision_import` and `cli` in a
  single diff, and to make any future shim warn-by-default.
- **`gm.docs.assert_shim_pages_documented()`** — small CI
  helper that walks the shim list and asserts each one is
  enumerated in `docs/21_ref_api.md::Canonical vs. shim
  import paths`. Closes the "five-shims-without-docs" entry
  in the sixth-pass Docs-backlog.
- **`gm.show_versions()`** — return the runtime version table
  for `groundmeas`, `sqlmodel`, `polars`, `pydantic`, `numpy`,
  `streamlit`, the OCR backends and the resolved
  `GROUNDMEAS_DB`. Mirror of the proposed
  `gi.show_versions()` and `gf.show_versions()`; needed by
  the cross-package `doctor` proposal so that all three
  packages output a shape that the dashboard / CI can
  compare without bespoke parsing.
- **`gm-cli changelog-mover` helper** — wrap the
  `scripts/_changelog.py` `[Unreleased]` mover behind a
  user-facing CLI command so the maintainer's release-day
  workflow does not depend on knowing which Python helper
  to invoke. Mirrored across all three repos by the proposed
  cross-repo `_release_shared.py` (ADR-0011 in `groundfield`).
- **`gm.dashboard.session_state`** — explicit, serialisable
  Streamlit session state so the dashboard can resume after
  a server-side rerun without losing the current filter set.
  Closes the half-fixed Pass-5 `init_db()` rerun footgun.

> Additions from the **seventh 2026-05-18 review pass**:

- **Cut `1.5.2` patch release.** Pass 7 reiterates: the
  Pass-5 implementation block has been on PyPI as
  unreleased work for five audit passes; the
  ``__version__`` drift will keep reappearing in every
  audit until ``pyproject.toml`` and
  ``src/groundmeas/__init__.py`` carry ``1.5.2``. Bundle
  the seventh-pass five-shim ``_shim.make_shim`` rollout,
  the ``init_db()`` stale-engine fix and the
  ``import_items_from_images`` batch handler into the
  same tag.
- **`gm.cross_repo` namespace** — mirror the proposed
  `gi.cross_repo` / `gf.cross_repo` re-exports so all
  three packages expose the same diagnostics surface
  (`show_versions`, `audit_apply`, `docs_assert`,
  `repo_hygiene`). Stops the cross-cutting helpers from
  bloating the top-level namespace.
- **`gm.repo_hygiene.check()`** — programmatic equivalent
  of the seventh-pass repo-root junk-check; useful both
  as a `pytest` fixture and as a `gm-cli doctor`
  sub-command. Lists known runtime artefacts that should
  not be present at the repository root (`feature.txt`,
  `dummy.xml`, `tmp_test.db`, ``Users/``,
  ``Python=3.14/``) so a fresh ``git clone`` is verifiable
  against a canonical clean state.
- **ADR-0001 — `groundmeas` ADR family.** `groundinsight`
  and `groundfield` carry ADR directories; `groundmeas`
  does not. Seven passes of cross-repo audit reports have
  accumulated a handful of architecture-level decisions
  (`__getattr__`-based shim deprecation, `_engine`-as-
  module-singleton + `threading.Lock`, NumPy-vs-MLX
  backend dispatch, dashboard read-only-mount handling)
  that deserve a per-decision ADR file rather than
  changelog-section archaeology. Open the `docs/adr/`
  directory and start with `ADR-0001 — Compatibility-shim
  deprecation strategy`.
