"""Diagrams of the per-tower protocol (PNG files).

The functions use matplotlib's object-oriented API (`matplotlib.figure.Figure`)
instead of ``pyplot``. They therefore need no GUI backend, are safe to call in
worker processes and do not change the global matplotlib configuration of the
calling program (e.g. a Jupyter notebook). Axis labels and legends are passed
in by the caller, which takes them from :mod:`groundmeas.towers.i18n`.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

import matplotlib as mpl
import numpy as np
from matplotlib.figure import Figure

__all__ = ["impedance_distance_plot", "step_voltage_plot", "touch_voltage_bar_plot"]

# Compact, print-friendly defaults so that three diagrams fit on one A4 page.
_FIGSIZE = (11, 4.8)
_DPI = 150
_ACCENT = "#1f4e79"
_RED = "#c0392b"
_GREY = "#7f7f7f"
_STYLE: dict[Any, Any] = {"font.size": 13}


def _save(fig: Figure, export_path: str | os.PathLike[str]) -> None:
    fig.tight_layout()
    fig.savefig(export_path, bbox_inches="tight")


def impedance_distance_plot(
    export_path: str | os.PathLike[str],
    distance: Sequence[float],
    grounding_impedance: Sequence[float],
    xlabel: str = "Distance in m",
    ylabel: str = "Earthing impedance in Ohm",
    dist_62: float | None = None,
    impedance_62: Any = None,
    voltage_profile: Sequence[float] | None = None,
    *,
    measured_label: str = "Measured values",
    value_62_label: str = "Value at 62 % of the current-electrode distance",
    voltage_label: str = "Voltage in kV",
) -> None:
    """Plot an impedance profile over the potential-probe distance.

    Parameters
    ----------
    export_path : str or os.PathLike
        PNG file to write.
    distance : sequence of float
        Probe distances in m (including the origin).
    grounding_impedance : sequence of float
        Impedance at every distance in Ohm.
    xlabel, ylabel : str, optional
        Axis labels.
    dist_62 : float or None, optional
        Distance of the 62 % point; marked if given together with
        ``impedance_62``.
    impedance_62 : float, str or None, optional
        Impedance at the 62 % point (``""`` means "not available").
    voltage_profile : sequence of float or None, optional
        Earth potential in kV on a secondary axis.
    measured_label, value_62_label, voltage_label : str, optional
        Legend and secondary-axis texts.
    """
    with mpl.rc_context(_STYLE):
        fig = Figure(figsize=_FIGSIZE, dpi=_DPI)
        ax1 = fig.subplots()
        ax1.plot(
            distance,
            grounding_impedance,
            "o-",
            markersize=7,
            color=_ACCENT,
            label=measured_label,
        )
        if dist_62 is not None and impedance_62 not in (None, ""):
            ax1.scatter(
                dist_62, impedance_62, s=90, color=_RED, zorder=5, label=value_62_label
            )
        ax1.set_xlabel(xlabel)
        ax1.set_ylabel(ylabel)
        ax1.grid(True, alpha=0.35)
        if voltage_profile is not None:
            ax2 = ax1.twinx()
            ax2.plot(distance, voltage_profile, color=_GREY, alpha=0.8)
            ax2.set_ylabel(voltage_label)
            ax2.grid(False)
        ax1.legend(loc="lower right", fontsize=10)
        _save(fig, export_path)


def step_voltage_plot(
    export_path: str | os.PathLike[str],
    distance: Sequence[float],
    step_voltage: Sequence[float],
    xlabel: str = "Distance in m",
    ylabel: str = "Step voltage in V",
) -> None:
    """Plot the open-circuit step voltage along the measuring profile.

    Parameters
    ----------
    export_path : str or os.PathLike
        PNG file to write.
    distance : sequence of float
        Distances in m (including the origin).
    step_voltage : sequence of float
        Step voltage at every distance in V.
    xlabel, ylabel : str, optional
        Axis labels.
    """
    with mpl.rc_context(_STYLE):
        fig = Figure(figsize=_FIGSIZE, dpi=_DPI)
        ax1 = fig.subplots()
        ax1.plot(distance, step_voltage, "-o", markersize=7, color=_ACCENT)
        ax1.set_xlabel(xlabel)
        ax1.set_ylabel(ylabel)
        ax1.grid(True, alpha=0.35)
        _save(fig, export_path)


def touch_voltage_bar_plot(
    export_path: str | os.PathLike[str],
    locations: Sequence[str],
    ut_without: Sequence[float],
    ut_with: Sequence[float],
    *,
    label_without: str = "without additional resistor",
    label_with: str = "with additional resistor",
    label_max_without: str = "Max. without add. resistor: {value:.0f} V",
    label_max_with: str = "Max. with add. resistor: {value:.0f} V",
    xlabel: str = "Measuring point",
    ylabel: str = "Touch voltage in V",
) -> None:
    """Compare touch voltages with and without additional resistor.

    One pair of bars per measuring point plus a dashed line at the maximum of
    each variant.

    Parameters
    ----------
    export_path : str or os.PathLike
        PNG file to write.
    locations : sequence of str
        Names of the measuring points (x-axis).
    ut_without, ut_with : sequence of float
        Touch voltages in V measured without / with the additional 1 kOhm
        series resistor.
    label_without, label_with : str, optional
        Legend texts of the bars.
    label_max_without, label_max_with : str, optional
        Legend texts of the maximum lines (``{value}`` is replaced).
    xlabel, ylabel : str, optional
        Axis labels.
    """
    n = max(len(ut_without), len(ut_with))
    x = np.arange(n)
    width = 0.4
    with mpl.rc_context(_STYLE):
        fig = Figure(figsize=_FIGSIZE, dpi=_DPI)
        ax = fig.subplots()
        if ut_without:
            ax.bar(
                x[: len(ut_without)] - width / 2,
                ut_without,
                width,
                label=label_without,
                color=_RED,
            )
            ax.axhline(
                max(ut_without),
                color=_RED,
                linestyle="--",
                linewidth=1.3,
                label=label_max_without.format(value=max(ut_without)),
            )
        if ut_with:
            ax.bar(
                x[: len(ut_with)] + width / 2,
                ut_with,
                width,
                label=label_with,
                color=_ACCENT,
            )
            ax.axhline(
                max(ut_with),
                color=_ACCENT,
                linestyle="--",
                linewidth=1.3,
                label=label_max_with.format(value=max(ut_with)),
            )
        ax.set_xticks(x[: len(locations)])
        ax.set_xticklabels(locations, rotation=25, ha="right", fontsize=10)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=9, ncol=2)
        ax.grid(True, axis="y", alpha=0.35)
        _save(fig, export_path)
