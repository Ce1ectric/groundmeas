# tests/test_db.py

import pytest
import datetime
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as SA_Session

import groundmeas.core.db as db
from groundmeas.core.db import (
    connect_db,
    _get_session,
    create_measurement,
    create_item,
    read_measurements,
    read_measurements_by,
    read_items_by,
    update_measurement,
    delete_measurement,
    update_item,
    delete_item,
)
from groundmeas.core.models import Location, Measurement, MeasurementItem


def test_connect_db_success(tmp_path):
    db._engine = None
    db_path = tmp_path / "test.db"
    # should not raise
    connect_db(str(db_path), echo=True)
    assert db._engine is not None
    # we can get a real Session
    sess = _get_session()
    assert isinstance(sess, SA_Session)
    sess.close()


def test_connect_db_failure(monkeypatch):
    # simulate create_engine raising
    def fake_create_engine(url, echo):
        raise SQLAlchemyError("boom")
    monkeypatch.setattr(db, "create_engine", fake_create_engine)
    with pytest.raises(RuntimeError) as exc:
        connect_db("dummy.db")
    assert "Could not initialize database" in str(exc.value)


def test_get_session_not_initialized():
    db._engine = None
    with pytest.raises(RuntimeError):
        _get_session()


# Helpers for faking sessions
class DummyMeas:
    def __init__(self):
        self.id = 7
        # have items attribute for read_measurements_by/tests
        self.items = [DummyItem()]
    def model_dump(self):
        return {"id": self.id, "foo": "bar"}


class DummyItem:
    def __init__(self):
        self.id = 99
    def model_dump(self):
        return {"id": self.id, "x": 42}


class FakeResult:
    def __init__(self, objs):
        self._objs = objs
    def scalars(self):
        return self
    def all(self):
        return self._objs


class FakeSessionReadMeasurements:
    """Session stub that always returns DummyMeas."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, stmt):
        return FakeResult([DummyMeas()])

class FakeSessionReadMeasurements:
    """Session stub that always returns DummyMeas."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, stmt):
        return FakeResult([DummyMeas()])

class FakeSessionReadItems:
    """Session stub that always returns DummyItem."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, stmt):
        return FakeResult([DummyItem()])

class FakeSessionGet:
    def __init__(self, to_get=None, error_on_commit=False):
        self._to_get = to_get
        self.error_on_commit = error_on_commit

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, cls, id_):
        return self._to_get

    def add(self, obj):
        # record that add was called
        self.added = obj

    def commit(self):
        if self.error_on_commit:
            raise SQLAlchemyError("commit failed")

    def refresh(self, obj):
        # assign an id if missing
        if not getattr(obj, "id", None):
            obj.id = 123

    def delete(self, obj):
        self.deleted = obj


def test_create_measurement_no_location(monkeypatch):
    fake = FakeSessionGet(to_get=None)
    # will be used for the measurement block only
    monkeypatch.setattr(db, "_get_session", lambda: fake)
    new_id = create_measurement({"foo": "bar"})
    assert new_id == 123


def test_create_measurement_with_location(monkeypatch):
    # two sessions: first for Location, second for Measurement
    loc = Location(name="X")
    meas = Measurement(foo="baz")
    # session1 refresh loc.id=123, session2 refresh meas.id=456
    class S1(FakeSessionGet):
        def refresh(self, obj):
            obj.id = 123
    class S2(FakeSessionGet):
        def refresh(self, obj):
            obj.id = 456

    seq = [S1(to_get=None), S2(to_get=None)]
    monkeypatch.setattr(db, "_get_session", lambda: seq.pop(0))
    result_id = create_measurement({"foo": "baz", "location": {"name": "X"}})
    assert result_id == 456


def test_create_measurement_location_error(monkeypatch):
    # first _get_session raises SQLAlchemyError
    monkeypatch.setattr(
        db,
        "_get_session",
        lambda: (_ for _ in ()).throw(SQLAlchemyError("loc fail"))
    )
    with pytest.raises(RuntimeError) as exc:
        create_measurement({"location": {"foo": "bar"}})
    assert "Could not create Location" in str(exc.value)


def test_create_measurement_error_on_meas(monkeypatch):
    # first session ok, second session commit fails
    class Good(FakeSessionGet):
        pass
    class Bad(FakeSessionGet):
        def commit(self):
            raise SQLAlchemyError("meas fail")

    seq = [Good(to_get=None), Bad(to_get=None)]
    monkeypatch.setattr(db, "_get_session", lambda: seq.pop(0))
    with pytest.raises(RuntimeError) as exc:
        create_measurement({"foo": "bar", "location": {"a": 1}})
    assert "Could not create Measurement" in str(exc.value)


def test_create_item_success(monkeypatch):
    fake = FakeSessionGet(to_get=None)
    monkeypatch.setattr(db, "_get_session", lambda: fake)
    item_id = create_item({"x": 5}, measurement_id=9)
    assert item_id == 123


def test_create_item_error(monkeypatch):
    bad = FakeSessionGet(to_get=None, error_on_commit=True)
    monkeypatch.setattr(db, "_get_session", lambda: bad)
    with pytest.raises(RuntimeError) as exc:
        create_item({"x": 5}, measurement_id=9)
    assert "Could not create MeasurementItem" in str(exc.value)


def test_read_measurements_error(monkeypatch):
    # _get_session raises
    monkeypatch.setattr(
        db,
        "_get_session",
        lambda: (_ for _ in ()).throw(RuntimeError("no db"))
    )
    with pytest.raises(RuntimeError) as exc:
        read_measurements()
    assert "Could not read measurements" in str(exc.value)


def test_read_measurements_success(monkeypatch):
    monkeypatch.setattr(db, "_get_session", lambda: FakeSessionReadMeasurements())
    recs, ids = read_measurements(where="something")
    assert isinstance(recs, list) and isinstance(ids, list)
    assert recs[0]["foo"] == "bar"
    assert isinstance(recs[0]["items"], list)
    assert ids == [7]


def test_read_measurements_by_unknown_field():
    with pytest.raises(ValueError) as exc:
        read_measurements_by(bogus=1)
    assert "Unknown filter field: bogus" in str(exc.value)


def test_read_measurements_by_unsupported_op():
    with pytest.raises(ValueError):
        read_measurements_by(id__bad=1)


def test_read_measurements_by_error(monkeypatch):
    monkeypatch.setattr(
        db,
        "_get_session",
        lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    with pytest.raises(RuntimeError) as exc:
        read_measurements_by(id=1)
    assert "Could not read measurements_by" in str(exc.value)


def test_read_measurements_by_success(monkeypatch):
    monkeypatch.setattr(db, "_get_session", lambda: FakeSessionReadMeasurements())
    recs, ids = read_measurements_by(id=7)
    assert recs[0]["foo"] == "bar"
    assert ids == [7]

def test_read_items_by_success(monkeypatch):
    monkeypatch.setattr(db, "_get_session", lambda: FakeSessionReadMeasurements())
    monkeypatch.setattr(db, "_get_session", lambda: FakeSessionReadItems())
    recs, ids = read_items_by(measurement_id=5)
    assert recs[0]["x"] == 42
    assert ids == [99]
