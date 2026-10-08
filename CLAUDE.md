# groundmeas — Projektkontext

Python-Paket zur Erfassung, Speicherung, Analyse und Visualisierung von Erdungsmessungen (grounding / earthing). Open Source (MIT), auf PyPI veröffentlicht, Dokumentation via MkDocs auf GitHub Pages.

- Repo: https://github.com/Ce1ectric/groundmeas
- Doku: https://ce1ectric.github.io/groundmeas/
- Aktuelle Version: `1.5.2` in Arbeit (siehe `pyproject.toml`, `CITATION.cff`, `src/groundmeas/__init__.py`; PyPI: 1.5.1)
- Branch: `main`

## Toolchain

- Python `>=3.14` (im CI wird genau `3.14` verwendet)
- Dependency-Management: **Poetry** (`poetry install`, `poetry shell`)
- Tests: `pytest` (+ `pytest-cov`), laufen über `poetry run pytest`
- Formatter: `black`
- Doku: `mkdocs` + `mkdocs-material` + `mkdocstrings[python]`, Theme `readthedocs`, Math via MathJax/arithmatex
- CI/CD: `.github/workflows/ci-cd.yml` — Tests auf jedem Push/PR gegen `main`, Publish auf PyPI via Trusted Publishing (OIDC) bei Tags `v*`
- Release-Skript: `scripts/release.py` (aufrufbar als `poetry run release`), bumpt Version in `pyproject.toml`, `CITATION.cff` und `__init__.py`
- Third-Party-Licenses: `scripts/generate_third_party_licenses.py` (`poetry run licenses`), erzeugt `THIRD_PARTY_NOTICES.md` und `THIRD_PARTY_LICENSES_RAW.txt`

## Projektstruktur

```
src/groundmeas/
├── core/                 # DB-Engine und SQLModel-Datenmodelle
│   ├── db.py             # connect_db, CRUD (create/read/update/delete_*)
│   └── models.py         # Location, Measurement, MeasurementItem + Literal-Typen
├── services/
│   ├── analytics.py      # Impedanz/Frequenz, rho–f-Modell, Distance-Profile,
│   │                     # 62 % (value_at_62_percent, conservative), Soil-Resistivity,
│   │                     # 1–3-Schicht-Inversion (Wenner/Schlumberger)
│   ├── export.py         # JSON/CSV/XML-Export
│   ├── json_import.py    # JSON-Import (Round-Trip zu export-json)
│   ├── omicron_import.py # COMPANO-100-/HGT1-Dateien -> Measurements/Items
│   └── vision_import.py  # OCR-Import aus Bildern (pytesseract + opencv)
├── instruments/
│   └── omicron.py        # CompanoXMLReader, Hgt1TXTReader (reine Reader, keine DB)
├── towers/               # Mastkampagnen (vormals tower-grounding-measurement), dateibasiert
│   ├── cli.py            # typer-Sub-App `gm-cli towers` (run, demo, example-config,
│   │                     # flatten, import-db, install-browser)
│   ├── analysis.py       # GroundingSystemAnalysis, LineModel, U_TP(t_F)
│   ├── campaign.py       # calculate_summary (--calc), Bewertung ZE/UT/MASS
│   ├── config.py         # Kampagnen-config.json, EXPORT_TEMPLATE, EXAMPLE_CONFIG
│   ├── files.py, naming.py, paths.py   # flacher Messordner, Leitung/Mast aus Dateinamen
│   ├── protocol.py, plots.py, results.py, pdf.py, templates/   # HTML/PDF-Protokolle
│   ├── stats.py          # Statistikbericht (deutsch)
│   ├── line_protection.py, i18n.py, demo.py, flatten.py
│   └── database.py       # import_campaign: Kampagne -> groundmeas-DB (towers import-db)
├── visualization/
│   ├── plots.py          # matplotlib
│   ├── vis_plotly.py     # plotly
│   └── map_vis.py        # folium-Karten
├── ui/
│   ├── cli.py            # typer-CLI (Entry-Point: gm-cli)
│   └── dashboard.py      # Streamlit-Dashboard
├── __init__.py           # Re-Exports für flache Public-API (groundmeas.connect_db usw.)
├── analytics.py          # Shim / Re-Export auf services.analytics
├── db.py, export.py, models.py, plots.py, vision_import.py  # Shims für Abwärtskompatibilität
└── cli.py                # Shim

tests/                    # pytest-Suite, eine Datei pro Modul (test_towers_*.py für towers/)
docs/                     # MkDocs-Quellen (index.md, 01..22, towers/, adr/, 99_contributing.md)
notebooks/                # Jupyter-Experimente (im .gitignore, nicht versionieren)
scripts/                  # release, license-checks
```

Public-API wird in `src/groundmeas/__init__.py` kuratiert — beim Hinzufügen öffentlicher Funktionen dort ergänzen und ins `__all__` aufnehmen.

## Entry-Points (aus `pyproject.toml`)

- `gm-cli` → `groundmeas.ui.cli:app` (typer)
- `licenses` → `scripts.generate_third_party_licenses:main`
- `release` → `scripts.release:app`

## Datenmodell (Kurzfassung)

Drei SQLModel-Tabellen, SQLite als Backend:

- **`Location`** — Messort mit `name`, `latitude`, `longitude`, `altitude`.
- **`Measurement`** — Messkampagne / -ereignis mit `timestamp` (UTC), `method`, `asset_type`, optional `voltage_level_kv`, `fault_resistance_ohm`, `operator`, `description`, Relation zu `Location` und `items`.
- **`MeasurementItem`** — Einzelmesspunkt, trägt entweder `value` (+ optional `value_angle_deg`) oder `value_real`/`value_imag`; ein SQLAlchemy-`before_insert`/`before_update`-Listener in `models.py` hält Polar- und Rechteck-Darstellung konsistent. Weitere Felder: `unit`, `frequency_hz`, `measurement_distance_m`, `distance_to_current_injection_m`, `additional_resistance_ohm`, `input_impedance_ohm`.

Zulässige Werte für `measurement_type`, `method`, `asset_type` sind als `Literal[...]` in `core/models.py` definiert — bei Erweiterung dort anpassen **und** die relevanten CLI/Dashboard-Completer mitziehen.

## DB-Pfad-Auflösung

Reihenfolge in CLI/Services:
1. `--db`-Flag (CLI)
2. Umgebungsvariable `GROUNDMEAS_DB`
3. `~/.config/groundmeas/config.json`
4. `./groundmeas.db`

`connect_db(path)` legt die Tabellen per `SQLModel.metadata.create_all` an (idempotent).

## Analytics-Kernfunktionen (`services/analytics.py`)

- `impedance_over_frequency`, `real_imag_over_frequency`
- `rho_f_model` — Fit von `Z(ρ,f) = k1·ρ + (k2+jk3)·f + (k4+jk5)·ρ·f`
- `distance_profile_value`, `value_over_distance[_detailed]` — Reduktionsalgorithmen: `maximum`, `62_percent`, `minimum_gradient`, `minimum_stddev`, `inverse` (1/Z-Extrapolation)
- `soil_resistivity_profile[_detailed]`, `soil_resistivity_curve`
- `layered_earth_forward`, `invert_layered_earth`, `invert_soil_resistivity_layers`, `multilayer_soil_model` — 1–3-Schicht-Inversion für Wenner/Schlumberger
- `calculate_split_factor`, `shield_currents_for_location`, `voltage_vt_epr`
- `value_at_62_percent(..., conservative=True)` = 62-%-Verfahren der Mastauswertung
  (Extrapolation + konservative Korrekturen); `distance_profile_value`,
  `impedance_over_frequency`, `voltage_vt_epr` sind frequenz- und profilfähig

Optionaler Math-Backend-Switch: `GROUNDMEAS_MATH_BACKEND` = `numpy` | `mlx` (MLX wird nur genutzt, wenn installiert; sonst NumPy-Fallback mit Warning). `scipy.special` wird weich importiert.

## Konventionen für Änderungen

- **Sprache in Code, Docstrings und neuer Doku: Englisch** (wie der bestehende Code). Commit-Messages und Chat gerne Deutsch.
- **Docstring-Stil**: NumPy-Format (Parameters/Returns/Raises-Sektionen), wie in `core/models.py` und `services/analytics.py`.
- **Logging**: pro Modul `logger = logging.getLogger(__name__)`, Library-Default ist `NullHandler` (im Paket-`__init__.py`). Keine `print`-Aufrufe in Library-Code.
- **Fehlerbehandlung**: DB-Fehler als `RuntimeError` mit `from e`-Chaining re-raisen, vorher `logger.exception`.
- **Typen**: Vollständige Typannotationen, `Optional`, `Literal`, `Tuple`, `Dict`, `List` werden im Bestand konsistent verwendet.
- **Öffentliche API** nur über `src/groundmeas/__init__.py` erweitern und in `__all__` aufnehmen.
- **Tests**: Jeder neue Service/Plot/CLI-Befehl bekommt einen Test in `tests/test_<modul>.py`. In-Memory-DB (`connect_db(":memory:")`) für Unit-Tests.
- **Commits**: Conventional-Commit-artig — bisherige Präfixe: `feat:`, `chore:`, `fix:`, `refactor:` (siehe `git log`). Keine Claude-Co-Author-Footer ohne explizite Aufforderung.
- **Version bumpen** nur via `poetry run release` (hält `pyproject.toml`, `CITATION.cff` und `__init__.__version__` synchron) und erzeugt einen Tag `vX.Y.Z`, der den Publish-Job triggert.

## Typische Workflow-Kommandos

```bash
# Setup
poetry install

# Tests + Coverage
poetry run pytest
poetry run pytest --cov=groundmeas --cov-report=term-missing

# Formatieren
poetry run black src tests

# CLI lokal
poetry run gm-cli list-measurements

# Dashboard
poetry run streamlit run src/groundmeas/ui/dashboard.py

# Mastkampagne (synthetische Demo)
poetry run gm-cli towers demo /tmp/demo
poetry run gm-cli towers run --config /tmp/demo/config.json --no-pdf
poetry run gm-cli --db /tmp/demo.db towers import-db --config /tmp/demo/config.json

# PDF-Protokolle: Extra + Browser
poetry install --extras pdf && poetry run gm-cli towers install-browser

# Doku lokal bauen
poetry run mkdocs serve

# Release (bumpt Version, committet, taggt)
poetry run release
```

## Gitignore-Besonderheiten

`*.csv`, `*.json`, `*.xml`, `*.db`, `notebooks/`, `dist/`, `site/` sind ignoriert. Export-Beispiele aus Tutorials daher nicht in `git add` ziehen — auch nicht `tmp_test.db`, `dummy.xml`, `notebooks/*`.

Ausnahme: `tests/data/*.xml` (synthetische Instrument-Exporte für die Tests, per `.gitattributes` byte-genau).

## Mastkampagnen (`groundmeas.towers`)

- Dateibasierter Workflow: flacher Messordner + Excel-Arbeitsmappen + `config.json`; die `towers`-Befehle öffnen **keine** Datenbank (Ausnahme `towers import-db`, verbindet sich selbst über `_connect_database`).
- JSON-Ergebnisse behalten die **deutschen Schlüssel** (`ZE_62_Ohm`, `UT_V`, …) — Kompatibilität mit bestehenden Auswertungen. Berührungsspannungen werden bewusst mit `np.ceil` aufgerundet (nicht ändern).
- Ergebnisse sind gegen tower-grounding-measurement 0.2 verifiziert (Demo + realer Mast: JSON/Excel identisch, PDFs pixelgleich bei gleicher matplotlib-Version). Änderungen an `towers/` mit dem Demo-Lauf gegenprüfen.
- Keine echten Messdaten, Netzdaten, Kampagnen-Configs, Logos oder Auftragnehmernamen ins Repo; Tests nutzen nur die synthetische Demo (`towers/demo.py`).
- Playwright ist optional (`[project.optional-dependencies] pdf`); ohne Extra laufen alle Tests, PDF-Tests werden übersprungen.

## Bekannte Altlasten / Hinweise

- In `src/groundmeas/` liegen flache Shim-Dateien (`db.py`, `analytics.py`, `export.py`, `cli.py`, `models.py`, `plots.py`, `vision_import.py`) parallel zur Paketstruktur unter `core/`, `services/`, `ui/`, `visualization/`. Neue Funktionalität gehört in die Subpakete; Shims existieren nur für Abwärtskompatibilität.
- `Python=3.14/` und `Users/` im Repo-Root sind versehentlich eingecheckte Artefakte — nicht bearbeiten.
- `THIRD_PARTY_LICENSES_RAW.txt` wird generiert, nicht von Hand editieren.

## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
