"""WMATA rail feeds: GTFS-RT vehicle positions and trip updates, plus the
StationPrediction API. All three require a free developer key from
https://developer.wmata.com/ passed as the api_key query parameter.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from google.transit import gtfs_realtime_pb2

from ..config import WMATA_API_BASE, WMATA_GTFSRT_BASE
from ..schemas import RailPrediction, TripStopTime, VehiclePosition, utcnow_iso


@dataclass
class VehiclePositionFeed:
    raw: bytes
    fetched_at: str
    vehicles: list[VehiclePosition] = field(default_factory=list)


@dataclass
class TripUpdateFeed:
    raw: bytes
    fetched_at: str
    stop_times: list[TripStopTime] = field(default_factory=list)


def parse_vehicle_positions(payload: bytes, fetched_at: str) -> list[VehiclePosition]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    out = []
    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue
        v = entity.vehicle
        trip = v.trip if v.HasField("trip") else None
        vehicle_id = v.vehicle.id if v.HasField("vehicle") and v.vehicle.id else entity.id
        out.append(VehiclePosition(
            vehicle_id=vehicle_id,
            trip_id=trip.trip_id if trip and trip.trip_id else None,
            route_id=trip.route_id if trip and trip.route_id else None,
            direction_id=trip.direction_id if trip and trip.HasField("direction_id") else None,
            stop_id=v.stop_id if v.stop_id else None,
            timestamp=v.timestamp if v.HasField("timestamp") else None,
            fetched_at=fetched_at,
        ))
    return out


def parse_trip_updates(payload: bytes, fetched_at: str) -> list[TripStopTime]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)
    out = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        trip = tu.trip
        for stu in tu.stop_time_update:
            out.append(TripStopTime(
                trip_id=trip.trip_id or None,
                route_id=trip.route_id or None,
                stop_id=stu.stop_id or None,
                arrival_time=stu.arrival.time if stu.HasField("arrival") else None,
                departure_time=stu.departure.time if stu.HasField("departure") else None,
                fetched_at=fetched_at,
            ))
    return out


def parse_predictions(payload: dict, station_code: str, fetched_at: str) -> list[RailPrediction]:
    return [
        RailPrediction(
            station_code=station_code,
            station_name=t.get("LocationName", ""),
            line=t.get("Line", ""),
            destination=t.get("DestinationName", "") or t.get("Destination", ""),
            minutes=t.get("Min", ""),
            group=t.get("Group"),
            fetched_at=fetched_at,
        )
        for t in payload.get("Trains", [])
    ]


class WMATAClient:
    def __init__(self, api_key: str, gtfsrt_base: str = WMATA_GTFSRT_BASE,
                 api_base: str = WMATA_API_BASE,
                 transport: httpx.BaseTransport | None = None, timeout: float = 15.0):
        if not api_key:
            raise ValueError("WMATAClient requires an API key")
        self.api_key = api_key
        self.gtfsrt_base = gtfsrt_base.rstrip("/")
        self.api_base = api_base.rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def close(self):
        self._client.close()

    def fetch_vehicle_positions(self) -> VehiclePositionFeed:
        resp = self._client.get(f"{self.gtfsrt_base}/rail-gtfsrt-vehiclepositions.pb",
                                params={"api_key": self.api_key})
        resp.raise_for_status()
        fetched_at = utcnow_iso()
        return VehiclePositionFeed(raw=resp.content, fetched_at=fetched_at,
                                   vehicles=parse_vehicle_positions(resp.content, fetched_at))

    def fetch_trip_updates(self) -> TripUpdateFeed:
        resp = self._client.get(f"{self.gtfsrt_base}/rail-gtfsrt-tripupdates.pb",
                                params={"api_key": self.api_key})
        resp.raise_for_status()
        fetched_at = utcnow_iso()
        return TripUpdateFeed(raw=resp.content, fetched_at=fetched_at,
                              stop_times=parse_trip_updates(resp.content, fetched_at))

    def fetch_predictions(self, station_code: str) -> list[RailPrediction]:
        resp = self._client.get(
            f"{self.api_base}/StationPrediction.svc/json/GetPrediction/{station_code}",
            params={"api_key": self.api_key})
        resp.raise_for_status()
        return parse_predictions(resp.json(), station_code, utcnow_iso())
