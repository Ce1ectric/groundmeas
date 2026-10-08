"""
groundmeas.instruments.omicron
==============================

Readers for OMICRON COMPANO 100 XML exports and OMICRON HGT1 reports.

* :class:`CompanoXMLReader` reads the *fall-of-potential* measurement
  (earthing-impedance profile, per test frequency and as the instrument's
  power-frequency result), the reduction-factor (clamp) measurement, the
  measuring current of the step/touch test and the soil-resistivity
  measurement of a COMPANO 100 XML export.
* :class:`Hgt1TXTReader` reads the tab-separated *StepTouch* report of the
  HGT1 handheld touch-voltage meter and interpolates the frequency-selective
  readings to the nominal power frequency.

Both readers raise :class:`MeasurementFileError` (a ``ValueError``) with a
descriptive message when a file is incomplete or malformed. Values are
returned in SI base units (V, A, m, Ω, Ωm).

The readers are independent of the database; :mod:`groundmeas.services.omicron_import`
turns their results into measurements, and :mod:`groundmeas.towers` uses
them for the evaluation of overhead-line tower campaigns.
"""

from __future__ import annotations

import logging
import math
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd

__all__ = [
    "CompanoXMLReader",
    "FallOfPotentialData",
    "Hgt1TXTReader",
    "MeasurementFileError",
    "ReductionFactorData",
    "SoilResistivityData",
    "TERMINATION_LABELS",
    "informative_locations",
]

logger = logging.getLogger(__name__)

UNIT_FACTORS: dict[str, dict[str, float]] = {
    "current": {"A": 1.0, "mA": 1e-3, "kA": 1e3, "µA": 1e-6, "uA": 1e-6},
    "voltage": {"V": 1.0, "mV": 1e-3, "kV": 1e3, "µV": 1e-6, "uV": 1e-6},
    "distance": {"m": 1.0, "cm": 1e-2, "km": 1e3, "ft": 0.3048},
}
"""Accepted units per quantity and their factor to the SI base unit (A, V, m)."""

_FALL_OF_POTENTIAL = "FallOfPotentialReport/FallOfPotentialWidgetData/FallOfPotentialMeasurementScreenData"
_REDUCTION_FACTOR = (
    "FallOfPotentialReport/FallOfPotentialWidgetData/ReductionFactorScreenData"
)
_STEP_TOUCH_SETUP = "StepAndTouchReport/StepTouchWidgetData/OutputSetupScreenData"
_SOIL = (
    "SoilResistanceReport/SoilResistanceWidgetData/SoilResistanceMeasurementScreenData"
)

TERMINATION_LABELS: dict[str, dict[str, str]] = {
    "en": {"1k": "no additional resistor", "2x1k": "with additional resistor 1kOhm"},
    "de": {"1k": "kein Zusatzwiderstand", "2x1k": "mit Zusatzwiderstand 1kOhm"},
}
"""Readable labels of the HGT1 terminations per language.

``1k``: voltage across the 1 kΩ body resistance without additional
resistance; ``2x1k``: with an additional 1 kΩ (footwear and standing
surface) in series.
"""


class MeasurementFileError(ValueError):
    """Raised when a measurement file cannot be interpreted."""


def _float(text: str | None, what: str) -> float:
    """Convert the text of an XML element to float or raise MeasurementFileError."""
    if text is None or not text.strip():
        raise MeasurementFileError(f"{what}: empty value")
    try:
        return float(text)
    except ValueError as exc:
        raise MeasurementFileError(f"{what}: {text!r} is not numeric") from exc


def _to_base_unit(
    values: np.ndarray, units: list[str], quantity: str, source: str
) -> np.ndarray:
    """Convert ``values`` to the SI base unit of ``quantity`` (A, V or m).

    Parameters
    ----------
    values : numpy.ndarray
        Values in the units given by ``units`` (one unit per value).
    units : list of str
        Unit of every value as written in the export.
    quantity : {"current", "voltage", "distance"}
        Physical quantity, used to check that the units are compatible.
    source : str
        Description used in error messages.

    Returns
    -------
    numpy.ndarray
        Converted values. Values already in the base unit are returned
        unchanged (bit-identical).
    """
    accepted = UNIT_FACTORS[quantity]
    factors = []
    for unit in units:
        unit = (unit or "").strip()
        if unit not in accepted:
            raise MeasurementFileError(f"{source}: unexpected {quantity} unit {unit!r}")
        factors.append(accepted[unit])
    if all(f == 1.0 for f in factors):
        return values
    return values * np.asarray(factors, dtype=float)


@dataclass(frozen=True)
class FallOfPotentialData:
    r"""Fall-of-potential test of a COMPANO 100 export.

    The instrument injects the current at two test frequencies next to the
    power frequency (e.g. 30 Hz and 70 Hz for 50 Hz) and stores, for every
    potential-probe distance, the complex voltage and current at both
    frequencies plus a *result* that is their complex mean, i.e. the linear
    interpolation to the power frequency.

    Attributes
    ----------
    distances_m : numpy.ndarray
        Potential-probe distances in m (order of the export).
    test_frequencies_hz : tuple of float
        The test frequencies, e.g. ``(30.0, 70.0)``.
    voltages : numpy.ndarray
        Complex probe voltages in V, shape ``(n_distances, n_frequencies)``.
    currents : numpy.ndarray
        Complex injected currents in A, same shape.
    result_voltages, result_currents : numpy.ndarray
        Complex instrument results (power frequency) per distance, in V/A.
    corrected_currents : numpy.ndarray or None
        Complex current into the footing per distance in A (injected
        current multiplied by the reduction factor), if the reduction factor
        was measured.
    reduction_factor : complex or None
        Share of the injected current that flows into the footing
        (``ReductionFactorData`` of the export).
    nominal_frequency_hz : float or None
        Power frequency configured on the instrument.
    timestamps : tuple of str
        Time stamp of every probe reading as written by the instrument.
    """

    distances_m: np.ndarray
    test_frequencies_hz: tuple[float, ...]
    voltages: np.ndarray
    currents: np.ndarray
    result_voltages: np.ndarray
    result_currents: np.ndarray
    corrected_currents: np.ndarray | None = None
    reduction_factor: complex | None = None
    nominal_frequency_hz: float | None = None
    timestamps: tuple[str, ...] = field(default_factory=tuple)

    def impedance(self, frequency_hz: float | None = None) -> np.ndarray:
        """Complex earthing impedance per distance in Ω.

        Parameters
        ----------
        frequency_hz : float, optional
            One of `test_frequencies_hz`; ``None`` (default) returns the
            power-frequency result ``U / I`` of the instrument.

        Returns
        -------
        numpy.ndarray
            Complex impedance per probe distance.

        Raises
        ------
        ValueError
            If ``frequency_hz`` is not a test frequency of the export.
        """
        if frequency_hz is None:
            return self.result_voltages / self.result_currents
        k = self._frequency_index(frequency_hz)
        return self.voltages[:, k] / self.currents[:, k]

    def footing_resistance(self) -> np.ndarray | None:
        """Complex footing (residual) resistance per distance in Ω.

        The probe voltage divided by the current that flows into the
        footing; ``None`` if the reduction factor was not measured.
        """
        if self.corrected_currents is None:
            return None
        return self.result_voltages / self.corrected_currents

    def _frequency_index(self, frequency_hz: float) -> int:
        for k, f in enumerate(self.test_frequencies_hz):
            if math.isclose(f, float(frequency_hz), abs_tol=1e-6):
                return k
        raise ValueError(
            f"{frequency_hz} Hz is not a test frequency of the export "
            f"({', '.join(f'{f:g}' for f in self.test_frequencies_hz)} Hz)"
        )


@dataclass(frozen=True)
class ReductionFactorData:
    """Reduction-factor (clamp) measurement of a COMPANO 100 export.

    The injected current is compared with the currents measured by a clamp
    (typically around the tower legs); the instrument's reduction factor is
    the share of the injected current that flows into the footing.

    Attributes
    ----------
    reduction_factor : complex
        Instrument result.
    output_currents : numpy.ndarray
        Complex injected current per clamp reading in A (power-frequency result).
    input_currents : numpy.ndarray
        Complex clamp current per reading in A (power-frequency result).
    timestamps : tuple of str
        Time stamp of every clamp reading.
    clamp_ratio_v_per_a : float or None
        Clamp ratio configured on the instrument.
    """

    reduction_factor: complex
    output_currents: np.ndarray
    input_currents: np.ndarray
    timestamps: tuple[str, ...] = field(default_factory=tuple)
    clamp_ratio_v_per_a: float | None = None


@dataclass(frozen=True)
class SoilResistivityData:
    r"""Soil-resistivity measurement of a COMPANO 100 export.

    The COMPANO describes the four-electrode arrangement by ``a`` (spacing
    of the potential electrodes), ``b`` (electrode depth) and ``c``
    (distance between a current electrode and the neighbouring potential
    electrode) and reports the apparent resistivity

    $$
    \rho_a = \pi\,\frac{c\,(c + a)}{a}\,R
    $$

    (Schlumberger; the Wenner arrangement is the special case ``c = a``
    with $\rho_a = 2\pi a R$).

    Attributes
    ----------
    rho_ohm_m : numpy.ndarray
        Apparent resistivity per reading in Ωm.
    spacing_a_m, depth_b_m, distance_c_m : numpy.ndarray
        Electrode geometry per reading in m.
    resistance_ohm : numpy.ndarray or None
        Measured resistance ``R`` per reading in Ω, if exported.
    timestamps : tuple of str
        Time stamp of every reading.
    """

    rho_ohm_m: np.ndarray
    spacing_a_m: np.ndarray
    depth_b_m: np.ndarray
    distance_c_m: np.ndarray
    resistance_ohm: np.ndarray | None = None
    timestamps: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ab_half_m(self) -> np.ndarray:
        """Half the current-electrode spacing ``AB/2 = c + a/2`` in m."""
        return self.distance_c_m + self.spacing_a_m / 2

    @property
    def mn_half_m(self) -> np.ndarray:
        """Half the potential-electrode spacing ``MN/2 = a/2`` in m."""
        return self.spacing_a_m / 2

    @property
    def is_wenner(self) -> bool:
        """``True`` if every reading has ``c = a`` (equally spaced electrodes)."""
        return bool(np.allclose(self.distance_c_m, self.spacing_a_m, rtol=1e-9))


class CompanoXMLReader:
    """Read an OMICRON COMPANO 100 XML export.

    Parameters
    ----------
    xml_path : str or os.PathLike
        Path of the XML file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.

    Examples
    --------
    >>> reader = CompanoXMLReader("ZE_LX-01_8.xml")  # doctest: +SKIP
    >>> data = reader.read_fall_of_potential()  # doctest: +SKIP
    >>> abs(data.impedance())  # power-frequency profile in Ω  # doctest: +SKIP
    >>> abs(data.impedance(70.0))  # at the upper test frequency  # doctest: +SKIP
    >>> impedance, residual = reader.get_impedance_to_ground_dataframe()  # doctest: +SKIP
    """

    def __init__(self, xml_path: str | os.PathLike[str]):
        if not os.path.exists(xml_path):
            raise FileNotFoundError(f"COMPANO XML file not found: {xml_path}")
        self.xml_path = os.fspath(xml_path)

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def convert_to_complex(mag: float, ang: float) -> complex:
        """Convert magnitude and phase angle (degrees) to a complex number.

        Parameters
        ----------
        mag : float
            Magnitude.
        ang : float
            Phase angle in degrees.

        Returns
        -------
        complex
            ``mag * exp(j * ang * pi / 180)``.
        """
        return mag * np.exp(1j * ang * np.pi / 180)

    def _root(self) -> ET.Element:
        """Parse the file and return the ``ReportData`` element."""
        try:
            root = ET.parse(self.xml_path).getroot()
        except ET.ParseError as exc:
            raise MeasurementFileError(
                f"{self._name}: not a valid XML file ({exc})"
            ) from exc
        report_data = root.find("ReportData")
        if report_data is None:
            raise MeasurementFileError(f"{self._name}: element 'ReportData' is missing")
        return report_data

    @property
    def _name(self) -> str:
        return os.path.basename(self.xml_path)

    def _find(self, parent: ET.Element, path: str) -> ET.Element:
        element = parent.find(path)
        if element is None:
            raise MeasurementFileError(f"{self._name}: element '{path}' is missing")
        return element

    def xml_iteration_subchild(
        self, element: ET.Element | None
    ) -> tuple[list[Any], list[str]]:
        """Collect the values and units below one measurement element.

        Three layouts occur in COMPANO exports:

        * ``<Distances><Distance><Value/><Unit/></Distance>...`` - plain values,
        * ``<RawOutputCurrents><Measurement><Result><Magnitude/><Phase/>`` -
          complex results (magnitude and phase),
        * ``<CorrectedOutputCurrents><OutputCurrent><Magnitude/><Phase/>`` -
          complex values without the ``Result`` level.

        Parameters
        ----------
        element : xml.etree.ElementTree.Element or None
            Parent element (e.g. ``Distances``).

        Returns
        -------
        values : list
            Floats for plain values, complex numbers for magnitude/phase pairs.
        units : list of str
            Unit of each value (magnitude unit for complex values).

        Raises
        ------
        MeasurementFileError
            If ``element`` is ``None`` or a value is not numeric.
        """
        if element is None:
            raise MeasurementFileError(f"{self._name}: measurement element is missing")
        values: list[Any] = []
        units: list[str] = []
        mag, ang, mag_unit = 0.0, 0.0, "A"

        def _magnitude_phase(node: ET.Element) -> None:
            nonlocal mag, ang, mag_unit
            for item in node:
                if item.tag == "Magnitude":
                    mag = _float(
                        self._find(item, "Value").text, f"{self._name} {element.tag}"
                    )
                    mag_unit = self._find(item, "Unit").text or ""
                elif item.tag == "Phase":
                    ang = _float(
                        self._find(item, "Value").text, f"{self._name} {element.tag}"
                    )
                    if (self._find(item, "Unit").text or "").strip().lower() == "rad":
                        ang = math.degrees(ang)

        for child in element:
            if child.tag != "Measurement" and element.tag != "CorrectedOutputCurrents":
                for sub_child in child:
                    if sub_child.tag == "Value":
                        values.append(
                            _float(sub_child.text, f"{self._name} {element.tag}")
                        )
                    elif sub_child.tag == "Unit":
                        units.append(sub_child.text or "")
            elif (
                child.tag == "OutputCurrent"
                and element.tag == "CorrectedOutputCurrents"
            ):
                _magnitude_phase(child)
                values.append(self.convert_to_complex(mag, ang))
                units.append(mag_unit)
            else:
                for sub_child in child:
                    if sub_child.tag == "Result":
                        _magnitude_phase(sub_child)
                        values.append(self.convert_to_complex(mag, ang))
                        units.append(mag_unit)
        if units and any(unit != units[0] for unit in units):
            logger.debug(
                "%s: mixed units in %s: %s", self._name, element.tag, sorted(set(units))
            )
        return values, units

    # --------------------------------------------------------------- measurements
    def get_impedance_to_ground_dataframe(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Read the fall-of-potential profile.

        The earthing impedance at every potential-probe distance is
        $Z(x) = |U(x) / I|$ with the raw output current $I$
        (``RawOutputCurrents``). Dividing by the current that actually flows
        into the tower footing (``CorrectedOutputCurrents``, i.e. corrected by
        the current returning through earth wires) gives the footing
        (residual) resistance profile.

        Returns
        -------
        impedance_to_ground : pandas.DataFrame
            Columns ``Distance`` (m), ``Impedance`` (Ohm), ``Unit`` and
            ``StepTouchCurrent`` (A, complex mean of the step/touch measuring
            currents, the same value in every row).
        residual_resistance : pandas.DataFrame
            Columns ``Distance`` (m), ``Impedance`` (Ohm), ``Unit`` and
            ``ResidualCurrent`` (A, complex mean of the corrected currents).

        Raises
        ------
        MeasurementFileError
            If a required element is missing, empty or has an unexpected unit.
        """
        report_data = self._root()
        measurement = self._find(report_data, _FALL_OF_POTENTIAL)
        distances_values, distances_units = self.xml_iteration_subchild(
            self._find(measurement, "Distances")
        )
        raw_values, raw_units = self.xml_iteration_subchild(
            self._find(measurement, "RawOutputCurrents")
        )
        corrected_values, corrected_units = self.xml_iteration_subchild(
            self._find(measurement, "CorrectedOutputCurrents")
        )
        voltage_values, voltage_units = self.xml_iteration_subchild(
            self._find(measurement, "InputVoltages")
        )
        step_touch_values, step_touch_units = self.xml_iteration_subchild(
            self._find(report_data, f"{_STEP_TOUCH_SETUP}/Measurements")
        )

        if len(distances_values) == 0:
            raise MeasurementFileError(f"{self._name}: no valid distance information")
        if len(raw_values) == 0 or len(voltage_values) == 0:
            raise MeasurementFileError(f"{self._name}: no valid impedance information")
        if not len(distances_values) == len(raw_values) == len(voltage_values):
            raise MeasurementFileError(
                f"{self._name}: {len(distances_values)} distances but {len(raw_values)} currents "
                f"and {len(voltage_values)} voltages"
            )

        distances = _to_base_unit(
            np.array(distances_values), distances_units, "distance", self._name
        )
        raw_currents = _to_base_unit(
            np.array(raw_values), raw_units, "current", self._name
        )
        corrected = _to_base_unit(
            np.array(corrected_values), corrected_units, "current", self._name
        )
        voltages = _to_base_unit(
            np.array(voltage_values), voltage_units, "voltage", self._name
        )
        step_touch = _to_base_unit(
            np.array(step_touch_values), step_touch_units, "current", self._name
        )
        step_touch_mean = np.mean(step_touch) if len(step_touch) else np.nan

        impedance_to_ground = pd.DataFrame(
            {
                "Distance": distances,
                "Impedance": np.abs(voltages / raw_currents),
                "Unit": "Ohm",
                "StepTouchCurrent": step_touch_mean,
            }
        )
        if len(corrected) != len(voltages):
            raise MeasurementFileError(
                f"{self._name}: {len(corrected)} corrected currents but {len(voltages)} voltages"
            )
        residual_resistance = pd.DataFrame(
            {
                "Distance": distances,
                "Impedance": np.abs(voltages / corrected),
                "Unit": "Ohm",
                "ResidualCurrent": np.mean(corrected),
            }
        )
        return impedance_to_ground, residual_resistance

    def get_soil_resistivity(self) -> dict[str, list[float]] | None:
        """Read a soil-resistivity measurement in the layout of the tower results.

        COMPANO already reports the apparent specific resistance for every
        electrode configuration, so no geometry calculation is needed. The
        keys match the per-tower JSON result of :mod:`groundmeas.towers`; use
        :meth:`read_soil_resistivity` for the geometry with English names.

        Returns
        -------
        dict or None
            ``{"rho_OhmMeter": [...], "DistanzA_m": [...], "DistanzB_m": [...],
            "DistanzC_m": [...]}`` or ``None`` if the export contains no
            soil-resistivity report.
        """
        report_data = self._root()
        screen = report_data.find(
            "SoilResistanceReport/SoilResistanceWidgetData/SoilResistanceMeasurementScreenData"
        )
        if screen is None:
            return None

        def _values(tag: str) -> list[float]:
            element = screen.find(tag)
            if element is None:
                return []
            collected = []
            for item in element:
                value = item.find("Value")
                if value is not None and value.text is not None:
                    collected.append(float(value.text))
            return collected

        rho = _values("SpecificResistances")
        if not rho:
            return None
        return {
            "rho_OhmMeter": rho,
            "DistanzA_m": _values("DistancesA"),
            "DistanzB_m": _values("DistancesB"),
            "DistanzC_m": _values("DistancesC"),
        }

    def get_nominal_frequency(self) -> float | None:
        """Return the nominal power frequency configured on the instrument.

        Returns
        -------
        float or None
            Frequency in Hz (``50.0`` or ``60.0``) or ``None`` if not present.
        """
        report_data = self._root()
        for path in (
            f"{_STEP_TOUCH_SETUP}/OutputSetupData/NominalFrequency/Value",
            "SystemConfiguration/RegionalConfiguration/NominalFrequency/Value",
        ):
            element = report_data.find(path)
            if element is not None and element.text:
                return float(element.text)
        return None

    # ------------------------------------------------------- per-frequency data
    def _magnitude_phase_value(
        self, node: ET.Element, what: str
    ) -> tuple[complex, str]:
        """Complex value and magnitude unit of a ``<Magnitude/><Phase/>`` node."""
        magnitude = self._find(node, "Magnitude")
        mag = _float(self._find(magnitude, "Value").text, what)
        unit = (magnitude.findtext("Unit") or "").strip()
        ang = 0.0
        phase = node.find("Phase")
        if phase is not None:
            ang = _float(self._find(phase, "Value").text, what)
            if (phase.findtext("Unit") or "").strip().lower() == "rad":
                ang = math.degrees(ang)
        return self.convert_to_complex(mag, ang), unit

    def _measurement_series(
        self, element: ET.Element | None, quantity: str, what: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """Per-frequency values and results of ``<X><Measurement>...``.

        Returns ``(per_frequency, result)``: complex arrays of shape
        ``(n, k)`` and ``(n,)`` in the SI base unit of ``quantity``.

        The result carries a unit (e.g. ``mV``); the per-frequency values do
        not. The instrument's result is the mean of the per-frequency values,
        so their unit is identified by comparing both: either they are in the
        unit of the result or already in the base unit.
        """
        if element is None:
            raise MeasurementFileError(f"{self._name}: element '{what}' is missing")
        rows: list[list[complex]] = []
        results: list[complex] = []
        units: list[str] = []
        for measurement in element.findall("Measurement"):
            rows.append(
                [
                    complex(
                        _float(c.findtext("Real"), f"{self._name} {what}"),
                        _float(c.findtext("Imag"), f"{self._name} {what}"),
                    )
                    for c in measurement.findall("Measurements/Complex")
                ]
            )
            result, unit = self._magnitude_phase_value(
                self._find(measurement, "Result"), f"{self._name} {what}"
            )
            results.append(result)
            units.append(unit)
        widths = {len(row) for row in rows}
        if len(widths) > 1:
            raise MeasurementFileError(
                f"{self._name}: {what} has a varying number of test frequencies"
            )
        width = widths.pop() if widths else 0
        per_frequency = np.array(rows, dtype=complex).reshape(len(rows), width)
        raw_results = np.array(results, dtype=complex)
        factors = _to_base_unit(
            np.ones(len(units)), units, quantity, f"{self._name} {what}"
        )
        row_factors = factors.copy()
        if width:
            means = np.abs(per_frequency.mean(axis=1))
            magnitudes = np.abs(raw_results)
            for i, (mean, magnitude, factor) in enumerate(
                zip(means, magnitudes, factors)
            ):
                if factor == 1.0 or magnitude == 0.0 or mean == 0.0:
                    continue
                if math.isclose(mean, magnitude, rel_tol=1e-2):
                    continue  # per-frequency values in the unit of the result
                if math.isclose(mean, magnitude * factor, rel_tol=1e-2):
                    row_factors[i] = 1.0  # already in the base unit
                    continue
                raise MeasurementFileError(
                    f"{self._name}: {what} per-frequency values do not match the "
                    "result of the instrument"
                )
        return per_frequency * row_factors[:, None], raw_results * factors

    def _frequencies(self, setup: ET.Element | None) -> tuple[float, ...]:
        if setup is None:
            return ()
        return tuple(
            _float(e.text, f"{self._name} test frequency")
            for e in setup.findall("OutputSetupData/Frequencies/TargetFrequency/Value")
        )

    def read_fall_of_potential(self) -> FallOfPotentialData:
        """Read the fall-of-potential test with the values at both test frequencies.

        Returns
        -------
        FallOfPotentialData
            Distances, complex voltages and currents per test frequency, the
            instrument results, the footing currents and the reduction factor.

        Raises
        ------
        MeasurementFileError
            If the export has no (complete) fall-of-potential test.

        Examples
        --------
        >>> data = CompanoXMLReader("ZE_L1_8.xml").read_fall_of_potential()  # doctest: +SKIP
        >>> abs(data.impedance(70.0))                                        # doctest: +SKIP
        array([0.033, 0.052, ...])
        """
        report_data = self._root()
        screen = self._find(report_data, _FALL_OF_POTENTIAL)
        distance_values, distance_units = self.xml_iteration_subchild(
            self._find(screen, "Distances")
        )
        distances = _to_base_unit(
            np.array(distance_values, dtype=float),
            distance_units,
            "distance",
            self._name,
        )
        voltages, result_voltages = self._measurement_series(
            screen.find("InputVoltages"), "voltage", "InputVoltages"
        )
        currents, result_currents = self._measurement_series(
            screen.find("RawOutputCurrents"), "current", "RawOutputCurrents"
        )
        if not len(distances) == len(voltages) == len(currents):
            raise MeasurementFileError(
                f"{self._name}: {len(distances)} distances but {len(currents)} currents "
                f"and {len(voltages)} voltages"
            )
        if len(distances) == 0:
            raise MeasurementFileError(f"{self._name}: no valid distance information")

        frequencies = self._frequencies(screen) or self._frequencies(
            report_data.find(_STEP_TOUCH_SETUP)
        )
        if voltages.shape[1] and len(frequencies) != voltages.shape[1]:
            raise MeasurementFileError(
                f"{self._name}: {voltages.shape[1]} values per distance but "
                f"{len(frequencies)} test frequencies"
            )

        corrected: np.ndarray | None = None
        corrected_element = screen.find("CorrectedOutputCurrents")
        if corrected_element is not None and len(corrected_element):
            corrected_values, corrected_units = self.xml_iteration_subchild(
                corrected_element
            )
            corrected = _to_base_unit(
                np.array(corrected_values, dtype=complex),
                corrected_units,
                "current",
                self._name,
            )
            if len(corrected) != len(distances):
                raise MeasurementFileError(
                    f"{self._name}: {len(corrected)} corrected currents but "
                    f"{len(distances)} distances"
                )

        reduction: complex | None = None
        reduction_element = screen.find("ReductionFactorData")
        if (
            reduction_element is not None
            and reduction_element.find("Magnitude") is not None
        ):
            reduction, _unit = self._magnitude_phase_value(
                reduction_element, f"{self._name} ReductionFactorData"
            )

        return FallOfPotentialData(
            distances_m=np.asarray(distances, dtype=float),
            test_frequencies_hz=frequencies,
            voltages=voltages,
            currents=currents,
            result_voltages=result_voltages,
            result_currents=result_currents,
            corrected_currents=corrected,
            reduction_factor=reduction,
            nominal_frequency_hz=self.get_nominal_frequency(),
            timestamps=tuple(
                (e.text or "").strip() for e in screen.findall("TimeStamps/TimeStamp")
            ),
        )

    def read_reduction_factor(self) -> ReductionFactorData | None:
        """Read the reduction-factor (clamp) measurement of the fall-of-potential test.

        Returns
        -------
        ReductionFactorData or None
            ``None`` if the export contains no reduction-factor result.

        Raises
        ------
        MeasurementFileError
            If the measurement is present but malformed.
        """
        report_data = self._root()
        screen = report_data.find(_REDUCTION_FACTOR)
        if screen is None:
            return None
        result = screen.find("ReductionFactorData")
        if result is None or result.find("Magnitude") is None:
            return None
        factor, _unit = self._magnitude_phase_value(
            result, f"{self._name} ReductionFactorData"
        )
        _out, output_results = self._measurement_series(
            screen.find("OutputCurrents"), "current", "OutputCurrents"
        )
        _in, input_results = self._measurement_series(
            screen.find("InputCurrents"), "current", "InputCurrents"
        )
        ratio: float | None = None
        ratio_value = screen.findtext("ClampRatio/Value")
        if ratio_value:
            ratio = _float(ratio_value, f"{self._name} ClampRatio")
        return ReductionFactorData(
            reduction_factor=factor,
            output_currents=output_results,
            input_currents=input_results,
            timestamps=tuple(
                (e.text or "").strip() for e in screen.findall("TimeStamps/TimeStamp")
            ),
            clamp_ratio_v_per_a=ratio,
        )

    def get_step_touch_currents(self) -> tuple[tuple[float, ...], np.ndarray]:
        """Output currents of the step/touch test per test frequency.

        Returns
        -------
        frequencies : tuple of float
            Test frequencies in Hz (may be empty if not exported).
        currents : numpy.ndarray
            Current magnitude per test frequency in A (empty if the export
            has no step/touch test).
        """
        report_data = self._root()
        setup = report_data.find(_STEP_TOUCH_SETUP)
        if setup is None:
            return (), np.array([], dtype=float)
        measurements = setup.find("Measurements")
        if measurements is None or not len(measurements):
            return self._frequencies(setup), np.array([], dtype=float)
        values, units = self.xml_iteration_subchild(measurements)
        currents = _to_base_unit(
            np.array(values, dtype=float), units, "current", f"{self._name} step/touch"
        )
        return self._frequencies(setup), currents

    def read_soil_resistivity(self) -> SoilResistivityData | None:
        """Read the soil-resistivity measurement with its electrode geometry.

        Returns
        -------
        SoilResistivityData or None
            ``None`` if the export contains no soil-resistivity readings.

        Raises
        ------
        MeasurementFileError
            If the geometry lists do not match the number of readings.
        """
        report_data = self._root()
        screen = report_data.find(_SOIL)
        if screen is None:
            return None

        def _values(tag: str, quantity: str | None) -> np.ndarray:
            element = screen.find(tag)
            if element is None:
                return np.array([], dtype=float)
            values: list[float] = []
            units: list[str] = []
            for item in element:
                value = item.find("Value")
                if value is None:
                    value = item.find("Magnitude/Value")
                    unit = item.findtext("Magnitude/Unit") or ""
                else:
                    unit = item.findtext("Unit") or ""
                if value is not None and value.text is not None:
                    values.append(_float(value.text, f"{self._name} {tag}"))
                    units.append(unit.strip())
            array = np.array(values, dtype=float)
            if quantity is not None and len(array):
                array = _to_base_unit(array, units, quantity, f"{self._name} {tag}")
            return array

        rho = _values("SpecificResistances", None)
        if not len(rho):
            return None
        a = _values("DistancesA", "distance")
        b = _values("DistancesB", "distance")
        c = _values("DistancesC", "distance")
        if not len(a) == len(b) == len(c) == len(rho):
            raise MeasurementFileError(
                f"{self._name}: {len(rho)} resistivities but {len(a)}/{len(b)}/{len(c)} "
                "distances a/b/c"
            )
        resistance = _values("Impedances", None)
        return SoilResistivityData(
            rho_ohm_m=rho,
            spacing_a_m=a,
            depth_b_m=b,
            distance_c_m=c,
            resistance_ohm=resistance if len(resistance) == len(rho) else None,
            timestamps=tuple(
                (e.text or "").strip() for e in screen.findall("TimeStamps/TimeStamp")
            ),
        )

    def get_report_timestamp(self) -> str | None:
        """Time stamp of the export (``ReportData/TimeStamp``) as written by the instrument."""
        text = self._root().findtext("TimeStamp")
        return text.strip() if text else None


def _read_text(path: str) -> str:
    """Read a text export, tolerating UTF-8 (with/without BOM) and Windows-1252."""
    with open(path, "rb") as file:
        raw = file.read()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


class Hgt1TXTReader:
    """Read an OMICRON HGT1 *StepTouch* report (tab-separated text).

    The HGT1 measures the voltage between a test electrode and the earthed
    object frequency-selectively at two frequencies ``f1`` and ``f2`` next to
    the power frequency (e.g. 30 Hz and 70 Hz for a 50 Hz system). The value at
    the nominal frequency is obtained by linear interpolation, see
    `calc_50_Hz_voltage`.

    Parameters
    ----------
    file_path : str or os.PathLike
        Path of the report (``*.txt``).
    nominal_frequency : float, optional
        Power frequency in Hz the readings are interpolated to, by default 50.
    language : str, optional
        Language of the termination labels (``"en"`` or ``"de"``).

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """

    COLUMNS = (
        "Location",
        "Meas. ID",
        "Date",
        "Time",
        "f1",
        "Level1",
        "f2",
        "Level2",
        "Termination",
    )
    """Columns of the parsed data frame (in this order)."""
    _NUMERIC = ("f1", "Level1", "f2", "Level2")
    _UNIT_OK: ClassVar[dict[str, tuple[str, ...]]] = {
        "f1": ("[Hz]",),
        "f2": ("[Hz]",),
        "Level1": ("[V]", "[mV]"),
        "Level2": ("[V]", "[mV]"),
    }

    def __init__(
        self,
        file_path: str | os.PathLike[str],
        nominal_frequency: float = 50.0,
        language: str = "en",
    ):
        self.df: pd.DataFrame | None = None
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"HGT1 report not found: {file_path}")
        self.file_path = os.fspath(file_path)
        self.nominal_frequency = float(nominal_frequency)
        self.language = language

    @property
    def _name(self) -> str:
        return os.path.basename(self.file_path)

    def _header_index(self, lines: list[str]) -> int:
        for index, line in enumerate(lines):
            cells = {cell.strip() for cell in line.split("\t")}
            if {"Location", "Termination", "Level1", "Level2"} <= cells:
                return index
        raise MeasurementFileError(
            f"{self._name}: header line of the StepTouch results not found"
        )

    def parse_report(self) -> pd.DataFrame:
        """Parse the *StepTouch Results* table.

        Returns
        -------
        pandas.DataFrame
            One row per reading with the columns `COLUMNS`; ``f1``,
            ``Level1``, ``f2`` and ``Level2`` are floats (Hz and V), all other
            columns are stripped strings.

        Raises
        ------
        MeasurementFileError
            If the table is missing, has unexpected units or malformed rows.
        """
        lines = _read_text(self.file_path).splitlines()
        header_index = self._header_index(lines)
        header = [cell.strip() for cell in lines[header_index].split("\t")]
        missing = [column for column in self.COLUMNS if column not in header]
        if missing:
            raise MeasurementFileError(f"{self._name}: columns {missing} are missing")
        position = {column: header.index(column) for column in self.COLUMNS}

        units = (
            [cell.strip() for cell in lines[header_index + 1].split("\t")]
            if (header_index + 1 < len(lines))
            else []
        )
        scale = dict.fromkeys(self._NUMERIC, 1.0)
        for column, accepted in self._UNIT_OK.items():
            unit = units[position[column]] if position[column] < len(units) else ""
            if unit not in accepted:
                raise MeasurementFileError(
                    f"{self._name}: unexpected unit {unit!r} for {column} (expected {accepted[0]})"
                )
            if unit == "[mV]":
                scale[column] = 1e-3

        rows: list[dict[str, Any]] = []
        for number, line in enumerate(
            lines[header_index + 2 :], start=header_index + 3
        ):
            if not line.strip():
                if rows:
                    break
                continue
            if line.lstrip().startswith("#"):
                break
            cells = line.split("\t")
            if len(cells) != len(header):
                raise MeasurementFileError(
                    f"{self._name}, line {number}: {len(cells)} fields, expected {len(header)}"
                )
            row: dict[str, Any] = {
                column: cells[position[column]].strip() for column in self.COLUMNS
            }
            try:
                for column in self._NUMERIC:
                    row[column] = float(row[column]) * scale[column]
            except ValueError as exc:
                raise MeasurementFileError(
                    f"{self._name}, line {number}: frequency or level is not numeric"
                ) from exc
            rows.append(row)
        if not rows:
            raise MeasurementFileError(f"{self._name}: the report contains no readings")
        self.df = pd.DataFrame(rows, columns=list(self.COLUMNS))
        return self.df

    def calc_50_Hz_voltage(self) -> None:
        r"""Interpolate the readings to the nominal frequency.

        For every reading the voltage at the nominal frequency $f_n$
        (default 50 Hz) is

        $$
        U_{f_n} = U_1 + (f_n - f_1)\,\frac{U_2 - U_1}{f_2 - f_1}
        $$

        The result is stored in the column ``Level50`` (the name is kept for
        compatibility; it holds the value at ``nominal_frequency``) together
        with ``f50`` and a readable ``TerminationLabel``.

        Raises
        ------
        MeasurementFileError
            If the report has not been parsed or ``f1 == f2``.
        """
        if self.df is None:
            raise MeasurementFileError(f"{self._name}: call parse_report() first")
        f0, f1 = self.df["f1"], self.df["f2"]
        u0, u1 = self.df["Level1"], self.df["Level2"]
        if (f1 == f0).any():
            raise MeasurementFileError(
                f"{self._name}: f1 and f2 must differ for the interpolation"
            )
        fn = self.nominal_frequency
        self.df["Level50"] = u0 + (fn - f0) * (u1 - u0) / (f1 - f0)
        self.df["f50"] = fn
        labels = TERMINATION_LABELS.get(self.language, TERMINATION_LABELS["en"])
        terminations = self.df["Termination"].astype(str).str.strip()
        self.df["TerminationLabel"] = terminations.map(labels).fillna(terminations)

    def get_touchvoltage_dataframe(self) -> pd.DataFrame:
        """Parse the report and interpolate it to the nominal frequency.

        Returns
        -------
        pandas.DataFrame
            Columns `COLUMNS` plus ``Level50`` (V), ``f50`` (Hz) and
            ``TerminationLabel``.
        """
        self.parse_report()
        self.calc_50_Hz_voltage()
        assert self.df is not None
        return self.df


def informative_locations(locations: Iterable[object]) -> bool:
    """Tell whether the HGT1 ``Location`` column carries real location names.

    Instruments that were not configured report a placeholder for every
    reading (``MyLocation`` or a number such as ``1``).

    Parameters
    ----------
    locations : iterable
        Values of the ``Location`` column.

    Returns
    -------
    bool
        ``True`` if at least one value is a real name.
    """
    for value in locations:
        text = str(value).strip()
        if (
            text
            and text.lower() not in {"mylocation", "nan", "none"}
            and not text.isdigit()
        ):
            return True
    return False
