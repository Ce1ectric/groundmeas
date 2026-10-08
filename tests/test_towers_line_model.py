"""Short-circuit current model along a line."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

import groundmeas.towers.analysis as analyzer_module
from groundmeas.towers.analysis import LineModel

N_TOWERS, SPAN_KM = 40, 0.3
PARAMS = {"a": 63.5, "b": 1.0, "c": 6.0, "d": 9.0}


def two_sided(x, a=PARAMS["a"], b=PARAMS["b"], c=PARAMS["c"], d=PARAMS["d"]):
    """Independent implementation of the generating model (current in kA)."""
    x = np.asarray(x, dtype=float)
    return a / (b * SPAN_KM * x + c) + a / (b * (N_TOWERS - x) * SPAN_KM + d)


def training_table(first_tower=1, steps=11, fill_all_towers=False):
    """Short-circuit table in 10 % steps of the line length (like Kurzschlussdaten.xlsx)."""
    length = SPAN_KM * (N_TOWERS - 1)
    l_km = np.linspace(0, length, steps)
    towers = first_tower + l_km / SPAN_KM
    mast = (
        towers.round().astype(int)
        if fill_all_towers
        else [first_tower] + [None] * (steps - 2) + [first_tower + N_TOWERS - 1]
    )
    return pd.DataFrame({"Ik": two_sided(l_km / SPAN_KM), "l": l_km, "Mast": mast})


def trained(table, line="L1"):
    model = LineModel()
    model.training_data[line] = table
    model.train_curve_model(line)
    return model


def test_fit_reproduces_the_generating_model():
    model = trained(training_table())
    assert model.curve_data["L1"]["type"] == "two_sided"
    towers = np.arange(1, N_TOWERS + 1)
    fitted = np.array([model.get_sc_current("L1", str(t)) for t in towers])
    # method 2: analytical model, method 3: linear interpolation of the table
    analytic = two_sided(towers - 1)
    table = training_table()
    interpolated = np.interp(towers, 1 + table["l"] / SPAN_KM, table["Ik"])
    np.testing.assert_allclose(fitted, analytic, rtol=5e-3, atol=0.01)
    np.testing.assert_allclose(fitted, interpolated, rtol=2e-2)


def test_endpoints_reproduce_the_table():
    model = trained(training_table())
    table = training_table()
    assert model.get_sc_current("L1", "1") == pytest.approx(
        table["Ik"].iloc[0], abs=0.01
    )
    assert model.get_sc_current("L1", str(N_TOWERS)) == pytest.approx(
        table["Ik"].iloc[-1], abs=0.01
    )


def test_numbering_offset_does_not_change_the_current():
    model = LineModel()
    model.training_data["zero"] = training_table(first_tower=0)
    model.training_data["offset"] = training_table(first_tower=22)
    model.train_curve_model("zero")
    model.train_curve_model("offset")
    assert model.curve_data["offset"]["first_tower"] == 22
    for index in (0, 1, 10, N_TOWERS - 1):
        assert model.get_sc_current("zero", str(index)) == pytest.approx(
            model.get_sc_current("offset", str(index + 22))
        )


def test_integer_tower_column_is_accepted():
    """All tower numbers filled -> int64 column (failed before 0.2)."""
    table = training_table(fill_all_towers=True)
    assert table["Mast"].dtype.kind == "i"
    model = trained(table)
    assert model.get_sc_current("L1", "20") == pytest.approx(
        float(two_sided(19)), rel=5e-3
    )


def test_linear_fallback(monkeypatch, caplog):
    def failing_fit(*args, **kwargs):
        raise RuntimeError("Optimal parameters not found")

    monkeypatch.setattr(analyzer_module, "curve_fit", failing_fit)
    table = training_table()
    with caplog.at_level(logging.WARNING, logger="groundmeas"):
        model = trained(table)
    assert model.curve_data["L1"]["type"] == "linear"
    assert "Fallback to the linear short-circuit model" in caplog.text
    slope, intercept = np.polyfit(table["l"] / SPAN_KM, table["Ik"], 1)  # second method
    assert model.get_sc_current("L1", "11") == pytest.approx(
        round(slope * 10 + intercept, 2)
    )


@pytest.mark.parametrize(
    ("mast", "message"),
    [
        ([5, None, 5], "no consistent tower numbers"),
        ([9, None, 5], "no consistent tower numbers"),
    ],
)
def test_inconsistent_tower_numbers(mast, message):
    model = LineModel()
    model.training_data["L1"] = pd.DataFrame(
        {"Ik": [8.0, 9.0, 10.0], "l": [0.0, 1.0, 2.0], "Mast": mast}
    )
    with pytest.raises(ValueError, match=message):
        model.train_curve_model("L1")


def test_errors_for_unknown_lines_and_towers():
    model = LineModel()
    with pytest.raises(ValueError, match="No training data"):
        model.train_curve_model("missing")
    with pytest.raises(ValueError, match="not available in the curve model"):
        model.get_sc_current("missing", "3")
    with pytest.raises(ValueError, match="no tower number"):
        trained(training_table()).get_sc_current("L1", "A")


def test_currents_are_recorded():
    model = trained(training_table())
    model.get_sc_current("L1", "3")
    model.get_sc_current("L1", "4")
    assert set(model.sc_data["L1"]) == {3, 4}


def test_read_training_parameter_from_excel(tmp_path, caplog):
    path = tmp_path / "short_circuit.xlsx"
    table = training_table()
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        table.assign(Fehlerort_Prozent=range(len(table)))[
            ["Fehlerort_Prozent", "Ik", "l", "Mast"]
        ].to_excel(writer, sheet_name="L1", index=False)
        pd.DataFrame({"x": [1], "Ik": [1], "l": [1], "other": [1]}).to_excel(
            writer, sheet_name="BAD", index=False
        )
    model = LineModel()
    loaded = model.read_training_parameter(str(path), "L1")
    assert list(loaded.columns) == ["Ik", "l", "Mast"]
    with caplog.at_level(logging.ERROR, logger="groundmeas"):
        assert model.read_training_parameter(str(path), "BAD") is None
    assert "do not match expected columns" in caplog.text
    with pytest.raises(FileNotFoundError):
        model.read_training_parameter(str(tmp_path / "missing.xlsx"), "L1")
