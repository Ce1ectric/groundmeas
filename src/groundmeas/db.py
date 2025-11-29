"""
groundmeas.db
=============

Database interface for groundmeas package.

Provides functions to connect to a SQLite database and perform
CRUD operations on Location, Measurement, and MeasurementItem models.
"""

import logging
from typing import List, Optional, Dict, Any, Tuple

from sqlalchemy import and_, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload, Session
from sqlmodel import SQLModel, create_engine, select

from .models import Location, Measurement, MeasurementItem

logger = logging.getLogger(__name__)

_engine = None


def connect_db(path: str, echo: bool = False) -> None:
    """
    Initialize a SQLite database (or connect to existing).

    Creates an SQLModel engine pointing at `path` and issues
    CREATE TABLE IF NOT EXISTS for all defined models.

    Args:
        path: Filesystem path to the SQLite file (use ":memory:" for RAM DB).
        echo: If True, SQLAlchemy will log all SQL statements.

    Raises:
        RuntimeError: if the database or tables cannot be created.
    """
    global _engine
    database_url = f"sqlite:///{path}"
    try:
        _engine = create_engine(database_url, echo=echo)
        SQLModel.metadata.create_all(_engine)
        logger.info("Connected to database at %s", path)
    except SQLAlchemyError as e:
        logger.exception("Failed to initialize database at %s", path)
        raise RuntimeError(f"Could not initialize database: {e}") from e


def _get_session() -> Session:
    """
    Internal: obtain a new Session bound to the global engine.

    Returns:
        A new SQLModel Session.

    Raises:
        RuntimeError: if `connect_db` has not been called.
    """
    if _engine is None:
        raise RuntimeError("Database not initialized; call connect_db() first")
    return Session(_engine)


def create_measurement(data: Dict[str, Any]) -> int:
    """
    Insert a new Measurement record, optionally creating a nested Location.

    Args:
        data: A dict of Measurement fields. May include a "location" key
              whose value is a dict for creating a Location.

    Returns:
        The primary key (id) of the newly created Measurement.

    Raises:
        RuntimeError: on any database error during insertion.
    """
    loc_data = data.pop("location", None)
    if loc_data:
        try:
            with _get_session() as session:
                loc = Location(**loc_data)
                session.add(loc)
                session.commit()
                session.refresh(loc)
                data["location_id"] = loc.id
        except SQLAlchemyError as e:
            logger.exception("Failed to create Location with data %s", loc_data)
            raise RuntimeError(f"Could not create Location: {e}") from e

    try:
        with _get_session() as session:
            meas = Measurement(**data)
            session.add(meas)
            session.commit()
            session.refresh(meas)
            return meas.id  # type: ignore
    except SQLAlchemyError as e:
        logger.exception("Failed to create Measurement with data %s", data)
        raise RuntimeError(f"Could not create Measurement: {e}") from e


def create_item(data: Dict[str, Any], measurement_id: int) -> int:
    """
    Insert a new MeasurementItem linked to an existing Measurement.

    Args:
        data: A dict of MeasurementItem fields (excluding measurement_id).
        measurement_id: The parent Measurement.id.

    Returns:
        The primary key (id) of the newly created MeasurementItem.

    Raises:
        RuntimeError: on any database error during insertion.
    """
    payload = data.copy()
    payload["measurement_id"] = measurement_id
    try:
        with _get_session() as session:
            item = MeasurementItem(**payload)
            session.add(item)
            session.commit()
            session.refresh(item)
            return item.id  # type: ignore
    except SQLAlchemyError as e:
        logger.exception(
            "Failed to create MeasurementItem for measurement_id=%s with data %s",
            measurement_id,
            data,
        )
        raise RuntimeError(f"Could not create MeasurementItem: {e}") from e


def read_measurements(
    where: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Retrieve Measurements, optionally filtered by a raw SQL WHERE clause.

    Args:
        where: A SQLAlchemy-compatible WHERE clause string (e.g. "asset_type = 'substation'").

    Returns:
        A tuple:
          - List of measurement dicts (each includes a nested "items" list)
          - List of measurement IDs in the same order

    Raises:
        RuntimeError: if a database error occurs.
    """
    stmt = select(Measurement).options(
        selectinload(Measurement.items),
        selectinload(Measurement.location),
    )
    if where:
        stmt = stmt.where(text(where))

    try:
        with _get_session() as session:
            result = session.execute(stmt)
            results = result.scalars().all()

    except Exception as e:
        logger.exception("Failed to execute read_measurements query")
        raise RuntimeError(f"Could not read measurements: {e}") from e

    records, ids = [], []
    for meas in results:
        d = meas.model_dump()
        loc = getattr(meas, "location", None)
        if loc is not None:
            d["location"] = loc.model_dump() if hasattr(loc, "model_dump") else loc
        else:
            d["location"] = None
        d["items"] = [it.model_dump() for it in meas.items]
        records.append(d)
        ids.append(meas.id)  # type: ignore
    return records, ids


def read_measurements_by(**filters: Any) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Retrieve Measurements by keyword filters with suffix operators.

    Supported operators: __eq (default), __ne, __lt, __lte, __gt, __gte, __in.

    Args:
        **filters: Field lookups, e.g. asset_type='substation',
                   voltage_level_kv__gte=10.

    Returns:
        A tuple of (list of measurement dicts, list of IDs).

    Raises:
        ValueError: on unsupported filter operator.
        RuntimeError: on database error.
    """
    stmt = select(Measurement).options(
        selectinload(Measurement.items),
        selectinload(Measurement.location),
    )
    clauses = []
    for key, val in filters.items():
        if "__" in key:
            field, op = key.split("__", 1)
        else:
            field, op = key, "eq"
        col = getattr(Measurement, field, None)
        if col is None:
            raise ValueError(f"Unknown filter field: {field}")
        if op == "eq":
            clauses.append(col == val)
        elif op == "ne":
            clauses.append(col != val)
        elif op == "lt":
            clauses.append(col < val)
        elif op == "lte":
            clauses.append(col <= val)
        elif op == "gt":
            clauses.append(col > val)
        elif op == "gte":
            clauses.append(col >= val)
        elif op == "in":
            clauses.append(col.in_(val))
        else:
            raise ValueError(f"Unsupported filter operator: {op}")
    if clauses:
        stmt = stmt.where(and_(*clauses))

    try:
        with _get_session() as session:
            result = session.execute(stmt)
            results = result.scalars().all()
    except Exception as e:
        logger.exception("Failed to read measurements by filters: %s", filters)
        raise RuntimeError(f"Could not read measurements_by: {e}") from e

    records, ids = [], []
    for meas in results:
        d = meas.model_dump()
        loc = getattr(meas, "location", None)
        if loc is not None:
            d["location"] = loc.model_dump() if hasattr(loc, "model_dump") else loc
        else:
            d["location"] = None
        d["items"] = [it.model_dump() for it in meas.items]
        records.append(d)
        ids.append(meas.id)  # type: ignore
    return records, ids


def read_items_by(**filters: Any) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Retrieve MeasurementItem records by keyword filters with suffix operators.

    Supported operators: __eq (default), __ne, __lt, __lte, __gt, __gte, __in.

    Args:
        **filters: Field lookups, e.g. measurement_id=1, frequency_hz__gte=50.

    Returns:
        A tuple of (list of item dicts, list of IDs).

    Raises:
        ValueError: on unsupported filter operator.
        RuntimeError: on database error.
    """
    stmt = select(MeasurementItem)
    clauses = []
    for key, val in filters.items():
        if "__" in key:
            field, op = key.split("__", 1)
        else:
            field, op = key, "eq"
        col = getattr(MeasurementItem, field, None)
        if col is None:
            raise ValueError(f"Unknown filter field: {field}")
        if op == "eq":
            clauses.append(col == val)
        elif op == "ne":
            clauses.append(col != val)
        elif op == "lt":
            clauses.append(col < val)
        elif op == "lte":
            clauses.append(col <= val)
        elif op == "gt":
            clauses.append(col > val)
        elif op == "gte":
            clauses.append(col >= val)
        elif op == "in":
            clauses.append(col.in_(val))
        else:
            raise ValueError(f"Unsupported filter operator: {op}")
    if clauses:
        stmt = stmt.where(and_(*clauses))

    try:
        with _get_session() as session:
            result = session.execute(stmt)
            results = result.scalars().all()
    except Exception as e:
        logger.exception("Failed to execute read_items_by query")
        raise RuntimeError(f"Could not read items_by: {e}") from e

    records, ids = [], []
    for it in results:
        records.append(it.model_dump())
        ids.append(it.id)  # type: ignore
    return records, ids


def update_measurement(measurement_id: int, updates: Dict[str, Any]) -> bool:
    """
    Update an existing Measurement by ID.

    Args:
        measurement_id: The ID of the Measurement to update.
        updates: Dict of field names to new values.

    Returns:
        True if the Measurement existed and was updated; False if not found.

    Raises:
        RuntimeError: on database error.
    """
    loc_updates = updates.pop("location", None)
    try:
        with _get_session() as session:
            meas = session.get(Measurement, measurement_id)
            if meas is None:
                return False
            if loc_updates:
                if meas.location_id and meas.location:
                    for field, val in loc_updates.items():
                        setattr(meas.location, field, val)
                    session.add(meas.location)
                else:
                    new_loc = Location(**loc_updates)
                    session.add(new_loc)
                    session.flush()
                    meas.location_id = new_loc.id
            for field, val in updates.items():
                setattr(meas, field, val)
            session.add(meas)
            session.commit()
            return True
    except SQLAlchemyError as e:
        logger.exception(
            "Failed to update Measurement %s with %s", measurement_id, updates
        )
        raise RuntimeError(f"Could not update measurement {measurement_id}: {e}") from e


def delete_measurement(measurement_id: int) -> bool:
    """
    Delete a Measurement (and its items) by ID.

    Args:
        measurement_id: The ID of the Measurement to delete.

    Returns:
        True if deleted; False if not found.

    Raises:
        RuntimeError: on database error.
    """
    try:
        with _get_session() as session:
            meas = session.get(Measurement, measurement_id)
            if meas is None:
                return False
            session.delete(meas)
            session.commit()
            return True
    except SQLAlchemyError as e:
        logger.exception("Failed to delete Measurement %s", measurement_id)
        raise RuntimeError(f"Could not delete measurement {measurement_id}: {e}") from e


def update_item(item_id: int, updates: Dict[str, Any]) -> bool:
    """
    Update an existing MeasurementItem by ID.

    Args:
        item_id: The ID of the item to update.
        updates: Dict of field names to new values.

    Returns:
        True if updated; False if not found.

    Raises:
        RuntimeError: on database error.
    """
    try:
        with _get_session() as session:
            it = session.get(MeasurementItem, item_id)
            if it is None:
                return False
            for field, val in updates.items():
                setattr(it, field, val)
            session.add(it)
            session.commit()
            return True
    except SQLAlchemyError as e:
        logger.exception(
            "Failed to update MeasurementItem %s with %s", item_id, updates
        )
        raise RuntimeError(f"Could not update item {item_id}: {e}") from e


def delete_item(item_id: int) -> bool:
    """
    Delete a MeasurementItem by ID.

    Args:
        item_id: The ID of the item to delete.

    Returns:
        True if deleted; False if not found.

    Raises:
        RuntimeError: on database error.
    """
    try:
        with _get_session() as session:
            it = session.get(MeasurementItem, item_id)
            if it is None:
                return False
            session.delete(it)
            session.commit()
            return True
    except SQLAlchemyError as e:
        logger.exception("Failed to delete MeasurementItem %s", item_id)
        raise RuntimeError(f"Could not delete item {item_id}: {e}") from e
