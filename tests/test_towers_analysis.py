"""Assessment of one tower: 62 % rule, touch and step voltages, limits.

Numerical results are checked against at least one independent method
(analytical solution, numerical integration, curve fit or a second
interpolation routine).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest
from scipy import integrate, interpolate
from scipy.optimize import curve_fit

from groundmeas.towers.analysis import (
    GroundingSystemAnalysis,
    permitted_voltage_for_time,
)

T_S = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 10.0]
U_TP = [633, 528, 410, 300, 204, 170, 140, 130, 120, 107, 80]
CURVE = dict(zip(T_S, U_TP, strict=True))
DISTANCES = [5.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 65.0, 70.0]
R_TRUE, RADIUS, D = 0.5, 2.0, 100.0


def hemisphere(x, r=R_TRUE, a=RADIUS, d=D):
    """Fall-of-potential curve, probe distance x measured from the electrode centre."""
    x = np.asarray(x, dtype=float)
    return r * a * (1 / a - 1 / d - 1 / x + 1 / (d - x))


def hemisphere_slope(x, r=R_TRUE, a=RADIUS, d=D):
    """Analytical derivative dZ/dx of `hemisphere`."""
    return r * a * (1 / x**2 + 1 / (d - x) ** 2)


def profile(distances=DISTANCES, impedance=None, current=0.1):
    z = hemisphere(distances) if impedance is None else impedance
    return pd.DataFrame(
        {
            "Distance": distances,
            "Impedance": z,
            "Unit": "Ohm",
            "StepTouchCurrent": current,
        }
    )


def touch(levels=(5e-3, 4e-3, 3e-3, 2e-3), terminations=("1k", "2x1k", "1k", "2x1k")):
    return pd.DataFrame({"Level50": list(levels), "Termination": list(terminations)})


def analyse(
    impedance=None,
    touch_voltage=None,
    *,
    fault_current=10_000.0,
    duration=0.4,
    r=0.6,
    residual=None,
    mode="with_resistor",
    probe=D,
    use_62=True,
):
    return GroundingSystemAnalysis(
        profile() if impedance is None else impedance,
        touch() if touch_voltage is None else touch_voltage,
        fault_current=fault_current,
        fault_duration=duration,
        reduction_factor=r,
        extended_resistance=False,
        residual_resistance=residual,
        current_probe_dist=probe,
        use_62_percent_method=use_62,
        touch_voltage_curve=CURVE,
        touch_voltage_evaluation=mode,
    )


# ----------------------------------------------------------------- permitted voltage
def test_permitted_voltage_exact_and_interpolated():
    assert permitted_voltage_for_time(CURVE, 0.4) == 300.0
    reference = interpolate.interp1d(T_S, U_TP)  # second method
    for t in (0.15, 0.25, 0.47, 0.95, 5.0):
        assert permitted_voltage_for_time(CURVE, t) == pytest.approx(
            float(reference(t))
        )


def test_permitted_voltage_is_clamped(caplog):
    with caplog.at_level(logging.WARNING, logger="groundmeas"):
        assert permitted_voltage_for_time(CURVE, 0.05) == 633.0
        assert permitted_voltage_for_time(CURVE, 20.0) == 80.0
    assert "outside the touch-voltage table" in caplog.text


# ----------------------------------------------------------------------- 62 % rule
def test_62_percent_value_agrees_with_theory_and_curve_fit():
    gsa = analyse()
    assert gsa.dist_62 == pytest.approx(62.0)
    # method 2: least-squares fit of the hemisphere model to the profile
    (r_fit, a_fit), _ = curve_fit(
        lambda x, r, a: hemisphere(x, r, a),
        DISTANCES,
        hemisphere(DISTANCES),
        p0=(1.0, 1.0),
    )
    assert r_fit == pytest.approx(R_TRUE, rel=1e-6)
    assert a_fit == pytest.approx(RADIUS, rel=1e-6)
    # method 3: analytical value; the 62 % rule is accurate to well below 1 %
    assert gsa.grounding_impedance_62 == pytest.approx(R_TRUE, rel=5e-3)
    assert gsa.grounding_impedance_62 == pytest.approx(r_fit, rel=5e-3)


def test_exact_61_8_percent_point_reproduces_the_true_resistance():
    # Z(x) = R exactly where 1/(D - x) = 1/x + 1/D, i.e. x = (sqrt(5) - 1) / 2 * D
    golden = (np.sqrt(5) - 1) / 2
    assert hemisphere(golden * D) == pytest.approx(R_TRUE, rel=1e-12)


def test_profile_ending_before_62_percent_uses_the_maximum():
    distances = [1.0, 10.0, 20.0, 30.0, 40.0, 50.0]
    z = [0.2, 0.5, 0.6, 0.55, 0.5, 0.45]
    gsa = analyse(profile(distances, z))
    assert gsa.grounding_impedance_62 == pytest.approx(0.6)


def test_higher_value_closer_than_62_percent_is_used():
    distances = [1.0, 10.0, 20.0, 40.0, 60.0, 65.0, 70.0]
    z = [0.1, 0.3, 0.7, 0.4, 0.45, 0.46, 0.47]
    gsa = analyse(profile(distances, z))
    assert gsa.grounding_impedance_62 == pytest.approx(0.7)


def test_short_profiles():
    two = analyse(profile([50.0, 70.0], [0.4, 0.5]))
    assert two.grounding_impedance_62 == pytest.approx(0.4 + 12 / 20 * 0.1)
    one = analyse(profile([60.0], [0.42]))
    assert one.grounding_impedance_62 == pytest.approx(0.42)


def test_footing_resistance_scaled_to_62_percent():
    impedance = profile()
    residual = impedance.assign(Impedance=2 * impedance["Impedance"])
    gsa = analyse(impedance, residual=residual)
    # R_A,62 = R_A,max * Z_62 / Z_max  ->  2 * Z_62 for a proportional profile
    assert gsa.residual_resistance_62 == pytest.approx(2 * gsa.grounding_impedance_62)
    mismatched = residual.iloc[:-1]
    assert analyse(impedance, residual=mismatched).residual_resistance_62 is None


def test_62_percent_requires_the_probe_distance():
    with pytest.raises(ValueError, match="current_probe_dist"):
        analyse(probe=None)


def test_maximum_method():
    gsa = analyse(use_62=False)
    assert gsa.get_summary()[0] == pytest.approx(hemisphere(DISTANCES).max())
    assert gsa.grounding_impedance_62 == pytest.approx(
        R_TRUE, rel=5e-3
    )  # still provided


# -------------------------------------------------------------------- touch voltage
def test_touch_voltages_scaled_to_the_earth_current():
    gsa = analyse()
    earth_current = 10_000.0 * 0.6
    expected = np.array([5e-3, 4e-3, 3e-3, 2e-3]) * earth_current / 0.1  # second method
    np.testing.assert_allclose(gsa.touch_voltage["CalculatedTouchVoltage"], expected)
    assert gsa.earth_current == pytest.approx(earth_current)


@pytest.mark.parametrize(
    ("mode", "expected"),
    [("with_resistor", 240.0), ("without_resistor", 300.0), ("all", 300.0)],
)
def test_evaluated_subset(mode, expected):
    assert analyse(mode=mode).touch_voltage_max == pytest.approx(expected)


def test_subset_falls_back_to_all_readings():
    readings = touch(levels=(5e-3, 3e-3), terminations=("1k", "1k"))
    assert analyse(touch_voltage=readings).touch_voltage_max == pytest.approx(300.0)
    no_termination = pd.DataFrame({"Level50": [1e-3, 2e-3]})
    assert analyse(touch_voltage=no_termination).touch_voltage_max == pytest.approx(
        120.0
    )


def test_complex_measuring_current_and_zero_current():
    gsa = analyse(profile(current=complex(0.06, 0.08)))  # |I| = 0.1 A
    assert gsa.touch_voltage_max == pytest.approx(240.0)
    zero = analyse(profile(current=0.0))
    assert (zero.touch_voltage["CalculatedTouchVoltage"] == 0).all()


def test_input_table_is_not_modified():
    readings = touch()
    analyse(touch_voltage=readings)
    assert "CalculatedTouchVoltage" not in readings.columns


# --------------------------------------------------------------------- assessment
def test_limits_and_flags():
    gsa = analyse()  # 0.4 s -> U_TP = 300 V, I_E = 6 kA
    assert gsa.permitted_touch_voltage == 300.0
    assert gsa.permitted_ground_impedance == pytest.approx(2 * 300 / 6000)
    assert gsa.impedance_to_high is True  # Z_62 ~ 0.5 Ohm > 0.1 Ohm
    assert gsa.touch_voltage_to_high is False  # 240 V <= 300 V
    assert analyse(duration=1.0).touch_voltage_to_high is True  # U_TP = 107 V
    low = analyse(profile(impedance=hemisphere(DISTANCES) / 10), fault_current=1_000.0)
    assert low.impedance_to_high is False  # Z_62 = 0.05 Ohm <= 2 * 300 V / 600 A


# ------------------------------------------------------------------- step voltage
def test_step_voltage_agrees_with_integrated_gradient():
    gsa = analyse()
    earth_current = 6000.0
    x = [0.0, *DISTANCES]
    steps = gsa.step_voltage
    assert len(steps) == len(x)
    # method 2: mean of the analytical gradient over every measured segment
    for i in range(1, len(x) - 1):
        mean_slope = integrate.quad(hemisphere_slope, x[i], x[i + 1])[0] / (
            x[i + 1] - x[i]
        )
        assert steps[i] == pytest.approx(earth_current * mean_slope, rel=1e-9)
    # first segment: from the tower (Z = 0) to the first probe position
    assert steps[0] == pytest.approx(earth_current * hemisphere(x[1]) / x[1])


def test_step_voltage_last_point_is_extrapolated_linearly():
    distances = [10.0, 20.0, 40.0, 60.0, 65.0]  # non-uniform spacing at the end
    gsa = analyse(profile(distances))
    s = gsa.step_voltage
    x = [0.0, *distances]
    slope = np.diff(hemisphere(distances)) / np.diff(distances) * 6000.0
    # the two last real slopes belong to x = 40 m and x = 60 m
    expected = slope[-1] + (x[-1] - x[-2]) * (slope[-1] - slope[-2]) / (x[-2] - x[-3])
    assert s[-1] == pytest.approx(abs(expected))
    # the pre-0.2 code returned a quarter of the last slope for this spacing
    assert s[-1] != pytest.approx(0.25 * abs(slope[-1]))


def test_step_voltage_single_point():
    gsa = analyse(profile([60.0], [0.42]))
    assert gsa.step_voltage.tolist() == pytest.approx([0.42 / 60 * 6000] * 2)
