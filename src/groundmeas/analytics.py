# src/groundmeas/analytics.py
"""
Analytics functions for groundmeas package.
"""
import itertools
from typing import Dict, Union, List, Tuple
import warnings

import numpy as np

from .db import read_items_by


def impedance_over_frequency(
    measurement_ids: Union[int, List[int]],
) -> Union[Dict[float, float], Dict[int, Dict[float, float]]]:
    """
    Return frequency-to-impedance mapping for one or multiple measurements.

    Args:
        measurement_ids: a single Measurement ID or a list of IDs.

    Returns:
        - If given a single ID, returns a dict:
            { frequency_hz: impedance_value, … }
        - If given multiple IDs, returns a dict:
            { measurement_id: { frequency_hz: impedance_value, … }, … }

    If no 'earthing_impedance' items are found for an ID, emits a warning
    and uses an empty dict for that ID.
    """
    # Normalize to a list of IDs
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, Dict[float, float]] = {}

    for mid in ids:
        # Pull only earthing_impedance items for this measurement
        items, _ = read_items_by(
            measurement_id=mid, measurement_type="earthing_impedance"
        )
        if not items:
            warnings.warn(
                f"No earthing_impedance measurements found for measurement_id={mid}",
                UserWarning,
            )
            all_results[mid] = {}
            continue

        freq_imp_map: Dict[float, float] = {}
        for item in items:
            freq = item.get("frequency_hz")
            value = item.get("value")
            if freq is None:
                warnings.warn(
                    f"MeasurementItem id={item.get('id')} missing frequency_hz; skipping",
                    UserWarning,
                )
                continue
            # Map frequency to impedance value (last one wins if duplicates)
            freq_imp_map[freq] = value

        all_results[mid] = freq_imp_map

    # Return single‐ID result or full mapping
    return all_results[ids[0]] if single else all_results


def real_imag_over_frequency(
    measurement_ids: Union[int, List[int]],
) -> Union[Dict[float, float], Dict[int, Dict[float, float]]]:
    """
    Return frequency-to-real/imaginary mapping for one or multiple measurements.

    Args:
        measurement_ids: a single Measurement ID or a list of IDs.

    Returns:
        - If given a single ID, returns a dict:
            { frequency_hz: (real_value, imag_value), … }
        - If given multiple IDs, returns a dict:
            { measurement_id: { frequency_hz: (real_value, imag_value), … }, … }

    If no 'earthing_impedance' items are found for an ID, emits a warning
    and uses an empty dict for that ID.
    """
    # Normalize to a list of IDs
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, Dict[float, Tuple[float, float]]] = {}

    for mid in ids:
        # Pull only earthing_impedance items for this measurement
        items, _ = read_items_by(
            measurement_id=mid, measurement_type="earthing_impedance"
        )
        if not items:
            warnings.warn(
                f"No earthing_impedance measurements found for measurement_id={mid}",
                UserWarning,
            )
            all_results[mid] = {}
            continue

        freq_real_map: Dict[float, Tuple[float, float]] = {}
        for item in items:
            freq = item.get("frequency_hz")
            value_real = item.get("value_real")
            value_imag = item.get("value_imag")
            if freq is None:
                warnings.warn(
                    f"MeasurementItem id={item.get('id')} missing frequency_hz; skipping",
                    UserWarning,
                )
                continue
            # Map frequency to real/imaginary value
            freq_real_map[freq] = {"real": value_real, "imag": value_imag}

        all_results[mid] = freq_real_map

    # Return single‐ID result or full mapping
    return all_results[ids[0]] if single else all_results


def rho_f_model(
    measurement_ids: List[int],
) -> Tuple[float, float, float, float, float, float]:
    """
    Fit a model of the form
        Z(rho, f) = (k1) * rho
                  + (k2 + i k3) * f
                  + (k4 + i k5) * rho * f
    using multiple measurements at a common soil-resistivity depth.

    Args:
        measurement_ids: list of Measurement IDs.

    Returns:
        (k1, k2, k3, k4, k5) as real floats.

    Raises:
        ValueError if no common depth or no impedance data.
    """
    # 1) grab R/X vs f
    rimap: Dict[int, Dict[float, Dict[str, float]]] = real_imag_over_frequency(
        measurement_ids
    )

    # 2) grab depth→rho for each ID
    rho_map: Dict[int, Dict[float, float]] = {}
    depth_options = []
    for mid in measurement_ids:
        items, _ = read_items_by(
            measurement_id=mid, measurement_type="soil_resistivity"
        )
        depth_to_rho = {}
        for it in items:
            d = it.get("measurement_distance_m")
            rho = it.get("value")
            if d is not None and rho is not None:
                depth_to_rho[d] = rho
        if not depth_to_rho:
            raise ValueError(f"No soil_resistivity for measurement {mid}")
        rho_map[mid] = depth_to_rho
        depth_options.append(list(depth_to_rho.keys()))

    # 3) find the combination of one depth per ID minimizing max-min spread
    best_combo = None
    best_spread = float("inf")
    for combo in itertools.product(*depth_options):
        spread = max(combo) - min(combo)
        if spread < best_spread:
            best_spread = spread
            best_combo = combo

    selected_depths = dict(zip(measurement_ids, best_combo))

    # 4) build regression data
    A_R_rows, yR = [], []
    A_X_rows, yX = [], []

    for mid in measurement_ids:
        rho = rho_map[mid][ selected_depths[mid] ]
        freq_map = rimap.get(mid, {})
        for f, comp in freq_map.items():
            R = comp.get("real"); X = comp.get("imag")
            if R is None or X is None:
                continue
            A_R_rows.append([rho, f, rho*f])
            yR.append(R)
            A_X_rows.append([f, rho*f])
            yX.append(X)

    if not A_R_rows:
        raise ValueError("No overlapping impedance data for fitting.")

    A_R = np.vstack(A_R_rows)     # shape (N,3): [ρ, f, ρ·f]
    A_X = np.vstack(A_X_rows)     # shape (N,2): [f, ρ·f]
    R_vec = np.array(yR)          # (N,)
    X_vec = np.array(yX)          # (N,)

    # 5) solve least‐squares
    kR, *_ = np.linalg.lstsq(A_R, R_vec, rcond=None)  # → [k1, k2, k4]
    kX, *_ = np.linalg.lstsq(A_X, X_vec, rcond=None)  # → [k3, k5]

    k1, k2, k4 = kR
    k3, k5    = kX

    return float(k1), float(k2), float(k3), float(k4), float(k5)
