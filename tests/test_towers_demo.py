"""Synthetic demo campaign."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from scipy.optimize import brentq

from groundmeas.towers.demo import (
    CURRENT_ELECTRODE_DISTANCE_M,
    DEMO_TOWERS,
    fall_of_potential_profile,
    short_circuit_current_kA,
    write_demo_campaign,
)


def test_profile_reaches_the_true_resistance_at_61_8_percent():
    r, a, d = 0.55, 2.0, CURRENT_ELECTRODE_DISTANCE_M
    # method 1: closed form, x measured from the electrode surface
    x_golden = (np.sqrt(5) - 1) / 2 * d - a
    assert fall_of_potential_profile([x_golden], r, a)[0] == pytest.approx(r, rel=1e-12)
    # method 2: numerical root of Z(x) = R
    root = brentq(lambda x: fall_of_potential_profile([x], r, a)[0] - r, 10, 90)
    assert root == pytest.approx(x_golden, rel=1e-9)


def test_profile_is_monotonic_in_the_measured_range():
    z = fall_of_potential_profile(np.linspace(0.5, 70, 50), 0.5, 2.0)
    assert np.all(np.diff(z) > 0)


def test_short_circuit_model_is_two_sided():
    n, span = 40, 0.3
    currents = short_circuit_current_kA(np.arange(n), n, span)
    assert currents.argmin() not in (
        0,
        n - 1,
    )  # minimum inside the line (two-sided infeed)
    assert currents[0] > currents[-1]  # stronger source at the start (c < d)


def test_files_and_texts(tmp_path):
    config_path = write_demo_campaign(tmp_path / "demo", language="de")
    root = config_path.parent
    names = sorted(p.name for p in (root / "measurements").iterdir())
    assert len(names) == 4 * 3 + 2
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert (
        config["language"] == "de"
        and config["directory"]["path_measurements"] == "measurements"
    )
    description = pd.read_excel(root / "measurement_description.xlsx")
    assert description["Sichtbefund"].iloc[0] == "Keine Auffälligkeiten"
    assert len(description) == len(DEMO_TOWERS)
    with pd.ExcelFile(root / "short_circuit_data.xlsx") as workbook:
        assert workbook.sheet_names == ["LX-01", "Leitungsschutz"]
    report = (root / "measurements" / "UT_LX-01_3.txt").read_bytes()
    assert b"\r\n" in report and b"MAST" in report


def test_refuses_non_empty_folder(tmp_path):
    (tmp_path / "x.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_demo_campaign(tmp_path)
    write_demo_campaign(tmp_path, overwrite=True)
