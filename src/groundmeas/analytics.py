# src/groundmeas/analytics.py
"""
Analytics functions for groundmeas package.
"""
from typing import Dict, Union, List
import warnings

from .db import read_items_by

def impedance_over_frequency(
    measurement_ids: Union[int, List[int]]
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
            measurement_id=mid,
            measurement_type="earthing_impedance"
        )
        if not items:
            warnings.warn(
                f"No earthing_impedance measurements found for measurement_id={mid}",
                UserWarning
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
                    UserWarning
                )
                continue
            # Map frequency to impedance value (last one wins if duplicates)
            freq_imp_map[freq] = value

        all_results[mid] = freq_imp_map

    # Return single‐ID result or full mapping
    return all_results[ids[0]] if single else all_results
