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
import os
import warnings
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, Sequence, Tuple, Union

import numpy as np

from ..core.db import read_items_by, read_measurements_by

# configure module‐level logger
logger = logging.getLogger(__name__)

try:
    import mlx.core as mx  # type: ignore
    _MLX_AVAILABLE = True
except Exception:
    mx = None  # type: ignore
    _MLX_AVAILABLE = False

try:
    from scipy import special as _scipy_special  # type: ignore
    _SCIPY_AVAILABLE = True
except Exception:
    _scipy_special = None  # type: ignore
    _SCIPY_AVAILABLE = False


def _resolve_math_backend(
    backend: Literal["auto", "numpy", "mlx"] = "auto",
) -> Tuple[str, Any]:
    """
    Resolve the math backend (NumPy or MLX) for lightweight computations.

    The backend can be set explicitly or via ``GROUNDMEAS_MATH_BACKEND`` when
    ``backend="auto"``. MLX is optional and only used if installed.
    """
    backend_key = backend.strip().lower()
    if backend_key == "auto":
        env = os.environ.get("GROUNDMEAS_MATH_BACKEND")
        if env:
            backend_key = env.strip().lower()
        elif _MLX_AVAILABLE:
            backend_key = "mlx"
        else:
            backend_key = "numpy"

    if backend_key == "mlx":
        if not _MLX_AVAILABLE:
            warnings.warn(
                "MLX backend requested but not installed; falling back to NumPy",
                UserWarning,
            )
            return "numpy", np
        return "mlx", mx

    return "numpy", np


def impedance_over_frequency(
    measurement_ids: Union[int, List[int]],
) -> Union[Dict[float, float], Dict[int, Dict[float, float]]]:
    """
    Map frequency (Hz) to impedance magnitude (Ω) for one or many measurements.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Measurement ID or list of IDs to query for ``earthing_impedance`` items.

    Returns
    -------
    dict
        If a single ID is provided: ``{frequency_hz: impedance_value}``.
        If multiple IDs: ``{measurement_id: {frequency_hz: impedance_value}}``.

    Raises
    ------
    RuntimeError
        If database access fails.
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
) -> Union[
    Dict[float, Dict[str, Optional[float]]],
    Dict[int, Dict[float, Dict[str, Optional[float]]]],
]:
    """
    Map frequency to real/imag components of impedance.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Measurement ID or list of IDs.

    Returns
    -------
    dict
        If single ID: ``{frequency_hz: {"real": R or None, "imag": X or None}}``.
        If multiple IDs: ``{measurement_id: {frequency_hz: {"real": R or None, "imag": X or None}}}``.

    Raises
    ------
    RuntimeError
        If database access fails.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, Dict[float, Dict[str, Optional[float]]]] = {}

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

        freq_map: Dict[float, Dict[str, Optional[float]]] = {}
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
    algorithm: Literal[
        "maximum",
        "62_percent",
        "minimum_gradient",
        "minimum_stddev",
        "inverse",
    ] = "maximum",
    window: int = 3,
) -> Dict[str, Any]:
    """
    Reduce a distance–value profile (impedance or voltage) to a single characteristic value.

    Parameters
    ----------
    measurement_id : int
        Measurement ID to read items from.
    measurement_type : str, default "earthing_impedance"
        MeasurementItem type to filter by.
    algorithm : {"maximum", "62_percent", "minimum_gradient", "minimum_stddev", "inverse"}, default "maximum"
        Reduction algorithm.
    window : int, default 3
        Window size for the ``minimum_stddev`` algorithm.

    Returns
    -------
    dict
        Computed value, distance, unit, injection distance, data points, and algorithm details.

    Raises
    ------
    RuntimeError
        On database read failures.
    ValueError
        On missing data or unsupported algorithm.
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
            raise ValueError(
                "Need at least two unique distances for 62_percent interpolation"
            )
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
    if units and len(set(units)) > 1:
        warnings.warn(
            "Mixed units across items; using the first one for output",
            UserWarning,
        )

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


# --- Layered earth soil modeling (Wenner/Schlumberger) -----------------------

DX_DEFAULT = float(math.log(10.0) / 3.0)

SCHLUMBERGER_SHORT: Dict[int, float] = {
    -2: -0.0723,
    -1: 0.3999,
    0: 0.3492,
    1: 0.1675,
    2: 0.0858,
    3: 0.0358,
    4: 0.0198,
    5: 0.0067,
    6: 0.0076,
}

WENNER_FILTER: Dict[int, float] = {
    -2: 0.0212,
    -1: -0.1199,
    0: 0.4226,
    1: 0.3553,
    2: 0.1664,
    3: 0.0873,
    4: 0.0345,
    5: 0.0208,
    6: 0.0118,
}
WENNER_SHIFT_FACTOR = 1.616

SCHLUMBERGER_INVERSE: Dict[int, float] = {
    -3: 0.0225,
    -2: -0.0499,
    -1: 0.1064,
    0: 0.1854,
    1: 1.9720,
    2: -1.5716,
    3: 0.4018,
    4: -0.0814,
    5: 0.0148,
}
SCHL_INV_SHIFT_FACTOR = 1.05


def _design_inverse_fir(
    direct_coeffs: Dict[int, float],
    L: int = 21,
    reg: float = 1e-2,
) -> Dict[int, float]:
    js = np.array(sorted(direct_coeffs.keys()), dtype=int)

    k_min = -(L // 2)
    k_max = k_min + L - 1
    ks = np.arange(k_min, k_max + 1, dtype=int)

    c_min = int(js.min() + ks.min())
    c_max = int(js.max() + ks.max())
    cs = np.arange(c_min, c_max + 1, dtype=int)

    C = np.zeros((len(cs), len(ks)), dtype=float)
    for p, c_idx in enumerate(cs):
        for r, k_idx in enumerate(ks):
            j_needed = c_idx - k_idx
            if j_needed in direct_coeffs:
                C[p, r] = direct_coeffs[j_needed]

    d = np.zeros(len(cs), dtype=float)
    d[int(0 - c_min)] = 1.0

    D2 = np.zeros((len(ks) - 2, len(ks)), dtype=float)
    for i in range(len(ks) - 2):
        D2[i, i] = 1.0
        D2[i, i + 1] = -2.0
        D2[i, i + 2] = 1.0

    A = np.vstack([C, np.sqrt(reg) * D2])
    b = np.linalg.lstsq(A, np.r_[d, np.zeros(D2.shape[0])], rcond=None)[0]
    return {int(k): float(b[i]) for i, k in enumerate(ks)}


WENNER_INVERSE = _design_inverse_fir(WENNER_FILTER, L=21, reg=1e-2)


def _loglog_extrapolate(y: np.ndarray, n_left: int, n_right: int) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    if len(y) < 3:
        return np.r_[np.full(n_left, y[0]), y, np.full(n_right, y[-1])]

    ly = np.log(y)
    m_left = ly[1] - ly[0]
    m_right = ly[-1] - ly[-2]

    left = np.exp(ly[0] - m_left * np.arange(n_left, 0, -1))
    right = np.exp(ly[-1] + m_right * np.arange(1, n_right + 1))
    return np.concatenate([left, y, right])


def _apply_filter(values: np.ndarray, coeffs: Dict[int, float]) -> np.ndarray:
    js = sorted(coeffs.keys())
    pad_left = max(0, max(js))
    pad_right = max(0, -min(js))

    vp = _loglog_extrapolate(values, n_left=pad_left, n_right=pad_right)

    out = np.zeros_like(values, dtype=float)
    for m in range(len(values)):
        acc = 0.0
        for j, aj in coeffs.items():
            acc += aj * vp[pad_left + m - j]
        out[m] = acc
    return out


def _resample_log_grid(x: np.ndarray, y: np.ndarray, dx: float) -> Tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if np.any(y <= 0):
        raise ValueError("Need y>0 for log interpolation")

    x0, x1 = float(x.min()), float(x.max())
    n = int(np.floor((x1 - x0) / dx)) + 1
    xg = x0 + dx * np.arange(n, dtype=float)

    logy = np.log(y)
    logy_interp = np.interp(xg, x, logy)
    yg = np.exp(logy_interp)
    return xg, yg


@dataclass(frozen=True)
class LayeredEarthModel:
    rho_layers: Tuple[float, ...]
    thicknesses_m: Tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if len(self.rho_layers) not in {1, 2, 3}:
            raise ValueError("rho_layers must define 1, 2, or 3 layers")
        if len(self.thicknesses_m) != max(0, len(self.rho_layers) - 1):
            raise ValueError("thicknesses_m must have length len(rho_layers)-1")
        if any(r <= 0 for r in self.rho_layers):
            raise ValueError("All resistivities must be > 0")
        if any(h <= 0 for h in self.thicknesses_m):
            raise ValueError("All thicknesses must be > 0")

    @property
    def n_layers(self) -> int:
        return len(self.rho_layers)

    def transform_T(self, lam: np.ndarray, *, backend: Literal["auto", "numpy", "mlx"] = "auto") -> np.ndarray:
        lam_arr = np.asarray(lam, dtype=float)
        if lam_arr.ndim != 1:
            raise ValueError("lam must be 1D")
        if np.any(lam_arr < 0):
            raise ValueError("lam must be >= 0")

        backend_name, _ = _resolve_math_backend(backend)
        if backend_name == "mlx":
            return self._transform_T_mlx(lam_arr)
        return self._transform_T_numpy(lam_arr)

    def _transform_T_numpy(self, lam: np.ndarray) -> np.ndarray:
        rhos = np.asarray(self.rho_layers, dtype=float)
        thks = np.asarray(self.thicknesses_m, dtype=float)

        r_eff = np.zeros_like(lam)
        for i in range(len(rhos) - 1, 0, -1):
            rho_i = rhos[i - 1]
            rho_ip1 = rhos[i]
            k = (rho_ip1 - rho_i) / (rho_ip1 + rho_i)
            r_eff = (k + r_eff) / (1.0 + k * r_eff)
            d = thks[i - 1]
            r_eff = r_eff * np.exp(-2.0 * lam * d)

        return rhos[0] * (1.0 + r_eff) / (1.0 - r_eff)

    def _transform_T_mlx(self, lam: np.ndarray) -> np.ndarray:
        lam_mx = mx.array(lam.astype(np.float32))
        rhos_mx = mx.array(np.asarray(self.rho_layers, dtype=np.float32))
        thks_mx = (
            mx.array(np.asarray(self.thicknesses_m, dtype=np.float32))
            if self.thicknesses_m
            else mx.array(np.array([], dtype=np.float32))
        )

        r_eff = mx.zeros_like(lam_mx)
        for i in range(len(self.rho_layers) - 1, 0, -1):
            rho_i = rhos_mx[i - 1]
            rho_ip1 = rhos_mx[i]
            k = (rho_ip1 - rho_i) / (rho_ip1 + rho_i)
            r_eff = (k + r_eff) / (1.0 + k * r_eff)
            d = thks_mx[i - 1]
            r_eff = r_eff * mx.exp(-2.0 * lam_mx * d)

        T = rhos_mx[0] * (1.0 + r_eff) / (1.0 - r_eff)
        return np.array(T)


def _layer_bounds(
    rho_layers: Sequence[float],
    thicknesses_m: Sequence[float],
) -> List[Dict[str, Any]]:
    layers_out: List[Dict[str, Any]] = []
    top = 0.0
    for idx, rho in enumerate(rho_layers):
        is_last = idx == len(rho_layers) - 1
        thickness = None if is_last else float(thicknesses_m[idx])
        bottom = None if is_last else float(top + thickness)
        layers_out.append(
            {
                "layer": idx + 1,
                "rho_ohm_m": float(rho),
                "top_depth_m": float(top),
                "bottom_depth_m": bottom,
                "thickness_m": thickness,
            }
        )
        if thickness is not None:
            top += thickness
    return layers_out


def _simulate_wenner_filter(
    model: LayeredEarthModel,
    spacing_m: np.ndarray,
    *,
    dx: float = DX_DEFAULT,
    backend: Literal["auto", "numpy", "mlx"] = "auto",
) -> np.ndarray:
    x = np.log(spacing_m)
    xg, _ = _resample_log_grid(x, np.ones_like(spacing_m), dx)
    a_grid = np.exp(xg)
    u_in = a_grid / WENNER_SHIFT_FACTOR
    lam = 1.0 / u_in

    T_grid = model.transform_T(lam, backend=backend)
    rhoa_grid = _apply_filter(T_grid, WENNER_INVERSE)
    rhoa_grid = np.maximum(rhoa_grid, 1e-30)

    return np.exp(np.interp(np.log(spacing_m), xg, np.log(rhoa_grid)))


def _simulate_schlumberger_filter(
    model: LayeredEarthModel,
    spacing_m: np.ndarray,
    *,
    ab_is_full: bool = True,
    dx: float = DX_DEFAULT,
    backend: Literal["auto", "numpy", "mlx"] = "auto",
) -> np.ndarray:
    s = spacing_m / 2.0 if ab_is_full else spacing_m
    x = np.log(s)
    xg, _ = _resample_log_grid(x, np.ones_like(s), dx)
    s_grid = np.exp(xg)
    u_in = s_grid / SCHL_INV_SHIFT_FACTOR
    lam = 1.0 / u_in

    T_grid = model.transform_T(lam, backend=backend)
    rhoa_grid = _apply_filter(T_grid, SCHLUMBERGER_INVERSE)
    rhoa_grid = np.maximum(rhoa_grid, 1e-30)

    return np.exp(np.interp(np.log(s), xg, np.log(rhoa_grid)))


def _lambda_grid_deltaT(
    model: LayeredEarthModel,
    r_min: float,
    depth_scale: float,
    n_lam: int,
) -> np.ndarray:
    lam_min = 1e-6 / max(depth_scale, 1.0)
    if model.thicknesses_m:
        h_min = float(min(model.thicknesses_m))
        lam_max = 20.0 / max(h_min, 1e-6)
    else:
        lam_max = 80.0 / max(r_min, 1e-6)
    return np.logspace(np.log10(lam_min), np.log10(lam_max), int(n_lam))


def _rhoa_collinear_integral(
    model: LayeredEarthModel,
    r_am: np.ndarray,
    r_an: np.ndarray,
    r_bm: np.ndarray,
    r_bn: np.ndarray,
    *,
    n_lam: int = 6000,
    backend: Literal["auto", "numpy", "mlx"] = "auto",
) -> np.ndarray:
    if not _SCIPY_AVAILABLE:
        raise RuntimeError("Integral forward model requires scipy to be installed")

    r_am = np.asarray(r_am, dtype=float)
    r_an = np.asarray(r_an, dtype=float)
    r_bm = np.asarray(r_bm, dtype=float)
    r_bn = np.asarray(r_bn, dtype=float)

    if not (r_am.shape == r_an.shape == r_bm.shape == r_bn.shape):
        raise ValueError("distance arrays must share shape")
    if np.any(r_am <= 0) or np.any(r_an <= 0) or np.any(r_bm <= 0) or np.any(r_bn <= 0):
        raise ValueError("all distances must be > 0")

    n_meas = len(r_am)
    rho1 = float(model.rho_layers[0])

    if model.n_layers == 1:
        return np.full(n_meas, rho1, dtype=float)

    g = (1.0 / r_am - 1.0 / r_an - 1.0 / r_bm + 1.0 / r_bn)
    K = 2.0 * math.pi / g

    r_min = float(np.min([r_am.min(), r_an.min(), r_bm.min(), r_bn.min()]))
    depth_scale = float(
        np.max([r_am.max(), r_an.max(), r_bm.max(), r_bn.max(), sum(model.thicknesses_m)])
    )

    lam = _lambda_grid_deltaT(model, r_min=r_min, depth_scale=depth_scale, n_lam=n_lam)
    t = np.log(lam)
    dt = float(np.mean(np.diff(t)))
    w = lam * dt

    T = model.transform_T(lam, backend=backend)
    dT = T - rho1

    L = lam[:, None]
    kern = (
        _scipy_special.j0(L * r_am[None, :])
        - _scipy_special.j0(L * r_an[None, :])
        - _scipy_special.j0(L * r_bm[None, :])
        + _scipy_special.j0(L * r_bn[None, :])
    )

    corr = (K / (2.0 * math.pi)) * np.sum((dT[:, None] * kern) * w[:, None], axis=0)
    return rho1 + corr


def _schlumberger_distances(
    AB: np.ndarray,
    MN: Union[float, np.ndarray],
    *,
    ab_is_full: bool = True,
    mn_is_full: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    s = AB / 2.0 if ab_is_full else AB
    m = MN / 2.0 if mn_is_full else MN
    if np.any(s <= m):
        raise ValueError("Invalid Schlumberger geometry: need AB/2 > MN/2")

    r_am = s - m
    r_an = s + m
    r_bm = r_an
    r_bn = r_am
    return r_am, r_an, r_bm, r_bn


def soil_resistivity_profile_detailed(
    measurement_id: int,
    method: Literal["wenner", "schlumberger"] = "wenner",
    value_kind: Literal["auto", "resistance", "resistivity"] = "auto",
    depth_factor: Optional[float] = None,
    ab_is_full: bool = False,
    mn_is_full: bool = False,
) -> List[Dict[str, Any]]:
    """
    Build a depth-resistivity profile from soil resistivity measurements.

    This function reads MeasurementItem rows with ``measurement_type="soil_resistivity"``
    and derives apparent resistivity and an effective depth for each point.

    Apparent resistivity formulas (R in ohms, spacings in meters):

    Wenner array:
        rho_a = 2 * pi * a * R

    Schlumberger array (AB = current electrode spacing, MN = potential spacing):
        rho_a = pi * (AB^2 - MN^2) / (4 * MN) * R

    If your data stores half-spacings (a = AB/2, b = MN/2), the Schlumberger
    formula becomes:
        rho_a = pi * (a^2 - b^2) / (2 * b) * R

    Effective depth is approximated as:
        z = depth_factor * spacing

    where spacing is ``a`` for Wenner and ``AB/2`` for Schlumberger. The default
    ``depth_factor`` is 0.5, so Schlumberger depth corresponds to roughly 0.25*AB.

    Parameters
    ----------
    measurement_id : int
        Measurement ID that contains soil_resistivity items.
    method : {"wenner", "schlumberger"}, default "wenner"
        Array method used for the resistivity survey.
    value_kind : {"auto", "resistance", "resistivity"}, default "auto"
        Interpret ``value`` as resistance (ohms) or resistivity (ohm-m). In auto
        mode, units containing "ohm" and "m" are treated as resistivity.
    depth_factor : float, optional
        Override the depth multiplier applied to spacing. Must be > 0.
    ab_is_full : bool, default False
        Interpret ``measurement_distance_m`` as full AB for Schlumberger. When False,
        it is treated as AB/2 (recommended for stored items).
    mn_is_full : bool, default False
        Interpret ``distance_to_current_injection_m`` as full MN for Schlumberger.

    Returns
    -------
    list[dict]
        Sorted list of points with keys: ``depth_m``, ``rho_ohm_m``, ``spacing_m``,
        ``effective_spacing_m``, optional ``mn_m``, ``method``, ``value_kind``,
        and ``item_ids``.

    Raises
    ------
    RuntimeError
        If database access fails.
    ValueError
        If no valid soil_resistivity points are found or inputs are invalid.
    """
    method_key = method.strip().lower()
    if method_key not in {"wenner", "schlumberger"}:
        raise ValueError(f"Unsupported method '{method}'")

    kind = value_kind.strip().lower()
    if kind not in {"auto", "resistance", "resistivity"}:
        raise ValueError(f"Unsupported value_kind '{value_kind}'")

    depth_factor_used = 0.5 if depth_factor is None else float(depth_factor)
    if depth_factor_used <= 0:
        raise ValueError("depth_factor must be > 0")

    try:
        items, _ = read_items_by(
            measurement_id=measurement_id, measurement_type="soil_resistivity"
        )
    except Exception as exc:
        logger.error(
            "Error reading soil_resistivity items for measurement %s: %s",
            measurement_id,
            exc,
        )
        raise RuntimeError(
            f"Failed to load soil_resistivity for measurement {measurement_id}"
        ) from exc

    if not items:
        raise ValueError(f"No soil_resistivity data for measurement {measurement_id}")

    raw_points: List[Dict[str, Any]] = []

    for item in items:
        spacing = item.get("measurement_distance_m")
        raw_value = item.get("value")
        if spacing is None or raw_value is None:
            warnings.warn(
                f"MeasurementItem id={item.get('id')} missing spacing or value; skipping",
                UserWarning,
            )
            continue

        try:
            spacing_m = float(spacing)
            if spacing_m <= 0:
                raise ValueError("non-positive spacing")
        except Exception:
            warnings.warn(
                f"MeasurementItem id={item.get('id')} has invalid spacing; skipping",
                UserWarning,
            )
            continue

        try:
            value = float(raw_value)
        except Exception:
            warnings.warn(
                f"MeasurementItem id={item.get('id')} has invalid value; skipping",
                UserWarning,
            )
            continue

        unit = item.get("unit")
        local_kind = kind
        if kind == "auto":
            local_kind = "resistivity"
            if unit:
                unit_text = str(unit)
                unit_str = unit_text.lower()
                if not (("ohm" in unit_str or "Ω" in unit_text) and "m" in unit_str):
                    local_kind = "resistance"
            else:
                local_kind = "resistance"

        effective_spacing_m = spacing_m
        if method_key == "schlumberger" and ab_is_full:
            effective_spacing_m = spacing_m / 2.0

        mn_m = None
        mn_effective_m = None
        if method_key == "schlumberger":
            mn_raw = item.get("distance_to_current_injection_m")
            if mn_raw is not None:
                try:
                    mn_m = float(mn_raw)
                    if mn_m <= 0:
                        raise ValueError("non-positive MN")
                except Exception:
                    if local_kind == "resistance":
                        warnings.warn(
                            f"MeasurementItem id={item.get('id')} has invalid MN spacing; skipping",
                            UserWarning,
                        )
                    mn_m = None
                else:
                    mn_effective_m = mn_m / 2.0 if mn_is_full else mn_m
                    if mn_effective_m <= 0:
                        if local_kind == "resistance":
                            warnings.warn(
                                f"MeasurementItem id={item.get('id')} has invalid MN spacing; skipping",
                                UserWarning,
                            )
                        mn_m = None
                        mn_effective_m = None
        rho_ohm_m = None
        source = None
        if local_kind == "resistivity":
            rho_ohm_m = value
            source = "direct"
        else:
            if method_key == "wenner":
                rho_ohm_m = 2.0 * math.pi * spacing_m * value
                source = "wenner"
            else:
                if mn_effective_m is None:
                    warnings.warn(
                        f"MeasurementItem id={item.get('id')} missing MN spacing for Schlumberger; skipping",
                        UserWarning,
                    )
                    continue
                rho_ohm_m = (
                    math.pi
                    * ((effective_spacing_m ** 2 - mn_effective_m ** 2) / (2.0 * mn_effective_m))
                    * value
                )
                source = "schlumberger"

        if rho_ohm_m is None:
            continue

        depth_m = effective_spacing_m * depth_factor_used
        raw_points.append(
            {
                "depth_m": float(depth_m),
                "rho_ohm_m": float(rho_ohm_m),
                "spacing_m": float(spacing_m),
                "effective_spacing_m": float(effective_spacing_m),
                "mn_m": None if mn_m is None else float(mn_m),
                "method": method_key,
                "value_kind": local_kind,
                "depth_factor": depth_factor_used,
                "unit": "ohm-m",
                "source": source,
                "ab_is_full": bool(ab_is_full),
                "mn_is_full": bool(mn_is_full),
                "item_id": item.get("id"),
            }
        )

    if not raw_points:
        raise ValueError(
            f"No usable soil_resistivity data for measurement {measurement_id}"
        )

    grouped: Dict[float, List[Dict[str, Any]]] = {}
    for point in raw_points:
        key = round(point["depth_m"], 6)
        grouped.setdefault(key, []).append(point)

    points: List[Dict[str, Any]] = []
    for key, group in grouped.items():
        rho_vals = [p["rho_ohm_m"] for p in group]
        spacing_vals = [p["spacing_m"] for p in group]
        eff_spacing_vals = [p["effective_spacing_m"] for p in group]
        mn_vals = [p["mn_m"] for p in group if p.get("mn_m") is not None]
        sources = {p.get("source") for p in group if p.get("source")}
        points.append(
            {
                "depth_m": float(sum(p["depth_m"] for p in group) / len(group)),
                "rho_ohm_m": float(sum(rho_vals) / len(rho_vals)),
                "spacing_m": float(sum(spacing_vals) / len(spacing_vals)),
                "effective_spacing_m": float(sum(eff_spacing_vals) / len(eff_spacing_vals)),
                "mn_m": None if not mn_vals else float(sum(mn_vals) / len(mn_vals)),
                "method": method_key,
                "value_kind": kind if kind != "auto" else "auto",
                "depth_factor": depth_factor_used,
                "unit": "ohm-m",
                "source": "mixed" if len(sources) > 1 else (sources.pop() if sources else None),
                "ab_is_full": bool(ab_is_full),
                "mn_is_full": bool(mn_is_full),
                "item_ids": [p["item_id"] for p in group],
            }
        )

    points.sort(key=lambda p: p["depth_m"])
    return points


def soil_resistivity_profile(
    measurement_id: int,
    method: Literal["wenner", "schlumberger"] = "wenner",
    value_kind: Literal["auto", "resistance", "resistivity"] = "auto",
    depth_factor: Optional[float] = None,
    ab_is_full: bool = False,
    mn_is_full: bool = False,
) -> Dict[float, float]:
    """
    Map effective depth (m) to apparent resistivity (ohm-m).

    This is a convenience wrapper around ``soil_resistivity_profile_detailed``.
    See that function for formulas and input assumptions.
    """
    points = soil_resistivity_profile_detailed(
        measurement_id=measurement_id,
        method=method,
        value_kind=value_kind,
        depth_factor=depth_factor,
        ab_is_full=ab_is_full,
        mn_is_full=mn_is_full,
    )
    return {float(p["depth_m"]): float(p["rho_ohm_m"]) for p in points}


def soil_resistivity_curve(
    measurement_id: int,
    method: Literal["wenner", "schlumberger"] = "wenner",
    value_kind: Literal["auto", "resistance", "resistivity"] = "auto",
    depth_factor: Optional[float] = None,
    ab_is_full: bool = False,
    mn_is_full: bool = False,
) -> List[Dict[str, Any]]:
    """
    Return the apparent resistivity curve as spacing → rho_a points.

    This is a convenience wrapper around ``soil_resistivity_profile_detailed`` that
    preserves spacing values for forward/inversion routines. For Schlumberger
    arrays, spacing follows the ``ab_is_full`` convention.
    """
    points = soil_resistivity_profile_detailed(
        measurement_id=measurement_id,
        method=method,
        value_kind=value_kind,
        depth_factor=depth_factor,
        ab_is_full=ab_is_full,
        mn_is_full=mn_is_full,
    )
    curve = [
        {
            "spacing_m": float(p["spacing_m"]),
            "rho_ohm_m": float(p["rho_ohm_m"]),
            "mn_m": None if p.get("mn_m") is None else float(p["mn_m"]),
        }
        for p in points
    ]
    curve.sort(key=lambda p: p["spacing_m"])
    return curve


def multilayer_soil_model(
    rho_layers: Sequence[float],
    thicknesses_m: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """
    Build a 1-3 layer soil model definition from resistivities and thicknesses.

    Parameters
    ----------
    rho_layers : sequence[float]
        Layer resistivities in ohm-m. Length defines the number of layers (1-3).
    thicknesses_m : sequence[float], optional
        Thicknesses for the top layers (length = n_layers - 1). The bottom layer
        is treated as infinite.

    Returns
    -------
    dict
        Layer table plus the raw parameters.
    """
    if rho_layers is None or len(rho_layers) == 0:
        raise ValueError("rho_layers must contain at least one resistivity value")
    if len(rho_layers) not in {1, 2, 3}:
        raise ValueError("rho_layers must define 1, 2, or 3 layers")

    thicknesses = list(thicknesses_m) if thicknesses_m is not None else []
    if len(thicknesses) != max(0, len(rho_layers) - 1):
        raise ValueError("thicknesses_m must have length len(rho_layers)-1")

    model = LayeredEarthModel(tuple(rho_layers), tuple(thicknesses))
    layers_out = _layer_bounds(model.rho_layers, model.thicknesses_m)
    total_thickness = float(sum(thicknesses)) if thicknesses else 0.0
    return {
        "layers_requested": model.n_layers,
        "rho_layers": [float(r) for r in model.rho_layers],
        "thicknesses_m": [float(h) for h in model.thicknesses_m],
        "layers": layers_out,
        "total_thickness_m": total_thickness,
    }


def layered_earth_forward(
    spacings_m: Sequence[float],
    rho_layers: Sequence[float],
    thicknesses_m: Optional[Sequence[float]] = None,
    method: Literal["wenner", "schlumberger"] = "wenner",
    *,
    mn_m: Optional[Union[float, Sequence[float]]] = None,
    ab_is_full: bool = True,
    mn_is_full: bool = True,
    forward: Literal["filter", "integral"] = "filter",
    dx: float = DX_DEFAULT,
    n_lam: int = 6000,
    backend: Literal["auto", "numpy", "mlx"] = "auto",
) -> List[float]:
    """
    Simulate apparent resistivity for a 1-3 layer earth model.

    Parameters
    ----------
    spacings_m : sequence[float]
        Electrode spacing (Wenner: a; Schlumberger: AB or AB/2 depending on ab_is_full).
    rho_layers : sequence[float]
        Layer resistivities in ohm-m (1-3 layers).
    thicknesses_m : sequence[float], optional
        Thicknesses for top layers (length = n_layers - 1).
    method : {"wenner", "schlumberger"}, default "wenner"
        Array method.
    mn_m : float or sequence[float], optional
        Potential electrode spacing (MN or MN/2 depending on mn_is_full) for Schlumberger.
        Required for the integral forward model.
    ab_is_full : bool, default True
        Interpret spacings as full AB for Schlumberger. If False, spacings are AB/2.
    mn_is_full : bool, default True
        Interpret MN spacing as full MN for Schlumberger. If False, MN/2 is expected.
    forward : {"filter", "integral"}, default "filter"
        Forward engine. "filter" uses digital filters (Schlumberger assumes MN << AB);
        "integral" uses a Hankel transform and requires scipy.
    dx : float, default log(10)/3
        Log step used by the digital filter engine.
    n_lam : int, default 6000
        Lambda grid size for the integral engine.
    backend : {"auto", "numpy", "mlx"}, default "auto"
        Math backend for the transform (MLX optional).

    Returns
    -------
    list[float]
        Apparent resistivity values aligned with the input spacings.
    """
    if rho_layers is None or len(rho_layers) == 0:
        raise ValueError("rho_layers must contain at least one resistivity value")
    if len(rho_layers) not in {1, 2, 3}:
        raise ValueError("rho_layers must define 1, 2, or 3 layers")

    thicknesses = list(thicknesses_m) if thicknesses_m is not None else []
    if len(thicknesses) != max(0, len(rho_layers) - 1):
        raise ValueError("thicknesses_m must have length len(rho_layers)-1")

    method_key = method.strip().lower()
    if method_key not in {"wenner", "schlumberger"}:
        raise ValueError(f"Unsupported method '{method}'")

    forward_key = forward.strip().lower()
    if forward_key not in {"filter", "integral"}:
        raise ValueError("forward must be 'filter' or 'integral'")

    spacing_arr = np.asarray(spacings_m, dtype=float)
    if spacing_arr.ndim != 1:
        raise ValueError("spacings_m must be 1D")
    if np.any(spacing_arr <= 0):
        raise ValueError("spacings_m must be positive")

    order = np.argsort(spacing_arr)
    spacing_sorted = spacing_arr[order]

    mn_arr = None
    if mn_m is not None:
        mn_arr = np.asarray(mn_m, dtype=float)
        if mn_arr.ndim == 0:
            mn_arr = np.full_like(spacing_sorted, float(mn_arr))
        else:
            if mn_arr.shape != spacing_arr.shape:
                raise ValueError("mn_m must match spacings_m length")
            mn_arr = mn_arr[order]
        if np.any(mn_arr <= 0):
            raise ValueError("mn_m must be positive")

    model = LayeredEarthModel(tuple(rho_layers), tuple(thicknesses))

    if method_key == "wenner":
        if forward_key == "filter":
            uniq, inv = np.unique(spacing_sorted, return_inverse=True)
            pred_unique = _simulate_wenner_filter(model, uniq, dx=dx, backend=backend)
            pred_sorted = pred_unique[inv]
        else:
            r_am = spacing_sorted
            r_an = 2.0 * spacing_sorted
            r_bm = 2.0 * spacing_sorted
            r_bn = spacing_sorted
            pred_sorted = _rhoa_collinear_integral(
                model, r_am, r_an, r_bm, r_bn, n_lam=n_lam, backend=backend
            )
    else:
        if forward_key == "filter":
            if mn_arr is not None:
                s = spacing_sorted / 2.0 if ab_is_full else spacing_sorted
                m = mn_arr / 2.0 if mn_is_full else mn_arr
                if np.any(s <= m):
                    raise ValueError("Invalid Schlumberger geometry: need AB/2 > MN/2")

            uniq, inv = np.unique(spacing_sorted, return_inverse=True)
            pred_unique = _simulate_schlumberger_filter(
                model, uniq, ab_is_full=ab_is_full, dx=dx, backend=backend
            )
            pred_sorted = pred_unique[inv]
        else:
            if mn_arr is None:
                raise ValueError("mn_m is required for Schlumberger integral forward model")
            r_am, r_an, r_bm, r_bn = _schlumberger_distances(
                spacing_sorted, mn_arr, ab_is_full=ab_is_full, mn_is_full=mn_is_full
            )
            pred_sorted = _rhoa_collinear_integral(
                model, r_am, r_an, r_bm, r_bn, n_lam=n_lam, backend=backend
            )

    preds = np.empty_like(pred_sorted)
    preds[order] = pred_sorted
    return [float(val) for val in preds]


def invert_layered_earth(
    spacings_m: Sequence[float],
    rho_obs: Sequence[float],
    layers: int = 2,
    method: Literal["wenner", "schlumberger"] = "wenner",
    initial_rho: Optional[Sequence[float]] = None,
    initial_thicknesses: Optional[Sequence[float]] = None,
    max_iter: int = 30,
    damping: float = 0.3,
    step_max: float = 0.5,
    tol: float = 1e-4,
    forward: Literal["filter", "integral"] = "filter",
    dx: float = DX_DEFAULT,
    n_lam: int = 6000,
    mn_m: Optional[Union[float, Sequence[float]]] = None,
    ab_is_full: bool = True,
    mn_is_full: bool = True,
    backend: Literal["auto", "numpy", "mlx"] = "auto",
) -> Dict[str, Any]:
    """
    Invert a 1D layered model using a damped Gauss-Newton scheme in log space.

    Parameters
    ----------
    spacings_m : sequence[float]
        Electrode spacings (Wenner: a; Schlumberger: AB or AB/2 per ab_is_full).
    rho_obs : sequence[float]
        Observed apparent resistivities (ohm-m).
    layers : int, default 2
        Number of layers (1-3).
    method : {"wenner", "schlumberger"}, default "wenner"
        Array method.
    initial_rho : sequence[float], optional
        Initial resistivity guesses.
    initial_thicknesses : sequence[float], optional
        Initial thickness guesses for top layers.
    max_iter : int, default 30
        Maximum Gauss-Newton iterations.
    damping : float, default 0.3
        Damping factor.
    step_max : float, default 0.5
        Maximum parameter step in log-space.
    tol : float, default 1e-4
        Convergence tolerance on RMSE change.
    forward : {"filter", "integral"}, default "filter"
        Forward engine used during inversion.
    dx : float, default log(10)/3
        Log step for the filter engine.
    n_lam : int, default 6000
        Lambda grid size for the integral engine.
    mn_m : float or sequence[float], optional
        MN spacing for Schlumberger (full/half per mn_is_full). Required for the
        integral engine.
    ab_is_full : bool, default True
        Interpret spacings as full AB for Schlumberger.
    mn_is_full : bool, default True
        Interpret MN as full MN for Schlumberger.
    backend : {"auto", "numpy", "mlx"}, default "auto"
        Math backend for the transform.

    Returns
    -------
    dict
        Contains fitted layers, thicknesses, predicted curve, and misfit stats.
    """
    if layers not in {1, 2, 3}:
        raise ValueError("layers must be 1, 2, or 3")

    spacings = np.asarray(spacings_m, dtype=float)
    rho_obs_arr = np.asarray(rho_obs, dtype=float)
    if spacings.size != rho_obs_arr.size:
        raise ValueError("spacings_m and rho_obs must have the same length")
    if np.any(spacings <= 0) or np.any(rho_obs_arr <= 0):
        raise ValueError("spacings_m and rho_obs must be positive")

    order = np.argsort(spacings)
    spacings = spacings[order]
    rho_obs_arr = rho_obs_arr[order]

    mn_arr = None
    if mn_m is not None:
        mn_arr = np.asarray(mn_m, dtype=float)
        if mn_arr.ndim == 0:
            mn_arr = np.full_like(spacings, float(mn_arr))
        if mn_arr.shape != spacings.shape:
            raise ValueError("mn_m must match spacings_m length")
        mn_arr = mn_arr[order]

    if initial_rho is None:
        rho_init = np.full(layers, float(np.median(rho_obs_arr)))
    else:
        if len(initial_rho) != layers:
            raise ValueError("initial_rho must have length equal to layers")
        rho_init = np.asarray(initial_rho, dtype=float)

    if layers == 1:
        thickness_init = np.array([], dtype=float)
    else:
        if initial_thicknesses is None:
            depth_min = max(spacings.min() * 0.25, 1e-3)
            depth_max = max(spacings.max() * 0.5, depth_min * 1.5)
            if layers == 2:
                boundaries = np.array([math.sqrt(depth_min * depth_max)])
            else:
                boundaries = np.geomspace(depth_min, depth_max, layers - 1)
            thickness_init = np.diff(np.concatenate([[0.0], boundaries]))
        else:
            if len(initial_thicknesses) != layers - 1:
                raise ValueError("initial_thicknesses must have length layers-1")
            thickness_init = np.asarray(initial_thicknesses, dtype=float)

    if np.any(rho_init <= 0) or np.any(thickness_init <= 0):
        raise ValueError("Initial resistivities and thicknesses must be positive")

    m = np.concatenate([np.log(rho_init), np.log(thickness_init)])
    n_params = m.size
    eps = 1e-3
    eps_pos = 1e-12

    prev_rmse = None
    iteration = 0
    for iteration in range(1, max_iter + 1):
        rho_layers = np.exp(m[:layers])
        thicknesses = np.exp(m[layers:]) if layers > 1 else []
        rho_pred = np.array(
            layered_earth_forward(
                spacings,
                rho_layers,
                thicknesses_m=list(thicknesses) if layers > 1 else None,
                method=method,
                mn_m=None if mn_arr is None else mn_arr,
                ab_is_full=ab_is_full,
                mn_is_full=mn_is_full,
                forward=forward,
                dx=dx,
                n_lam=n_lam,
                backend=backend,
            )
        )

        rho_pred = np.clip(rho_pred, eps_pos, np.inf)
        residual = np.log(rho_obs_arr) - np.log(rho_pred)
        rmse = float(np.sqrt(np.mean(residual ** 2)))
        if prev_rmse is not None and abs(prev_rmse - rmse) < tol:
            break
        prev_rmse = rmse

        J = np.zeros((spacings.size, n_params), dtype=float)
        for idx in range(n_params):
            m_pert = m.copy()
            m_pert[idx] += eps
            rho_layers_p = np.exp(m_pert[:layers])
            thicknesses_p = np.exp(m_pert[layers:]) if layers > 1 else []
            rho_pred_p = np.array(
                layered_earth_forward(
                    spacings,
                    rho_layers_p,
                    thicknesses_m=list(thicknesses_p) if layers > 1 else None,
                    method=method,
                    mn_m=None if mn_arr is None else mn_arr,
                    ab_is_full=ab_is_full,
                    mn_is_full=mn_is_full,
                    forward=forward,
                    dx=dx,
                    n_lam=n_lam,
                    backend=backend,
                )
            )
            rho_pred_p = np.clip(rho_pred_p, eps_pos, np.inf)
            J[:, idx] = (np.log(rho_pred_p) - np.log(rho_pred)) / eps

        lhs = J.T @ J + (damping ** 2) * np.eye(n_params)
        rhs = J.T @ residual
        try:
            delta = np.linalg.solve(lhs, rhs)
        except np.linalg.LinAlgError:
            delta, *_ = np.linalg.lstsq(lhs, rhs, rcond=None)

        max_step = np.max(np.abs(delta)) if delta.size else 0.0
        if max_step > step_max:
            delta = delta * (step_max / max_step)

        m = m + delta

    rho_layers = np.exp(m[:layers])
    thicknesses = np.exp(m[layers:]) if layers > 1 else []
    rho_pred = np.array(
        layered_earth_forward(
            spacings,
            rho_layers,
            thicknesses_m=list(thicknesses) if layers > 1 else None,
            method=method,
            mn_m=None if mn_arr is None else mn_arr,
            ab_is_full=ab_is_full,
            mn_is_full=mn_is_full,
            forward=forward,
            dx=dx,
            n_lam=n_lam,
            backend=backend,
        )
    )

    rho_pred = np.clip(rho_pred, eps_pos, np.inf)
    residual = np.log(rho_obs_arr) - np.log(rho_pred)
    misfit = {
        "rmse_log": float(np.sqrt(np.mean(residual ** 2))),
        "mae_log": float(np.mean(np.abs(residual))),
        "n_points": int(spacings.size),
        "iterations": iteration,
    }

    layers_out = _layer_bounds(list(rho_layers), list(thicknesses))

    return {
        "layers": layers_out,
        "rho_layers": [float(val) for val in rho_layers],
        "thicknesses_m": [float(val) for val in thicknesses],
        "observed_curve": [
            {"spacing_m": float(s), "rho_ohm_m": float(r)}
            for s, r in zip(spacings, rho_obs_arr)
        ],
        "predicted_curve": [
            {"spacing_m": float(s), "rho_ohm_m": float(r)}
            for s, r in zip(spacings, rho_pred)
        ],
        "misfit": misfit,
        "method": method,
        "forward": forward,
        "ab_is_full": bool(ab_is_full),
        "mn_is_full": bool(mn_is_full),
    }


def invert_soil_resistivity_layers(
    measurement_id: int,
    method: Literal["wenner", "schlumberger"] = "wenner",
    layers: int = 2,
    value_kind: Literal["auto", "resistance", "resistivity"] = "auto",
    depth_factor: Optional[float] = None,
    ab_is_full: bool = False,
    mn_is_full: bool = False,
    mn_m: Optional[Union[float, Sequence[float]]] = None,
    forward: Literal["filter", "integral"] = "filter",
    dx: float = DX_DEFAULT,
    n_lam: int = 6000,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Invert a layered-earth model directly from stored soil resistivity items.

    Parameters
    ----------
    measurement_id : int
        Measurement ID containing soil_resistivity items.
    method : {"wenner", "schlumberger"}, default "wenner"
        Array method for apparent resistivity.
    layers : int, default 2
        Number of layers to fit (1-3).
    value_kind : {"auto", "resistance", "resistivity"}, default "auto"
        Interpret values as resistance or resistivity.
    depth_factor : float, optional
        Depth factor passed to ``soil_resistivity_profile_detailed``.
    ab_is_full : bool, default False
        Interpret stored spacings as full AB for Schlumberger. When False, AB/2 is used.
    mn_is_full : bool, default False
        Interpret MN values as full MN for Schlumberger. When False, MN/2 is used.
    mn_m : float or sequence[float], optional
        Optional MN override for Schlumberger (full/half per mn_is_full).
    forward : {"filter", "integral"}, default "filter"
        Forward engine used during inversion.
    dx : float, default log(10)/3
        Log step for the filter engine.
    n_lam : int, default 6000
        Lambda grid size for the integral engine.
    **kwargs
        Additional options forwarded to ``invert_layered_earth``.

    Returns
    -------
    dict
        Inversion result with metadata and fitted layer parameters.
    """
    curve = soil_resistivity_curve(
        measurement_id=measurement_id,
        method=method,
        value_kind=value_kind,
        depth_factor=depth_factor,
        ab_is_full=ab_is_full,
        mn_is_full=mn_is_full,
    )
    if not curve:
        raise ValueError(f"No soil_resistivity data for measurement {measurement_id}")

    spacings = [p["spacing_m"] for p in curve]
    rho_obs = [p["rho_ohm_m"] for p in curve]

    method_key = method.strip().lower()
    mn_values = None
    if method_key == "schlumberger":
        if mn_m is not None:
            mn_values = mn_m
        else:
            mn_candidates = [p.get("mn_m") for p in curve]
            if any(val is not None for val in mn_candidates):
                if all(val is not None for val in mn_candidates):
                    mn_values = [float(val) for val in mn_candidates]
                else:
                    warnings.warn(
                        "Some MN values are missing; MN will be ignored for forward modeling.",
                        UserWarning,
                    )

        if forward == "integral" and mn_values is None:
            raise ValueError("MN spacing is required for Schlumberger integral inversion")

    result = invert_layered_earth(
        spacings_m=spacings,
        rho_obs=rho_obs,
        layers=layers,
        method=method,
        mn_m=mn_values,
        ab_is_full=ab_is_full,
        mn_is_full=mn_is_full,
        forward=forward,
        dx=dx,
        n_lam=n_lam,
        **kwargs,
    )
    result.update(
        {
            "measurement_id": measurement_id,
            "method": method,
            "value_kind": value_kind,
            "depth_factor": depth_factor,
            "ab_is_full": bool(ab_is_full),
            "mn_is_full": bool(mn_is_full),
            "forward": forward,
        }
    )
    return result


def rho_f_model(
    measurement_ids: List[int],
) -> Tuple[float, float, float, float, float]:
    """
    Fit the rho–f model coefficients.

    The model is:

    $$
    Z(\\rho,f) = k_1 \\cdot \\rho + (k_2 + j k_3) \\cdot f + (k_4 + j k_5) \\cdot \\rho \\cdot f
    $$

    Parameters
    ----------
    measurement_ids : list[int]
        Measurements to include in the fit.

    Returns
    -------
    tuple
        Coefficients ``(k1, k2, k3, k4, k5)``.

    Raises
    ------
    ValueError
        If no soil resistivity data or no overlapping impedance data exist.
    RuntimeError
        If the least-squares solve fails.
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
    frequency: float = 50.0,
) -> Union[Dict[str, float], Dict[int, Dict[str, float]]]:
    """
    Calculate per-ampere touch voltages and EPR at a given frequency.

    Requires ``earthing_impedance`` and ``earthing_current`` at the specified frequency.
    Uses ``prospective_touch_voltage`` and ``touch_voltage`` if available.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Measurement ID or list of IDs.
    frequency : float, default 50.0
        Frequency in Hz.

    Returns
    -------
    dict
        If single ID: mapping with keys ``epr``, optional ``vtp_min/max``, ``vt_min/max``.
        If multiple IDs: nested dict keyed by measurement_id.
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
                frequency_hz=frequency,
            )
            Z = float(imp_items[0]["value"])
        except Exception:
            warnings.warn(
                f"Measurement {mid}: missing earthing_impedance@{frequency}Hz → skipping",
                UserWarning,
            )
            continue

        # 2) Mandatory: current I (A) at this frequency
        try:
            cur_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="earthing_current",
                frequency_hz=frequency,
            )
            I = float(cur_items[0]["value"])
            if I == 0:
                raise ValueError("zero current")
        except Exception:
            warnings.warn(
                f"Measurement {mid}: missing or zero earthing_current@{frequency}Hz → skipping",
                UserWarning,
            )
            continue

        entry: Dict[str, float] = {}

        # 3) Set EPR
        entry["epr"] = Z

        # 4) Optional: prospective touch voltage (V/A)
        try:
            vtp_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="prospective_touch_voltage",
                frequency_hz=frequency,
            )
            vtp_vals = [float(it["value"]) / I for it in vtp_items]
            entry["vtp_min"] = min(vtp_vals)
            entry["vtp_max"] = max(vtp_vals)
        except Exception:
            warnings.warn(
                f"Measurement {mid}: no prospective_touch_voltage@{frequency}Hz",
                UserWarning,
            )

        # 5) Optional: actual touch voltage (V/A)
        try:
            vt_items, _ = read_items_by(
                measurement_id=mid,
                measurement_type="touch_voltage",
                frequency_hz=frequency,
            )
            vt_vals = [float(it["value"]) / I for it in vt_items]
            entry["vt_min"] = min(vt_vals)
            entry["vt_max"] = max(vt_vals)
        except Exception:
            warnings.warn(
                f"Measurement {mid}: no touch_voltage@{frequency}Hz",
                UserWarning,
            )

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
    Collect shield-current items for a location.

    Parameters
    ----------
    location_id : int
        Location ID to search under.
    frequency_hz : float, optional
        Frequency filter.

    Returns
    -------
    list[dict]
        Shield-current items with ``measurement_id`` included.

    Raises
    ------
    RuntimeError
        If reading measurements fails.
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
    Compute split factor and local earthing current from shield currents.

    The caller must choose shield-current items with a consistent angle reference.

    Parameters
    ----------
    earth_fault_current_id : int
        MeasurementItem ID carrying total earth fault current.
    shield_current_ids : list[int]
        MeasurementItem IDs of shield currents to subtract.

    Returns
    -------
    dict
        Contains ``split_factor``, ``shield_current_sum``, ``local_earthing_current``,
        and ``earth_fault_current`` (each with magnitude/angle/real/imag).

    Raises
    ------
    ValueError
        If inputs are missing or zero.
    RuntimeError
        If database access fails.
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


def value_over_distance(
    measurement_ids: Union[int, List[int]],
    measurement_type: str = "earthing_impedance",
) -> Union[Dict[float, float], Dict[int, Dict[float, float]]]:
    """
    Map measurement distance to value magnitude.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Measurement ID or list of IDs.
    measurement_type : str, default "earthing_impedance"
        Item type to filter by.

    Returns
    -------
    dict
        If single ID: ``{distance_m: value}``; if multiple: ``{measurement_id: {distance_m: value}}``.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, Dict[float, float]] = {}

    for mid in ids:
        try:
            items, _ = read_items_by(
                measurement_id=mid, measurement_type=measurement_type
            )
        except Exception as e:
            logger.error("Error reading items for measurement %s: %s", mid, e)
            raise RuntimeError(
                f"Failed to load data for measurement {mid}"
            ) from e

        dist_val_map: Dict[float, float] = {}
        for item in items:
            dist = item.get("measurement_distance_m")
            value = item.get("value")

            if dist is None or value is None:
                continue

            try:
                dist_val_map[float(dist)] = float(value)
            except Exception:
                continue

        all_results[mid] = dist_val_map

    return all_results[ids[0]] if single else all_results


def value_over_distance_detailed(
    measurement_ids: Union[int, List[int]],
    measurement_type: str = "earthing_impedance",
) -> Union[List[Dict[str, Any]], Dict[int, List[Dict[str, Any]]]]:
    """
    Retrieve distance–value–frequency points for one or many measurements.

    Parameters
    ----------
    measurement_ids : int or list[int]
        Measurement ID or list of IDs.
    measurement_type : str, default "earthing_impedance"
        Item type to filter by.

    Returns
    -------
    list[dict] or dict[int, list[dict]]
        If single ID: list of ``{"distance": d, "value": v, "frequency": f}``;
        if multiple: dict keyed by measurement_id with lists of points.
    """
    single = isinstance(measurement_ids, int)
    ids: List[int] = [measurement_ids] if single else list(measurement_ids)
    all_results: Dict[int, List[Dict[str, Any]]] = {}

    for mid in ids:
        try:
            items, _ = read_items_by(
                measurement_id=mid, measurement_type=measurement_type
            )
        except Exception as e:
            logger.error("Error reading items for measurement %s: %s", mid, e)
            raise RuntimeError(
                f"Failed to load data for measurement {mid}"
            ) from e

        data_points: List[Dict[str, Any]] = []
        for item in items:
            dist = item.get("measurement_distance_m")
            value = item.get("value")
            freq = item.get("frequency_hz")

            if dist is None or value is None:
                continue

            try:
                data_points.append(
                    {
                        "distance": float(dist),
                        "value": float(value),
                        "frequency": float(freq) if freq is not None else None,
                    }
                )
            except Exception:
                continue

        all_results[mid] = data_points

    return all_results[ids[0]] if single else all_results
