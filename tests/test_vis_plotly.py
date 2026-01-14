import plotly.graph_objects as go
import pytest

from groundmeas.visualization import vis_plotly


def test_plot_imp_over_f_plotly_normalized(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "impedance_over_frequency",
        lambda mid: {10.0: 2.0, 20.0: 4.0},
    )
    fig = vis_plotly.plot_imp_over_f_plotly(1, normalize_freq_hz=10.0)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert list(fig.data[0].y) == [1.0, 2.0]


def test_plot_rho_f_model_plotly_adds_model(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "impedance_over_frequency",
        lambda mid: {10.0: 1.0},
    )
    monkeypatch.setattr(
        vis_plotly,
        "real_imag_over_frequency",
        lambda ids: {1: {10.0: {"real": 1.0, "imag": 0.0}}},
    )
    fig = vis_plotly.plot_rho_f_model_plotly([1], (1.0, 0.0, 0.0, 0.0, 0.0), rho=50.0)
    assert len(fig.data) == 2


def test_plot_voltage_vt_epr_plotly(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "voltage_vt_epr",
        lambda ids, frequency=50.0: {1: {"epr": 10.0, "vtp_min": 1.0, "vtp_max": 2.0, "vt_min": 0.5, "vt_max": 0.8}},
    )
    fig = vis_plotly.plot_voltage_vt_epr_plotly([1])
    assert len(fig.data) == 5


def test_plot_value_over_distance_plotly_all_freqs(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "value_over_distance_detailed",
        lambda mid, measurement_type="earthing_impedance": [
            {"distance": 1.0, "value": 2.0, "frequency": 50.0},
            {"distance": 2.0, "value": 4.0, "frequency": 60.0},
        ],
    )
    fig = vis_plotly.plot_value_over_distance_plotly(1, show_all_frequencies=True)
    assert len(fig.data) == 2


def test_plot_value_over_distance_plotly_target_freq(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "value_over_distance_detailed",
        lambda mid, measurement_type="earthing_impedance": [
            {"distance": 1.0, "value": 2.0, "frequency": 50.0},
            {"distance": 2.0, "value": 4.0, "frequency": 60.0},
        ],
    )
    fig = vis_plotly.plot_value_over_distance_plotly(1, target_frequency=50.0)
    assert len(fig.data) == 1
    assert list(fig.data[0].y) == [2.0]


def test_plot_soil_model_plotly(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "multilayer_soil_model",
        lambda rho_layers, thicknesses_m=None: {
            "layers": [
                {"top_depth_m": 0.0, "bottom_depth_m": 1.0, "rho_ohm_m": 100.0},
                {"top_depth_m": 1.0, "bottom_depth_m": None, "rho_ohm_m": 200.0},
            ],
            "total_thickness_m": 1.0,
        },
    )
    fig = vis_plotly.plot_soil_model_plotly([100.0, 200.0], thicknesses_m=[1.0])
    assert len(fig.data) == 1


def test_plot_soil_inversion_plotly(monkeypatch):
    monkeypatch.setattr(
        vis_plotly,
        "invert_soil_resistivity_layers",
        lambda **kwargs: {
            "observed_curve": [{"spacing_m": 1.0, "rho_ohm_m": 10.0}],
            "predicted_curve": [{"spacing_m": 1.0, "rho_ohm_m": 12.0}],
        },
    )
    fig = vis_plotly.plot_soil_inversion_plotly(1)
    assert len(fig.data) == 2
