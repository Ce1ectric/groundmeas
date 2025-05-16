"""
groundmeas.analytics
====================

Analytics functions for the groundmeas package. Provides routines to fetch and
process impedance and resistivity data for earthing measurements, and to fit
and evaluate rho–f models.
"""

import itertools
import logging
import warnings
from typing import Dict, Union, List, Tuple

import numpy as np

from .db import read_items_by

# configure module‐level logger
logger = logging.getLogger(__name__)


def impedance_over_frequency(
    measurement_ids: Union[int, List[int]],
) -> Union[Dict[float, float], Dict[int, Dict[float, float]]]:
    """
    Build a mapping from frequency (Hz) to impedance magnitude (Ω).

    Args:
        measurement_ids: A single measurement ID or a list of IDs for which
            to retrieve earthing_impedance data.

    Returns:
        If a single ID is provided, returns:
            { frequency_hz: impedance_value, ... }
        If multiple IDs, returns:
            { measurement_id: { frequency_hz: impedance_value, ... }, ... }

    Raises:
        RuntimeError: if retrieving items from the database fails.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, Dict[float, float]] = {}

    for mid in ids:
        try:
            items, _ = read_items_by(
                measurement_id=mid, measurement_type="earthing_impedance"
            )
        except Exception as e:
            logger.error("Error reading impedance items for measurement %s: %s", mid, e)
            raise RuntimeError(
                f"Failed to load impedance data for measurement {mid}"
            ) from e

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
            try:
                freq_imp_map[float(freq)] = float(value)
            except Exception:
                warnings.warn(
                    f"Could not convert item {item.get('id')} to floats; skipping",
                    UserWarning,
                )

        all_results[mid] = freq_imp_map

    return all_results[ids[0]] if single else all_results


def real_imag_over_frequency(
    measurement_ids: Union[int, List[int]],
) -> Union[Dict[float, Dict[str, float]], Dict[int, Dict[float, Dict[str, float]]]]:
    """
    Build a mapping from frequency to real & imaginary components.

    Args:
        measurement_ids: A single measurement ID or list of IDs.

    Returns:
        If single ID:
            { frequency_hz: {"real": real_part, "imag": imag_part}, ... }
        If multiple IDs:
            { measurement_id: { frequency_hz: {...}, ... }, ... }

    Raises:
        RuntimeError: if retrieving items from the database fails.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, Dict[float, Dict[str, float]]] = {}

    for mid in ids:
        try:
            items, _ = read_items_by(
                measurement_id=mid, measurement_type="earthing_impedance"
            )
        except Exception as e:
            logger.error("Error reading impedance items for measurement %s: %s", mid, e)
            raise RuntimeError(
                f"Failed to load impedance data for measurement {mid}"
            ) from e

        if not items:
            warnings.warn(
                f"No earthing_impedance measurements found for measurement_id={mid}",
                UserWarning,
            )
            all_results[mid] = {}
            continue

        freq_map: Dict[float, Dict[str, float]] = {}
        for item in items:
            freq = item.get("frequency_hz")
            r = item.get("value_real")
            i = item.get("value_imag")
            if freq is None:
                warnings.warn(
                    f"MeasurementItem id={item.get('id')} missing frequency_hz; skipping",
                    UserWarning,
                )
                continue
            try:
                freq_map[float(freq)] = {
                    "real": float(r) if r is not None else None,
                    "imag": float(i) if i is not None else None,
                }
            except Exception:
                warnings.warn(
                    f"Could not convert real/imag for item {item.get('id')}; skipping",
                    UserWarning,
                )

        all_results[mid] = freq_map

    return all_results[ids[0]] if single else all_results


def rho_f_model(
    measurement_ids: List[int],
) -> Tuple[float, float, float, float, float]:
    """
    Fit the rho–f model:
        Z(ρ,f) = k1*ρ + (k2 + j*k3)*f + (k4 + j*k5)*ρ*f

    Enforces that at f=0 the impedance is purely real (→ k1*ρ).

    Args:
        measurement_ids: List of measurement IDs to include in the fit.

    Returns:
        A tuple (k1, k2, k3, k4, k5) of real coefficients.

    Raises:
        ValueError: if no soil_resistivity or no impedance overlap.
        RuntimeError: if the least-squares solve fails.
    """
    # 1) Gather real/imag data
    rimap = real_imag_over_frequency(measurement_ids)

    # 2) Gather available depths → ρ
    rho_map: Dict[int, Dict[float, float]] = {}
    depth_choices: List[List[float]] = []

    for mid in measurement_ids:
        try:
            items, _ = read_items_by(
                measurement_id=mid, measurement_type="soil_resistivity"
            )
        except Exception as e:
            logger.error("Error reading soil_resistivity for %s: %s", mid, e)
            raise RuntimeError(
                f"Failed to load soil_resistivity for measurement {mid}"
            ) from e

        dt = {
            float(it["measurement_distance_m"]): float(it["value"])
            for it in items
            if it.get("measurement_distance_m") is not None
            and it.get("value") is not None
        }
        if not dt:
            raise ValueError(f"No soil_resistivity data for measurement {mid}")
        rho_map[mid] = dt
        depth_choices.append(list(dt.keys()))

    # 3) Select depths minimizing spread
    best_combo, best_spread = None, float("inf")
    for combo in itertools.product(*depth_choices):
        spread = max(combo) - min(combo)
        if spread < best_spread:
            best_spread, best_combo = spread, combo

    selected_rhos = {
        mid: rho_map[mid][depth] for mid, depth in zip(measurement_ids, best_combo)
    }

    # 4) Assemble design matrices & response vectors
    A_R, yR, A_X, yX = [], [], [], []

    for mid in measurement_ids:
        rho = selected_rhos[mid]
        for f, comp in rimap.get(mid, {}).items():
            R = comp.get("real")
            X = comp.get("imag")
            if R is None or X is None:
                continue
            A_R.append([rho, f, rho * f])
            yR.append(R)
            A_X.append([f, rho * f])
            yX.append(X)

    if not A_R:
        raise ValueError("No overlapping impedance data available for fitting")

    try:
        A_R = np.vstack(A_R)
        A_X = np.vstack(A_X)
        R_vec = np.asarray(yR)
        X_vec = np.asarray(yX)

        kR, *_ = np.linalg.lstsq(A_R, R_vec, rcond=None)  # [k1, k2, k4]
        kX, *_ = np.linalg.lstsq(A_X, X_vec, rcond=None)  # [k3, k5]
    except Exception as e:
        logger.error("Least-squares solve failed: %s", e)
        raise RuntimeError("Failed to solve rho-f least-squares problem") from e

    k1, k2, k4 = kR
    k3, k5 = kX

    return float(k1), float(k2), float(k3), float(k4), float(k5)
