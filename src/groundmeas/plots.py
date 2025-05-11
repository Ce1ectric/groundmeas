# src/groundmeas/plots.py
"""
Plotting functions for groundmeas package.
"""
import matplotlib.pyplot as plt
from typing import Union, List, Dict, Any, Optional
import warnings
from .analytics import impedance_over_frequency


def plot_imp_over_f(
    measurement_ids: Union[int, List[int]],
    normalize_freq_hz: Optional[float] = None
) -> plt.Figure:
    """
    Plot earthing impedance versus frequency for one or multiple measurements on a single figure.

    Args:
        measurement_ids: single ID or list of Measurement IDs.
        normalize_freq_hz: if provided, normalize each impedance curve by its impedance at this frequency.

    Returns:
        A matplotlib Figure containing all curves.

    Raises:
        ValueError: if normalize_freq_hz is specified but a measurement lacks that frequency,
                    or if no data is available for a single measurement.
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
                UserWarning
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
        ax.plot(freqs, imps, marker='o', linestyle='-', label=f"ID {mid}")
        plotted = True

    if not plotted:
        if single:
            raise ValueError(
                f"No earthing_impedance data available for measurement_id={measurement_ids}"
            )
        else:
            raise ValueError("No earthing_impedance data available for the provided measurement IDs.")

    # Labels and title
    ax.set_xlabel('Frequency (Hz)')
    ylabel = 'Normalized Impedance' if normalize_freq_hz is not None else 'Impedance (Ω)'
    ax.set_ylabel(ylabel)
    title = 'Impedance vs Frequency'
    if normalize_freq_hz is not None:
        title += f' (Normalized @ {normalize_freq_hz} Hz)'
    ax.set_title(title)

    # Grid and scientific tick formatting
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    ax.ticklabel_format(axis='y', style='sci', scilimits=(0,0))

    # Legend
    ax.legend()
    fig.tight_layout()
    return fig

