"""Polling ingest: pull each feed on its interval, store the raw snapshot
plus normalized rows, and broadcast a compact event to the feed."""
from __future__ import annotations

import asyncio
import logging

from . import config
from .db import TransitDB
from .hub import EventHub
from .schemas import utcnow_iso
from .sources.gbfs import GBFSClient
from .sources.wmata import WMATAClient

log = logging.getLogger("transit_platform.ingest")


class Poller:
    def __init__(self, db: TransitDB, hub: EventHub,
                 gbfs: GBFSClient | None = None, wmata: WMATAClient | None = None,
                 prediction_stations: list[str] | None = None,
                 bike_interval: float = config.BIKESHARE_POLL_SECONDS,
                 info_interval: float = config.STATION_INFO_POLL_SECONDS,
                 rail_interval: float = config.RAIL_POLL_SECONDS):
        self.db = db
        self.hub = hub
        self.gbfs = gbfs or GBFSClient()
        self.wmata = wmata  # None when no API key is configured
        self.prediction_stations = prediction_stations or config.WMATA_PREDICTION_STATIONS
        self.bike_interval = bike_interval
        self.info_interval = info_interval
        self.rail_interval = rail_interval

    # -- single poll cycles (also used directly by tests) ----------------

    async def poll_station_status_once(self) -> int:
        feed = await asyncio.to_thread(self.gbfs.fetch_station_status)
        await asyncio.to_thread(self.db.record_snapshot,
                                "bikeshare_gbfs", feed.fetched_at, feed.raw)
        n = await asyncio.to_thread(self.db.insert_station_status, feed.stations)
        total_bikes = sum(s.num_bikes_available for s in feed.stations)
        total_ebikes = sum(s.num_ebikes_available for s in feed.stations)
        await self.hub.publish({
            "type": "bikeshare_status", "ts": feed.fetched_at,
            "data": {
                "stations_updated": n,
                "total_bikes_available": total_bikes,
                "total_ebikes_available": total_ebikes,
                "stations": [s.model_dump() for s in feed.stations],
            },
        })
        return n

    async def poll_station_info_once(self) -> int:
        feed = await asyncio.to_thread(self.gbfs.fetch_station_information)
        await asyncio.to_thread(self.db.record_snapshot,
                                "bikeshare_gbfs_info", feed.fetched_at, feed.raw)
        await asyncio.to_thread(self.db.upsert_stations, feed.stations, feed.fetched_at)
        return len(feed.stations)

    async def poll_rail_once(self) -> dict:
        if self.wmata is None:
            return {"skipped": "no WMATA_API_KEY configured"}
        positions = await asyncio.to_thread(self.wmata.fetch_vehicle_positions)
        await asyncio.to_thread(self.db.record_snapshot,
                                "wmata_gtfsrt_vehicles", positions.fetched_at, positions.raw)
        nv = await asyncio.to_thread(self.db.insert_vehicle_positions, positions.vehicles)
        await self.hub.publish({
            "type": "rail_vehicles", "ts": positions.fetched_at,
            "data": {"vehicles": [v.model_dump() for v in positions.vehicles]},
        })
        npred = 0
        for code in self.prediction_stations:
            preds = await asyncio.to_thread(self.wmata.fetch_predictions, code)
            npred += await asyncio.to_thread(self.db.insert_predictions, preds)
            await self.hub.publish({
                "type": "rail_predictions", "ts": utcnow_iso(),
                "data": {"station_code": code,
                         "predictions": [p.model_dump() for p in preds]},
            })
        return {"vehicles": nv, "predictions": npred}

    # -- loops ------------------------------------------------------------

    async def _loop(self, name, interval, once):
        while True:
            try:
                await once()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s poll failed; retrying next cycle", name)
                await self.hub.publish({
                    "type": "error", "ts": utcnow_iso(),
                    "data": {"poller": name},
                })
            await asyncio.sleep(interval)

    async def run(self):
        loops = [
            self._loop("station_status", self.bike_interval, self.poll_station_status_once),
            self._loop("station_info", self.info_interval, self.poll_station_info_once),
        ]
        if self.wmata is not None:
            loops.append(self._loop("rail", self.rail_interval, self.poll_rail_once))
        await asyncio.gather(*loops)
