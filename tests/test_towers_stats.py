"""Statistics report over all towers (``--stats``)."""

from __future__ import annotations

import shutil

import numpy as np
import pytest

from groundmeas.towers.stats import generate_asset_report, load_dataframe


def test_report(evaluated_demo, tmp_path):
    target = tmp_path / "campaign"
    shutil.copytree(evaluated_demo.parent, target)
    _html_path, pdf_path = generate_asset_report(
        config_path=target / "config.json", print_pdf=False
    )
    folder = target / "results" / "Statistik"
    text = (folder / "Asset_Auswertung.html").read_text(encoding="utf-8")
    assert "4 Masten" in text and "1 Leitungen" in text
    for name in (
        "hist_ut.png",
        "hist_ue.png",
        "exceed_by_line.png",
        "corr.png",
        "scatter.png",
    ):
        assert (folder / name).is_file()
        assert f'src="{name}"' in text
    assert pdf_path.endswith("Asset_Auswertung.pdf")


def test_dataframe(evaluated_demo):
    df = load_dataframe(str(evaluated_demo.parent / "results"))
    assert len(df) == 4
    row = df[df["Mast"] == "3"].iloc[0]
    assert row["UT_zu_hoch"]
    assert row["UE_kV"] == pytest.approx(row["Ik"] * row["r"] * row["ZE"])
    assert not df["default_ik"].any()


def test_empty_folder(demo_campaign):
    with pytest.raises(ValueError, match="Run the calc step first"):
        generate_asset_report(config_path=demo_campaign, print_pdf=False)


def test_values_without_numbers(tmp_path):
    (tmp_path / "LX_1.json").write_text(
        '{"Leitung": "LX", "Mast": "1", "ZE_62_Ohm": ""}', encoding="utf-8"
    )
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    df = load_dataframe(str(tmp_path))
    assert len(df) == 1 and np.isnan(df["ZE"].iloc[0])
