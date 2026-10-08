"""Importing tower campaigns into the database (``gm-cli towers import-db``)."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

import groundmeas as gm
from groundmeas.towers.config import read_config
from groundmeas.towers.database import (
    ASSET_TYPE,
    find_tower_files,
    import_campaign,
    location_name,
)
from groundmeas.ui import cli as main_cli

runner = CliRunner(mix_stderr=False)


@pytest.fixture
def db():
    gm.connect_db(":memory:")
    yield
    gm.disconnect_db()


def _measurements():
    records, _ = gm.read_measurements_by(asset_type=ASSET_TYPE)
    return records


def _by_location(records):
    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["location"]["name"], []).append(record)
    return grouped


def _starting(records, head):
    return next(r for r in records if r["description"].startswith(head))


# ----------------------------------------------------------------- files
def test_location_name_normalises_the_tower():
    assert location_name("LX-01", "008n") == "LX-01 tower 8N"
    assert location_name(" LX-01 ", 12.0) == "LX-01 tower 12"


def test_find_tower_files(demo_campaign):
    config = read_config(demo_campaign)
    towers = find_tower_files(config["directory_path"])
    assert [t.tower for t in towers] == ["3", "8", "21", "37"]  # numeric order
    tower8 = towers[1]
    assert tower8.fall_of_potential.name == "ZE_LX-01_8.xml"
    assert tower8.touch_voltage.name == "UT_LX-01_8.txt"
    assert [(p.name, n) for p, n in tower8.neighbour_reports] == [
        ("UT_LX-01_8-9.txt", "9")
    ]
    assert [p.name for p in tower8.soil] == ["ZE_LX-01_8_spez.Erdw..xml"]
    assert tower8.location_name == "LX-01 tower 8"
    assert towers[0].soil == () and towers[0].neighbour_reports == ()


def test_dry_run_needs_no_database(demo_campaign):
    records = import_campaign(demo_campaign, dry_run=True)
    assert len(records) == 10
    assert {r["status"] for r in records} == {"planned"}
    assert Counter(r["test"] for r in records) == {
        "fall_of_potential": 4,
        "touch_voltage": 4,
        "transferred_potential": 1,
        "soil": 1,
    }


# ---------------------------------------------------------------- import
def test_import_campaign(db, demo_campaign):
    records = import_campaign(
        demo_campaign, voltage_level_kv=110, timezone="Europe/Berlin"
    )
    assert [r["status"] for r in records] == ["imported"] * 10
    measurements = _measurements()
    assert len(measurements) == 10
    towers = _by_location(measurements)
    assert sorted(towers) == [
        "LX-01 tower 21",
        "LX-01 tower 3",
        "LX-01 tower 37",
        "LX-01 tower 8",
    ]
    assert len(towers["LX-01 tower 8"]) == 4
    description = pd.read_excel(
        read_config(demo_campaign)["measurement_description_path"]
    )
    row = description[description["Mast"].astype(str) == "8"].iloc[0]
    fop = _starting(towers["LX-01 tower 8"], "Fall-of-potential test")
    assert fop["method"] == "injection_earth_electrode"
    assert fop["voltage_level_kv"] == 110
    assert fop["operator"] == f"{row['Vorname']} {row['Name']}, {row['Firma']}"
    assert "(ZE_LX-01_8.xml)" in fop["description"]
    assert f"current electrode {row['Entfernung_Hilfserder_m']:g} m" in (
        fop["description"]
    )
    profile = [
        item
        for item in fop["items"]
        if item["measurement_type"] == "earthing_impedance"
    ]
    assert {item["distance_to_current_injection_m"] for item in profile} == {
        float(row["Entfernung_Hilfserder_m"])
    }
    assert {item["frequency_hz"] for item in profile} >= {50.0}
    soil = _starting(towers["LX-01 tower 8"], "Soil resistivity")
    assert soil["method"] in ("wenner", "schlumberger")
    neighbour = _starting(towers["LX-01 tower 8"], "Transferred potential at tower 9")
    assert {i["measurement_type"] for i in neighbour["items"]} == {
        "transferred_potential",
        "earthing_current",
    }


def test_repeated_import_skips_known_files(db, demo_campaign):
    import_campaign(demo_campaign)
    again = import_campaign(demo_campaign)
    assert {r["status"] for r in again} == {"skipped"}
    assert len(_measurements()) == 10
    forced = import_campaign(demo_campaign, skip_existing=False)
    assert {r["status"] for r in forced} == {"imported"}
    assert len(_measurements()) == 20


def test_without_test_frequencies(db, demo_campaign):
    import_campaign(demo_campaign, per_frequency=False)
    for record in _measurements():
        frequencies = {item.get("frequency_hz") for item in record["items"]}
        assert frequencies <= {50.0, None}


def test_coordinates_from_the_description(db, demo_campaign):
    path = Path(read_config(demo_campaign)["measurement_description_path"])
    description = pd.read_excel(path)
    description["Breitengrad"] = 52.0 + description.index * 0.01
    description["Längengrad"] = 10.0
    description.to_excel(path, index=False)
    import_campaign(demo_campaign)
    locations = {
        r["location"]["name"]: (r["location"]["latitude"], r["location"]["longitude"])
        for r in _measurements()
    }
    assert all(lat is not None and lon == 10.0 for lat, lon in locations.values())


def test_broken_file_is_reported_and_retried(db, demo_campaign):
    folder = Path(read_config(demo_campaign)["directory_path"])
    original = (folder / "ZE_LX-01_37.xml").read_bytes()
    (folder / "ZE_LX-01_37.xml").write_text("<x/>", encoding="utf-8")
    records = import_campaign(demo_campaign)
    failed = [r for r in records if r["status"] == "failed"]
    # the profile and the touch voltages (reference current) need the export
    assert [(r["tower"], r["test"]) for r in failed] == [
        ("37", "fall_of_potential"),
        ("37", "touch_voltage"),
    ]
    assert all("MeasurementFileError" in r["message"] for r in failed)
    assert sum(r["status"] == "imported" for r in records) == 8
    (folder / "ZE_LX-01_37.xml").write_bytes(original)
    again = import_campaign(demo_campaign)
    assert [r["status"] for r in again if r["tower"] == "37"] == ["imported"] * 2
    assert len(_measurements()) == 10


def test_tower_without_description_row_is_not_imported(db, demo_campaign):
    folder = Path(read_config(demo_campaign)["directory_path"])
    for name in ("ZE_LX-01_8.xml", "UT_LX-01_8.txt"):
        (folder / name.replace("_8.", "_99.")).write_bytes((folder / name).read_bytes())
    records = import_campaign(demo_campaign)
    tower99 = [r for r in records if r["tower"] == "99"]
    assert [r["status"] for r in tower99] == ["failed", "failed"]
    assert all("no row in the measurement description" in r["message"] for r in tower99)
    assert "LX-01 tower 99" not in {m["location"]["name"] for m in _measurements()}


def test_missing_current_electrode_distance(db, demo_campaign):
    path = Path(read_config(demo_campaign)["measurement_description_path"])
    original = pd.read_excel(path)
    description = original.copy()
    description["Entfernung_Hilfserder_m"] = np.nan
    description.to_excel(path, index=False)
    planned = import_campaign(demo_campaign, dry_run=True)
    profiles = [r for r in planned if r["test"] == "fall_of_potential"]
    assert {r["status"] for r in profiles} == {"failed"}
    assert all("no current-electrode distance" in r["message"] for r in profiles)
    records = import_campaign(demo_campaign)
    assert sum(r["status"] == "imported" for r in records) == 6  # not the profiles
    # after fixing the description the profiles are imported
    original.to_excel(path, index=False)
    again = import_campaign(demo_campaign)
    assert [r["test"] for r in again if r["status"] == "imported"] == [
        "fall_of_potential"
    ] * 4
    assert {r["status"] for r in again if r["test"] != "fall_of_potential"} == {
        "skipped"
    }


@pytest.mark.parametrize("broken", ["missing column", "title row", "not a workbook"])
def test_unusable_description_stops_the_import(db, demo_campaign, broken):
    path = Path(read_config(demo_campaign)["measurement_description_path"])
    description = pd.read_excel(path)
    if broken == "missing column":
        description.drop(columns="Entfernung_Hilfserder_m").to_excel(path, index=False)
    elif broken == "title row":
        with pd.ExcelWriter(path) as writer:
            description.to_excel(writer, index=False, startrow=1)
    else:
        path.write_text("not a workbook", encoding="utf-8")
    with pytest.raises(ValueError, match="measurement description"):
        import_campaign(demo_campaign)
    assert _measurements() == []


def test_all_neighbour_reports_and_soil_exports(db, demo_campaign):
    folder = Path(read_config(demo_campaign)["directory_path"])
    (folder / "UT_LX-01_8-7.txt").write_bytes(
        (folder / "UT_LX-01_8-9.txt").read_bytes()
    )
    (folder / "ZE_LX-01_8_spez_2.xml").write_bytes(
        (folder / "ZE_LX-01_8_spez.Erdw..xml").read_bytes()
    )
    records = import_campaign(demo_campaign)
    tower8 = [(r["test"], r["file"]) for r in records if r["tower"] == "8"]
    assert ("transferred_potential", "UT_LX-01_8-7.txt") in tower8
    assert ("transferred_potential", "UT_LX-01_8-9.txt") in tower8
    assert [f for t, f in tower8 if t == "soil"] == [
        "ZE_LX-01_8_spez.Erdw..xml",
        "ZE_LX-01_8_spez_2.xml",
    ]
    descriptions = [
        m["description"]
        for m in _measurements()
        if m["location"]["name"] == "LX-01 tower 8"
    ]
    assert any(d.startswith("Transferred potential at tower 7") for d in descriptions)
    assert len(descriptions) == 6


def test_two_exports_of_one_tower(db, demo_campaign, caplog):
    folder = Path(read_config(demo_campaign)["directory_path"])
    (folder / "ZE_LX-01_008.xml").write_bytes((folder / "ZE_LX-01_8.xml").read_bytes())
    with caplog.at_level("WARNING", logger="groundmeas"):
        records = import_campaign(demo_campaign)
    assert "Several fall-of-potential exports for LX-01 tower 8" in caplog.text
    tower8 = [r for r in records if r["tower"] in ("8", "008")]
    imported = [r["file"] for r in tower8 if r["status"] == "imported"]
    assert sorted(imported) == sorted(
        [
            "ZE_LX-01_008.xml",
            "ZE_LX-01_8.xml",
            "UT_LX-01_8.txt",
            "UT_LX-01_8-9.txt",
            "ZE_LX-01_8_spez.Erdw..xml",
        ]
    )
    statuses: dict[str, list[str]] = {}
    for r in tower8:
        statuses.setdefault(r["file"], []).append(r["status"])
    # both exports list the same further files; they are imported once
    assert statuses["UT_LX-01_8.txt"] == ["imported", "skipped"]
    assert statuses["ZE_LX-01_8_spez.Erdw..xml"] == ["imported", "skipped"]


def test_failed_import_leaves_nothing_behind(db, demo_campaign, monkeypatch):
    import groundmeas.towers.database as database

    real = database.import_step_touch

    def flaky(path, **kwargs):
        if Path(path).name == "UT_LX-01_3.txt":
            raise RuntimeError("database is locked")
        return real(path, **kwargs)

    monkeypatch.setattr(database, "import_step_touch", flaky)
    records = import_campaign(demo_campaign)
    assert [r["file"] for r in records if r["status"] == "failed"] == ["UT_LX-01_3.txt"]
    monkeypatch.setattr(database, "import_step_touch", real)
    again = import_campaign(demo_campaign)
    assert [r["file"] for r in again if r["status"] == "imported"] == ["UT_LX-01_3.txt"]
    assert len(_measurements()) == 10


def test_database_reproduces_the_tower_evaluation(db, evaluated_demo):
    """Two methods: groundmeas analytics on the imported data vs. the calc step."""
    import_campaign(evaluated_demo)
    towers = _by_location(_measurements())
    root = evaluated_demo.parent
    grid = pd.read_excel(root / "grid_data.xlsx")
    results = sorted((root / "results").glob("LX-01_*.json"))
    assert len(results) == 4
    for path in results:
        result = json.loads(path.read_text(encoding="utf-8"))
        records = towers[location_name(result["Leitung"], result["Mast"])]
        fop = _starting(records, "Fall-of-potential test")
        z62 = gm.distance_profile_value(
            fop["id"],
            algorithm="62_percent",
            conservative=True,
            frequency_hz=50.0,
        )
        assert round(z62["result_value"], 3) == result["ZE_62_Ohm"]

        grid_row = grid[grid["Mast"].astype(str) == str(result["Mast"])].iloc[0]
        earth_current = grid_row["Fehlerstrom"] * grid_row["Reduktionsfaktor"]
        touch = _starting(records, "Touch voltages")
        items = [i for i in touch["items"] if i["frequency_hz"] == 50.0]
        reference = next(
            i["value"] for i in items if i["measurement_type"] == "earthing_current"
        )
        scaled = [
            int(np.ceil(i["value"] * earth_current / reference))
            for i in items
            if i["measurement_type"] == "touch_voltage"
        ]
        assert scaled == result["UT_V"]


# ------------------------------------------------------------------- CLI
def run(*args: str):
    return runner.invoke(main_cli.app, list(args))


def test_cli_import_db(tmp_path, demo_campaign):
    db_path = tmp_path / "towers.db"
    args = ["--db", str(db_path), "towers", "import-db", "--config", str(demo_campaign)]
    result = run(*args, "--voltage-level-kv", "110", "-q")
    assert result.exit_code == 0, result.output
    assert "LX-01 tower 8" in result.stdout
    assert "10 measurements imported, 0 skipped, 0 failed (4 towers)" in result.stdout
    gm.disconnect_db()
    result = run(*args, "-q")
    assert result.exit_code == 0, result.output
    assert "0 measurements imported, 10 skipped" in result.stdout
    gm.disconnect_db()
    gm.connect_db(str(db_path))
    assert len(_measurements()) == 10


def test_cli_dry_run_does_not_create_a_database(tmp_path, demo_campaign):
    db_path = tmp_path / "towers.db"
    result = run(
        "--db",
        str(db_path),
        "towers",
        "import-db",
        "--config",
        str(demo_campaign),
        "--dry-run",
    )
    assert result.exit_code == 0, result.output
    assert "10 files of 4 towers to import, 0 cannot be imported (dry run)" in (
        result.stdout
    )
    assert not db_path.exists()


def test_cli_reports_failures(tmp_path, demo_campaign):
    folder = Path(read_config(demo_campaign)["directory_path"])
    (folder / "ZE_LX-01_99.xml").write_text("<x/>", encoding="utf-8")
    args = ["--db", str(tmp_path / "t.db"), "towers", "import-db"]
    args += ["--config", str(demo_campaign), "-q"]
    result = run(*args, "--dry-run")
    assert result.exit_code == 1
    assert "10 files of 5 towers to import, 1 cannot be imported" in result.stdout
    result = run(*args)
    assert result.exit_code == 1
    assert "FAILED: no row in the measurement description" in result.stdout
    assert "10 measurements imported, 0 skipped, 1 failed (5 towers)" in result.stdout


def test_cli_unusable_description(tmp_path, demo_campaign):
    path = Path(read_config(demo_campaign)["measurement_description_path"])
    path.write_text("not a workbook", encoding="utf-8")
    result = run(
        "--db",
        str(tmp_path / "t.db"),
        "towers",
        "import-db",
        "--config",
        str(demo_campaign),
    )
    assert result.exit_code == 1
    assert "could not be read" in result.stderr


@pytest.mark.parametrize(
    "extra",
    [["--timezone", "Mars/Olympus"], ["-v", "-q"]],
)
def test_cli_invalid_options(tmp_path, demo_campaign, extra):
    result = run(
        "--db",
        str(tmp_path / "t.db"),
        "towers",
        "import-db",
        "--config",
        str(demo_campaign),
        *extra,
    )
    assert result.exit_code == 2
    assert not (tmp_path / "t.db").exists()


def test_cli_missing_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("--db", str(tmp_path / "t.db"), "towers", "import-db")
    assert result.exit_code == 2
    assert "configuration file not found" in result.stderr
