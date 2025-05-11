# src/groundmeas/db.py
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy import and_, text
from sqlalchemy.orm import selectinload
from sqlmodel import SQLModel, Session, create_engine, select
from .models import Location, Measurement, MeasurementItem

_engine = None


def connect_db(path: str, echo: bool = False) -> None:
    """
    Initialize the SQLite database at the given path.

    This will:
      - create an engine bound to the file (or in-memory if `:memory:`)
      - create all tables defined in SQLModel metadata
    """
    global _engine
    database_url = f"sqlite:///{path}"
    _engine = create_engine(database_url, echo=echo)
    SQLModel.metadata.create_all(_engine)


def _get_session() -> Session:
    if _engine is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return Session(_engine)


def create_measurement(data: Dict[str, Any]) -> int:
    """
    Insert a Measurement record into the database.

    Args:
      data: dict of Measurement fields (site_id must be provided if location).

    Returns:
      The newly created measurement's primary key (id).
    """
    # 1) Pull out and create Location if present
    loc_data = data.pop("location", None)
    if loc_data:
        loc = Location(**loc_data)
        with _get_session() as session:
            session.add(loc)
            session.commit()
            session.refresh(loc)
        data["location_id"] = loc.id

    m = Measurement(**data)
    with _get_session() as session:
        session.add(m)
        session.commit()
        session.refresh(m)
        return m.id  # type: ignore


def create_item(data: Dict[str, Any], measurement_id: int) -> int:
    """
    Insert a MeasurementItem linked to an existing Measurement.

    Args:
      data: dict of MeasurementItem fields (excluding measurement_id).
      measurement_id: the parent Measurement.id

    Returns:
      The newly created item’s primary key (id).
    """
    data = data.copy()
    data["measurement_id"] = measurement_id
    item = MeasurementItem(**data)
    with _get_session() as session:
        session.add(item)
        session.commit()
        session.refresh(item)
        return item.id  # type: ignore


def read_measurements(
    where: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Read all Measurement records matching an optional SQL WHERE string.

    Args:
      where: a SQLAlchemy-compatible WHERE clause, e.g.
        "asset_type = 'substation'"
        "method = 'staged_fault_test' OR method = 'injection_remote_substation'"
        "voltage_level_kv > 10 AND fault_resistance_ohm = 0.0"

    Returns:
      A list of dicts, each including its nested 'items'.
    """
    stmt = select(Measurement).options(
        selectinload(Measurement.items),
        selectinload(Measurement.location),
    )
    if where:
        stmt = stmt.where(text(where))

    with _get_session() as session:
        results = session.exec(stmt).all()

    out: List[Dict[str, Any]] = []
    mids: List[int] = []
    for m in results:
        d = m.model_dump()
        d["items"] = [item.model_dump() for item in m.items]
        out.append(d)
        mids.append(m.id)
    return out, mids

def read_measurements_by(**filters: Any) -> List[Dict[str, Any]]:
    """
    Read Measurements by keyword filters. Supports operators via suffix:

      __eq  (default), __ne, __lt, __lte, __gt, __gte, __in

    Example:
        read_measurements_by(
            asset_type="substation",
            voltage_level_kv__lt=20,
            method__in=["staged_fault_test", "injection_remote_substation"],
        )
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
        col = getattr(Measurement, field)
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
    with _get_session() as session:
        results = session.exec(stmt).all()
    out: List[Dict[str, Any]] = []
    mids: List[int] = []
    for m in results:
        d = m.model_dump()
        d["items"] = [i.model_dump() for i in m.items]
        mids.append(m.id)  # type: ignore
        out.append(d)
    return out, mids

def read_items_by(**filters: Any) -> Tuple[List[Dict[str, Any]], List[int]]:
    """
    Read MeasurementItem records by keyword filters with suffix operators __eq, __ne, __lt, __lte, __gt, __gte, __in.
    Returns (records, ids).

    Example:
        items, iids = read_items_by(
            measurement_id=mid,
            measurement_type="earthing_impedance",
            frequency_hz=50,
        )
    """
    stmt = select(MeasurementItem)
    clauses = []
    for key, val in filters.items():
        if "__" in key:
            field, op = key.split("__", 1)
        else:
            field, op = key, "eq"
        col = getattr(MeasurementItem, field)
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
    with _get_session() as session:
        results = session.exec(stmt).all()
    out: List[Dict[str, Any]] = []
    iids: List[int] = []
    for item in results:
        out.append(item.model_dump())
        iids.append(item.id)  # type: ignore
    return out, iids