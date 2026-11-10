"""Validated shapes for everything that crosses a boundary: feed payloads,
database rows, and the WebSocket event stream."""
from __future__ import annotations

import datetime as dt
from typing import Optional

from pydantic import BaseModel, Field


def utcnow_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class StationInfo(BaseModel):
    station_id: str
    name: str
    short_name: Optional[str] = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    capacity: Optional[int] = None
    region_id: Optional[str] = None


class StationStatus(BaseModel):
    station_id: str
    fetched_at: str
    num_bikes_available: int = Field(ge=0)
    num_ebikes_available: int = 0
    num_docks_available: int = Field(ge=0)
    is_installed: int = 1
    is_renting: int = 1
    is_returning: int = 1
    last_reported: Optional[int] = None


class VehiclePosition(BaseModel):
    vehicle_id: str
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    direction_id: Optional[int] = None
    stop_id: Optional[str] = None
    timestamp: Optional[int] = None
    fetched_at: str


class TripStopTime(BaseModel):
    trip_id: Optional[str] = None
    route_id: Optional[str] = None
    stop_id: Optional[str] = None
    arrival_time: Optional[int] = None
    departure_time: Optional[int] = None
    fetched_at: str


class RailPrediction(BaseModel):
    station_code: str
    station_name: str
    line: str
    destination: str
    minutes: str  # WMATA gives "3", "BRD", "ARR", or "---"; keep it verbatim
    group: Optional[str] = None
    fetched_at: str


class FeedEvent(BaseModel):
    """One message on the WebSocket feed."""
    type: str  # hello | bikeshare_status | rail_vehicles | rail_predictions | error
    ts: str
    source: str = "transit-platform"
    data: dict = {}
