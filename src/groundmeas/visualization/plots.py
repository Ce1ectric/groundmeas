"""
groundmeas.plots
================

Matplotlib-based plotting functions for earthing measurements.

Provides functions to visualize:
- Impedance vs. Frequency
- Rho-f model comparisons
- Touch voltages and EPR (Earth Potential Rise)
- Values over distance (e.g. soil resistivity profiles)
- Layered soil models and inversion fits
"""

import warnings
from typing import List, Optional, Tuple, Union

import matplotlib.pyplot as plt
import numpy as np

from ..services.analytics import (
    impedance_over_frequency,
    real_imag_over_frequency,
    voltage_vt_epr,
    value_over_distance,
    multilayer_soil_model,
    invert_soil_resistivity_layers,
    DX_DEFAULT,
)


def plot_imp_over_f(
    measurement_ids: Union[int, List[int]], normalize_freq_hz: Optional[float] = None
) -> plt.Figure:
    """
    Plot earthing impedance versus frequency on one figure.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Single measurement ID or list of IDs.
    normalize_freq_hz : float, optional
        Normalize each curve by its impedance at this frequency.

    Returns
    -------
    matplotlib.figure.Figure
        Figure with one curve per measurement.

    Raises
    ------
    ValueError
        If normalization frequency is missing or no data is available.
    """
    # Normalize input to list
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)

    # Create a single figure and axis
    fig, ax = plt.subplots()

    plotted = False
    for mid in ids:
        # Retrieve impedance-frequency map
        freq_imp = impedance_over_frequency(mid)
        if not freq_imp:
            warnings.warn(
                f"No earthing_impedance data for measurement_id={mid}; skipping curve",
                UserWarning,
            )
            continue

        # Sort frequencies
        freqs = sorted(freq_imp.keys())
        imps = [freq_imp[f] for f in freqs]

        # Normalize if requested
        if normalize_freq_hz is not None:
            baseline = freq_imp.get(normalize_freq_hz)
            if baseline is None:
                raise ValueError(
                    f"Measurement {mid} has no impedance at {normalize_freq_hz} Hz for normalization"
                )
            imps = [val / baseline for val in imps]

        # Plot the curve
        ax.plot(freqs, imps, marker="o", linestyle="-", label=f"ID {mid}")
        plotted = True

    if not plotted:
        if single:
            raise ValueError(
                f"No earthing_impedance data available for measurement_id={measurement_ids}"
            )
        else:
            raise ValueError(
                "No earthing_impedance data available for the provided measurement IDs."
            )

    # Labels and title
    ax.set_xlabel("Frequency (Hz)")
    ylabel = (
        "Normalized Impedance" if normalize_freq_hz is not None else "Impedance (Ω)"
    )
    ax.set_ylabel(ylabel)
    title = "Impedance vs Frequency"
    if normalize_freq_hz is not None:
        title += f" (Normalized @ {normalize_freq_hz} Hz)"
    ax.set_title(title)

    # Grid and scientific tick formatting
    ax.grid(True, which="both", linestyle="--", linewidth=0.5)
    ax.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

    # Legend
    ax.legend()
    fig.tight_layout()
    return fig


def plot_rho_f_model(
    measurement_ids: List[int],
    rho_f: Tuple[float, float, float, float, float],
    rho: Union[float, List[float]] = 100,
) -> plt.Figure:
    """
    Plot measured impedance and rho–f model curves.

    Parameters
    ----------
    measurement_ids : list[int]
        Measurement IDs to plot.
    rho_f : tuple[float, float, float, float, float]
        Model coefficients ``(k1, k2, k3, k4, k5)``.
    rho : float or list[float], default 100
        Soil resistivity values to plot model curves for.

    Returns
    -------
    matplotlib.figure.Figure
        Figure with measured and modeled magnitude vs frequency.
    """
    # Plot measured curves
    fig = plot_imp_over_f(measurement_ids)
    ax = fig.axes[0]

    # Gather real/imag data
    rimap = real_imag_over_frequency(measurement_ids)
    # Union of frequencies
    all_freqs = set()
    for freq_map in rimap.values():
        all_freqs.update(freq_map.keys())
    freqs = sorted(all_freqs)

    # Unpack model coefficients
    k1, k2, k3, k4, k5 = rho_f

    # Normalize rho parameter to list
    rhos: List[float] = [rho] if isinstance(rho, (int, float)) else list(rho)

    # Plot model curves for each rho
    for rho_val in rhos:
        model_mag = [
            abs((k1) * rho_val + (k2 + 1j * k3) * f + (k4 + 1j * k5) * rho_val * f)
            for f in freqs
        ]
        ax.plot(
            freqs, model_mag, linestyle="--", linewidth=2, label=f"Model (ρ={rho_val})"
        )

    ax.legend()
    return fig


def plot_voltage_vt_epr(
    measurement_ids: Union[int, List[int]],
    frequency: float = 50.0,
) -> plt.Figure:
    """
    Plot EPR and touch voltages (prospective and actual) as grouped bars.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Single measurement ID or list of IDs.
    frequency : float, default 50.0
        Frequency in Hz.

    Returns
    -------
    matplotlib.figure.Figure
        Figure containing grouped bars for EPR, Vtp min/max, Vt min/max.
    """
    # 1) get the numbers
    data = voltage_vt_epr(measurement_ids, frequency=frequency)
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    if single:
        data = {measurement_ids: data}

    # 2) prepare figure
    fig, ax = plt.subplots()
    x = np.arange(len(ids))
    width = 0.25

    # 3) EPR bars
    epr = [data[mid].get("epr", 0.0) for mid in ids]
    ax.bar(x - width, epr, width, label="EPR (V/A)", color="C0")

    # 4) Prospective TV (V/A): max behind (semi‐transparent), min on top
    vtp_max = [data[mid].get("vtp_max", 0.0) for mid in ids]
    vtp_min = [data[mid].get("vtp_min", 0.0) for mid in ids]
    ax.bar(x, vtp_max, width, color="C1", alpha=0.6, label="Vtp max")
    ax.bar(x, vtp_min, width, color="C1", alpha=1.0, label="Vtp min")

    # 5) Actual TV (V/A): max behind, min on top
    vt_max = [data[mid].get("vt_max", 0.0) for mid in ids]
    vt_min = [data[mid].get("vt_min", 0.0) for mid in ids]
    ax.bar(x + width, vt_max, width, color="C2", alpha=0.6, label="Vt max")
    ax.bar(x + width, vt_min, width, color="C2", alpha=1.0, label="Vt min")

    # 6) formatting
    ax.set_xticks(x)
    ax.set_xticklabels([str(mid) for mid in ids])
    ax.set_xlabel("Measurement ID")
    ax.set_ylabel("V/A")
    ax.set_title(f"EPR & Touch Voltages Min/Max @ {frequency} Hz")
    ax.legend()
    ax.grid(True, which="both", linestyle="--", linewidth=0.5)
    fig.tight_layout()
    return fig


def plot_value_over_distance(
    measurement_ids: Union[int, List[int]],
    measurement_type: str = "earthing_impedance",
) -> plt.Figure:
    """
    Plot value versus measurement distance for one or multiple measurements.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Single measurement ID or list of IDs.
    measurement_type : str, default "earthing_impedance"
        Item type to plot.

    Returns
    -------
    matplotlib.figure.Figure
        Line plot of value vs distance.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)

    fig, ax = plt.subplots()
    plotted = False

    for mid in ids:
        dist_val = value_over_distance(mid, measurement_type=measurement_type)
        if not dist_val:
            continue

        # Sort by distance
        dists = sorted(dist_val.keys())
        vals = [dist_val[d] for d in dists]

        ax.plot(dists, vals, marker="o", linestyle="-", label=f"ID {mid}")
        plotted = True

    if not plotted:
        if single:
            raise ValueError(
                f"No data available for measurement_id={measurement_ids} type={measurement_type}"
            )
        else:
            raise ValueError("No data available for the provided measurement IDs.")

    ax.set_xlabel("Distance (m)")
    ax.set_ylabel(f"{measurement_type} Value")
    ax.set_title(f"{measurement_type} vs Distance")
    ax.grid(True, which="both", linestyle="--", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_soil_model(
    rho_layers: List[float],
    thicknesses_m: Optional[List[float]] = None,
    max_depth_m: Optional[float] = None,
) -> plt.Figure:
    """
    Plot a layered soil model as a resistivity-vs-depth step curve.

    Parameters
    ----------
    rho_layers : list[float]
        Layer resistivities in ohm-m (1-3 layers).
    thicknesses_m : list[float], optional
        Thicknesses for the top layers (length = n_layers - 1).
    max_depth_m : float, optional
        Depth for plotting the bottom (infinite) layer. Defaults to total thickness.

    Returns
    -------
    matplotlib.figure.Figure
        Figure with layer step curve.
    """
    model = multilayer_soil_model(rho_layers=rho_layers, thicknesses_m=thicknesses_m)
    layers = model.get("layers", [])
    if not layers:
        raise ValueError("No layers available for plotting")

    total_thickness = float(model.get("total_thickness_m", 0.0))
    plot_bottom = float(max_depth_m) if max_depth_m is not None else max(total_thickness, 1.0)

    fig, ax = plt.subplots()
    x_step: List[float] = []
    y_step: List[float] = []
    prev_rho: Optional[float] = None
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

    ax.plot(x_step, y_step, linestyle="--", linewidth=2, label="Layered model")
    ax.set_xlabel("Depth (m)")
    ax.set_ylabel("Resistivity (ohm-m)")
    ax.set_title(f"Soil model ({len(layers)} layer)")
    ax.grid(True, linestyle="--", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_soil_inversion(
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
) -> plt.Figure:
    """
    Plot apparent resistivity data and the layered-earth inversion fit.

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
        Override depth multiplier for spacing (profile build).
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
        Math backend for the transform ("auto", "numpy", "mlx").
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
    matplotlib.figure.Figure
        Figure with observed points and predicted curve.
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
        raise ValueError(f"No soil_resistivity data for measurement_id={measurement_id}")

    fig, ax = plt.subplots()
    ax.plot(
        [p["spacing_m"] for p in obs],
        [p["rho_ohm_m"] for p in obs],
        marker="o",
        linestyle="",
        label="Observed",
    )
    ax.plot(
        [p["spacing_m"] for p in pred],
        [p["rho_ohm_m"] for p in pred],
        linestyle="-",
        linewidth=2,
        label="Inversion fit",
    )
    ax.set_xlabel("Spacing (m)")
    ax.set_ylabel("Apparent resistivity (ohm-m)")
    ax.set_title(f"Soil inversion ({method}, {layers} layer)")
    ax.grid(True, linestyle="--", linewidth=0.5)
    ax.legend()
    fig.tight_layout()
    return fig
