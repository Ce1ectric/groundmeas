"""Assessment of one tower and the short-circuit current model of a line.

* `permitted_voltage_for_time` - permissible touch voltage for a fault
  clearing time from a tabulated curve.
* `GroundingSystemAnalysis` - evaluates the fall-of-potential profile
  (earthing impedance at 62 % of the current-electrode distance), scales the
  measured touch voltages to the earth-fault current, derives the step-voltage
  profile and compares everything with the permissible values.
* `LineModel` - fits the single-phase short-circuit current along a
  line from a few calculated values (two-sided infeed model, linear fallback).

The physics behind these calculations is explained on the *Physical
background* pages of the documentation. The 62 % method is the shared
implementation :func:`groundmeas.value_at_62_percent` with
``conservative=True``.
"""

from __future__ import annotations

import logging
import numbers
import re
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

from ..services.analytics import SIXTY_TWO_PERCENT, value_at_62_percent
from .config import read_config

__all__ = ["GroundingSystemAnalysis", "LineModel", "permitted_voltage_for_time"]

logger = logging.getLogger(__name__)


def permitted_voltage_for_time(
    curve: Mapping[Any, Any], fault_duration: float
) -> float:
    """Permissible voltage of a tabulated $U(t)$ curve for a clearing time.

    Exact table entries are returned unchanged; between two entries the value
    is interpolated linearly. Times outside the table are clamped to the
    nearest table end and a warning is logged (the table should then be
    extended, e.g. with ``10 s -> 80 V`` for compensated networks).

    Parameters
    ----------
    curve : Mapping
        ``{t_s: U_V}`` pairs; keys and values must be convertible to float.
    fault_duration : float
        Fault clearing time in s.

    Returns
    -------
    float
        Permissible voltage in V.

    Examples
    --------
    >>> curve = {0.1: 633, 0.2: 528, 0.4: 300}
    >>> permitted_voltage_for_time(curve, 0.2)
    528.0
    >>> permitted_voltage_for_time(curve, 0.15)
    580.5
    """
    t = float(fault_duration)
    times = sorted(float(k) for k in curve)
    values = {float(k): float(v) for k, v in curve.items()}
    for k in times:
        if abs(k - t) < 1e-9:
            return values[k]
    if t < times[0] or t > times[-1]:
        logger.warning(
            "Clearing time %s s is outside the touch-voltage table (%s ... %s s); "
            "the value at the table end is used.",
            t,
            times[0],
            times[-1],
        )
        return values[times[0]] if t < times[0] else values[times[-1]]
    return float(np.interp(t, times, [values[k] for k in times]))


class GroundingSystemAnalysis:
    r"""Evaluate the measurements of one tower.

    The constructor runs the complete evaluation; results are available as
    attributes afterwards (see *Attributes*).

    Parameters
    ----------
    impedance_to_ground : pandas.DataFrame
        Fall-of-potential profile from
        `CompanoXMLReader.get_impedance_to_ground_dataframe`
        (columns ``Distance``, ``Impedance``, ``StepTouchCurrent``).
    touch_voltage : pandas.DataFrame
        HGT1 readings with the column ``Level50`` (V at the nominal frequency)
        and optionally ``Termination``.
    fault_current : float
        Single-phase short-circuit (earth-fault) current $I_k$ in A.
    fault_duration : float
        Fault clearing time in s.
    reduction_factor : float
        Reduction factor $r$ of the earth wire; the earth current is
        $I_E = r \cdot I_k$.
    extended_resistance : bool
        Request the curve with additional resistances (U_D2). Kept for
        compatibility; the assessment always uses U_D1.
    residual_resistance : pandas.DataFrame or None, optional
        Footing-resistance profile (same distances as ``impedance_to_ground``).
    current_probe_dist : float or None, optional
        Distance between tower and current electrode in m.
    use_62_percent_method : bool, optional
        Assess the impedance at 62 % of ``current_probe_dist`` (default) or the
        maximum of the profile.
    touch_voltage_curve : Mapping or None, optional
        Permissible touch voltage ``{t_s: U_V}``. ``None`` reads it from the
        active configuration.
    touch_voltage_curve_extended : Mapping or None, optional
        Curve with additional resistances; defaults to the configuration.
    touch_voltage_evaluation : str or None, optional
        ``"with_resistor"``, ``"without_resistor"`` or ``"all"``; defaults to
        the configuration.

    Attributes
    ----------
    earth_current : float
        $I_E = r \cdot I_k$ in A.
    permitted_touch_voltage : float
        $U_{TP}$ for the clearing time in V.
    permitted_ground_impedance : float
        $2\,U_{TP} / I_E$ in Ohm.
    impedance_max : float
        Highest measured earthing impedance in Ohm.
    grounding_impedance_62 : float
        Assessed earthing impedance in Ohm (see `get_62_percentage_value`).
    dist_62 : float
        62 % of the current-electrode distance in m.
    residual_resistance_62 : float or None
        Footing resistance scaled to the 62 % point.
    touch_voltage_max : float
        Highest touch voltage of the evaluated subset in V.
    impedance_to_high, touch_voltage_to_high : bool
        Results of the comparison with the permissible values.
    step_voltage : numpy.ndarray
        Open-circuit step voltage per metre along the profile in V.
    """

    def __init__(
        self,
        impedance_to_ground: pd.DataFrame,
        touch_voltage: pd.DataFrame,
        fault_current: float,
        fault_duration: float,
        reduction_factor: float,
        extended_resistance: bool,
        residual_resistance: pd.DataFrame | None = None,
        current_probe_dist: float | None = None,
        use_62_percent_method: bool = True,
        *,
        touch_voltage_curve: Mapping[Any, Any] | None = None,
        touch_voltage_curve_extended: Mapping[Any, Any] | None = None,
        touch_voltage_evaluation: str | None = None,
    ):
        self.impedance_to_ground = impedance_to_ground
        # work on a copy: the evaluation adds columns to the touch-voltage table
        self.touch_voltage = touch_voltage.copy()
        self.fault_current = fault_current
        self.fault_duration = fault_duration
        self.reduction_factor = reduction_factor
        self.extended_resistance_requested = bool(extended_resistance)
        # The curve with additional resistances (U_D2) is not used for the assessment.
        self.extended_resistance = False
        self.earth_current = self.fault_current * self.reduction_factor
        self.residual_resistance = residual_resistance
        self.current_probe_dist = current_probe_dist
        self.use_62_percent_method = use_62_percent_method

        if touch_voltage_curve is None or touch_voltage_evaluation is None:
            config = read_config()
            if touch_voltage_curve is None:
                touch_voltage_curve = dict(
                    zip(config["t_s"], config["U_TP_V"], strict=True)
                )
                touch_voltage_curve_extended = touch_voltage_curve_extended or dict(
                    zip(config["t_s"], config["U_TP_ext_V"], strict=True)
                )
            touch_voltage_evaluation = (
                touch_voltage_evaluation or config["touch_voltage_evaluation"]
            )
        if touch_voltage_curve_extended is None:
            touch_voltage_curve_extended = touch_voltage_curve

        self.permitted_touch_voltage_dict = dict(touch_voltage_curve)
        self.permitted_touch_voltage_extended_dict = dict(touch_voltage_curve_extended)
        self.t_s = list(self.permitted_touch_voltage_dict)
        self.U_TP_V = list(self.permitted_touch_voltage_dict.values())
        self.U_TP_ext_V = list(self.permitted_touch_voltage_extended_dict.values())
        self.touch_voltage_evaluation = touch_voltage_evaluation

        self.permitted_touch_voltage = permitted_voltage_for_time(
            self.permitted_touch_voltage_dict, self.fault_duration
        )
        self.permitted_touch_voltage_extended = permitted_voltage_for_time(
            self.permitted_touch_voltage_extended_dict, self.fault_duration
        )
        # U_E <= 2 U_TP  <=>  Z_E <= 2 U_TP / I_E
        self.permitted_ground_impedance = (
            2 * self.permitted_touch_voltage / self.earth_current
        )
        self.permitted_ground_impedance_extended = (
            2 * self.permitted_touch_voltage_extended / self.earth_current
        )

        self.summarize_results()
        if not self.use_62_percent_method:
            # the 62 % value is still needed for the export and the plots
            self.get_62_percentage_value()
        self.step_voltage_calculation()

    # ------------------------------------------------------------ touch voltage
    def calculate_touch_voltage(self) -> None:
        r"""Scale the measured touch voltages to the earth-fault current.

        The HGT1 reading $U_{T,meas}$ was taken while the COMPANO injected
        the measuring current $I_{meas}$ (``StepTouchCurrent``). Because
        the earthing system is linear,

        $$
        U_T = U_{T,meas} \cdot \frac{I_E}{I_{meas}}
        $$

        The result is stored in the column ``CalculatedTouchVoltage``
        (``0`` if no valid measuring current is available).
        """
        mean_step_current = np.abs(self.impedance_to_ground["StepTouchCurrent"]).mean()
        self.touch_voltage["StepTouchCurrent"] = mean_step_current
        if mean_step_current and mean_step_current > 0:
            self.touch_voltage["CalculatedTouchVoltage"] = (
                self.touch_voltage.Level50 * self.earth_current / mean_step_current
            )
        else:
            self.touch_voltage["CalculatedTouchVoltage"] = 0

    def _evaluation_touch_voltage_series(self) -> pd.Series:
        """Touch voltages used for the assessment.

        ``"with_resistor"`` (default) keeps the readings taken with an
        additional 1 kOhm series resistor (HGT1 termination ``2x1k``),
        ``"without_resistor"`` those with the 1 kOhm measuring resistor only
        (``1k``). If the requested subset is empty or no termination is known,
        all readings are used.
        """
        tv = self.touch_voltage
        series = tv["CalculatedTouchVoltage"]
        mode = self.touch_voltage_evaluation
        if (
            mode in ("with_resistor", "without_resistor")
            and "Termination" in tv.columns
        ):
            wanted = "2x1k" if mode == "with_resistor" else "1k"
            subset = series[tv["Termination"].astype(str).str.strip() == wanted]
            if not subset.empty:
                return subset
        return series

    def summarize_results(self) -> None:
        """Run the assessment (touch voltages, 62 % value, limit comparison)."""
        self.calculate_touch_voltage()
        self.impedance_max = self.impedance_to_ground["Impedance"].max()
        self.impedance_to_high = False
        self.touch_voltage_max = self._evaluation_touch_voltage_series().max()
        self.touch_voltage_to_high = False

        if self.check_residual_resistance():
            assert self.residual_resistance is not None
            self.residual_resistance_max = self.residual_resistance["Impedance"].max()
        else:
            self.residual_resistance_max = None

        if not self.use_62_percent_method:
            self.compare_to_permitted_touch_voltage(
                impedance=self.impedance_max, voltage=self.touch_voltage_max
            )
        else:
            self.get_62_percentage_value()
            self.compare_to_permitted_touch_voltage(
                impedance=self.grounding_impedance_62, voltage=self.touch_voltage_max
            )

    def compare_to_permitted_touch_voltage(
        self, impedance: float, voltage: float
    ) -> None:
        """Compare impedance and touch voltage with the permissible values.

        Parameters
        ----------
        impedance : float
            Assessed earthing impedance in Ohm.
        voltage : float
            Highest assessed touch voltage in V.
        """
        if self.extended_resistance:
            if impedance > self.permitted_ground_impedance_extended:
                self.impedance_to_high = True
            if voltage > self.permitted_touch_voltage_extended:
                self.touch_voltage_to_high = True
        else:
            if impedance > self.permitted_ground_impedance:
                self.impedance_to_high = True
            if voltage > self.permitted_touch_voltage:
                self.touch_voltage_to_high = True

    def get_summary(self) -> tuple[float, bool, float, bool]:
        """Return the key results.

        Returns
        -------
        tuple
            ``(impedance_max, impedance_to_high, touch_voltage_max,
            touch_voltage_to_high)``.
        """
        return (
            self.impedance_max,
            self.impedance_to_high,
            self.touch_voltage_max,
            self.touch_voltage_to_high,
        )

    # ---------------------------------------------------------------- 62 % rule
    def get_62_percentage_value(self) -> None:
        r"""Determine the earthing impedance at 62 % of the current-electrode distance.

        1. $d_{62} = 0.62\,D$ with the current-electrode distance
           $D$ (same unit as the profile distances).
        2. $Z(d_{62})$ is interpolated linearly between the (up to) three
           measuring points closest to $d_{62}$; outside the measured range
           it is extrapolated.
        3. Conservative corrections: if $d_{62}$ lies beyond the profile
           and the maximum is higher, the maximum is used; if a point closer
           than $d_{62}$ shows a higher value, that value is used.
        4. The footing resistance at $d_{62}$ is the maximum footing
           resistance scaled with $Z_{62} / Z_{max}$.

        Sets `dist_62`, `grounding_impedance_62` and
        `residual_resistance_62`.
        """
        if self.current_probe_dist is None:
            raise ValueError("current_probe_dist is required for the 62 % method")
        result = value_at_62_percent(
            self.impedance_to_ground["Distance"].to_numpy(),
            self.impedance_to_ground["Impedance"].to_numpy(),
            self.current_probe_dist,
            conservative=True,
        )
        self.dist_62 = self.current_probe_dist * SIXTY_TWO_PERCENT
        self.grounding_impedance_62 = result["value"]

        if self.check_residual_resistance():
            assert self.residual_resistance_max is not None
            k = self.impedance_max / self.grounding_impedance_62
            self.residual_resistance_62 = self.residual_resistance_max / k
        else:
            self.residual_resistance_62 = None

    def check_residual_resistance(self) -> bool:
        """Return ``True`` if a usable footing-resistance profile is available.

        Returns
        -------
        bool
            Whether the profile exists and has as many points as the
            earthing-impedance profile.
        """
        profile = self.residual_resistance
        if profile is None:
            return False
        return len(profile["Distance"]) == len(self.impedance_to_ground["Distance"])

    # ---------------------------------------------------------------- step voltage
    def step_voltage_calculation(self) -> None:
        r"""Derive the open-circuit step voltage from the potential profile.

        The fall-of-potential profile $Z(x)$ is the potential (relative to
        the tower) per ampere of earth current. The step voltage over one metre
        at position $x_i$ is approximated by the slope of the segment
        $[x_i, x_{i+1}]$:

        $$
        U_S(x_i) = I_E \left| \frac{Z(x_{i+1}) - Z(x_i)}{x_{i+1} - x_i} \right|
        $$

        with $x_0 = 0$, $Z(0) = 0$ at the tower. The value at the
        last measuring point (no further segment) is extrapolated linearly
        from the two preceding slopes. The result (one value per point
        including $x_0$) is stored in `step_voltage`.
        """
        dist = [0.0, *self.impedance_to_ground["Distance"].tolist()]
        impedance = [0.0, *self.impedance_to_ground["Impedance"].tolist()]
        n = len(dist)
        gradient = np.zeros(n, dtype=float)
        for i in range(n - 1):
            gradient[i] = (impedance[i + 1] - impedance[i]) / (dist[i + 1] - dist[i])
        gradient *= self.fault_current * self.reduction_factor
        if n >= 3:
            # linear extrapolation through the slopes at x_{n-3} and x_{n-2}
            x0, x1, x_last = dist[-3], dist[-2], dist[-1]
            g0, g1 = gradient[-3], gradient[-2]
            gradient[-1] = g1 + (x_last - x1) * (g1 - g0) / (x1 - x0)
        elif n == 2:
            gradient[-1] = gradient[0]
        self.step_voltage = np.abs(gradient)


class LineModel:
    r"""Short-circuit current along an overhead line.

    The single-phase short-circuit current at tower $x$ of a line fed
    from both ends is modelled as

    $$
    I_k(x) = \frac{a}{b\,l\,x + c} + \frac{a}{b\,(N - x)\,l + d}
    $$

    with the fit parameters $a$ (driving voltage), $b$ (impedance
    per km), $c, d$ (source impedances at both ends) and the line data
    $l$ (mean span length) and $N$ (number of towers). If the fit
    does not converge, a straight line (one-sided infeed) is fitted instead.

    Training data are read per line from a sheet of the short-circuit workbook
    with the columns ``Ik`` (kA), ``l`` (km from the line start) and ``Mast``
    (only the first and last tower number are required).

    Attributes
    ----------
    training_data : dict[str, pandas.DataFrame]
        Training tables per line.
    curve_data : dict[str, dict]
        Fitted parameters per line (``type`` is ``"two_sided"`` or ``"linear"``).
    sc_data : dict[str, dict]
        Currents returned by `get_sc_current` per line and tower.
    """

    def __init__(self) -> None:
        self.training_data: dict[str, pd.DataFrame] = {}
        self.curve_data: dict[str, dict[str, Any]] = {}
        self.sc_data: dict[str, dict[Any, float]] = {}

    @staticmethod
    def _extract_numeric_part(s: object) -> int | None:
        """Return the first group of digits of ``s`` as int (``"28N"`` -> 28)."""
        match = re.search(r"\d+", str(s))
        return int(match.group()) if match else None

    def get_sc_current(self, line_number: str, tower: object) -> float:
        """Short-circuit current at a tower from the trained model.

        Parameters
        ----------
        line_number : str
            Line identifier (must have been trained).
        tower : object
            Tower identifier; its numeric part is used.

        Returns
        -------
        float
            Current in kA, rounded to 0.01 kA.

        Raises
        ------
        ValueError
            If the line has not been trained or the tower has no number.
        """
        number = self._extract_numeric_part(s=tower)
        if number is None:
            raise ValueError(f"Tower {tower!r} has no tower number")
        if line_number not in self.curve_data:
            raise ValueError(
                f"The line number {line_number} is not available in the curve model. "
                "Maybe the training should be performed"
            )
        data = self.curve_data[line_number]
        # The model is trained on a 0-based tower index; shift the absolute
        # tower number by the line's first tower number.
        x = number - data.get("first_tower", 0)
        if data.get("type", "two_sided") == "linear":
            sc_current = np.round(data["slope"] * x + data["intercept"], 2)
        else:
            sc_current = np.round(
                self._curve_function(
                    x, data["a"], data["b"], data["c"], data["d"], data["l"], data["N"]
                ),
                2,
            )
        self.sc_data.setdefault(line_number, {})[number] = sc_current
        return sc_current

    @staticmethod
    def _curve_function(
        x: Any, a: float, b: float, c: float, d: float, l: float, N: float
    ) -> Any:  # noqa: E741
        """Two-sided infeed model, see the class docstring."""
        return a / (b * l * x + c) + a / (b * (N - x) * l + d)

    def train_curve_model(self, line_number: str) -> Any:
        """Fit the short-circuit model of one line.

        Parameters
        ----------
        line_number : str
            Line identifier; its training data must have been loaded with
            `read_training_parameter`.

        Returns
        -------
        numpy.ndarray or tuple
            ``(a, b, c, d)`` of the two-sided model, or ``(slope, intercept)``
            of the linear fallback.

        Raises
        ------
        ValueError
            If no training data exist or the tower numbers are inconsistent.
        """
        data = self.training_data.get(line_number)
        if not isinstance(data, pd.DataFrame):
            raise ValueError("No training data available for the given line number.")
        # Only the first and last entry of the Mast column must be filled. The
        # numbering does not have to start at 0 (e.g. towers 22..49); the
        # offset is stored and applied again in get_sc_current.
        towers = data.Mast.dropna()
        first_tower_number = towers.iloc[0]
        last_tower_number = towers.iloc[-1]
        self._validate_numeric_value(x=first_tower_number)
        self._validate_numeric_value(x=last_tower_number)
        N = last_tower_number - first_tower_number
        if N <= 0:
            raise ValueError(
                f"The input table has no consistent tower numbers: "
                f"first={first_tower_number}, last={last_tower_number}"
            )
        N = int(N + 1)

        line_length = data.l.iloc[-1]
        self._validate_numeric_value(x=line_length)
        # mean span length (unit of the input, typically km per span)
        length_per_tower = line_length / (N - 1)
        if not length_per_tower:
            raise ValueError(f"Line {line_number}: the line length must be positive")
        x_training = data.l / length_per_tower
        y_training = data.Ik

        try:
            popt, _ = curve_fit(
                lambda x, a, b, c, d: self._curve_function(
                    x, a, b, c, d, length_per_tower, N
                ),
                x_training,
                y_training,
            )
        except Exception as exc:
            # one-sided infeed: straight line over the tower index
            m, b = np.polyfit(x_training, y_training, 1)
            self.curve_data[line_number] = {
                "type": "linear",
                "slope": m,
                "intercept": b,
                "N": N,
                "l": length_per_tower,
                "first_tower": first_tower_number,
            }
            logger.warning(
                "Fallback to the linear short-circuit model for line %s: %s",
                line_number,
                exc,
            )
            return m, b
        self.curve_data[line_number] = {
            "type": "two_sided",
            "a": popt[0],
            "b": popt[1],
            "c": popt[2],
            "d": popt[3],
            "N": N,
            "l": length_per_tower,
            "first_tower": first_tower_number,
        }
        return popt

    def read_training_parameter(
        self, path: str, line_number: str
    ) -> pd.DataFrame | None:
        """Load the training table of one line.

        Parameters
        ----------
        path : str
            Short-circuit workbook (``.xlsx``).
        line_number : str
            Sheet name (= line identifier). Columns ``B:D`` must contain ``Ik``,
            ``l`` and ``Mast`` (in any order).

        Returns
        -------
        pandas.DataFrame or None
            The table, or ``None`` if the sheet is invalid (an error is
            logged).

        Raises
        ------
        FileNotFoundError
            If the workbook does not exist.
        """
        try:
            df = pd.read_excel(path, sheet_name=line_number, usecols="B:D")
            self._validate_dataframe_columns(df=df)
        except FileNotFoundError:
            logger.error("The file '%s' was not found.", path)
            raise
        except Exception as exc:
            logger.error(
                "Short-circuit data of line %s not usable: %s", line_number, exc
            )
            return None
        self.training_data[line_number] = df
        return df

    @staticmethod
    def _validate_dataframe_columns(df: pd.DataFrame) -> None:
        expected_columns = ["Ik", "l", "Mast"]
        if set(df.columns) != set(expected_columns):
            raise ValueError(
                f"DataFrame columns do not match expected columns. Expected: {expected_columns}, "
                f"Found: {list(df.columns)}"
            )

    @staticmethod
    def _validate_numeric_value(x: object) -> None:
        if isinstance(x, bool) or not isinstance(x, numbers.Real) or np.isnan(float(x)):
            raise ValueError(f"The value of the table is not a numeric value: {x}")
