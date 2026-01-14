"""
groundmeas.vis_plotly
=====================

Interactive Plotly visualizations for the dashboard.
"""

from typing import List, Optional, Tuple, Union

import plotly.graph_objects as go

from ..services.analytics import (
    impedance_over_frequency,
    real_imag_over_frequency,
    voltage_vt_epr,
    value_over_distance,
    value_over_distance_detailed,
    multilayer_soil_model,
    invert_soil_resistivity_layers,
    DX_DEFAULT,
)

SYMBOL_MAP = {
    "prospective_touch_voltage": "Vtv",
    "touch_voltage": "Vt",
    "earthing_impedance": "ZE",
    "earthing_resistance": "RA",
    "earthing_current": "IE",
}


def plot_imp_over_f_plotly(
    measurement_ids: Union[int, List[int]], normalize_freq_hz: Optional[float] = None
) -> go.Figure:
    """
    Create an interactive Plotly figure of earthing impedance vs frequency.

    Plots one curve per measurement ID and optionally normalizes to a baseline frequency.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Single measurement ID or list of IDs.
    normalize_freq_hz : float, optional
        Frequency (Hz) to normalize against.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive impedance plot.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)

    fig = go.Figure()

    for mid in ids:
        freq_imp = impedance_over_frequency(mid)
        if not freq_imp:
            continue

        freqs = sorted(freq_imp.keys())
        imps = [freq_imp[f] for f in freqs]

        if normalize_freq_hz is not None:
            baseline = freq_imp.get(normalize_freq_hz)
            if baseline is None:
                continue  # Or raise error
            imps = [val / baseline for val in imps]

        fig.add_trace(go.Scatter(
            x=freqs,
            y=imps,
            mode='lines+markers',
            name=f"ID {mid}"
        ))

    ylabel = "Normalized Impedance" if normalize_freq_hz is not None else f"Impedance {SYMBOL_MAP.get('earthing_impedance', 'Z')} (Ω)"
    title = "Impedance vs Frequency"
    if normalize_freq_hz is not None:
        title += f" (Normalized @ {normalize_freq_hz} Hz)"

    fig.update_layout(
        title=title,
        xaxis_title="Frequency (Hz)",
        yaxis_title=ylabel,
        hovermode="x unified",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )

    # Engineering notation
    fig.update_yaxes(tickformat="s")
    fig.update_xaxes(tickformat="s")

    return fig


def plot_rho_f_model_plotly(
    measurement_ids: List[int],
    rho_f: Tuple[float, float, float, float, float],
    rho: Union[float, List[float]] = 100,
) -> go.Figure:
    """
    Create an interactive Plotly figure comparing measured impedance with the rho–f model.

    Parameters
    ----------
    measurement_ids : list[int]
        Measurement IDs to plot.
    rho_f : tuple[float, float, float, float, float]
        Model coefficients ``(k1, k2, k3, k4, k5)``.
    rho : float or list[float], default 100
        Resistivity value(s) to plot model curves for.

    Returns
    -------
    plotly.graph_objects.Figure
        Figure with measured and model curves.
    """
    # Start with measured data
    fig = plot_imp_over_f_plotly(measurement_ids)

    # Gather frequencies for model evaluation
    rimap = real_imag_over_frequency(measurement_ids)
    all_freqs = set()
    for freq_map in rimap.values():
        all_freqs.update(freq_map.keys())
    freqs = sorted(all_freqs)

    if not freqs:
        return fig

    k1, k2, k3, k4, k5 = rho_f
    rhos: List[float] = [rho] if isinstance(rho, (int, float)) else list(rho)

    for rho_val in rhos:
        model_mag = [
            abs((k1) * rho_val + (k2 + 1j * k3) * f + (k4 + 1j * k5) * rho_val * f)
            for f in freqs
        ]
        fig.add_trace(go.Scatter(
            x=freqs,
            y=model_mag,
            mode='lines',
            line=dict(dash='dash'),
            name=f"Model (ρ={rho_val})"
        ))

    return fig


def plot_voltage_vt_epr_plotly(
    measurement_ids: Union[int, List[int]],
    frequency: float = 50.0
) -> go.Figure:
    """
    Create an interactive grouped bar chart of EPR and touch voltages.

    Visualizes EPR, prospective touch voltage (min/max), and actual touch voltage (min/max).

    Parameters
    ----------
    measurement_ids : int or list[int]
        Single Measurement ID or list of IDs.
    frequency : float, default 50.0
        Frequency in Hz.

    Returns
    -------
    plotly.graph_objects.Figure
        Grouped bar chart.
    """
    data = voltage_vt_epr(measurement_ids, frequency=frequency)
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    if single:
        data = {measurement_ids: data}

    fig = go.Figure()

    # We group by measurement ID
    # Categories: EPR, Vtp (min/max), Vt (min/max)

    # EPR
    fig.add_trace(go.Bar(
        name='EPR',
        x=[str(mid) for mid in ids],
        y=[data[mid].get("epr", 0.0) for mid in ids],
        marker_color='blue'
    ))

    # Vtp Max
    fig.add_trace(go.Bar(
        name=f'{SYMBOL_MAP.get("prospective_touch_voltage", "Vtp")} Max',
        x=[str(mid) for mid in ids],
        y=[data[mid].get("vtp_max", 0.0) for mid in ids],
        marker_color='orange',
        opacity=0.6
    ))

    # Vtp Min (overlayed? In plotly grouped bars are side-by-side usually)
    # To replicate the "overlay" effect of matplotlib code (min on top of max),
    # we can just add them to the group.
    # Or we can use 'overlay' barmode, but that affects all bars.
    # Standard grouped bar chart is probably clearer for interactive use.

    fig.add_trace(go.Bar(
        name=f'{SYMBOL_MAP.get("prospective_touch_voltage", "Vtp")} Min',
        x=[str(mid) for mid in ids],
        y=[data[mid].get("vtp_min", 0.0) for mid in ids],
        marker_color='orange'
    ))

    # Vt Max
    fig.add_trace(go.Bar(
        name=f'{SYMBOL_MAP.get("touch_voltage", "Vt")} Max',
        x=[str(mid) for mid in ids],
        y=[data[mid].get("vt_max", 0.0) for mid in ids],
        marker_color='green',
        opacity=0.6
    ))

    # Vt Min
    fig.add_trace(go.Bar(
        name=f'{SYMBOL_MAP.get("touch_voltage", "Vt")} Min',
        x=[str(mid) for mid in ids],
        y=[data[mid].get("vt_min", 0.0) for mid in ids],
        marker_color='green'
    ))

    fig.update_layout(
        barmode='group',
        title=f"EPR & Touch Voltages @ {frequency} Hz",
        xaxis_title="Measurement ID",
        yaxis_title="Voltage (V)",
        hovermode="x unified",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    fig.update_yaxes(tickformat="s")

    return fig


def plot_value_over_distance_plotly(
    measurement_ids: Union[int, List[int]],
    measurement_type: str = "earthing_impedance",
    show_all_frequencies: bool = False,
    target_frequency: Optional[float] = None,
) -> go.Figure:
    """
    Create an interactive Plotly figure of values vs. distance.

    Useful for visualizing soil resistivity profiles or potential gradients.

    Args:
        measurement_ids: Single Measurement ID or list of IDs.
        measurement_type: The type of measurement item to plot (e.g., "earthing_impedance").
        show_all_frequencies: If True, plots a separate curve for each frequency found.
        target_frequency: If provided (and show_all_frequencies is False), plots only this frequency.

    Returns:
        A plotly.graph_objects.Figure containing the plot.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)

    fig = go.Figure()

    for mid in ids:
        data_points = value_over_distance_detailed(mid, measurement_type=measurement_type)
        if not data_points:
            continue

        if show_all_frequencies:
            # Group by frequency
            freq_groups: dict[float, list[dict[str, float | None]]] = {}
            for pt in data_points:
                f = pt["frequency"]
                if f is None:
                    f = 0.0
                freq_groups.setdefault(f, []).append(pt)

            for f in sorted(freq_groups.keys()):
                pts = sorted(freq_groups[f], key=lambda x: x["distance"])
                fig.add_trace(go.Scatter(
                    x=[p["distance"] for p in pts],
                    y=[p["value"] for p in pts],
                    mode='lines+markers',
                    name=f"ID {mid} @ {f}Hz"
                ))
        else:
            # Filter by target_frequency
            if target_frequency is not None:
                filtered_pts = [p for p in data_points if p["frequency"] == target_frequency]
                if filtered_pts:
                    filtered_pts.sort(key=lambda x: x["distance"])
                    fig.add_trace(go.Scatter(
                        x=[p["distance"] for p in filtered_pts],
                        y=[p["value"] for p in filtered_pts],
                        mode='lines+markers',
                        name=f"ID {mid} @ {target_frequency}Hz"
                    ))

    y_label = f"{SYMBOL_MAP.get(measurement_type, measurement_type)} Value"

    fig.update_layout(
        title=f"{measurement_type} vs Distance",
        xaxis_title="Distance (m)",
        yaxis_title=y_label,
        hovermode="closest",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )

    fig.update_yaxes(tickformat="s")
    fig.update_xaxes(tickformat="s")

    return fig


def plot_soil_model_plotly(
    rho_layers: List[float],
    thicknesses_m: Optional[List[float]] = None,
    max_depth_m: Optional[float] = None,
) -> go.Figure:
    """
    Create an interactive plot of a layered soil model (resistivity vs depth).

    Parameters
    ----------
    rho_layers : list[float]
        Layer resistivities in ohm-m (1-3 layers).
    thicknesses_m : list[float], optional
        Thicknesses for the top layers (length = n_layers - 1).
    max_depth_m : float, optional
        Depth for plotting the bottom (infinite) layer.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive layer step plot.
    """
    model = multilayer_soil_model(rho_layers=rho_layers, thicknesses_m=thicknesses_m)
    layers = model.get("layers", [])
    if not layers:
        return go.Figure()

    total_thickness = float(model.get("total_thickness_m", 0.0))
    plot_bottom = float(max_depth_m) if max_depth_m is not None else max(total_thickness, 1.0)

    x_step: List[float] = []
    y_step: List[float] = []
    prev_rho = None
    for layer in layers:
        top = float(layer["top_depth_m"])
        bottom = layer.get("bottom_depth_m")
        bottom_val = plot_bottom if bottom is None else float(bottom)
        rho_val = float(layer["rho_ohm_m"])
        if prev_rho is not None:
            x_step.extend([top, top])
            y_step.extend([prev_rho, rho_val])
        x_step.extend([top, bottom_val])
        y_step.extend([rho_val, rho_val])
        prev_rho = rho_val

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_step,
            y=y_step,
            mode="lines",
            line=dict(dash="dash"),
            name="Layered model",
        )
    )

    fig.update_layout(
        title=f"Soil model ({len(layers)} layer)",
        xaxis_title="Depth (m)",
        yaxis_title="Resistivity (ohm-m)",
        hovermode="x unified",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    fig.update_yaxes(tickformat="s")
    fig.update_xaxes(tickformat="s")
    return fig


def plot_soil_inversion_plotly(
    measurement_id: int,
    method: str = "wenner",
    layers: int = 2,
    value_kind: str = "auto",
    depth_factor: Optional[float] = None,
    ab_is_full: bool = False,
    mn_is_full: bool = False,
    mn_m: Optional[float] = None,
    forward: str = "filter",
    dx: float = DX_DEFAULT,
    n_lam: int = 6000,
    backend: str = "auto",
    max_iter: int = 30,
    damping: float = 0.3,
    step_max: float = 0.5,
    tol: float = 1e-4,
    initial_rho: Optional[List[float]] = None,
    initial_thicknesses: Optional[List[float]] = None,
) -> go.Figure:
    """
    Create an interactive plot of observed apparent resistivity vs inversion fit.

    Parameters
    ----------
    measurement_id : int
        Measurement ID containing soil_resistivity items.
    method : str, default "wenner"
        Array method ("wenner" or "schlumberger").
    layers : int, default 2
        Number of layers to invert.
    value_kind : str, default "auto"
        Interpret values as resistance or resistivity.
    depth_factor : float, optional
        Override depth multiplier for spacing.
    ab_is_full : bool, default False
        Interpret spacings as full AB for Schlumberger. When False, AB/2 is used.
    mn_is_full : bool, default False
        Interpret MN as full MN for Schlumberger. When False, MN/2 is used.
    mn_m : float, optional
        Optional MN override for Schlumberger.
    forward : str, default "filter"
        Forward engine ("filter" or "integral").
    dx : float, default log(10)/3
        Log step for the filter engine.
    n_lam : int, default 6000
        Lambda grid size for the integral engine.
    backend : str, default "auto"
        Math backend ("auto", "numpy", "mlx").
    max_iter : int, default 30
        Maximum Gauss-Newton iterations.
    damping : float, default 0.3
        Damping factor.
    step_max : float, default 0.5
        Max step size in log-space.
    tol : float, default 1e-4
        Convergence tolerance on RMSE change.
    initial_rho : list[float], optional
        Initial resistivity guesses.
    initial_thicknesses : list[float], optional
        Initial thickness guesses.

    Returns
    -------
    plotly.graph_objects.Figure
        Interactive observed vs predicted curve.
    """
    result = invert_soil_resistivity_layers(
        measurement_id=measurement_id,
        method=method,
        layers=layers,
        value_kind=value_kind,
        depth_factor=depth_factor,
        ab_is_full=ab_is_full,
        mn_is_full=mn_is_full,
        mn_m=mn_m,
        forward=forward,
        dx=dx,
        n_lam=n_lam,
        backend=backend,
        max_iter=max_iter,
        damping=damping,
        step_max=step_max,
        tol=tol,
        initial_rho=initial_rho,
        initial_thicknesses=initial_thicknesses,
    )
    obs = result.get("observed_curve", [])
    pred = result.get("predicted_curve", [])
    if not obs or not pred:
        return go.Figure()

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=[p["spacing_m"] for p in obs],
            y=[p["rho_ohm_m"] for p in obs],
            mode="markers",
            name="Observed",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[p["spacing_m"] for p in pred],
            y=[p["rho_ohm_m"] for p in pred],
            mode="lines",
            name="Inversion fit",
        )
    )
    fig.update_layout(
        title=f"Soil inversion ({method}, {layers} layer)",
        xaxis_title="Spacing (m)",
        yaxis_title="Apparent resistivity (ohm-m)",
        hovermode="x unified",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    fig.update_yaxes(tickformat="s")
    fig.update_xaxes(tickformat="s")
    return fig
