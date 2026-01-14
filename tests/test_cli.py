import json
import subprocess
from pathlib import Path

import pytest
import typer

from groundmeas.ui import cli


def _seq(values):
    iterator = iter(values)
    return lambda *args, **kwargs: next(iterator)


def test_resolve_db_uses_arg(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "cfg.json")
    assert cli._resolve_db("x.db") == "x.db"


def test_resolve_db_uses_config(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text(json.dumps({"db_path": "cfg.db"}))
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg)
    assert cli._resolve_db(None) == "cfg.db"


def test_resolve_db_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "CONFIG_PATH", tmp_path / "cfg.json")
    resolved = cli._resolve_db(None)
    assert resolved.endswith("groundmeas.db")


def test_save_default_db(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg)
    cli._save_default_db("x.db")
    assert json.loads(cfg.read_text())["db_path"] == "x.db"


def test_existing_helpers(monkeypatch):
    monkeypatch.setattr(
        cli,
        "read_measurements_by",
        lambda **kwargs: (
            [
                {"location": {"name": "A"}, "operator": "Op1", "voltage_level_kv": 10},
                {"location": {"name": "B"}, "operator": "Op2", "voltage_level_kv": 20},
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        cli,
        "read_items_by",
        lambda **kwargs: (
            [
                {"unit": "ohm", "frequency_hz": 50},
                {"unit": "A", "frequency_hz": 60},
            ],
            None,
        ),
    )
    assert cli._existing_locations() == ["A", "B"]
    assert cli._existing_measurement_values("operator") == ["Op1", "Op2"]
    assert cli._existing_item_units("earthing_impedance") == ["A", "ohm"]
    assert cli._existing_item_values("frequency_hz") == ["50", "60"]


def test_existing_helpers_error(monkeypatch):
    monkeypatch.setattr(cli, "read_measurements_by", lambda **kwargs: (_ for _ in ()).throw(Exception("fail")))
    monkeypatch.setattr(cli, "read_items_by", lambda **kwargs: (_ for _ in ()).throw(Exception("fail")))
    assert cli._existing_locations() == []
    assert cli._existing_measurement_values("operator") == []
    assert cli._existing_item_units("earthing_impedance") == []
    assert cli._existing_item_values("frequency_hz") == []


def test_resolve_db_invalid_json(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{bad")
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg)
    assert cli._resolve_db(None).endswith("groundmeas.db")


def test_prompt_text_default(monkeypatch):
    monkeypatch.setattr(cli, "prompt", lambda *args, **kwargs: "")
    assert cli._prompt_text("Name", default="x") == "x"


def test_prompt_float_invalid_then_default(monkeypatch):
    monkeypatch.setattr(cli, "_prompt_text", _seq(["bad", ""]))
    assert cli._prompt_float("Value", default=3.5) == 3.5


def test_prompt_float_empty_returns_none(monkeypatch):
    monkeypatch.setattr(cli, "_prompt_text", _seq([""]))
    assert cli._prompt_float("Value", default=None) is None


def test_prompt_choice_default(monkeypatch):
    monkeypatch.setattr(cli, "prompt", lambda *args, **kwargs: "")
    assert cli._prompt_choice("Mode", choices=["a", "b"], default="b") == "b"


def test_prompt_choice_invalid_then_valid(monkeypatch):
    monkeypatch.setattr(cli, "prompt", _seq(["x", "a"]))
    assert cli._prompt_choice("Mode", choices=["a", "b"]) == "a"


def test_load_measurement_not_found(monkeypatch):
    monkeypatch.setattr(cli, "read_measurements_by", lambda **kwargs: ([], None))
    with pytest.raises(typer.Exit):
        cli._load_measurement(1)


def test_load_measurement_success(monkeypatch):
    monkeypatch.setattr(cli, "read_measurements_by", lambda **kwargs: ([{"id": 1}], None))
    assert cli._load_measurement(1)["id"] == 1


def test_load_item_not_found(monkeypatch):
    monkeypatch.setattr(cli, "read_items_by", lambda **kwargs: ([], None))
    with pytest.raises(typer.Exit):
        cli._load_item(1)


def test_load_item_success(monkeypatch):
    monkeypatch.setattr(cli, "read_items_by", lambda **kwargs: ([{"id": 1}], None))
    assert cli._load_item(1)["id"] == 1


def test_dump_or_print_json(tmp_path):
    out = tmp_path / "out.json"
    cli._dump_or_print({"a": 1}, out)
    assert json.loads(out.read_text()) == {"a": 1}


def test_dump_or_print_stdout(capsys):
    cli._dump_or_print({"a": 1}, None)
    assert '"a": 1' in capsys.readouterr().out


def test_print_measurement_summary(capsys):
    cli._print_measurement_summary(
        1,
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Site"},
            "description": "note",
            "operator": "op",
        },
        [{"id": 1, "measurement_type": "earthing_impedance", "value": 1.0, "unit": "ohm"}],
    )
    out = capsys.readouterr().out
    assert "Measurement id=1" in out
    assert "Items (1):" in out


def test_connect_callback(tmp_path, monkeypatch, capsys):
    db_path = tmp_path / "db.sqlite"
    monkeypatch.setattr(cli, "_resolve_db", lambda db: str(db_path))
    monkeypatch.setattr(cli, "connect_db", lambda path: None)
    cli._connect(db=None)
    out = capsys.readouterr().out
    assert f"Connected to {db_path}" in out


def test_add_measurement(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_existing_locations", lambda: ["Site"])
    monkeypatch.setattr(cli, "_existing_measurement_values", lambda field: [])
    monkeypatch.setattr(cli, "_existing_item_values", lambda field, measurement_type=None: [])
    monkeypatch.setattr(cli, "_existing_item_units", lambda measurement_type: [])

    monkeypatch.setattr(cli, "_prompt_text", _seq(["Site", "desc", "op", "ohm", "item desc"]))
    monkeypatch.setattr(cli, "_prompt_float", _seq([1.0, 2.0, 3.0, 10.0, 0.5, 50.0, 100.0, 0.0, 1.0, 2.0, 0.1]))
    monkeypatch.setattr(
        cli,
        "_prompt_choice",
        _seq(["staged_fault_test", "cable", "earthing_impedance", "magnitude_angle", "done"]),
    )

    created = {"measurement": None, "items": []}

    def fake_create_measurement(data):
        created["measurement"] = data
        return 7

    def fake_create_item(item, measurement_id):
        created["items"].append(item)
        return 11

    monkeypatch.setattr(cli, "create_measurement", fake_create_measurement)
    monkeypatch.setattr(cli, "create_item", fake_create_item)
    monkeypatch.setattr(
        cli,
        "read_measurements_by",
        lambda **kwargs: ([{"id": 7, "items": created["items"]}], None),
    )

    cli.add_measurement()
    out = capsys.readouterr().out
    assert "Created measurement id=7" in out
    assert created["measurement"]["location"]["name"] == "Site"


def test_list_measurements_empty(monkeypatch, capsys):
    monkeypatch.setattr(cli, "read_measurements_by", lambda **kwargs: ([], None))
    cli.list_measurements()
    assert "No measurements found." in capsys.readouterr().out


def test_list_items(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "read_items_by",
        lambda **kwargs: ([{"id": 1, "measurement_type": "earthing_impedance", "value": 1.5, "unit": "ohm"}], None),
    )
    cli.list_items(1)
    out = capsys.readouterr().out
    assert "earthing_impedance" in out


def test_cli_delete_measurement_aborted(monkeypatch):
    monkeypatch.setattr(typer, "confirm", lambda *args, **kwargs: False)
    with pytest.raises(typer.Exit):
        cli.cli_delete_measurement(5, force=False)


def test_cli_delete_measurement(monkeypatch, capsys):
    monkeypatch.setattr(cli, "delete_measurement", lambda mid: True)
    cli.cli_delete_measurement(5, force=True)
    assert "Deleted measurement id=5." in capsys.readouterr().out


def test_cli_delete_measurement_not_found(monkeypatch):
    monkeypatch.setattr(cli, "delete_measurement", lambda mid: False)
    with pytest.raises(typer.Exit):
        cli.cli_delete_measurement(5, force=True)


def test_cli_delete_item_not_found(monkeypatch):
    monkeypatch.setattr(cli, "delete_item", lambda item_id: False)
    with pytest.raises(typer.Exit):
        cli.cli_delete_item(5, force=True)


def test_add_item(monkeypatch):
    monkeypatch.setattr(cli, "_prompt_choice", _seq(["earthing_impedance", "magnitude_angle"]))
    monkeypatch.setattr(cli, "_prompt_float", _seq([50.0, 10.0, 0.0, 1.0, 2.0, 0.1]))
    monkeypatch.setattr(cli, "_prompt_text", _seq(["ohm", "desc"]))
    monkeypatch.setattr(cli, "_existing_item_values", lambda field, measurement_type=None: [])
    monkeypatch.setattr(cli, "_existing_item_units", lambda measurement_type: [])
    monkeypatch.setattr(cli, "create_item", lambda item, measurement_id: 1)
    cli.add_item(1)


def test_edit_measurement(monkeypatch):
    record = {
        "location": {"name": "Site"},
        "method": "wenner",
        "asset_type": "substation",
    }
    monkeypatch.setattr(cli, "_load_measurement", lambda mid: record)
    monkeypatch.setattr(cli, "_existing_locations", lambda: ["Site"])
    monkeypatch.setattr(cli, "_existing_measurement_values", lambda field: [])
    monkeypatch.setattr(cli, "_prompt_text", _seq(["Site", "desc", "op"]))
    monkeypatch.setattr(cli, "_prompt_float", _seq([1.0, 2.0, 3.0, 10.0, 0.5]))
    monkeypatch.setattr(cli, "_prompt_choice", _seq(["wenner", "substation"]))
    monkeypatch.setattr(cli, "update_measurement", lambda mid, updates: True)
    cli.edit_measurement(1)


def test_edit_measurement_not_found(monkeypatch):
    record = {
        "location": {"name": "Site"},
        "method": "wenner",
        "asset_type": "substation",
    }
    monkeypatch.setattr(cli, "_load_measurement", lambda mid: record)
    monkeypatch.setattr(cli, "_existing_locations", lambda: ["Site"])
    monkeypatch.setattr(cli, "_existing_measurement_values", lambda field: [])
    monkeypatch.setattr(cli, "_prompt_text", _seq(["Site", "desc", "op"]))
    monkeypatch.setattr(cli, "_prompt_float", _seq([1.0, 2.0, 3.0, 10.0, 0.5]))
    monkeypatch.setattr(cli, "_prompt_choice", _seq(["wenner", "substation"]))
    monkeypatch.setattr(cli, "update_measurement", lambda mid, updates: False)
    with pytest.raises(typer.Exit):
        cli.edit_measurement(1)


def test_edit_item(monkeypatch):
    item = {
        "measurement_type": "earthing_impedance",
        "frequency_hz": 50.0,
        "value": 10.0,
        "value_angle_deg": 0.0,
    }
    monkeypatch.setattr(cli, "_load_item", lambda item_id: item)
    monkeypatch.setattr(cli, "_existing_item_values", lambda field, measurement_type=None: [])
    monkeypatch.setattr(cli, "_existing_item_units", lambda measurement_type: [])
    monkeypatch.setattr(cli, "_prompt_choice", _seq(["earthing_impedance", "real_imag"]))
    monkeypatch.setattr(cli, "_prompt_float", _seq([60.0, 1.0, 2.0, 3.0, 4.0, 5.0]))
    monkeypatch.setattr(cli, "_prompt_text", _seq(["ohm", "desc"]))
    monkeypatch.setattr(cli, "update_item", lambda item_id, updates: True)
    cli.edit_item(1)


def test_edit_item_not_found(monkeypatch):
    item = {"measurement_type": "earthing_impedance", "frequency_hz": 50.0}
    monkeypatch.setattr(cli, "_load_item", lambda item_id: item)
    monkeypatch.setattr(cli, "_existing_item_values", lambda field, measurement_type=None: [])
    monkeypatch.setattr(cli, "_existing_item_units", lambda measurement_type: [])
    monkeypatch.setattr(cli, "_prompt_choice", _seq(["earthing_impedance", "magnitude_angle"]))
    monkeypatch.setattr(cli, "_prompt_float", _seq([50.0, 1.0, 2.0, 3.0, 4.0, 5.0]))
    monkeypatch.setattr(cli, "_prompt_text", _seq(["ohm", "desc"]))
    monkeypatch.setattr(cli, "update_item", lambda item_id, updates: False)
    with pytest.raises(typer.Exit):
        cli.edit_item(1)


def test_cli_distance_profile_value_inf(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "distance_profile_value",
        lambda **kwargs: {"result_value": 1.0, "result_distance_m": float("inf"), "algorithm": "inverse"},
    )
    cli.cli_distance_profile_value(
        1,
        measurement_type="earthing_impedance",
        algorithm="inverse",
        json_out=None,
    )
    out = capsys.readouterr().out
    assert "inf" in out


def test_cli_distance_profile_invalid_type():
    with pytest.raises(typer.Exit):
        cli.cli_distance_profile_value(1, measurement_type="bad", json_out=None)


def test_cli_import_from_images_invalid_type():
    with pytest.raises(typer.Exit):
        cli.cli_import_from_images(1, Path("."), measurement_type="bad")


def test_cli_import_from_images_json_out(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli,
        "import_items_from_images",
        lambda **kwargs: {"created_item_ids": [1], "skipped": [], "parsed_row_count": 2},
    )
    out = tmp_path / "summary.json"
    cli.cli_import_from_images(1, tmp_path, measurement_type="earthing_impedance", json_out=out)
    assert json.loads(out.read_text())["parsed_row_count"] == 2


def test_cli_import_from_images_skipped(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli,
        "import_items_from_images",
        lambda **kwargs: {"created_item_ids": [], "skipped": ["one"], "parsed_row_count": 0},
    )
    cli.cli_import_from_images(
        1,
        tmp_path,
        measurement_type="earthing_impedance",
        json_out=None,
    )
    out = capsys.readouterr().out
    assert "Skipped:" in out


def test_cli_impedance_over_frequency(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "impedance_over_frequency", lambda ids: {"a": 1})
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_impedance_over_frequency([1])
    assert seen["data"] == {"a": 1}


def test_cli_real_imag_over_frequency(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "real_imag_over_frequency", lambda ids: {"a": 1})
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_real_imag_over_frequency([1])
    assert seen["data"] == {"a": 1}


def test_cli_soil_profile(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "soil_resistivity_profile_detailed", lambda **kwargs: [{"depth_m": 1.0}])
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_soil_profile(1)
    assert seen["data"] == [{"depth_m": 1.0}]


def test_cli_soil_inversion(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "invert_soil_resistivity_layers", lambda **kwargs: {"layers": []})
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_soil_inversion(1)
    assert "layers" in seen["data"]


def test_cli_rho_f_model(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "rho_f_model", lambda ids: (1, 2, 3, 4, 5))
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_rho_f_model([1])
    assert seen["data"]["k5"] == 5


def test_cli_voltage_vt_epr(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "voltage_vt_epr", lambda ids, frequency=50.0: {"epr": 1.0})
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_voltage_vt_epr([1], frequency=60.0)
    assert seen["data"]["epr"] == 1.0


def test_cli_shield_currents(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "shield_currents_for_location", lambda **kwargs: [{"id": 1}])
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_shield_currents(1)
    assert seen["data"] == [{"id": 1}]


def test_cli_calculate_split_factor(monkeypatch):
    seen = {}
    monkeypatch.setattr(cli, "calculate_split_factor", lambda **kwargs: {"split_factor": 0.5})
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_calculate_split_factor(earth_fault_current_id=1, shield_current_ids=[2])
    assert seen["data"]["split_factor"] == 0.5


def test_cli_soil_model(monkeypatch):
    monkeypatch.setattr(cli, "multilayer_soil_model", lambda rho_layers, thicknesses_m=None: {"layers": []})
    monkeypatch.setattr(cli, "layered_earth_forward", lambda **kwargs: [1.0])
    seen = {}
    monkeypatch.setattr(cli, "_dump_or_print", lambda data, json_out: seen.setdefault("data", data))
    cli.cli_soil_model(rho=[100.0], thicknesses=[], spacings=[1.0])
    assert "predicted_curve" in seen["data"]


def test_cli_plot_impedance(monkeypatch, tmp_path):
    out = tmp_path / "plot.png"

    class DummyFig:
        def savefig(self, path):
            Path(path).write_text("img")

    monkeypatch.setattr(cli, "plot_imp_over_f", lambda *args, **kwargs: DummyFig())
    cli.cli_plot_impedance([1], output=out)
    assert out.exists()


def test_cli_plot_rho_f_model_coeff_error():
    with pytest.raises(typer.Exit):
        cli.cli_plot_rho_f_model([1], rho_f_coeffs=[1, 2, 3], output=Path("x.png"))


def test_cli_plot_rho_f_model(monkeypatch, tmp_path):
    out = tmp_path / "plot.png"

    class DummyFig:
        def savefig(self, path):
            Path(path).write_text("img")

    monkeypatch.setattr(cli, "plot_rho_f_model", lambda *args, **kwargs: DummyFig())
    monkeypatch.setattr(cli, "rho_f_model", lambda ids: (1, 2, 3, 4, 5))
    cli.cli_plot_rho_f_model([1], rho_f_coeffs=None, rho=[100.0], output=out)
    assert out.exists()


def test_cli_plot_voltage_vt_epr(monkeypatch, tmp_path):
    out = tmp_path / "plot.png"

    class DummyFig:
        def savefig(self, path):
            Path(path).write_text("img")

    monkeypatch.setattr(cli, "plot_voltage_vt_epr", lambda *args, **kwargs: DummyFig())
    cli.cli_plot_voltage_vt_epr([1], output=out)
    assert out.exists()


def test_cli_plot_soil_model(monkeypatch, tmp_path):
    out = tmp_path / "plot.png"

    class DummyFig:
        def savefig(self, path):
            Path(path).write_text("img")

    monkeypatch.setattr(cli, "plot_soil_model", lambda *args, **kwargs: DummyFig())
    cli.cli_plot_soil_model(rho=[100.0], output=out)
    assert out.exists()


def test_cli_plot_soil_inversion(monkeypatch, tmp_path):
    out = tmp_path / "plot.png"

    class DummyFig:
        def savefig(self, path):
            Path(path).write_text("img")

    monkeypatch.setattr(cli, "plot_soil_inversion", lambda *args, **kwargs: DummyFig())
    cli.cli_plot_soil_inversion(1, output=out)
    assert out.exists()


def test_import_json_single(tmp_path, monkeypatch, capsys):
    payload = {"method": "wenner", "asset_type": "substation", "items": [{"value": 1}]}
    file_path = tmp_path / "one.json"
    file_path.write_text(json.dumps(payload))

    created = {"items": 0}
    monkeypatch.setattr(cli, "create_measurement", lambda m: 1)
    monkeypatch.setattr(cli, "create_item", lambda it, measurement_id: created.__setitem__("items", created["items"] + 1))

    cli.import_json(file_path)
    assert "Successfully imported" in capsys.readouterr().out
    assert created["items"] == 1


def test_import_json_directory_merge(tmp_path, monkeypatch, capsys):
    meas_path = tmp_path / "sample_measurement.json"
    items_path = tmp_path / "sample_items.json"
    meas_path.write_text(json.dumps({"method": "wenner", "asset_type": "substation"}))
    items_path.write_text(json.dumps([{"value": 1}, {"value": 2}]))

    created = {"items": 0}
    monkeypatch.setattr(cli, "create_measurement", lambda m: 1)
    monkeypatch.setattr(
        cli,
        "create_item",
        lambda it, measurement_id: created.__setitem__("items", created["items"] + 1),
    )

    cli.import_json(tmp_path)
    out = capsys.readouterr().out
    assert "Merged items from" in out
    assert created["items"] == 2


def test_import_json_invalid_json(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{invalid")
    monkeypatch.setattr(cli, "create_measurement", lambda m: 1)
    cli.import_json(bad)
    assert "Error reading" in capsys.readouterr().err


def test_import_json_unsupported_structure(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "bad2.json"
    bad.write_text(json.dumps("string"))
    monkeypatch.setattr(cli, "create_measurement", lambda m: 1)
    cli.import_json(bad)
    assert "Unsupported JSON structure" in capsys.readouterr().out


def test_export_json(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "export_measurements_to_json", lambda path, **filters: seen.setdefault("filters", filters))
    cli.export_json(tmp_path / "out.json", measurement_ids=[1, 2])
    assert seen["filters"]["id__in"] == [1, 2]


def test_export_json_no_filters(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(cli, "export_measurements_to_json", lambda path, **filters: seen.setdefault("filters", filters))
    cli.export_json(tmp_path / "out.json", measurement_ids=None)
    assert seen["filters"] == {}


def test_cli_map_success(monkeypatch):
    monkeypatch.setattr(cli, "read_measurements_by", lambda **kwargs: ([{"id": 1}], None))
    monkeypatch.setattr(cli, "generate_map", lambda *args, **kwargs: None)
    cli.cli_map(measurement_ids=None, output=Path("map.html"), open_browser=False)


def test_cli_map_error(monkeypatch):
    monkeypatch.setattr(cli, "read_measurements_by", lambda **kwargs: ([], None))
    monkeypatch.setattr(cli, "generate_map", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("x")))
    with pytest.raises(typer.Exit):
        cli.cli_map(output=Path("map.html"))


def test_cli_dashboard_subprocess_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "cmd")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(typer.Exit):
        cli.cli_dashboard()


def test_cli_dashboard_keyboard_interrupt(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: (_ for _ in ()).throw(KeyboardInterrupt()))
    cli.cli_dashboard()


def test_set_default_db(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "cfg.json"
    monkeypatch.setattr(cli, "CONFIG_PATH", cfg)
    cli.set_default_db(tmp_path / "db.sqlite")
    assert cfg.exists()
    assert "Default DB path saved" in capsys.readouterr().out
