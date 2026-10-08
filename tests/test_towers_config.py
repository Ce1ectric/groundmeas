"""Reading and validating campaign configurations."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from groundmeas.towers.config import (
    CONFIG_ENV_VAR,
    EXAMPLE_CONFIG,
    LEGACY_CONFIG_ENV_VAR,
    ConfigError,
    read_config,
    read_export_json,
    resolve_config_path,
    write_example_config,
)


def test_demo_config_is_valid(demo_campaign):
    config = read_config(demo_campaign)
    root = demo_campaign.parent
    assert Path(config["directory_path"]) == root / "measurements"
    assert Path(config["json_export_path"]) == root / "results"
    assert Path(config["export_path"]) == root / "results" / "summary.xlsx"
    assert config["language"] == "en"
    assert config["logo_path"] == ""
    assert config["nominal_frequency_Hz"] == 50.0
    assert config["default_fault_current"] == 12000.0
    assert config["line_protection_enabled"] is True
    assert config["config_dir"] == str(root)


def test_relative_paths_do_not_depend_on_the_working_directory(
    demo_campaign, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config = read_config(demo_campaign)
    assert Path(config["grid_data_path"]).is_file()


def test_config_with_byte_order_mark(demo_campaign):
    text = demo_campaign.read_text(encoding="utf-8")
    demo_campaign.write_bytes("﻿".encode() + text.encode("utf-8"))
    assert read_config(demo_campaign)["language"] == "en"


def test_resolution_order(tmp_path, monkeypatch):
    explicit = tmp_path / "explicit.json"
    monkeypatch.setenv(CONFIG_ENV_VAR, str(tmp_path / "from_env.json"))
    assert resolve_config_path(explicit) == str(explicit)
    assert resolve_config_path() == str(tmp_path / "from_env.json")
    monkeypatch.delenv(CONFIG_ENV_VAR)
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path() == os.path.abspath("config.json")


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="Configuration file not found"):
        read_config(tmp_path / "missing.json")


def test_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        read_config(path)


def test_optional_keys_have_defaults(demo_campaign, edit_config, DELETE):
    edit_config(
        demo_campaign,
        language=DELETE,
        logo=DELETE,
        nominal_frequency_Hz=DELETE,
        default_grid_data=DELETE,
        line_protection=DELETE,
        contacts=DELETE,
        touch_voltage_evaluation=DELETE,
        directory__path_summary=DELETE,
        directory__export_path_pdf=DELETE,
        directory__sc_current_data_path=DELETE,
        touch_voltages__U_TP_ext_V=DELETE,
    )
    config = read_config(demo_campaign)
    results = demo_campaign.parent / "results"
    assert config["language"] == "en"
    assert config["default_t"] == 0.4 and config["default_r"] == 1.0
    assert config["default_fault_current"] == 12000.0
    assert config["line_protection_enabled"] is False
    assert config["touch_voltage_evaluation"] == "with_resistor"
    assert Path(config["export_path"]) == results / "summary.xlsx"
    assert Path(config["export_path_pdf"]) == results / "protocols.zip"
    assert config["sc_current_data_path"] == ""
    assert config["U_TP_ext_V"] == config["U_TP_V"]


def test_output_folder_does_not_need_to_exist(demo_campaign, edit_config):
    edit_config(demo_campaign, directory__json_export_path="new/output/folder")
    assert read_config(demo_campaign)["json_export_path"].endswith(
        os.path.join("new", "output", "folder")
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"touch_voltages__U_TP_V": [10, 20]}, "does not match the length of U_TP_V"),
        (
            {"touch_voltages__U_TP_ext_V": [1, 2]},
            "does not match the length of U_TP_ext_V",
        ),
        ({"touch_voltages__t_s": []}, "non-empty list"),
        ({"touch_voltages__t_s": [0.1, "x"]}, "must be a number"),
        ({"default_grid_data__r": "0.66"}, "default_grid_data.r must be a number"),
        ({"default_grid_data__tripping_time": True}, "tripping_time must be a number"),
        (
            {"directory__path_measurements": "missing"},
            "path_measurements: directory does not exist",
        ),
        (
            {"directory__path_grid_data": "missing.xlsx"},
            "path_grid_data: file does not exist",
        ),
        (
            {"directory__measurement_description_path": ""},
            "measurement_description_path is not set",
        ),
        ({"directory__json_export_path": ""}, "json_export_path is not set"),
        (
            {"directory__grounding_impedance_structure": "X"},
            "grounding_impedance_structure",
        ),
        ({"touch_voltage_evaluation": "sometimes"}, "touch_voltage_evaluation"),
        ({"language": "xx"}, "Unsupported language"),
        ({"logo": "missing.png"}, "logo: file does not exist"),
        ({"nominal_frequency_Hz": 0}, "must be positive"),
    ],
)
def test_invalid_values(demo_campaign, edit_config, changes, message):
    edit_config(demo_campaign, **changes)
    with pytest.raises(ConfigError, match=message):
        read_config(demo_campaign)


def test_missing_sections(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"directory": {}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="touch_voltages"):
        read_config(path)
    path.write_text(
        json.dumps({"touch_voltages": {"t_s": [1], "U_TP_V": [1]}}), encoding="utf-8"
    )
    with pytest.raises(ConfigError, match="directory"):
        read_config(path)


def test_config_error_is_a_value_error():
    assert issubclass(ConfigError, ValueError)


def test_example_config_is_complete(tmp_path):
    path = write_example_config(tmp_path / "config.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == EXAMPLE_CONFIG
    assert {"touch_voltages", "directory", "contacts", "default_grid_data"} <= set(data)
    assert data["language"] == "en"
    with pytest.raises(FileExistsError):
        write_example_config(path)


def test_example_config_works_with_demo_data(tmp_path, demo_campaign):
    """The example becomes a valid configuration once the paths exist."""
    target = demo_campaign.parent / "example.json"
    write_example_config(target)
    data = json.loads(target.read_text(encoding="utf-8"))
    data["directory"]["path_grid_data"] = "grid_data.xlsx"
    target.write_text(json.dumps(data), encoding="utf-8")
    config = read_config(target)
    assert config["touch_voltage_evaluation"] == "with_resistor"


def test_legacy_environment_variable(demo_campaign, monkeypatch):
    monkeypatch.setenv(LEGACY_CONFIG_ENV_VAR, str(demo_campaign))
    assert resolve_config_path() == os.path.abspath(demo_campaign)
    monkeypatch.setenv(CONFIG_ENV_VAR, "/elsewhere/config.json")
    assert resolve_config_path() == os.path.abspath("/elsewhere/config.json")


def test_export_template_contains_all_keys():
    template = read_export_json()
    for key in (
        "Leitung",
        "Mast",
        "ZE_62_Ohm",
        "UT_V",
        "Messpunkte_UT_Termination",
        "Bewertung_Kategorie",
    ):
        assert key in template
    template["Leitung"] = "changed"
    assert read_export_json()["Leitung"] == ""  # a fresh copy every time


def test_export_template_errors(tmp_path):
    with pytest.raises(FileNotFoundError, match="No json file in the given path"):
        read_export_json(tmp_path / "missing.json")
    broken = tmp_path / "broken.json"
    broken.write_text("[1, 2", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON"):
        read_export_json(broken)
    array = tmp_path / "array.json"
    array.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        read_export_json(array)
