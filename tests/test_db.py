# tests/test_db.py

import pytest

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
    update_item,
    delete_measurement,
    delete_item,
)


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
        self.value = None
        self.unit = None
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

    def flush(self):
        pass


class DummyLocation:
    def __init__(self, name="Loc"):
        self.id = None
        self.name = name


class DummyMeasurement:
    def __init__(self, location_id=None, location=None):
        self.location_id = location_id
        self.location = location
        self.method = None
        self.asset_type = None


def test_create_measurement_no_location(monkeypatch):
    fake = FakeSessionGet(to_get=None)
    # will be used for the measurement block only
    monkeypatch.setattr(db, "_get_session", lambda: fake)
    new_id = create_measurement({"foo": "bar"})
    assert new_id == 123


def test_create_measurement_with_location(tmp_path):
    """
    Creating a measurement with a nested ``location`` persists both rows in a
    single transaction and links them via the foreign key.
    """
    db._engine = None
    connect_db(str(tmp_path / "meas.db"))

    mid = create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Site X", "latitude": 51.0, "longitude": 10.0},
        }
    )
    assert isinstance(mid, int)

    recs, _ = read_measurements_by(id=mid)
    assert recs[0]["location"]["name"] == "Site X"
    assert recs[0]["location"]["latitude"] == pytest.approx(51.0)


def test_create_measurement_error_on_meas(tmp_path, monkeypatch):
    """
    A ``SQLAlchemyError`` raised from the shared session during measurement
    creation must be re-raised as :class:`RuntimeError` with the expected
    message prefix.
    """
    db._engine = None
    connect_db(str(tmp_path / "meas.db"))

    class _FailingSession:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def execute(self, stmt):
            class _Empty:
                def scalars(self):
                    return self
                def all(self):
                    return []
            return _Empty()
        def add(self, obj):
            pass
        def flush(self):
            pass
        def commit(self):
            raise SQLAlchemyError("meas fail")
        def refresh(self, obj):
            pass

    monkeypatch.setattr(db, "_get_session", lambda: _FailingSession())
    with pytest.raises(RuntimeError) as exc:
        create_measurement({"method": "wenner", "asset_type": "substation"})
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
    monkeypatch.setattr(db, "_get_session", lambda: FakeSessionReadItems())
    recs, ids = read_items_by(measurement_id=5)
    assert recs[0]["x"] == 42
    assert ids == [99]


def test_read_items_by_unsupported_op():
    with pytest.raises(ValueError):
        read_items_by(id__bad=1)


def test_update_measurement_updates_location(monkeypatch):
    loc = DummyLocation(name="Old")
    meas = DummyMeasurement(location_id=1, location=loc)

    session = FakeSessionGet(to_get=meas)
    monkeypatch.setattr(db, "_get_session", lambda: session)

    updated = update_measurement(1, {"method": "wenner", "location": {"name": "New"}})
    assert updated is True
    assert meas.method == "wenner"
    assert meas.location.name == "New"


def test_update_measurement_creates_location(tmp_path):
    """
    Adding a ``location`` payload to a measurement that previously had none
    should persist a new Location and link it via ``location_id`` — unless a
    matching Location already exists, which is covered by a separate dedup
    test below.
    """
    db._engine = None
    connect_db(str(tmp_path / "meas.db"))

    mid = create_measurement({"method": "wenner", "asset_type": "substation"})

    ok = update_measurement(mid, {"location": {"name": "Fresh Site"}})
    assert ok is True

    recs, _ = read_measurements_by(id=mid)
    assert recs[0]["location"]["name"] == "Fresh Site"
    assert recs[0]["location_id"] is not None


def test_update_measurement_not_found(monkeypatch):
    session = FakeSessionGet(to_get=None)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert update_measurement(5, {"method": "wenner"}) is False


def test_update_item_success(monkeypatch):
    item = DummyItem()
    session = FakeSessionGet(to_get=item)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert update_item(5, {"value": 1.5, "unit": "ohm"}) is True
    assert item.value == 1.5
    assert item.unit == "ohm"


def test_update_item_not_found(monkeypatch):
    session = FakeSessionGet(to_get=None)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert update_item(5, {"value": 1.5}) is False


def test_delete_measurement_success(monkeypatch):
    meas = DummyMeasurement()
    session = FakeSessionGet(to_get=meas)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert delete_measurement(3) is True
    assert session.deleted is meas


def test_delete_measurement_not_found(monkeypatch):
    session = FakeSessionGet(to_get=None)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert delete_measurement(3) is False


def test_delete_item_success(monkeypatch):
    item = DummyItem()
    session = FakeSessionGet(to_get=item)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert delete_item(4) is True
    assert session.deleted is item


def test_delete_item_not_found(monkeypatch):
    session = FakeSessionGet(to_get=None)
    monkeypatch.setattr(db, "_get_session", lambda: session)
    assert delete_item(4) is False


# --- Location dedup tests (Bug #1 / #2) ----------------------------------


def _count_locations() -> int:
    """Helper: count Location rows in the currently connected DB."""
    from groundmeas.core.models import Location
    from sqlmodel import select

    with db._get_session() as session:
        return len(session.execute(select(Location)).scalars().all())


def test_create_measurement_reuses_location_by_name(tmp_path):
    """
    Two measurements referencing the same site name (and no coordinates on
    either side) must share a single Location row.
    """
    db._engine = None
    connect_db(str(tmp_path / "dedup.db"))

    mid_a = create_measurement(
        {"method": "wenner", "asset_type": "substation", "location": {"name": "Site A"}}
    )
    mid_b = create_measurement(
        {"method": "wenner", "asset_type": "substation", "location": {"name": "Site A"}}
    )

    assert _count_locations() == 1

    recs_a, _ = read_measurements_by(id=mid_a)
    recs_b, _ = read_measurements_by(id=mid_b)
    assert recs_a[0]["location_id"] == recs_b[0]["location_id"]


def test_create_measurement_reuses_location_by_coords(tmp_path):
    """
    Two measurements at the same name + (lat, lon) share a Location even if
    the second payload passes coordinates that differ below the dedup
    precision (~1 m).
    """
    db._engine = None
    connect_db(str(tmp_path / "dedup.db"))

    mid_a = create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Site A", "latitude": 51.12345, "longitude": 10.54321},
        }
    )
    mid_b = create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            # Differs only in the 6th decimal → below _COORD_PRECISION.
            "location": {
                "name": "Site A",
                "latitude": 51.123451,
                "longitude": 10.543211,
            },
        }
    )

    assert _count_locations() == 1

    recs_a, _ = read_measurements_by(id=mid_a)
    recs_b, _ = read_measurements_by(id=mid_b)
    assert recs_a[0]["location_id"] == recs_b[0]["location_id"]


def test_create_measurement_creates_new_location_for_different_coords(tmp_path):
    """
    When the name matches but coordinates differ meaningfully, a new Location
    row must be created so that distinct physical sites stay distinguishable.
    """
    db._engine = None
    connect_db(str(tmp_path / "dedup.db"))

    create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Site A", "latitude": 51.0, "longitude": 10.0},
        }
    )
    create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Site A", "latitude": 52.0, "longitude": 11.0},
        }
    )

    assert _count_locations() == 2


def test_find_or_create_location_backfills_missing_coords(tmp_path):
    """
    If a Location was first inserted without coordinates and a later
    measurement supplies them, the row is enriched in place rather than
    duplicated.
    """
    db._engine = None
    connect_db(str(tmp_path / "dedup.db"))

    create_measurement(
        {"method": "wenner", "asset_type": "substation", "location": {"name": "Site B"}}
    )
    create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Site B", "latitude": 51.5, "longitude": 10.5},
        }
    )

    assert _count_locations() == 1

    recs, _ = read_measurements_by()
    loc = recs[0]["location"]
    assert loc["latitude"] == pytest.approx(51.5)
    assert loc["longitude"] == pytest.approx(10.5)


def test_update_measurement_reuses_existing_location(tmp_path):
    """
    Assigning a location payload to a measurement that previously had none
    must reuse an existing Location row rather than silently creating a
    duplicate (regression test for the ``update_measurement`` half of Bug 1).
    """
    db._engine = None
    connect_db(str(tmp_path / "dedup.db"))

    # Seed an existing Location via a first measurement.
    mid_a = create_measurement(
        {
            "method": "wenner",
            "asset_type": "substation",
            "location": {"name": "Shared", "latitude": 50.0, "longitude": 9.0},
        }
    )

    # Second measurement starts without a location and is later linked.
    mid_b = create_measurement({"method": "wenner", "asset_type": "substation"})
    assert update_measurement(
        mid_b,
        {"location": {"name": "Shared", "latitude": 50.0, "longitude": 9.0}},
    ) is True

    assert _count_locations() == 1
    recs_a, _ = read_measurements_by(id=mid_a)
    recs_b, _ = read_measurements_by(id=mid_b)
    assert recs_a[0]["location_id"] == recs_b[0]["location_id"]
