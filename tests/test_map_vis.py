from types import SimpleNamespace

import pytest

from groundmeas.visualization import map_vis


def test_generate_map_requires_folium(monkeypatch):
    monkeypatch.setattr(map_vis, "folium", None)
    with pytest.raises(RuntimeError):
        map_vis.generate_map([])


def test_generate_map_writes_file(monkeypatch, tmp_path):
    output = tmp_path / "map.html"

    class DummyMap:
        def __init__(self, location=None, zoom_start=None):
            self.location = location
            self.zoom_start = zoom_start

        def save(self, path):
            output.write_text("map")

    class DummyMarker:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def add_to(self, m):
            return self

    class DummyPopup:
        def __init__(self, html, max_width=None):
            self.html = html
            self.max_width = max_width

    dummy_folium = SimpleNamespace(Map=DummyMap, Marker=DummyMarker, Popup=DummyPopup)
    monkeypatch.setattr(map_vis, "folium", dummy_folium)

    measurements = [
        {
            "id": 1,
            "asset_type": "substation",
            "method": "wenner",
            "timestamp": "2024-01-01",
            "location": {"name": "Site", "latitude": 1.0, "longitude": 2.0},
        }
    ]
    map_vis.generate_map(measurements, output_file=str(output), open_browser=False)
    assert output.exists()


def test_generate_map_open_browser(monkeypatch, tmp_path):
    output = tmp_path / "map.html"
    opened = {"count": 0}

    class DummyMap:
        def __init__(self, location=None, zoom_start=None):
            pass

        def save(self, path):
            output.write_text("map")

    class DummyMarker:
        def __init__(self, **kwargs):
            pass

        def add_to(self, m):
            return self

    class DummyPopup:
        def __init__(self, html, max_width=None):
            pass

    dummy_folium = SimpleNamespace(Map=DummyMap, Marker=DummyMarker, Popup=DummyPopup)
    monkeypatch.setattr(map_vis, "folium", dummy_folium)
    monkeypatch.setattr(map_vis.webbrowser, "open", lambda url: opened.__setitem__("count", opened["count"] + 1))

    measurements = [
        {
            "id": 1,
            "asset_type": "substation",
            "method": "wenner",
            "timestamp": "2024-01-01",
            "location": {"name": "Site", "latitude": 1.0, "longitude": 2.0},
        }
    ]
    map_vis.generate_map(measurements, output_file=str(output), open_browser=True)
    assert opened["count"] == 1


def test_generate_map_no_valid_measurements(monkeypatch, tmp_path):
    class DummyMap:
        def __init__(self, location=None, zoom_start=None):
            pass

        def save(self, path):
            raise AssertionError("should not save when no valid locations")

    dummy_folium = SimpleNamespace(Map=DummyMap, Marker=object, Popup=object)
    monkeypatch.setattr(map_vis, "folium", dummy_folium)

    measurements = [{"id": 1, "location": {"name": "Site", "latitude": None, "longitude": None}}]
    map_vis.generate_map(measurements, output_file=str(tmp_path / "map.html"), open_browser=False)
