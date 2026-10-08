"""Command-line interface ``gm-cli towers``."""

from __future__ import annotations

import json
import sys

import pytest
from typer.testing import CliRunner

from groundmeas.ui import cli as main_cli

runner = CliRunner(mix_stderr=False)


def run(*args: str):
    return runner.invoke(main_cli.app, ["towers", *args])


def test_help_lists_commands():
    result = run("--help")
    assert result.exit_code == 0
    for command in (
        "run",
        "demo",
        "example-config",
        "install-browser",
        "flatten",
        "import-db",
    ):
        assert command in result.stdout


def test_run_help_mentions_all_steps():
    result = run("run", "--help")
    assert result.exit_code == 0
    for option in (
        "--calc",
        "--print",
        "--zip",
        "--stats",
        "--config",
        "--no-pdf",
        "--worker",
    ):
        assert option in result.stdout


def test_towers_commands_do_not_create_a_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GROUNDMEAS_DB", raising=False)
    monkeypatch.setattr(main_cli, "CONFIG_PATH", tmp_path / "no_config.json")
    result = run("example-config", str(tmp_path / "config.json"))
    assert result.exit_code == 0, result.output
    assert "Connected to" not in result.stdout
    assert not (tmp_path / "groundmeas.db").exists()


def test_demo_and_full_run_without_pdf(tmp_path):
    target = tmp_path / "demo"
    result = run("demo", str(target), "--language", "de")
    assert result.exit_code == 0, result.output
    config = target / "config.json"
    assert json.loads(config.read_text(encoding="utf-8"))["language"] == "de"
    result = run("run", "--config", str(config), "--no-pdf", "-q")
    assert result.exit_code == 0, result.output
    results = target / "results"
    assert len(list(results.glob("*.json"))) == 4
    assert len(list((results / "html_files").glob("*.html"))) == 4
    assert not (results / "protocols.zip").exists()  # nothing to zip without PDFs


def test_demo_refuses_a_non_empty_folder(tmp_path):
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    result = run("demo", str(tmp_path))
    assert result.exit_code == 2
    assert "not empty" in result.stderr


def test_steps_run_in_pipeline_order(monkeypatch, demo_campaign):
    calls: list[str] = []
    import groundmeas.towers.campaign as campaign
    import groundmeas.towers.protocol as protocol
    import groundmeas.towers.stats as stats

    monkeypatch.setattr(
        campaign, "calculate_summary", lambda **kw: calls.append("calc")
    )
    monkeypatch.setattr(
        protocol, "print_protocol", lambda **kw: calls.append(f"print:{kw}")
    )
    monkeypatch.setattr(protocol, "zip_protocols", lambda **kw: calls.append("zip"))
    monkeypatch.setattr(
        stats, "generate_asset_report", lambda **kw: calls.append("stats")
    )

    assert (
        run("run", "--config", str(demo_campaign), "--stats", "--calc").exit_code == 0
    )
    assert calls == ["calc", "stats"]
    calls.clear()
    assert run("run", "--config", str(demo_campaign), "--worker", "3").exit_code == 0
    assert calls == ["calc", "print:{'worker_count': 3, 'print_pdf': True}", "zip"]
    calls.clear()
    assert run("run", "--config", str(demo_campaign), "--no-pdf").exit_code == 0
    assert calls == ["calc", "print:{'worker_count': 1, 'print_pdf': False}"]


def test_config_from_environment(monkeypatch, demo_campaign):
    import groundmeas.towers.campaign as campaign

    calls = []
    monkeypatch.setattr(
        campaign, "calculate_summary", lambda **kw: calls.append("calc")
    )
    monkeypatch.setenv("TOWER_GROUNDING_CONFIG", str(demo_campaign))  # former name
    assert run("run", "--calc").exit_code == 0
    assert calls == ["calc"]


def test_missing_configuration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run("run", "--calc")
    assert result.exit_code == 2
    assert "configuration file not found" in result.stderr


def test_invalid_configuration_returns_2(demo_campaign, edit_config):
    edit_config(demo_campaign, language="xx")
    assert run("run", "--config", str(demo_campaign), "--calc", "-q").exit_code == 2


def test_processing_error_returns_1(demo_campaign):
    # --stats without results -> ValueError("... Run the calc step first")
    assert run("run", "--config", str(demo_campaign), "--stats", "-q").exit_code == 1


def test_invalid_worker_count(demo_campaign):
    assert run("run", "--config", str(demo_campaign), "--worker", "0").exit_code == 2


def test_verbose_and_quiet_exclude_each_other(demo_campaign):
    assert run("run", "--config", str(demo_campaign), "-v", "-q").exit_code == 2


def test_example_config(tmp_path):
    target = tmp_path / "campaign" / "config.json"
    result = run("example-config", str(target))
    assert result.exit_code == 0
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["directory"]["path_measurements"] == "measurements"
    assert run("example-config", str(target)).exit_code == 2
    assert run("example-config", str(target), "--overwrite").exit_code == 0


def test_lazy_public_api():
    import groundmeas.towers as towers

    assert towers.GroundingSystemAnalysis.__name__ == "GroundingSystemAnalysis"
    assert "calculate_summary" in dir(towers)
    with pytest.raises(AttributeError):
        _ = towers.does_not_exist


def test_install_browser_uses_the_running_interpreter(monkeypatch):
    import groundmeas.towers.pdf as pdf

    calls = []
    monkeypatch.setattr(
        pdf.subprocess, "call", lambda command: calls.append(command) or 0
    )
    assert run("install-browser").exit_code == 0
    assert calls == [[sys.executable, "-m", "playwright", "install", "chromium"]]
    monkeypatch.setattr(pdf.subprocess, "call", lambda command: 3)
    assert run("install-browser").exit_code == 3
