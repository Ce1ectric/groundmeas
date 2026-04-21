# groundmeas — Projektkontext

Python-Paket zur Erfassung, Speicherung, Analyse und Visualisierung von Erdungsmessungen (grounding / earthing). Open Source (MIT), auf PyPI veröffentlicht, Dokumentation via MkDocs auf GitHub Pages.

- Repo: https://github.com/Ce1ectric/groundmeas
- Doku: https://ce1ectric.github.io/groundmeas/
- Aktuelle Version: `1.4.0` (siehe `pyproject.toml`, `CITATION.cff`, `src/groundmeas/__init__.py`)
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
│   │                     # Soil-Resistivity, 1–3-Schicht-Inversion (Wenner/Schlumberger)
│   ├── export.py         # JSON/CSV/XML-Export
│   └── vision_import.py  # OCR-Import aus Bildern (pytesseract + opencv)
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

tests/                    # pytest-Suite, eine Datei pro Modul
docs/                     # MkDocs-Quellen (index.md, 01..22, 99_contributing.md)
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

# Doku lokal bauen
poetry run mkdocs serve

# Release (bumpt Version, committet, taggt)
poetry run release
```

## Gitignore-Besonderheiten

`*.csv`, `*.json`, `*.xml`, `*.db`, `notebooks/`, `dist/`, `site/` sind ignoriert. Export-Beispiele aus Tutorials daher nicht in `git add` ziehen — auch nicht `tmp_test.db`, `dummy.xml`, `notebooks/*`.

## Bekannte Altlasten / Hinweise

- In `src/groundmeas/` liegen flache Shim-Dateien (`db.py`, `analytics.py`, `export.py`, `cli.py`, `models.py`, `plots.py`, `vision_import.py`) parallel zur Paketstruktur unter `core/`, `services/`, `ui/`, `visualization/`. Neue Funktionalität gehört in die Subpakete; Shims existieren nur für Abwärtskompatibilität.
- `Python=3.14/` und `Users/` im Repo-Root sind versehentlich eingecheckte Artefakte — nicht bearbeiten.
- `THIRD_PARTY_LICENSES_RAW.txt` wird generiert, nicht von Hand editieren.
