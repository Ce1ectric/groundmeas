"""
groundmeas.plots
================

Matplotlib-based plotting functions for earthing measurements.

Provides functions to visualize:
- Impedance vs. Frequency
- Rho-f model comparisons
- Touch voltages and EPR (Earth Potential Rise)
- Values over distance (e.g. soil resistivity profiles)
"""

import matplotlib.pyplot as plt
from typing import Tuple, Union, List, Dict, Any, Optional
import warnings
import numpy as np

from ..services.analytics import (
    impedance_over_frequency,
    real_imag_over_frequency,
    voltage_vt_epr,
    value_over_distance,
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
    frequency: float = 50.0
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
