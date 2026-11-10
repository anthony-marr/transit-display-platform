"""Capital Bikeshare GBFS client. Keyless public feed; the discovery
document at https://gbfs.capitalbikeshare.com/gbfs/gbfs.json lists these
endpoints. Data refreshes roughly every minute (the feed's own ttl is 60s).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

from ..config import GBFS_BASE
from ..schemas import StationInfo, StationStatus, utcnow_iso


@dataclass
class StationInfoFeed:
    raw: bytes
    fetched_at: str
    stations: list[StationInfo] = field(default_factory=list)


@dataclass
class StationStatusFeed:
    raw: bytes
    fetched_at: str
    last_updated: int | None
    stations: list[StationStatus] = field(default_factory=list)


def parse_station_information(payload: bytes, fetched_at: str) -> list[StationInfo]:
    doc = json.loads(payload)
    return [
        StationInfo(
            station_id=s["station_id"],
            name=s["name"],
            short_name=s.get("short_name"),
            lat=s["lat"],
            lon=s["lon"],
            capacity=s.get("capacity"),
            region_id=s.get("region_id"),
        )
        for s in doc["data"]["stations"]
    ]


def parse_station_status(payload: bytes, fetched_at: str) -> tuple[int | None, list[StationStatus]]:
    doc = json.loads(payload)
    stations = [
        StationStatus(
            station_id=s["station_id"],
            fetched_at=fetched_at,
            num_bikes_available=s.get("num_bikes_available", 0),
            num_ebikes_available=s.get("num_ebikes_available", 0),
            num_docks_available=s.get("num_docks_available", 0),
            is_installed=s.get("is_installed", 1),
            is_renting=s.get("is_renting", 1),
            is_returning=s.get("is_returning", 1),
            last_reported=s.get("last_reported"),
        )
        for s in doc["data"]["stations"]
    ]
    return doc.get("last_updated"), stations


class GBFSClient:
    def __init__(self, base_url: str = GBFS_BASE, transport: httpx.BaseTransport | None = None,
                 timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def close(self):
        self._client.close()

    def _get(self, name: str) -> tuple[bytes, str]:
        resp = self._client.get(f"{self.base_url}/{name}")
        resp.raise_for_status()
        return resp.content, utcnow_iso()

    def fetch_station_information(self) -> StationInfoFeed:
        raw, fetched_at = self._get("station_information.json")
        return StationInfoFeed(raw=raw, fetched_at=fetched_at,
                               stations=parse_station_information(raw, fetched_at))

    def fetch_station_status(self) -> StationStatusFeed:
        raw, fetched_at = self._get("station_status.json")
        last_updated, stations = parse_station_status(raw, fetched_at)
        return StationStatusFeed(raw=raw, fetched_at=fetched_at,
                                 last_updated=last_updated, stations=stations)
