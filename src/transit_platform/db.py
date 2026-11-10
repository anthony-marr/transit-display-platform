"""History store. SQLite by default (zero setup on a laptop), Postgres via
TRANSIT_DATABASE_URL for the always-on deployment. Raw feed snapshots are
kept alongside the cleaned rows so any ingest bug can be replayed.
"""
from __future__ import annotations

from sqlalchemy import (Column, Integer, MetaData, String, Table, Text,
                        create_engine, func, select)
from sqlalchemy.pool import StaticPool

from .config import DATABASE_URL
from .schemas import (RailPrediction, StationInfo, StationStatus,
                      TripStopTime, VehiclePosition)

metadata = MetaData()

raw_snapshots = Table(
    "raw_snapshots", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("source", String(64), nullable=False),
    Column("fetched_at", String(40), nullable=False),
    Column("payload", Text, nullable=False),
)

stations = Table(
    "stations", metadata,
    Column("station_id", String(64), primary_key=True),
    Column("name", Text, nullable=False),
    Column("short_name", String(32)),
    Column("lat", String(24), nullable=False),
    Column("lon", String(24), nullable=False),
    Column("capacity", Integer),
    Column("region_id", String(32)),
    Column("updated_at", String(40), nullable=False),
)

station_status = Table(
    "station_status", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("station_id", String(64), nullable=False, index=True),
    Column("fetched_at", String(40), nullable=False, index=True),
    Column("num_bikes_available", Integer, nullable=False),
    Column("num_ebikes_available", Integer, nullable=False),
    Column("num_docks_available", Integer, nullable=False),
    Column("is_installed", Integer, nullable=False),
    Column("is_renting", Integer, nullable=False),
    Column("is_returning", Integer, nullable=False),
    Column("last_reported", Integer),
)

vehicle_positions = Table(
    "vehicle_positions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("vehicle_id", String(64), nullable=False, index=True),
    Column("trip_id", String(64)),
    Column("route_id", String(32), index=True),
    Column("direction_id", Integer),
    Column("stop_id", String(32)),
    Column("timestamp", Integer),
    Column("fetched_at", String(40), nullable=False, index=True),
)

trip_stop_times = Table(
    "trip_stop_times", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("trip_id", String(64), index=True),
    Column("route_id", String(32)),
    Column("stop_id", String(32)),
    Column("arrival_time", Integer),
    Column("departure_time", Integer),
    Column("fetched_at", String(40), nullable=False, index=True),
)

rail_predictions = Table(
    "rail_predictions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("station_code", String(8), nullable=False, index=True),
    Column("station_name", Text, nullable=False),
    Column("line", String(8), nullable=False),
    Column("destination", Text, nullable=False),
    Column("minutes", String(8), nullable=False),
    Column("grp", String(8)),
    Column("fetched_at", String(40), nullable=False, index=True),
)


class TransitDB:
    """Thin repository over the store. All inserts take the pydantic models
    from schemas.py, so rows are validated before they land."""

    def __init__(self, url: str = DATABASE_URL):
        self.url = url
        if url in (":memory:", "sqlite://", "sqlite:///:memory:"):
            self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                                        poolclass=StaticPool)
        else:
            self.engine = create_engine(url)
        metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    # -- writes ---------------------------------------------------------

    def record_snapshot(self, source: str, fetched_at: str, payload: bytes) -> None:
        with self.engine.begin() as conn:
            conn.execute(raw_snapshots.insert().values(
                source=source, fetched_at=fetched_at,
                payload=payload.decode("utf-8", errors="replace")))

    def upsert_stations(self, rows: list[StationInfo], updated_at: str) -> None:
        with self.engine.begin() as conn:
            for r in rows:
                values = dict(station_id=r.station_id, name=r.name, short_name=r.short_name,
                              lat=str(r.lat), lon=str(r.lon), capacity=r.capacity,
                              region_id=r.region_id, updated_at=updated_at)
                existing = conn.execute(
                    select(stations.c.station_id).where(
                        stations.c.station_id == r.station_id)).first()
                if existing:
                    conn.execute(stations.update().where(
                        stations.c.station_id == r.station_id).values(**values))
                else:
                    conn.execute(stations.insert().values(**values))

    def insert_station_status(self, rows: list[StationStatus]) -> int:
        if not rows:
            return 0
        with self.engine.begin() as conn:
            conn.execute(station_status.insert(), [r.model_dump() for r in rows])
        return len(rows)

    def insert_vehicle_positions(self, rows: list[VehiclePosition]) -> int:
        if not rows:
            return 0
        with self.engine.begin() as conn:
            conn.execute(vehicle_positions.insert(), [r.model_dump() for r in rows])
        return len(rows)

    def insert_trip_stop_times(self, rows: list[TripStopTime]) -> int:
        if not rows:
            return 0
        with self.engine.begin() as conn:
            conn.execute(trip_stop_times.insert(), [r.model_dump() for r in rows])
        return len(rows)

    def insert_predictions(self, rows: list[RailPrediction]) -> int:
        if not rows:
            return 0
        with self.engine.begin() as conn:
            conn.execute(rail_predictions.insert(), [{
                "station_code": r.station_code, "station_name": r.station_name,
                "line": r.line, "destination": r.destination, "minutes": r.minutes,
                "grp": r.group, "fetched_at": r.fetched_at}
                for r in rows])
        return len(rows)

    # -- reads ----------------------------------------------------------

    def latest_station_status(self, station_id: str | None = None,
                              limit: int = 1000) -> list[dict]:
        latest = select(station_status.c.station_id,
                        func.max(station_status.c.fetched_at).label("mf")
                        ).group_by(station_status.c.station_id).subquery()
        q = (select(station_status, stations.c.name, stations.c.lat, stations.c.lon,
                    stations.c.capacity)
             .select_from(station_status.join(
                 latest, (station_status.c.station_id == latest.c.station_id)
                 & (station_status.c.fetched_at == latest.c.mf))
             .join(stations, stations.c.station_id == station_status.c.station_id,
                   isouter=True)))
        if station_id:
            q = q.where(station_status.c.station_id == station_id)
        q = q.limit(limit)
        with self.engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(q)]

    def latest_vehicle_positions(self, limit: int = 500) -> list[dict]:
        latest = select(func.max(vehicle_positions.c.fetched_at)).scalar_subquery()
        q = select(vehicle_positions).where(
            vehicle_positions.c.fetched_at == latest).limit(limit)
        with self.engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(q)]

    def station_history(self, station_id: str, limit: int = 200) -> list[dict]:
        q = (select(station_status)
             .where(station_status.c.station_id == station_id)
             .order_by(station_status.c.fetched_at.desc()).limit(limit))
        with self.engine.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(q)]

    def source_status(self) -> dict:
        out = {}
        with self.engine.connect() as conn:
            for row in conn.execute(
                    select(raw_snapshots.c.source,
                           func.max(raw_snapshots.c.fetched_at),
                           func.count()).group_by(raw_snapshots.c.source)):
                out[row[0]] = {"last_fetch": row[1], "snapshots": row[2]}
            counts = {
                "station_status_rows": conn.execute(
                    select(func.count()).select_from(station_status)).scalar(),
                "stations": conn.execute(
                    select(func.count()).select_from(stations)).scalar(),
                "vehicle_position_rows": conn.execute(
                    select(func.count()).select_from(vehicle_positions)).scalar(),
                "prediction_rows": conn.execute(
                    select(func.count()).select_from(rail_predictions)).scalar(),
            }
        return {"sources": out, "rows": counts}
