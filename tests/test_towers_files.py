"""Collecting the measurements of a campaign folder."""

from __future__ import annotations

import logging
import shutil
import unicodedata

import pytest

from groundmeas.towers.files import (
    find_neighbor_touch_voltage_file,
    find_soil_file,
    find_touch_voltage_file,
    read_from_device,
    read_from_omicron,
)


@pytest.fixture
def folder(tmp_path):
    for name in [
        "UT_LX-01_008.txt",
        "UT_LX-01_8-9.txt",
        "ut_lx-01_12a.TXT",
        "ZE_LX-01_8_spez.Erdw..xml",
        "UT_LX-02_8.txt",
        unicodedata.normalize("NFD", "UT_Lö-1_3.txt"),
    ]:
        (tmp_path / name).write_text("x", encoding="utf-8")
    return tmp_path


def test_find_touch_voltage_file(folder):
    assert find_touch_voltage_file(str(folder), "LX-01", "8").endswith(
        "UT_LX-01_008.txt"
    )
    assert (
        find_touch_voltage_file(str(folder), "LX-01", "12A")
        .lower()
        .endswith("ut_lx-01_12a.txt")
    )
    assert find_touch_voltage_file(str(folder), "LX-01", "9") is None
    # a file name stored in NFD (macOS) matches an NFC line identifier
    assert find_touch_voltage_file(str(folder), "Lö-1", "3") is not None


def test_find_neighbour_and_soil_files(folder):
    path, neighbour = find_neighbor_touch_voltage_file(str(folder), "LX-01", "08")
    assert path.endswith("UT_LX-01_8-9.txt") and neighbour == "9"
    assert find_neighbor_touch_voltage_file(str(folder), "LX-02", "8") == (None, None)
    assert find_soil_file(str(folder), "LX-01", "8").endswith("_spez.Erdw..xml")
    assert find_soil_file(str(folder), "LX-01", "9") is None


def test_read_demo_campaign(demo_campaign):
    measurements = demo_campaign.parent / "measurements"
    data = read_from_device(
        str(measurements),
        structure="PREFIX_LINENUMBER_TOWER",
        nominal_frequency=50.0,
        language="en",
    )
    assert [d["Mast"] for d in data] == ["3", "8", "21", "37"]  # numerical order
    tower_8 = data[1]
    assert set(tower_8) >= {
        "Leitung",
        "Mast",
        "ZE_Ohm",
        "UT_V",
        "RA_Ohm",
        "rhoE_profile",
        "neighbor_ut",
    }
    assert tower_8["neighbor_tower"] == "9"
    assert len(tower_8["UT_V"]) == 6


def test_read_uses_the_active_configuration(demo_campaign, use_config):
    use_config(demo_campaign)
    assert len(read_from_device(str(demo_campaign.parent / "measurements"))) == 4


def test_problems_are_logged_and_skipped(demo_campaign, caplog):
    measurements = demo_campaign.parent / "measurements"
    (measurements / "notes.xml").write_text("<x/>", encoding="utf-8")
    (measurements / "ZE_LX-01_99.xml").write_text("broken", encoding="utf-8")
    shutil.copy(measurements / "ZE_LX-01_37.xml", measurements / "ZE_LX-01_38.xml")
    with caplog.at_level(logging.INFO, logger="groundmeas"):
        data = read_from_device(
            str(measurements),
            structure="PREFIX_LINENUMBER_TOWER",
            nominal_frequency=50.0,
            language="en",
        )
    messages = caplog.text
    assert "unrecognised name: notes.xml" in messages
    assert "ZE_LX-01_99.xml" in messages and "could not be read" in messages
    assert "No HGT1 report for ZE_LX-01_38.xml" in messages
    assert "_spez" not in messages  # soil exports are expected, not reported
    tower_38 = next(d for d in data if d["Mast"] == "38")
    assert tower_38["UT_V"] is None


def test_unsupported_device(tmp_path):
    with pytest.raises(ValueError, match="Unsupported device"):
        read_from_device(
            str(tmp_path),
            device="OTHER",
            structure="PREFIX_LINENUMBER_TOWER",
            nominal_frequency=50,
            language="en",
        )


def test_read_from_omicron_with_broken_hgt1(compano_xml, tmp_path):
    broken = tmp_path / "UT_X_1.txt"
    broken.write_text("nothing useful", encoding="utf-8")
    impedance, residual, touch = read_from_omicron(str(compano_xml), str(broken))
    assert impedance is not None and residual is not None and touch is None
    assert read_from_omicron(str(broken)) == (None, None, None)
