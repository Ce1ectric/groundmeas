"""Flattening nested measurement deliveries (``gm-cli towers flatten``)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from typer.testing import CliRunner

from groundmeas.towers.flatten import apply_flatten, plan_flatten
from groundmeas.ui import cli as main_cli

runner = CliRunner(mix_stderr=False)
HGT1 = "StepTouch Reporting:\t\tStepTouch\\X_ST_000_Report.txt\r\n"


def run(*args: str):
    return runner.invoke(main_cli.app, ["towers", "flatten", *args])


@pytest.fixture
def delivery(tmp_path):
    root = tmp_path / "delivery"
    files = {
        "LH-01-0815/Mast 015/ZE_LH-01-0815_15.xml": "<x/>",
        "LH-01-0815/Mast 015/UT_LH_01-0815_15.txt": HGT1,  # typo in the file name
        "LH-01-0815/Mast 015/Map_LH-01-0815_15.png": "png",
        "LH-01-0815/Mast 015/photo.jpg": "jpg",
        "LH-01-0815/Mast 16N - zugewachsen/ZE_x.txt": HGT1,  # HGT1 named ZE_*.txt
        "LH-01-0815/Mast 16N - zugewachsen/ZE_x spez. Erd.xml": "<x/>",
        "LH-01-0815/Mast 16N - zugewachsen/UT_LH-01-0815_16N-17.txt": HGT1,
        "LH-01-0815/Mast 16N - zugewachsen/UT_notes.txt": "plain notes",
    }
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


EXPECTED = [
    "Map_01-0815_15.png",
    "UT_LH-01-0815_15.txt",
    "UT_LH-01-0815_16N-17.txt",
    "UT_LH-01-0815_16N.txt",
    "ZE_LH-01-0815_15.xml",
    "ZE_LH-01-0815_16N_spez.Erdw..xml",
]


def test_plan_maps_folders_to_canonical_names(delivery):
    rows = plan_flatten(delivery)
    targets = {Path(row["src"]).name: row for row in rows}
    assert sorted(row["dst"] for row in rows if row["dst"]) == EXPECTED
    assert targets["UT_LH_01-0815_15.txt"]["renamed"] == "yes"
    assert targets["ZE_LH-01-0815_15.xml"]["renamed"] == "no"
    assert targets["ZE_x.txt"]["reason"] == "HGT1 report was named ZE_*.txt"
    assert targets["UT_notes.txt"]["dst"] == ""
    assert "photo.jpg" not in targets  # photos are not copied


def test_plan_restricted_to_one_tower(delivery):
    rows = plan_flatten(delivery, only=["Mast 015"])
    assert {Path(row["src"]).parent.name for row in rows} == {"Mast 015"}


def test_plan_keeps_line_in_map_names(delivery):
    rows = plan_flatten(delivery, map_strip="")
    assert "Map_LH-01-0815_15.png" in [row["dst"] for row in rows]


def test_apply_refuses_conflicts(delivery, tmp_path):
    duplicate = delivery / "LH-01-0815" / "Mast 15" / "ZE_other.xml"
    duplicate.parent.mkdir()
    duplicate.write_text("<x/>", encoding="utf-8")
    rows = plan_flatten(delivery)
    conflicts = [row for row in rows if "CONFLICT" in row["reason"]]
    assert len(conflicts) == 1
    # folders are walked in sorted order: "Mast 015" comes first
    assert Path(conflicts[0]["src"]).parent.name == "Mast 15"
    assert "CONFLICT with LH-01-0815/Mast 015/ZE_LH-01-0815_15.xml" in (
        conflicts[0]["reason"]
    )
    with pytest.raises(ValueError, match="conflicts"):
        apply_flatten(rows, delivery, tmp_path / "flat")
    assert not (tmp_path / "flat").exists()


def test_report_is_appended(delivery, tmp_path):
    report = tmp_path / "mapping.csv"
    rows = plan_flatten(delivery)
    assert apply_flatten(rows, delivery, tmp_path / "a", report=report) == 6
    assert apply_flatten(rows, delivery, tmp_path / "b", report=report) == 6
    with open(report, encoding="utf-8", newline="") as handle:
        lines = list(csv.reader(handle, delimiter=";"))
    assert lines.count(["source", "target", "renamed", "note"]) == 1
    assert len(lines) == 1 + 2 * len(rows)


def test_dry_run_plans_but_does_not_copy(delivery, tmp_path):
    dest = tmp_path / "flat"
    result = run(str(delivery), str(dest))
    assert result.exit_code == 0, result.output
    assert not dest.exists()
    assert "6 files, 4 renamed, 0 conflicts" in result.stdout
    assert "Dry run" in result.stdout


def test_apply_copies_with_normalised_names(delivery, tmp_path):
    dest, report = tmp_path / "flat", tmp_path / "mapping.csv"
    result = run(str(delivery), str(dest), "--apply", "--report", str(report))
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in dest.iterdir()) == EXPECTED
    with open(report, encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter=";"))
    assert rows[0] == ["source", "target", "renamed", "note"]
    assert any("not an HGT1 report" in row[3] for row in rows[1:])
    # the originals stay untouched
    assert (delivery / "LH-01-0815" / "Mast 015" / "UT_LH_01-0815_15.txt").exists()


def test_conflicts_abort(delivery, tmp_path):
    duplicate = delivery / "LH-01-0815" / "Mast 15" / "ZE_other.xml"
    duplicate.parent.mkdir()
    duplicate.write_text("<x/>", encoding="utf-8")
    result = run(str(delivery), str(tmp_path / "flat"), "--apply")
    assert result.exit_code == 1
    assert "name conflicts" in result.stderr
    assert not (tmp_path / "flat").exists()


def test_custom_patterns(tmp_path):
    root = tmp_path / "delivery"
    (root / "L123" / "Tower 7").mkdir(parents=True)
    (root / "L123" / "Tower 7" / "ZE_whatever.xml").write_text("<x/>", encoding="utf-8")
    dest = tmp_path / "flat"
    result = run(
        str(root),
        str(dest),
        "--apply",
        "--line-pattern",
        r"(L\d{3})",
        "--tower-pattern",
        r"^Tower\s+(\S+)",
    )
    assert result.exit_code == 0, result.output
    assert [p.name for p in dest.iterdir()] == ["ZE_L123_7.xml"]


def test_only_is_repeatable(delivery, tmp_path):
    dest = tmp_path / "flat"
    result = run(
        str(delivery),
        str(dest),
        "--apply",
        "--only",
        "Mast 015",
        "--only",
        "LH-01-0815/Mast 16N - zugewachsen",
    )
    assert result.exit_code == 0, result.output
    assert sorted(p.name for p in dest.iterdir()) == EXPECTED


@pytest.mark.parametrize(
    ("option", "pattern", "message"),
    [
        ("--line-pattern", "(LH", "not a valid regular expression"),
        ("--tower-pattern", r"^Mast\s+\S+", "needs one capture group"),
    ],
)
def test_invalid_patterns(delivery, tmp_path, option, pattern, message):
    result = run(str(delivery), str(tmp_path / "flat"), option, pattern)
    assert result.exit_code == 2
    assert message in result.stderr


def test_missing_source_folder(tmp_path):
    result = run(str(tmp_path / "missing"), str(tmp_path / "flat"))
    assert result.exit_code == 2


def test_flatten_does_not_create_a_database(delivery, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GROUNDMEAS_DB", raising=False)
    monkeypatch.setattr(main_cli, "CONFIG_PATH", tmp_path / "no_config.json")
    assert run(str(delivery), str(tmp_path / "flat")).exit_code == 0
    assert not (tmp_path / "groundmeas.db").exists()
