"""
groundmeas.dashboard
====================

Streamlit dashboard for interactive visualization and analysis.
"""

import streamlit as st
from streamlit_folium import st_folium
import folium
import pandas as pd
import matplotlib.pyplot as plt
from typing import List, Dict, Any, Optional
import json
from pathlib import Path
import os

from groundmeas.core.db import read_measurements_by, connect_db
from groundmeas.visualization.vis_plotly import (
    plot_imp_over_f_plotly,
    plot_rho_f_model_plotly,
    plot_voltage_vt_epr_plotly,
    plot_value_over_distance_plotly,
)
from groundmeas.services.analytics import impedance_over_frequency, value_over_distance_detailed

# Page config
st.set_page_config(page_title="Groundmeas Dashboard", layout="wide")

CONFIG_PATH = Path.home() / ".config" / "groundmeas" / "config.json"

def resolve_db_path() -> str:
    """
    Determine the database path from environment variables or config file.

    Priority:
      1. ``GROUNDMEAS_DB`` environment variable
      2. ``~/.config/groundmeas/config.json`` (``"db_path"``)
      3. Default ``groundmeas.db`` in the current working directory

    Returns
    -------
    str
        Resolved database path.
    """
    # Check environment variable
    env_db = os.environ.get("GROUNDMEAS_DB")
    if env_db:
        return env_db
        
    # Check config file
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text())
            cfg_path = cfg.get("db_path")
            if cfg_path:
                return cfg_path
        except Exception:
            pass
            
    # Default
    return str(Path("groundmeas.db").resolve())

def init_db():
    """
    Initialize the database connection.

    Calls ``connect_db`` with the resolved path. Displays an error in Streamlit
    if the connection fails.
    """
    db_path = resolve_db_path()
    try:
        connect_db(db_path)
        # st.toast(f"Connected to database: {db_path}")
    except Exception as e:
        st.error(f"Failed to connect to database at {db_path}: {e}")

def main():
    """
    Main entry point for the Streamlit dashboard.

    Sets up the layout, loads data, renders the map, and handles user interactions
    for filtering and analysis.
    """
    # Initialize DB connection
    init_db()

    st.title("Groundmeas Dashboard")

    # --- Sidebar: Data Loading & Filters ---
    st.sidebar.header("Filters")
    
    # Load all measurements (could be optimized to load only metadata first)
    # In a real app, we might want to cache this
    @st.cache_data
    def load_data():
        measurements, _ = read_measurements_by()
        return measurements

    all_measurements = load_data()
    
    # Filter by Asset Type
    asset_types = sorted(list(set(m.get("asset_type", "") for m in all_measurements)))
    selected_assets = st.sidebar.multiselect("Asset Type", asset_types, default=asset_types)
    
    # Filter measurements
    filtered_measurements = [
        m for m in all_measurements 
        if m.get("asset_type") in selected_assets
        and m.get("location") 
        and m["location"].get("latitude") is not None
    ]

    st.sidebar.write(f"Showing {len(filtered_measurements)} measurements")

    # --- Main Area: Map ---
    
    # Calculate center
    if filtered_measurements:
        lats = [m["location"]["latitude"] for m in filtered_measurements]
        longs = [m["location"]["longitude"] for m in filtered_measurements]
        center = [sum(lats)/len(lats), sum(longs)/len(longs)]
    else:
        center = [51.1657, 10.4515] # Germany center approx

    m = folium.Map(location=center, zoom_start=6)

    # Add markers
    # We use a FeatureGroup to allow potential future layer controls
    fg = folium.FeatureGroup(name="Measurements")
    
    for meas in filtered_measurements:
        loc = meas["location"]
        # Tooltip shows basic info
        tooltip = f"ID: {meas['id']} - {loc['name']}"
        
        # We can color code by type
        color = "blue"
        if meas.get("asset_type") == "substation":
            color = "red"
        elif meas.get("asset_type") == "overhead_line_tower":
            color = "green"

        folium.Marker(
            location=[loc["latitude"], loc["longitude"]],
            tooltip=tooltip,
            icon=folium.Icon(color=color),
            # We embed the ID in the popup or just rely on the click return
            # st_folium returns the last clicked object info
        ).add_to(fg)
    
    fg.add_to(m)

    # Render map with st_folium
    # returned_objects=["last_object_clicked"] allows us to see what was clicked
    st.write("### Map Overview")
    st.info("Click on a marker to see details below. Use the multiselect box for batch analysis.")
    
    map_data = st_folium(m, width=None, height=500, returned_objects=["last_object_clicked_tooltip"])

    # --- Interaction Logic ---
    
    # 1. Handle Map Click (Single Selection)
    selected_id_from_map = None
    if map_data and map_data.get("last_object_clicked_tooltip"):
        tooltip_text = map_data["last_object_clicked_tooltip"]
        # Parse ID from "ID: 123 - Name"
        try:
            selected_id_from_map = int(tooltip_text.split(":")[1].split("-")[0].strip())
        except (ValueError, IndexError):
            pass

    # 2. Multi-Selection Widget
    all_ids = [m["id"] for m in filtered_measurements]
    
    # Ensure the widget key exists in session state
    if "multiselect_ids" not in st.session_state:
        st.session_state["multiselect_ids"] = []

    # Checkbox for multi-select behavior (simulating Shift+Click)
    multi_select_mode = st.checkbox("Multi-select mode (append to selection)", value=False, help="If checked, clicking a marker adds it to the selection. Otherwise, it replaces the selection.")

    # Update logic
    if selected_id_from_map:
        # We need to check if this click is "new" or if we already handled it.
        if "last_clicked_tooltip" not in st.session_state:
            st.session_state["last_clicked_tooltip"] = None
            
        current_tooltip = map_data.get("last_object_clicked_tooltip")
        
        if current_tooltip != st.session_state["last_clicked_tooltip"]:
            # New click detected
            st.session_state["last_clicked_tooltip"] = current_tooltip
            
            current_selection = st.session_state["multiselect_ids"]
            
            if multi_select_mode:
                if selected_id_from_map not in current_selection:
                    st.session_state["multiselect_ids"] = current_selection + [selected_id_from_map]
                    st.rerun()
            else:
                # Exclusive selection
                if current_selection != [selected_id_from_map]:
                    st.session_state["multiselect_ids"] = [selected_id_from_map]
                    st.rerun()

    selected_ids = st.multiselect(
        "Selected Measurements for Analysis", 
        options=all_ids,
        key="multiselect_ids"
    )
    
    # Sync back to session state (if user removed something via UI)
    # st.session_state.selected_ids = selected_ids # Not needed if we use key directly

    # --- Details & Analysis Section ---
    
    if selected_ids:
        st.divider()
        st.header("Analysis")
        
        tabs = st.tabs(["Measurement Items", "Impedance Plot", "Rho-f Model", "Voltage/EPR", "Value vs Distance"])
        
        # Get selected measurement objects
        selected_objs = [m for m in all_measurements if m["id"] in selected_ids]

        with tabs[0]:
            st.subheader("Measurement Items")
            for meas in selected_objs:
                with st.expander(f"Measurement {meas['id']} - {meas['location']['name']}", expanded=True):
                    st.json(meas) # Show full metadata
                    
                    # Show items as table
                    if meas.get("items"):
                        df_items = pd.DataFrame(meas["items"])
                        # Select relevant columns
                        cols = ["id", "measurement_type", "value", "unit", "frequency_hz", "description", "measurement_distance_m"]
                        available_cols = [c for c in cols if c in df_items.columns]
                        st.dataframe(df_items[available_cols], width="stretch")
                    else:
                        st.warning("No items found.")

        with tabs[1]:
            st.subheader("Impedance vs Frequency")
            if st.button("Generate Impedance Plot"):
                try:
                    fig = plot_imp_over_f_plotly(selected_ids)
                    st.plotly_chart(fig, width="stretch")
                except Exception as e:
                    st.error(f"Error generating plot: {e}")

        with tabs[2]:
            st.subheader("Rho-f Model")
            st.write("Fits the rho-f model to the selected measurements.")
            if st.button("Fit & Plot Model"):
                try:
                    # We need to call the analytics/plot function
                    # Note: plot_rho_f_model requires coefficients. 
                    # We might need to calculate them first if not provided.
                    # The CLI does: coeffs = rho_f_model(ids) -> plot
                    from groundmeas.analytics import rho_f_model
                    
                    coeffs = rho_f_model(selected_ids)
                    st.write(f"Calculated Coefficients: {coeffs}")
                    
                    fig = plot_rho_f_model_plotly(selected_ids, coeffs)
                    st.plotly_chart(fig, width="stretch")
                except Exception as e:
                    st.error(f"Error: {e}")

        with tabs[3]:
            st.subheader("Voltage / EPR")
            freq = st.number_input("Frequency (Hz)", value=50.0)
            if st.button("Plot Voltage/EPR"):
                try:
                    fig = plot_voltage_vt_epr_plotly(selected_ids, frequency=freq)
                    st.plotly_chart(fig, width="stretch")
                except Exception as e:
                    st.error(f"Error: {e}")

        with tabs[4]:
            st.subheader("Value vs Distance")
            meas_type = st.selectbox(
                "Measurement Type", 
                ["earthing_impedance", "soil_resistivity", "earthing_resistance"],
                index=0
            )
            
            show_all_freq = st.checkbox("Show all frequencies", value=False)
            target_freq = None
            
            if not show_all_freq:
                # Fetch available frequencies
                available_freqs = set()
                try:
                    # selected_ids is a list from st.multiselect
                    raw_data = value_over_distance_detailed(selected_ids, measurement_type=meas_type)
                    if isinstance(raw_data, dict):
                        for mid, points in raw_data.items():
                            for p in points:
                                if p["frequency"] is not None:
                                    available_freqs.add(p["frequency"])
                except Exception:
                    pass
                
                sorted_freqs = sorted(list(available_freqs))
                if sorted_freqs:
                    default_idx = 0
                    if 50.0 in sorted_freqs:
                        default_idx = sorted_freqs.index(50.0)
                    target_freq = st.selectbox("Frequency (Hz)", sorted_freqs, index=default_idx)
                else:
                    st.warning("No frequency data found for selection.")

            if st.button("Plot Value vs Distance"):
                try:
                    fig = plot_value_over_distance_plotly(
                        selected_ids, 
                        measurement_type=meas_type,
                        show_all_frequencies=show_all_freq,
                        target_frequency=target_freq
                    )
                    st.plotly_chart(fig, width="stretch")
                except Exception as e:
                    st.error(f"Error: {e}")

    else:
        st.info("Select measurements on the map or in the dropdown to see details.")

if __name__ == "__main__":
    main()
