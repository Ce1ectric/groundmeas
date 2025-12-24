
def value_over_distance(
    measurement_ids: Union[int, List[int]],
    measurement_type: str = "earthing_impedance",
) -> Union[Dict[float, float], Dict[int, Dict[float, float]]]:
    """
    Build a mapping from measurement_distance_m to value magnitude.

    Args:
        measurement_ids: A single measurement ID or a list of IDs.
        measurement_type: The type of measurement item to filter by.

    Returns:
        If a single ID is provided, returns:
            { distance_m: value, ... }
        If multiple IDs, returns:
            { measurement_id: { distance_m: value, ... }, ... }
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
            
            if dist is None:
                continue
                
            try:
                dist_val_map[float(dist)] = float(value)
            except Exception:
                continue

        all_results[mid] = dist_val_map

    return all_results[ids[0]] if single else all_results
