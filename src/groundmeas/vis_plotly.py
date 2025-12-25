"""
groundmeas.vis_plotly
=====================

Interactive Plotly visualizations for the dashboard.
"""

import plotly.graph_objects as go
from typing import List, Union, Optional, Tuple, Dict
import numpy as np
import warnings

from .analytics import (
    impedance_over_frequency,
    real_imag_over_frequency,
    voltage_vt_epr,
    value_over_distance,
    value_over_distance_detailed,
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
    Create an interactive Plotly figure of earthing impedance vs. frequency.

    Plots one curve per measurement ID. Supports normalization to a baseline frequency.

    Args:
        measurement_ids: Single Measurement ID or list of IDs.
        normalize_freq_hz: Optional frequency (Hz) to normalize values against.

    Returns:
        A plotly.graph_objects.Figure containing the plot.
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
                continue # Or raise error
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
    Create an interactive Plotly figure comparing measured impedance with the Rho-f model.

    Args:
        measurement_ids: List of Measurement IDs to plot as measured data.
        rho_f: Tuple of model coefficients (k1, k2, k3, k4, k5).
        rho: Single resistivity value or list of values to plot model curves for.

    Returns:
        A plotly.graph_objects.Figure containing measured data and model curves.
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
    Create an interactive grouped bar chart of EPR and Touch Voltages.

    Visualizes:
    - Earth Potential Rise (EPR)
    - Prospective Touch Voltage (Vtp) - Min/Max
    - Actual Touch Voltage (Vt) - Min/Max

    Args:
        measurement_ids: Single Measurement ID or list of IDs.
        frequency: Frequency in Hz to extract data for (default: 50.0).

    Returns:
        A plotly.graph_objects.Figure containing the bar chart.
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
            freq_groups = {}
            for pt in data_points:
                f = pt["frequency"]
                if f is None: f = 0
                if f not in freq_groups: freq_groups[f] = []
                freq_groups[f].append(pt)
            
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
