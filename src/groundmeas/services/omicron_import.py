"""
groundmeas.services.omicron_import
==================================

Import OMICRON COMPANO 100 and HGT1 exports into the groundmeas database.

One :class:`~groundmeas.core.models.Measurement` is created per test:

========================  ==================================================
Test (file)               Items
========================  ==================================================
fall of potential         ``earthing_impedance`` per probe distance at the
(COMPANO XML,             power frequency (instrument result) and, by
``injection_earth_        default, at both test frequencies;
electrode``)              ``earthing_resistance`` (footing resistance) if
                          the reduction factor was applied;
                          ``earthing_current`` (injected current);
                          ``earth_fault_current`` and ``shield_current``
                          derived from the clamp readings of the reduction
                          factor, so that :func:`~groundmeas.calculate_split_factor`
                          returns the footing share.
touch voltages            ``touch_voltage`` (or ``transferred_potential``)
(HGT1 report,             per reading with ``input_impedance_ohm = 1000``
``injection_earth_        and ``additional_resistance_ohm`` 0 (``1k``) or
electrode``)              1000 (``2x1k``); high-impedance readings
                          (``HIGH Z``) as ``prospective_touch_voltage``;
                          ``earthing_current`` of the step/touch test from
                          the COMPANO export.
soil resistivity          ``soil_resistivity`` per reading; Wenner: spacing
(COMPANO XML, ``wenner``  ``a`` in ``measurement_distance_m``;
or ``schlumberger``)      Schlumberger: ``AB/2`` in ``measurement_distance_m``
                          and ``MN/2`` in ``distance_to_current_injection_m``.
========================  ==================================================

The item builders (``*_items``) are pure functions and are also used by the
tower campaign import of :mod:`groundmeas.towers`.
"""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime, timezone as _timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from ..core.db import create_measurement_with_items
from ..instruments.omicron import (
    CompanoXMLReader,
    FallOfPotentialData,
    Hgt1TXTReader,
    ReductionFactorData,
    SoilResistivityData,
)

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]
LocationLike = Union[str, Dict[str, Any]]

HGT1_INPUT_IMPEDANCE_OHM: float = 1000.0
"""Body resistance of the HGT1 touch-voltage measurement (Ω)."""

HGT1_ADDITIONAL_RESISTANCE_OHM: Dict[str, float] = {"1k": 0.0, "2x1k": 1000.0}
"""Additional resistance in series with the body resistance per termination (Ω)."""

HGT1_HIGH_IMPEDANCE = re.compile(r"hi(?:gh)?[\s_-]*z|200\s*k(?:ohm|Ω)?", re.IGNORECASE)
"""Termination of a high-impedance (open-circuit) reading of the HGT1."""

_TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d")


# ----------------------------------------------------------------------------- helpers
def _polar(value: complex) -> Dict[str, float]:
    return {
        "value": float(abs(value)),
        "value_angle_deg": float(math.degrees(math.atan2(value.imag, value.real))),
    }


def _item(
    measurement_type: str, value: Union[complex, float], unit: str, **fields: Any
) -> Dict[str, Any]:
    item: Dict[str, Any] = {"measurement_type": measurement_type, "unit": unit}
    if isinstance(value, complex):
        item.update(_polar(value))
    else:
        item["value"] = float(value)
    item.update({key: val for key, val in fields.items() if val is not None})
    return item


def parse_instrument_timestamp(
    text: Optional[str], timezone: Optional[str] = None
) -> Optional[datetime]:
    """
    Parse a time stamp written by an OMICRON instrument.

    Parameters
    ----------
    text : str or None
        ``"2025-09-10 12:19:39.914"``, ``"2025-09-10 12:19:39"`` or ``"2025-09-10"``.
    timezone : str, optional
        IANA time zone of the instrument clock (e.g. ``"Europe/Berlin"``). If
        given, the time is converted to naive UTC as stored by groundmeas;
        otherwise the instrument's local time is kept.

    Returns
    -------
    datetime or None
        ``None`` for empty or unparsable text.
    """
    if not text or not text.strip():
        return None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            parsed = datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
        if timezone:
            parsed = (
                parsed.replace(tzinfo=ZoneInfo(timezone))
                .astimezone(_timezone.utc)
                .replace(tzinfo=None)
            )
        return parsed
    logger.warning("Unrecognised instrument time stamp %r", text)
    return None


def _location_payload(location: LocationLike) -> Dict[str, Any]:
    if isinstance(location, str):
        if not location.strip():
            raise ValueError("location name must not be empty")
        return {"name": location.strip()}
    if isinstance(location, dict) and location.get("name"):
        return dict(location)
    raise ValueError("location must be a name or a dict with at least 'name'")


def _measurement_payload(
    *,
    location: LocationLike,
    asset_type: str,
    method: str,
    timestamp: Optional[datetime],
    description: Optional[str],
    operator: Optional[str],
    voltage_level_kv: Optional[float],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "method": method,
        "asset_type": asset_type,
        "location": _location_payload(location),
        "description": description,
        "operator": operator,
        "voltage_level_kv": voltage_level_kv,
    }
    if timestamp is not None:
        payload["timestamp"] = timestamp
    return {k: v for k, v in payload.items() if v is not None}


def _reduction_factor_measured(reduction: Optional[ReductionFactorData]) -> bool:
    return reduction is not None and len(reduction.input_currents) > 0


# ----------------------------------------------------------------------- item builders
def fall_of_potential_items(
    data: FallOfPotentialData,
    *,
    current_electrode_distance_m: Optional[float] = None,
    per_frequency: bool = True,
    reduction: Optional[ReductionFactorData] = None,
    nominal_frequency_hz: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Build MeasurementItem payloads for a COMPANO fall-of-potential test.

    Parameters
    ----------
    data : FallOfPotentialData
        Result of :meth:`CompanoXMLReader.read_fall_of_potential`.
    current_electrode_distance_m : float, optional
        Distance of the current electrode; needed for the 62 % method.
    per_frequency : bool, default True
        Also store the impedance at both test frequencies.
    reduction : ReductionFactorData, optional
        Clamp readings of the reduction factor (adds ``earth_fault_current``
        and ``shield_current``).
    nominal_frequency_hz : float, optional
        Frequency of the instrument result; defaults to the nominal frequency
        of the export (50 Hz if not exported).

    Returns
    -------
    list of dict
        Item payloads for :func:`groundmeas.create_items`.
    """
    nominal = nominal_frequency_hz or data.nominal_frequency_hz or 50.0
    if per_frequency and not data.has_test_frequency_values:
        logger.info(
            "The export contains no values at the test frequencies; only the "
            "power-frequency result is stored"
        )
        per_frequency = False
    impedance = data.impedance()
    footing = data.footing_resistance()
    if footing is not None and np.allclose(
        data.corrected_currents, data.result_currents, rtol=1e-9
    ):
        footing = None  # no reduction factor applied: footing = impedance
    items: List[Dict[str, Any]] = []
    for k, distance in enumerate(data.distances_m):
        geometry = {
            "measurement_distance_m": float(distance),
            "distance_to_current_injection_m": current_electrode_distance_m,
        }
        items.append(
            _item(
                "earthing_impedance",
                complex(impedance[k]),
                "Ω",
                frequency_hz=nominal,
                **geometry,
            )
        )
        if per_frequency:
            for f in data.test_frequencies_hz:
                items.append(
                    _item(
                        "earthing_impedance",
                        complex(data.impedance(f)[k]),
                        "Ω",
                        frequency_hz=f,
                        **geometry,
                    )
                )
        if footing is not None:
            items.append(
                _item(
                    "earthing_resistance",
                    complex(footing[k]),
                    "Ω",
                    frequency_hz=nominal,
                    description="footing resistance: probe voltage / current into "
                    "the footing (COMPANO reduction factor applied)",
                    **geometry,
                )
            )
    items.append(
        _item(
            "earthing_current",
            complex(np.mean(data.result_currents)),
            "A",
            frequency_hz=nominal,
            description="injected current of the fall-of-potential test "
            f"(mean of {len(data.result_currents)} readings)",
        )
    )
    if _reduction_factor_measured(reduction):
        assert reduction is not None
        injected = complex(np.mean(reduction.output_currents))
        factor = reduction.reduction_factor
        angle = math.degrees(math.atan2(factor.imag, factor.real))
        note = (
            f"COMPANO reduction factor r = {abs(factor):.4f} at {angle:.1f} deg from "
            f"{len(reduction.input_currents)} clamp readings"
        )
        items.append(
            _item(
                "earth_fault_current",
                injected,
                "A",
                frequency_hz=nominal,
                description=f"injected test current of the clamp measurement; {note}",
            )
        )
        items.append(
            _item(
                "shield_current",
                injected * (1 - factor),
                "A",
                frequency_hz=nominal,
                description="current not flowing into the footing (earth wires), "
                f"derived as I (1 - r); {note}",
            )
        )
    return items


def step_touch_items(
    readings: pd.DataFrame,
    *,
    reference_frequencies_hz: Sequence[float] = (),
    reference_currents_a: Sequence[float] = (),
    nominal_frequency_hz: float = 50.0,
    per_frequency: bool = True,
    measurement_type: str = "touch_voltage",
) -> List[Dict[str, Any]]:
    """
    Build MeasurementItem payloads for HGT1 touch-voltage readings.

    Parameters
    ----------
    readings : pandas.DataFrame
        Result of :meth:`Hgt1TXTReader.get_touchvoltage_dataframe`.
    reference_frequencies_hz, reference_currents_a : sequence of float
        Output current of the step/touch test per test frequency (from the
        COMPANO export, see :meth:`CompanoXMLReader.get_step_touch_currents`).
    nominal_frequency_hz : float, default 50.0
        Frequency of the interpolated values (``Level50``).
    per_frequency : bool, default True
        Also store the readings at both test frequencies.
    measurement_type : {"touch_voltage", "transferred_potential"}
        Item type of the voltages.

    Returns
    -------
    list of dict
        Item payloads for :func:`groundmeas.create_items`.
    """
    items: List[Dict[str, Any]] = []
    unknown: List[str] = []
    for _, row in readings.iterrows():
        termination = str(row["Termination"]).strip()
        item_type = measurement_type
        input_impedance: Optional[float] = None
        if termination in HGT1_ADDITIONAL_RESISTANCE_OHM:
            input_impedance = HGT1_INPUT_IMPEDANCE_OHM
        elif HGT1_HIGH_IMPEDANCE.fullmatch(termination):
            # open-circuit voltage: the prospective touch voltage
            if measurement_type == "touch_voltage":
                item_type = "prospective_touch_voltage"
        elif termination not in unknown:
            unknown.append(termination)
        fields = {
            "input_impedance_ohm": input_impedance,
            "additional_resistance_ohm": HGT1_ADDITIONAL_RESISTANCE_OHM.get(
                termination
            ),
            "description": f"{str(row['Location']).strip()} ({termination}, "
            f"HGT1 reading {str(row['Meas. ID']).strip()})",
        }
        items.append(
            _item(
                item_type,
                float(row["Level50"]),
                "V",
                frequency_hz=nominal_frequency_hz,
                **fields,
            )
        )
        if per_frequency:
            for f_col, u_col in (("f1", "Level1"), ("f2", "Level2")):
                items.append(
                    _item(
                        item_type,
                        float(row[u_col]),
                        "V",
                        frequency_hz=float(row[f_col]),
                        **fields,
                    )
                )
    if unknown:
        logger.warning(
            "Unknown HGT1 termination %s; the readings are stored without input "
            "impedance and additional resistance",
            ", ".join(repr(t) for t in unknown),
        )
    currents = [float(c) for c in reference_currents_a]
    if currents:
        items.append(
            _item(
                "earthing_current",
                float(np.mean(currents)),
                "A",
                frequency_hz=nominal_frequency_hz,
                description="output current of the step/touch test",
            )
        )
        if per_frequency and len(reference_frequencies_hz) == len(currents):
            for f, current in zip(reference_frequencies_hz, currents):
                items.append(
                    _item(
                        "earthing_current",
                        current,
                        "A",
                        frequency_hz=float(f),
                        description="output current of the step/touch test",
                    )
                )
    return items


def soil_resistivity_items(
    data: SoilResistivityData,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build MeasurementItem payloads for a COMPANO soil-resistivity measurement.

    Parameters
    ----------
    data : SoilResistivityData
        Result of :meth:`CompanoXMLReader.read_soil_resistivity`.

    Returns
    -------
    method : {"wenner", "schlumberger"}
        ``"wenner"`` if every reading has ``c = a``.
    items : list of dict
        One ``soil_resistivity`` item per reading (apparent resistivity in Ωm).
    """
    wenner = data.is_wenner
    items: List[Dict[str, Any]] = []
    for i, rho in enumerate(data.rho_ohm_m):
        a = float(data.spacing_a_m[i])
        c = float(data.distance_c_m[i])
        b = float(data.depth_b_m[i])
        geometry: Dict[str, Any]
        if wenner:
            geometry = {"measurement_distance_m": a}
        else:
            geometry = {
                "measurement_distance_m": float(data.ab_half_m[i]),
                "distance_to_current_injection_m": float(data.mn_half_m[i]),
            }
        note = f"COMPANO a={a:g} m, b={b:g} m, c={c:g} m"
        if data.resistance_ohm is not None:
            note += f", R={float(data.resistance_ohm[i]):.6g} Ω"
        items.append(
            _item("soil_resistivity", float(rho), "Ωm", description=note, **geometry)
        )
    return ("wenner" if wenner else "schlumberger"), items


# ----------------------------------------------------------------------------- imports
def import_fall_of_potential(
    xml_path: PathLike,
    *,
    location: LocationLike,
    asset_type: str,
    current_electrode_distance_m: Optional[float] = None,
    per_frequency: bool = True,
    operator: Optional[str] = None,
    description: Optional[str] = None,
    voltage_level_kv: Optional[float] = None,
    timezone: Optional[str] = None,
) -> int:
    """
    Import the fall-of-potential test of a COMPANO 100 export.

    Parameters
    ----------
    xml_path : str or Path
        COMPANO XML export.
    location : str or dict
        Location name or payload (``name``, optional ``latitude``,
        ``longitude``, ``altitude``); existing locations are reused.
    asset_type : str
        Asset type of the measurement (e.g. ``"overhead_line_tower"``).
    current_electrode_distance_m : float, optional
        Distance of the current electrode (stored on every profile item;
        required for the 62 % method).
    per_frequency : bool, default True
        Also store the profile at both test frequencies.
    operator, description : str, optional
        Measurement metadata (a description naming the file is generated if
        omitted).
    voltage_level_kv : float, optional
        Nominal voltage of the installation.
    timezone : str, optional
        IANA time zone of the instrument clock; converts the time stamp to UTC.

    Returns
    -------
    int
        ID of the created measurement.

    Raises
    ------
    groundmeas.instruments.MeasurementFileError
        If the export is incomplete.
    RuntimeError
        On database errors.
    """
    path = Path(xml_path)
    reader = CompanoXMLReader(path)
    data = reader.read_fall_of_potential()
    reduction = reader.read_reduction_factor()
    if current_electrode_distance_m is None:
        logger.warning(
            "%s: no current-electrode distance given; the 62 %% method will not "
            "be available for this profile",
            path.name,
        )
    items = fall_of_potential_items(
        data,
        current_electrode_distance_m=current_electrode_distance_m,
        per_frequency=per_frequency,
        reduction=reduction,
    )
    stamp = data.timestamps[0] if data.timestamps else reader.get_report_timestamp()
    measurement_id, _item_ids = create_measurement_with_items(
        _measurement_payload(
            location=location,
            asset_type=asset_type,
            method="injection_earth_electrode",
            timestamp=parse_instrument_timestamp(stamp, timezone),
            description=description
            or f"Fall-of-potential test, OMICRON COMPANO 100 ({path.name})",
            operator=operator,
            voltage_level_kv=voltage_level_kv,
        ),
        items,
    )
    logger.info(
        "Imported %s as measurement %d (%d items)",
        path.name,
        measurement_id,
        len(items),
    )
    return measurement_id


def import_step_touch(
    hgt1_path: PathLike,
    *,
    location: LocationLike,
    asset_type: str,
    compano_xml_path: Optional[PathLike] = None,
    nominal_frequency_hz: Optional[float] = None,
    per_frequency: bool = True,
    transferred: bool = False,
    operator: Optional[str] = None,
    description: Optional[str] = None,
    voltage_level_kv: Optional[float] = None,
    timezone: Optional[str] = None,
) -> int:
    """
    Import an HGT1 touch-voltage report.

    Parameters
    ----------
    hgt1_path : str or Path
        HGT1 *StepTouch* report.
    location : str or dict
        Location name or payload.
    asset_type : str
        Asset type of the measurement.
    compano_xml_path : str or Path, optional
        COMPANO export of the same test; its step/touch output current is
        stored as the reference ``earthing_current`` (needed for per-ampere
        values and the scaling to the earth-fault current).
    nominal_frequency_hz : float, optional
        Power frequency for the interpolation; defaults to the nominal
        frequency of the COMPANO export or 50 Hz.
    per_frequency : bool, default True
        Also store the readings at both test frequencies.
    transferred : bool, default False
        Store the voltages as ``transferred_potential`` (e.g. readings at a
        neighbouring tower while the current is injected at this one).
    operator, description : str, optional
        Measurement metadata.
    voltage_level_kv : float, optional
        Nominal voltage of the installation.
    timezone : str, optional
        IANA time zone of the instrument clock.

    Returns
    -------
    int
        ID of the created measurement.
    """
    path = Path(hgt1_path)
    frequencies: Sequence[float] = ()
    currents: Sequence[float] = ()
    nominal = nominal_frequency_hz
    if compano_xml_path is not None:
        compano = CompanoXMLReader(compano_xml_path)
        frequencies, currents_array = compano.get_step_touch_currents()
        currents = [float(c) for c in currents_array]
        nominal = nominal or compano.get_nominal_frequency()
    nominal = nominal or 50.0
    readings = Hgt1TXTReader(
        path, nominal_frequency=nominal
    ).get_touchvoltage_dataframe()
    items = step_touch_items(
        readings,
        reference_frequencies_hz=frequencies,
        reference_currents_a=currents,
        nominal_frequency_hz=nominal,
        per_frequency=per_frequency,
        measurement_type="transferred_potential" if transferred else "touch_voltage",
    )
    first = readings.iloc[0]
    stamp = f"{str(first['Date']).strip()} {str(first['Time']).strip()}".strip()
    kind = "Transferred potential" if transferred else "Touch voltages"
    measurement_id, _item_ids = create_measurement_with_items(
        _measurement_payload(
            location=location,
            asset_type=asset_type,
            method="injection_earth_electrode",
            timestamp=parse_instrument_timestamp(stamp, timezone),
            description=description or f"{kind}, OMICRON HGT1 ({path.name})",
            operator=operator,
            voltage_level_kv=voltage_level_kv,
        ),
        items,
    )
    logger.info(
        "Imported %s as measurement %d (%d items)",
        path.name,
        measurement_id,
        len(items),
    )
    return measurement_id


def import_soil_resistivity(
    xml_path: PathLike,
    *,
    location: LocationLike,
    asset_type: str,
    operator: Optional[str] = None,
    description: Optional[str] = None,
    voltage_level_kv: Optional[float] = None,
    timezone: Optional[str] = None,
) -> int:
    """
    Import the soil-resistivity measurement of a COMPANO 100 export.

    Parameters
    ----------
    xml_path : str or Path
        COMPANO XML export with a soil-resistivity report.
    location : str or dict
        Location name or payload.
    asset_type : str
        Asset type of the measurement.
    operator, description : str, optional
        Measurement metadata.
    voltage_level_kv : float, optional
        Nominal voltage of the installation.
    timezone : str, optional
        IANA time zone of the instrument clock.

    Returns
    -------
    int
        ID of the created measurement (method ``wenner`` or ``schlumberger``).

    Raises
    ------
    ValueError
        If the export contains no soil-resistivity readings.
    """
    path = Path(xml_path)
    reader = CompanoXMLReader(path)
    data = reader.read_soil_resistivity()
    if data is None:
        raise ValueError(f"{path.name}: no soil-resistivity readings in the export")
    method, items = soil_resistivity_items(data)
    stamp = data.timestamps[0] if data.timestamps else reader.get_report_timestamp()
    measurement_id, _item_ids = create_measurement_with_items(
        _measurement_payload(
            location=location,
            asset_type=asset_type,
            method=method,
            timestamp=parse_instrument_timestamp(stamp, timezone),
            description=description
            or f"Soil resistivity ({method}), OMICRON COMPANO 100 ({path.name})",
            operator=operator,
            voltage_level_kv=voltage_level_kv,
        ),
        items,
    )
    logger.info(
        "Imported %s as measurement %d (%d items)",
        path.name,
        measurement_id,
        len(items),
    )
    return measurement_id
