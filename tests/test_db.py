import groundmeas as gm
import pytest
from sqlmodel import Session
from groundmeas.db import _engine

def test_functions_before_connect_raise():
    # Ensure that DB functions error if not connected
    gm._engine = None  # reset engine
    with pytest.raises(RuntimeError):
        gm.create_measurement({})
    with pytest.raises(RuntimeError):
        gm.create_item({}, 1)
    with pytest.raises(RuntimeError):
        gm.read_measurement(1)

def test_connect_db_creates_file(tmp_path):
    gm.db._engine = None        # reset
    db_file = tmp_path / "test.db"
    gm.connect_db(str(db_file))

    # Now inspect the live attribute on the module:
    assert gm.db._engine is not None

def test_create_and_read_measurement_and_item(tmp_path):
    # Use a file-based DB for persistence across sessions
    db_file = tmp_path / "persist.db"
    gm.connect_db(str(db_file))

    # Create a measurement
    measurement_data = {
        "method": "staged_fault_test",
        "asset_type": "substation"
    }
    mid = gm.create_measurement(measurement_data)
    assert isinstance(mid, int)

    # Create a measurement item
    item_data = {
        "measurement_type": "touch_voltage",
        "value": 12.34,
        "unit": "V"
    }
    iid = gm.create_item(item_data, mid)
    assert isinstance(iid, int)

    # Read back the measurement
    result = gm.read_measurement(mid)
    assert result is not None
    assert result["id"] == mid
    assert result["method"] == measurement_data["method"]
    # Check nested items
    items = result["items"]
    assert isinstance(items, list) and len(items) == 1
    assert items[0]["id"] == iid
    assert items[0]["measurement_type"] == item_data["measurement_type"]

def test_read_nonexistent_returns_none(tmp_path):
    # Connect fresh DB without data
    gm.connect_db(str(tmp_path / "empty.db"))
    assert gm.read_measurement(999) is None