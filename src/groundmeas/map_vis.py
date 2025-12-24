"""
groundmeas.map_vis
==================

Visualization of measurements on a map using Folium.
"""

import logging
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import folium
except ImportError:
    folium = None

logger = logging.getLogger(__name__)


def generate_map(
    measurements: List[Dict[str, Any]],
    output_file: str = "measurements_map.html",
    open_browser: bool = True,
) -> None:
    """
    Generate an interactive map showing measurement locations.

    Args:
        measurements: List of measurement dictionaries (as returned by db.read_measurements_by).
                      Each dict should have a "location" key with "latitude" and "longitude".
        output_file: Path to save the HTML map.
        open_browser: Whether to open the generated map in the default web browser.

    Raises:
        RuntimeError: If folium is not installed.
    """
    if folium is None:
        raise RuntimeError(
            "The 'folium' library is required for map visualization. "
            "Please install it with: pip install folium"
        )

    # Filter measurements with valid location data
    valid_measurements = []
    for m in measurements:
        loc = m.get("location")
        if loc and loc.get("latitude") is not None and loc.get("longitude") is not None:
            valid_measurements.append(m)

    if not valid_measurements:
        logger.warning("No measurements with valid GPS coordinates found.")
        return

    # Calculate center of the map
    lats = [m["location"]["latitude"] for m in valid_measurements]
    longs = [m["location"]["longitude"] for m in valid_measurements]
    center_lat = sum(lats) / len(lats)
    center_long = sum(longs) / len(longs)

    # Create map
    m = folium.Map(location=[center_lat, center_long], zoom_start=10)

    # Add markers
    for meas in valid_measurements:
        loc = meas["location"]
        lat = loc["latitude"]
        lon = loc["longitude"]
        
        # Create popup content
        popup_html = f"""
        <b>ID:</b> {meas.get('id')}<br>
        <b>Site:</b> {loc.get('name')}<br>
        <b>Date:</b> {meas.get('timestamp')}<br>
        <b>Type:</b> {meas.get('measurement_type')}<br>
        <b>Method:</b> {meas.get('method')}<br>
        """
        
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"{loc.get('name')} (ID: {meas.get('id')})"
        ).add_to(m)

    # Save map
    output_path = Path(output_file).resolve()
    m.save(str(output_path))
    logger.info(f"Map saved to {output_path}")

    if open_browser:
        webbrowser.open(f"file://{output_path}")
