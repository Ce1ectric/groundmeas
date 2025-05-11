# test_models.py

from groundmeas.models import (
    Location,
    Measurement,
    MeasurementItem
)
import datetime as dt

def test_location_instantiation():
    raw = {
        "name": "Test Location",
        "latitude": 12.34,
        "longitude": 56.78,
        "altitude": 100.0,
    }
    location = Location(**raw)
    assert location.name == raw["name"]
    assert location.latitude == raw["latitude"]
    assert location.longitude == raw["longitude"]
    assert location.altitude == raw["altitude"]
    assert location.measurements == []
    assert location.id is None

def test_measurementitem_instantiation():
    raw = {
        "measurement_type": "touch_voltage",
        "value": 100.0,
        "unit": "V",
        "frequency_hz": 50.0,
    }
    measurement_item = MeasurementItem(**raw)
    assert measurement_item.measurement_type == raw["measurement_type"]
    assert measurement_item.value == raw["value"]
    assert measurement_item.unit == raw["unit"]
    assert measurement_item.frequency_hz == raw["frequency_hz"]
    assert measurement_item.id is None
    assert measurement_item.measurement is None
    assert measurement_item.measurement_id is None

def test_measurement_instantiation():
    raw = {
        "timestamp": dt.date(2023, 10, 1),
        "location_id": 1,
        "method": "staged_fault_test",
        "voltage_level_kv": 11.0,
        "asset_type": "substation",
        "fault_resistance_ohm": 0.5,
        "operator": "John Doe",
        "description": "Test measurement",
    }
    measurement = Measurement(**raw)
    assert measurement.timestamp == raw["timestamp"]
    assert measurement.location_id == raw["location_id"]
    assert measurement.method == raw["method"]
    assert measurement.voltage_level_kv == raw["voltage_level_kv"]
    assert measurement.asset_type == raw["asset_type"]
    assert measurement.fault_resistance_ohm == raw["fault_resistance_ohm"]
    assert measurement.operator == raw["operator"]
    assert measurement.description == raw["description"]
    assert measurement.items == []
    assert measurement.id is None

