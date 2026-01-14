# tests/test_plots.py
import pytest
import matplotlib.pyplot as plt

from groundmeas.visualization import plots


def test_plot_imp_over_f_single_success(monkeypatch):
    # stub a simple two‐point impedance curve
    monkeypatch.setattr(
        plots,
        "impedance_over_frequency",
        lambda mid: {10.0: 1.0, 100.0: 2.0},
    )
    fig = plots.plot_imp_over_f(1)
    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]
    # one line: freq [10,100], imp [1,2]
    lines = ax.get_lines()
    assert len(lines) == 1
    xdata, ydata = lines[0].get_xdata(), lines[0].get_ydata()
    assert list(xdata) == [10.0, 100.0]
    assert list(ydata) == [1.0, 2.0]
    assert ax.get_xlabel() == "Frequency (Hz)"
    assert ax.get_ylabel() == "Impedance (Ω)"
    assert ax.get_title() == "Impedance vs Frequency"


def test_plot_imp_over_f_normalize_success(monkeypatch):
    # stub with known baseline at 10 Hz
    monkeypatch.setattr(
        plots,
        "impedance_over_frequency",
        lambda mid: {10.0: 2.0, 100.0: 6.0},
    )
    fig = plots.plot_imp_over_f(1, normalize_freq_hz=10.0)
    ax = fig.axes[0]
    line = ax.get_lines()[0]
    # normalized y = [2/2, 6/2] = [1,3]
    assert list(line.get_ydata()) == [1.0, 3.0]
    assert ax.get_ylabel() == "Normalized Impedance"
    assert ax.get_title() == "Impedance vs Frequency (Normalized @ 10.0 Hz)"


def test_plot_imp_over_f_normalize_missing_baseline(monkeypatch):
    # stub missing the requested normalize_freq_hz
    monkeypatch.setattr(
        plots,
        "impedance_over_frequency",
        lambda mid: {100.0: 5.0},
    )
    with pytest.raises(ValueError) as exc:
        plots.plot_imp_over_f(1, normalize_freq_hz=10.0)
    assert "has no impedance at 10.0 Hz for normalization" in str(exc.value)


def test_plot_imp_over_f_single_no_data(monkeypatch):
    # stub empty dict
    monkeypatch.setattr(plots, "impedance_over_frequency", lambda mid: {})
    with pytest.raises(ValueError) as exc:
        plots.plot_imp_over_f(42)
    assert "measurement_id=42" in str(exc.value)


def test_plot_imp_over_f_multi_all_missing(monkeypatch):
    # stub always empty
    monkeypatch.setattr(plots, "impedance_over_frequency", lambda mid: {})
    with pytest.raises(ValueError) as exc:
        plots.plot_imp_over_f([1, 2, 3])
    assert "provided measurement IDs" in str(exc.value)


def test_plot_imp_over_f_multi_partial(monkeypatch):
    # id=1 missing, id=2 present
    def imp(mid):
        return {} if mid == 1 else {1.0: 10.0, 10.0: 20.0}
    monkeypatch.setattr(plots, "impedance_over_frequency", imp)

    with pytest.warns(UserWarning) as record:
        fig = plots.plot_imp_over_f([1, 2])
    # one warning about skipping ID 1
    assert any("measurement_id=1" in str(w.message) for w in record)
    ax = fig.axes[0]
    # only the second curve plotted
    assert len(ax.get_lines()) == 1


def test_plot_rho_f_model_single_rho(monkeypatch):
    # stub plot_imp_over_f to give a figure with one existing curve
    def fake_plot(ids):
        fig, ax = plt.subplots()
        ax.plot([1, 2], [3, 4], label="measured")
        return fig
    monkeypatch.setattr(plots, "plot_imp_over_f", fake_plot)

    # stub real_imag_over_frequency: two frequencies 10 & 100
    rimap = {
        1: {10.0: 1+0j, 100.0: 1+0j},
        2: {100.0: 1+0j, 1000.0: 1+0j},
    }
    monkeypatch.setattr(plots, "real_imag_over_frequency", lambda ids: rimap)

    rho_f = (1.0, 0.5, 0.0, 0.1, 0.0)
    fig = plots.plot_rho_f_model([1, 2], rho_f, rho=50.0)
    ax = fig.axes[0]
    lines = ax.get_lines()
    # 1 measured + 1 model
    assert len(lines) == 2
    model = lines[1]
    # style checks
    assert model.get_linestyle() == "--"
    assert model.get_linewidth() == 2.0
    assert "ρ=50.0" in model.get_label()


def test_plot_rho_f_model_multiple_rho(monkeypatch):
    # same stub
    def fake_plot(ids):
        fig, ax = plt.subplots()
        ax.plot([1, 2], [3, 4], label="measured")
        return fig
    monkeypatch.setattr(plots, "plot_imp_over_f", fake_plot)

    rimap = {1: {1.0: 0+0j}, 2: {1.0: 0+0j}}
    monkeypatch.setattr(plots, "real_imag_over_frequency", lambda ids: rimap)

    rho_f = (0, 0, 0, 0, 0)
    fig = plots.plot_rho_f_model([1, 2], rho_f, rho=[10.0, 20.0])
    ax = fig.axes[0]
    lines = ax.get_lines()
    # 1 measured + 2 models
    assert len(lines) == 3
    labels = [ln.get_label() for ln in lines[1:]]
    assert "ρ=10.0" in labels[0]
    assert "ρ=20.0" in labels[1]


def test_plot_soil_model():
    fig = plots.plot_soil_model(
        rho_layers=[100.0, 200.0],
        thicknesses_m=[2.0],
        max_depth_m=5.0,
    )
    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]
    lines = ax.get_lines()
    assert len(lines) == 1
    assert ax.get_xlabel() == "Depth (m)"
    assert ax.get_ylabel() == "Resistivity (ohm-m)"


def test_plot_soil_inversion(monkeypatch):
    result = {
        "observed_curve": [
            {"spacing_m": 1.0, "rho_ohm_m": 100.0},
            {"spacing_m": 2.0, "rho_ohm_m": 120.0},
        ],
        "predicted_curve": [
            {"spacing_m": 1.0, "rho_ohm_m": 110.0},
            {"spacing_m": 2.0, "rho_ohm_m": 115.0},
        ],
    }
    monkeypatch.setattr(plots, "invert_soil_resistivity_layers", lambda *args, **kwargs: result)

    fig = plots.plot_soil_inversion(1, method="wenner", layers=2)
    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]
    lines = ax.get_lines()
    assert len(lines) == 2
    assert ax.get_xlabel() == "Spacing (m)"
    assert ax.get_ylabel() == "Apparent resistivity (ohm-m)"


def test_plot_voltage_vt_epr(monkeypatch):
    monkeypatch.setattr(
        plots,
        "voltage_vt_epr",
        lambda ids, frequency=50.0: {1: {"epr": 10.0, "vtp_min": 1.0, "vtp_max": 2.0, "vt_min": 0.5, "vt_max": 1.0}},
    )
    fig = plots.plot_voltage_vt_epr(1, frequency=50.0)
    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]
    assert ax.get_xlabel() == "Measurement ID"
    assert ax.get_ylabel() == "V/A"


def test_plot_value_over_distance(monkeypatch):
    monkeypatch.setattr(
        plots,
        "value_over_distance",
        lambda mid, measurement_type="earthing_impedance": {1.0: 2.0, 2.0: 4.0},
    )
    fig = plots.plot_value_over_distance(1, measurement_type="earthing_impedance")
    assert isinstance(fig, plt.Figure)
    ax = fig.axes[0]
    line = ax.get_lines()[0]
    assert list(line.get_xdata()) == [1.0, 2.0]
    assert list(line.get_ydata()) == [2.0, 4.0]
