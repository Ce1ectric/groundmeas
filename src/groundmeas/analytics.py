"""
groundmeas.analytics
====================

Analytics functions for the groundmeas package. Provides routines to fetch and
process impedance and resistivity data for earthing measurements, and to fit
and evaluate rho–f models.
"""

import itertools
import logging
import math
import warnings
from typing import Any, Callable, Dict, List, Literal, Tuple, Union

import numpy as np

from .db import read_items_by, read_measurements_by

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


def distance_profile_value(
    measurement_id: int,
    measurement_type: str = "earthing_impedance",
    algorithm: Literal["maximum", "62_percent", "minimum_gradient", "minimum_stddev", "inverse"] = "maximum",
    window: int = 3,
) -> Dict[str, Any]:
    """
    Reduce a distance–value profile (impedance or voltage) to a single characteristic value.

    Algorithms:
      - maximum: largest measured value.
      - 62_percent: interpolate the value at 62% of the distance_to_current_injection_m.
      - minimum_gradient: point with the smallest |dy/dx|.
      - minimum_stddev: sliding window with minimum stddev → take its maximum value.
      - inverse: fit 1/value vs 1/distance and return value at distance → infinity.

    Args:
        measurement_id: Measurement.id to read items from.
        measurement_type: MeasurementItem.measurement_type to filter by.
        algorithm: Algorithm selector.
        window: Window size for the minimum_stddev algorithm.

    Returns:
        Dict with the computed value, distance, and underlying data points.

    Raises:
        RuntimeError: on database read failures.
        ValueError: on missing data or unsupported algorithm.
    """
    try:
        items, _ = read_items_by(
            measurement_id=measurement_id, measurement_type=measurement_type
        )
    except Exception as exc:
        logger.error(
            "Error reading %s items for measurement %s: %s",
            measurement_type,
            measurement_id,
            exc,
        )
        raise RuntimeError(
            f"Failed to load {measurement_type} data for measurement {measurement_id}"
        ) from exc

    points: List[Dict[str, Any]] = []
    injection_candidates: List[float] = []
    units: List[str] = []

    for item in items:
        dist = item.get("measurement_distance_m")
        val = item.get("value")
        if dist is None or val is None:
            warnings.warn(
                f"MeasurementItem id={item.get('id')} missing distance or value; skipping",
                UserWarning,
            )
            continue

        inj = item.get("distance_to_current_injection_m")
        if inj is not None:
            try:
                injection_candidates.append(float(inj))
            except Exception:
                warnings.warn(
                    f"MeasurementItem id={item.get('id')} has invalid distance_to_current_injection_m; skipping that field",
                    UserWarning,
                )

        if item.get("unit"):
            units.append(str(item.get("unit")))

        try:
            point = {
                "item_id": item.get("id"),
                "distance_m": float(dist),
                "value": float(val),
                "unit": item.get("unit"),
                "distance_to_current_injection_m": inj
                if inj is None
                else float(inj),
                "description": item.get("description"),
            }
        except Exception:
            warnings.warn(
                f"Could not convert MeasurementItem id={item.get('id')} to floats; skipping",
                UserWarning,
            )
            continue
        points.append(point)

    if not points:
        raise ValueError(
            f"No {measurement_type} items with distance/value found for measurement {measurement_id}"
        )

    points.sort(key=lambda p: p["distance_m"])

    def _dedupe_by_interpolation(raw_points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """For duplicate distances, keep the point closest to linear interpolation."""
        by_dist: Dict[float, List[Dict[str, Any]]] = {}
        for p in raw_points:
            by_dist.setdefault(p["distance_m"], []).append(p)
        distances = sorted(by_dist.keys())

        def _mean_val(d: float) -> float:
            vals = [pp["value"] for pp in by_dist[d] if pp.get("value") is not None]
            return float(sum(vals) / len(vals)) if vals else 0.0

        selected: List[Dict[str, Any]] = []
        for idx, dist in enumerate(distances):
            group = by_dist[dist]
            if len(group) == 1:
                selected.append(group[0])
                continue

            try:
                if idx == 0 and len(distances) > 1:
                    x1, y1 = 0.0, 0.0
                    x2 = distances[idx + 1]
                    y2 = _mean_val(x2)
                elif idx == len(distances) - 1 and len(distances) >= 2:
                    x2 = distances[idx - 1]
                    y2 = _mean_val(x2)
                    if idx >= 2:
                        x1 = distances[idx - 2]
                        y1 = _mean_val(x1)
                    else:
                        x1, y1 = x2, y2
                else:
                    x1 = distances[idx - 1]
                    y1 = _mean_val(x1)
                    x2 = distances[idx + 1]
                    y2 = _mean_val(x2)

                if x2 == x1:
                    expected = _mean_val(dist)
                else:
                    expected = y1 + (dist - x1) * (y2 - y1) / (x2 - x1)
            except Exception:
                expected = _mean_val(dist)

            best = min(group, key=lambda p: abs(p["value"] - expected))
            selected.append(best)

        selected.sort(key=lambda p: p["distance_m"])
        return selected

    points = _dedupe_by_interpolation(points)

    # Determine a consistent injection distance if provided
    injection_distance = None
    if injection_candidates:
        uniq = {round(val, 6) for val in injection_candidates}
        injection_distance = injection_candidates[0]
        if len(uniq) > 1:
            warnings.warn(
                "distance_to_current_injection_m is not consistent across items; using the first value",
                UserWarning,
            )

    def _algo_maximum() -> Tuple[float, float, Dict[str, Any]]:
        best = max(points, key=lambda p: p["value"])
        return best["value"], best["distance_m"], {"point": best}

    def _algo_62_percent() -> Tuple[float, float, Dict[str, Any]]:
        if injection_distance is None:
            raise ValueError(
                "distance_to_current_injection_m is required for the 62_percent algorithm"
            )
        target = 0.62 * float(injection_distance)
        nearest = sorted(points, key=lambda p: abs(p["distance_m"] - target))[:3]
        # ensure strictly increasing x for np.interp
        ordered = []
        seen: set[float] = set()
        for p in sorted(nearest, key=lambda p: p["distance_m"]):
            if p["distance_m"] in seen:
                continue
            seen.add(p["distance_m"])
            ordered.append(p)
        if len(ordered) < 2:
            raise ValueError("Need at least two unique distances for 62_percent interpolation")
        xs = [p["distance_m"] for p in ordered]
        ys = [p["value"] for p in ordered]
        interpolated = float(np.interp(target, xs, ys))
        return interpolated, target, {
            "target_distance_m": target,
            "used_points": ordered,
        }

    def _algo_minimum_gradient() -> Tuple[float, float, Dict[str, Any]]:
        if len(points) < 2:
            raise ValueError("minimum_gradient requires at least two points")
        distances = np.array([p["distance_m"] for p in points], dtype=float)
        values = np.array([p["value"] for p in points], dtype=float)
        gradients = np.gradient(values, distances)
        idx = int(np.argmin(np.abs(gradients)))
        return points[idx]["value"], points[idx]["distance_m"], {
            "distance_m": points[idx]["distance_m"],
            "gradient": float(gradients[idx]),
        }

    def _algo_minimum_stddev() -> Tuple[float, float, Dict[str, Any]]:
        if window < 2:
            raise ValueError("window must be >= 2 for minimum_stddev")
        if len(points) < window:
            raise ValueError(
                f"minimum_stddev requires at least {window} points; have {len(points)}"
            )
        best_std = float("inf")
        best_window: List[Dict[str, Any]] | None = None
        for start in range(0, len(points) - window + 1):
            segment = points[start : start + window]
            vals = [p["value"] for p in segment]
            std = float(np.std(vals))
            if std < best_std:
                best_std = std
                best_window = segment
        assert best_window is not None
        peak = max(best_window, key=lambda p: p["value"])
        return peak["value"], peak["distance_m"], {
            "window_size": window,
            "stddev": best_std,
            "window_points": best_window,
        }

    def _algo_inverse() -> Tuple[float, float, Dict[str, Any]]:
        if len(points) < 2:
            raise ValueError("inverse algorithm requires at least two points")
        distances = np.array([p["distance_m"] for p in points], dtype=float)
        values = np.array([p["value"] for p in points], dtype=float)
        if np.any(distances == 0) or np.any(values == 0):
            raise ValueError("Distances and values must be non-zero for inverse algorithm")
        x = 1.0 / distances
        y = 1.0 / values
        coeffs = np.polyfit(x, y, 1)
        slope, intercept = float(coeffs[0]), float(coeffs[1])
        if intercept == 0:
            raise ValueError("Inverse fit produced zero intercept; cannot compute limit")
        limit_value = 1.0 / intercept
        return limit_value, float("inf"), {"slope": slope, "intercept": intercept}

    algo_key = algorithm.lower().strip().replace(" ", "_").replace("-", "_")
    if algo_key == "62%":
        algo_key = "62_percent"
    algo_map: Dict[str, Callable[[], Tuple[float, float, Dict[str, Any]]]] = {
        "maximum": _algo_maximum,
        "62_percent": _algo_62_percent,
        "minimum_gradient": _algo_minimum_gradient,
        "minimum_stddev": _algo_minimum_stddev,
        "inverse": _algo_inverse,
    }

    if algo_key not in algo_map:
        raise ValueError(f"Unsupported algorithm '{algorithm}'")

    result_value, result_distance, details = algo_map[algo_key]()

    unit = units[0] if units else None
    if units and len({u for u in units}) > 1:
        warnings.warn("Mixed units across items; using the first one for output", UserWarning)

    return {
        "measurement_id": measurement_id,
        "measurement_type": measurement_type,
        "algorithm": algo_key,
        "result_value": float(result_value),
        "result_distance_m": float(result_distance),
        "unit": unit,
        "distance_to_current_injection_m": injection_distance,
        "data_points": points,
        "details": details,
    }


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

def voltage_vt_epr(
    measurement_ids: Union[int, List[int]],
    frequency: float = 50.0
) -> Union[Dict[str, float], Dict[int, Dict[str, float]]]:
    """
    Calculate per-ampere touch voltages and EPR for measurements at a given frequency.

    Mandatory data:
      - earthing_impedance (Z in Ω = V/A)
      - earthing_current   (I in A)

    Optional data (include whichever is present):
      - prospective_touch_voltage (V)
      - touch_voltage             (V)

    Returns:
      - If single ID: a dict {key: value, ...}
      - If multiple IDs: a dict {measurement_id: {...}, ...}

    Keys in each result dict:
      - epr        : Earth potential rise = Z * I
      - vtp_min
      - vtp_max    (if prospective_touch_voltage data exist)
      - vt_min
      - vt_max     (if touch_voltage data exist)
    """
    single = isinstance(measurement_ids, int)
    ids = [measurement_ids] if single else list(measurement_ids)
    results: Dict[int, Dict[str, float]] = {}

    for mid in ids:
        # 1) Mandatory: impedance Z (V/A) at this frequency
        try:
            imp_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="earthing_impedance",
                frequency_hz=frequency
            )
            Z = float(imp_items[0]["value"])
        except Exception:
            warnings.warn(f"Measurement {mid}: missing earthing_impedance@{frequency}Hz → skipping", UserWarning)
            continue

        # 2) Mandatory: current I (A) at this frequency
        try:
            cur_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="earthing_current",
                frequency_hz=frequency
            )
            I = float(cur_items[0]["value"])
            if I == 0:
                raise ValueError("zero current")
        except Exception:
            warnings.warn(f"Measurement {mid}: missing or zero earthing_current@{frequency}Hz → skipping", UserWarning)
            continue

        entry: Dict[str, float] = {}

        # 3) Set EPR
        entry["epr"] = Z 

        # 4) Optional: prospective touch voltage (V/A)
        try:
            vtp_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="prospective_touch_voltage",
                frequency_hz=frequency
            )
            vtp_vals = [float(it["value"]) / I for it in vtp_items]
            entry["vtp_min"] = min(vtp_vals)
            entry["vtp_max"] = max(vtp_vals)
        except Exception:
            warnings.warn(f"Measurement {mid}: no prospective_touch_voltage@{frequency}Hz", UserWarning)

        # 5) Optional: actual touch voltage (V/A)
        try:
            vt_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="touch_voltage",
                frequency_hz=frequency
            )
            vt_vals = [float(it["value"]) / I for it in vt_items]
            entry["vt_min"] = min(vt_vals)
            entry["vt_max"] = max(vt_vals)
        except Exception:
            warnings.warn(f"Measurement {mid}: no touch_voltage@{frequency}Hz", UserWarning)

        results[mid] = entry

    # if single measurement, return its dict directly (or empty dict if skipped)
    return results[ids[0]] if single else results


def _current_item_to_complex(item: Dict[str, Any]) -> complex:
    """
    Convert a MeasurementItem-like dict into a complex current (A).

    Prefers rectangular components if present, otherwise uses magnitude/angle.
    """
    real = item.get("value_real")
    imag = item.get("value_imag")
    if real is not None or imag is not None:
        return complex(float(real or 0.0), float(imag or 0.0))

    value = item.get("value")
    if value is None:
        raise ValueError(f"MeasurementItem id={item.get('id')} has no current value")

    angle_deg = item.get("value_angle_deg")
    try:
        magnitude = float(value)
        if angle_deg is None:
            return complex(magnitude, 0.0)
        angle_rad = math.radians(float(angle_deg))
    except Exception as exc:
        raise ValueError(
            f"Invalid magnitude/angle for MeasurementItem id={item.get('id')}"
        ) from exc

    return complex(
        magnitude * math.cos(angle_rad),
        magnitude * math.sin(angle_rad),
    )


def shield_currents_for_location(
    location_id: int, frequency_hz: float | None = None
) -> List[Dict[str, Any]]:
    """
    Collect all shield_current MeasurementItems for a given location.

    Args:
        location_id: Location.id to search under.
        frequency_hz: Optional frequency filter.

    Returns:
        List of item dicts (one per shield_current) with measurement_id included.

    Raises:
        RuntimeError: if reading measurements fails.
    """
    try:
        measurements, _ = read_measurements_by(location_id=location_id)
    except Exception as e:
        logger.error(
            "Error reading measurements for location_id=%s: %s", location_id, e
        )
        raise RuntimeError(
            f"Failed to read measurements for location_id={location_id}"
        ) from e

    candidates: List[Dict[str, Any]] = []
    for meas in measurements:
        mid = meas.get("id")
        for item in meas.get("items", []):
            if item.get("measurement_type") != "shield_current":
                continue
            if frequency_hz is not None:
                freq = item.get("frequency_hz")
                try:
                    if freq is None or float(freq) != float(frequency_hz):
                        continue
                except Exception:
                    continue
            candidate = {
                "id": item.get("id"),
                "measurement_id": mid,
                "frequency_hz": item.get("frequency_hz"),
                "value": item.get("value"),
                "value_angle_deg": item.get("value_angle_deg"),
                "value_real": item.get("value_real"),
                "value_imag": item.get("value_imag"),
                "unit": item.get("unit"),
                "description": item.get("description"),
            }
            candidates.append(candidate)

    if not candidates:
        warnings.warn(
            f"No shield_current items found for location_id={location_id}",
            UserWarning,
        )
    return candidates


def calculate_split_factor(
    earth_fault_current_id: int, shield_current_ids: List[int]
) -> Dict[str, Any]:
    """
    Compute the split factor and local earthing current from selected shield currents.

    The caller is responsible for choosing shield_current items with a consistent
    angle reference. Use `shield_currents_for_location` to list candidates and
    pass the chosen item IDs here.

    Args:
        earth_fault_current_id: MeasurementItem.id carrying the total earth fault current.
        shield_current_ids: MeasurementItem.ids of shield_current values to subtract.

    Returns:
        Dict with:
            - split_factor (float)
            - shield_current_sum (magnitude/angle/real/imag)
            - local_earthing_current (magnitude/angle/real/imag)
            - earth_fault_current (magnitude/angle/real/imag)

    Raises:
        ValueError: if inputs are missing or zero.
        RuntimeError: if database access fails.
    """
    if not shield_current_ids:
        raise ValueError("Provide at least one shield_current id for split factor")

    try:
        earth_items, _ = read_items_by(
            id=earth_fault_current_id, measurement_type="earth_fault_current"
        )
    except Exception as e:
        logger.error(
            "Error reading earth_fault_current id=%s: %s", earth_fault_current_id, e
        )
        raise RuntimeError("Failed to read earth_fault_current item") from e

    if not earth_items:
        raise ValueError(f"No earth_fault_current item found with id={earth_fault_current_id}")

    try:
        shield_items, _ = read_items_by(
            measurement_type="shield_current", id__in=shield_current_ids
        )
    except Exception as e:
        logger.error(
            "Error reading shield_current ids=%s: %s", shield_current_ids, e
        )
        raise RuntimeError("Failed to read shield_current items") from e

    if not shield_items:
        raise ValueError("No shield_current items found for the provided IDs")

    found_ids = {it.get("id") for it in shield_items}
    missing = [sid for sid in shield_current_ids if sid not in found_ids]
    if missing:
        warnings.warn(
            f"shield_current IDs not found and skipped: {missing}", UserWarning
        )

    earth_current = _current_item_to_complex(earth_items[0])
    if abs(earth_current) == 0:
        raise ValueError("Earth fault current magnitude is zero; cannot compute split factor")

    shield_vectors = [_current_item_to_complex(it) for it in shield_items]
    shield_sum = sum(shield_vectors, 0 + 0j)

    split_factor = 1 - (abs(shield_sum) / abs(earth_current))
    local_current = earth_current - shield_sum

    def _angle_deg(val: complex) -> float:
        return 0.0 if val == 0 else math.degrees(math.atan2(val.imag, val.real))

    return {
        "split_factor": split_factor,
        "shield_current_sum": {
            "value": abs(shield_sum),
            "value_angle_deg": _angle_deg(shield_sum),
            "value_real": shield_sum.real,
            "value_imag": shield_sum.imag,
        },
        "local_earthing_current": {
            "value": abs(local_current),
            "value_angle_deg": _angle_deg(local_current),
            "value_real": local_current.real,
            "value_imag": local_current.imag,
        },
        "earth_fault_current": {
            "value": abs(earth_current),
            "value_angle_deg": _angle_deg(earth_current),
            "value_real": earth_current.real,
            "value_imag": earth_current.imag,
        },
    }
